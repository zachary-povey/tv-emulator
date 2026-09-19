"""Build channel playlists by reusing the create_playlist script's logic.

The tablet's `~/Scripts/create_playlist` is an executable without a .py
extension, so it is loaded from its file location rather than imported by name.
Reusing it keeps one definition of what counts as a video file and how the
ordering modes behave, instead of duplicating that here.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
from types import ModuleType

_CANDIDATE_PATHS = [
    Path(os.path.expanduser("~/Scripts/create_playlist")),
    Path(__file__).resolve().parent.parent / "emulator_scripts" / "create_playlist",
]

_module: ModuleType | None = None


class PlaylistBuilderUnavailable(RuntimeError):
    """Raised when the create_playlist script cannot be located or loaded."""


def _load() -> ModuleType:
    """Load and cache the create_playlist script as a module.

    Returns:
        The loaded module, exposing collect_video_files, folder_round_robin and
        write_m3u_playlist.

    Raises:
        PlaylistBuilderUnavailable: If the script is missing from every known
            location, or does not expose the expected helpers.
    """
    global _module
    if _module is not None:
        return _module

    override = os.environ.get("TV_CREATE_PLAYLIST")
    candidates = [Path(override)] if override else list(_CANDIDATE_PATHS)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        spec = importlib.util.spec_from_loader(
            "tv_create_playlist",
            importlib.machinery.SourceFileLoader("tv_create_playlist", str(candidate)),
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        required = ("collect_video_files", "folder_round_robin", "write_m3u_playlist")
        missing = [name for name in required if not hasattr(module, name)]
        if missing:
            raise PlaylistBuilderUnavailable(
                f"{candidate} is missing expected helpers: {', '.join(missing)}"
            )
        _module = module
        return _module

    searched = ", ".join(str(c) for c in candidates)
    raise PlaylistBuilderUnavailable(
        f"Could not find the create_playlist script (looked in: {searched})"
    )


def build(root: Path, output: Path, mode: str = "file-order") -> int:
    """Write a playlist of the videos under *root*.

    The playlist is written via a temporary file and renamed into place so MPV
    never reads a half-written playlist. Nothing is written when no videos are
    found, leaving any existing playlist intact.

    Args:
        root: Directory to search recursively for video files.
        output: Playlist file to write.
        mode: `file-order` or `folder-round-robin`.

    Returns:
        The number of videos written, or zero when none were found.
    """
    module = _load()

    videos = module.collect_video_files(root)
    if mode == "folder-round-robin":
        videos = module.folder_round_robin(videos)

    if not videos:
        return 0

    tmp = output.with_name(output.name + ".tmp")
    module.write_m3u_playlist(videos, tmp)
    tmp.replace(output)
    return len(videos)
