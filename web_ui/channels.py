"""Inspect and modify the channel directories the MPV cycler reads.

A channel is a subdirectory of the channels root holding a playlist and,
optionally, a settings file. Channels are presented in the same alphabetical
order that channel_cycler.lua uses, so the UI matches the order the physical
button cycles through.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import config, playlist_builder

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._ -]*$")


class ChannelError(ValueError):
    """Raised when a channel name is invalid or the channel does not exist."""


@dataclass
class Channel:
    """One channel directory.

    Attributes:
        name: The directory name, which is also the channel's display name.
        path: Absolute path to the channel directory.
        has_playlist: Whether a playlist file is present.
        video_count: Number of entries in the playlist.
        volume: Configured per-channel volume, if set.
        missing_count: Playlist entries whose files no longer exist.
    """

    name: str
    path: Path
    has_playlist: bool
    video_count: int
    volume: int | None
    missing_count: int

    @property
    def playlist_path(self) -> Path:
        """Path to this channel's playlist file."""
        return self.path / config.PLAYLIST_FILENAME

    @property
    def settings_path(self) -> Path:
        """Path to this channel's settings file."""
        return self.path / config.SETTINGS_FILENAME


def resolve(name: str) -> Path:
    """Return the directory for channel *name*.

    Args:
        name: The channel (directory) name.

    Returns:
        The absolute path to the channel directory.

    Raises:
        ChannelError: If the name is unsafe or no such channel exists. Names are
            validated to keep a request from reaching outside the channels root.
    """
    if not _SAFE_NAME.match(name) or "/" in name or ".." in name:
        raise ChannelError(f"Invalid channel name: {name!r}")

    path = config.CHANNELS_DIR / name
    if not path.is_dir():
        raise ChannelError(f"No such channel: {name}")

    # Guard against a symlink pointing out of the channels root.
    root = config.CHANNELS_DIR.resolve()
    if not str(path.resolve()).startswith(str(root)):
        raise ChannelError(f"Channel resolves outside the channels directory: {name}")
    return path


def read_settings(path: Path) -> dict:
    """Return a channel's settings, or an empty dict when absent or unreadable."""
    settings_path = path / config.SETTINGS_FILENAME
    if not settings_path.is_file():
        return {}
    try:
        data = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def playlist_entries(path: Path) -> list[str]:
    """Return the media paths listed in a channel's playlist."""
    playlist = path / config.PLAYLIST_FILENAME
    if not playlist.is_file():
        return []
    entries = []
    for line in playlist.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def load(name: str) -> Channel:
    """Return a single channel's details.

    Raises:
        ChannelError: If the channel does not exist.
    """
    return _describe(resolve(name))


def list_channels() -> list[Channel]:
    """Return every channel, alphabetically, matching the cycler's ordering."""
    if not config.CHANNELS_DIR.is_dir():
        return []
    dirs = sorted((p for p in config.CHANNELS_DIR.iterdir() if p.is_dir()), key=lambda p: p.name)
    return [_describe(p) for p in dirs]


def set_volume(name: str, volume: int | None) -> None:
    """Set or clear a channel's volume in its settings file.

    Other keys in the settings file are preserved.

    Args:
        name: The channel name.
        volume: Volume between 0 and 180 (matching mpv.conf's volume-max), or
            None to remove the setting and fall back to the session default.

    Raises:
        ChannelError: If the channel is unknown or the volume is out of range.
    """
    path = resolve(name)
    if volume is not None and not 0 <= volume <= 180:
        raise ChannelError(f"Volume must be between 0 and 180 (got {volume}).")

    settings = read_settings(path)
    if volume is None:
        settings.pop("volume", None)
    else:
        settings["volume"] = volume

    settings_path = path / config.SETTINGS_FILENAME
    if settings:
        tmp = settings_path.with_name(settings_path.name + ".tmp")
        tmp.write_text(json.dumps(settings, indent=2) + "\n")
        tmp.replace(settings_path)
    elif settings_path.is_file():
        settings_path.unlink()


def rebuild_playlist(name: str, mode: str = "file-order") -> int:
    """Regenerate a channel's playlist from the video files it contains.

    Args:
        name: The channel name.
        mode: Either `file-order` or `folder-round-robin`, matching the
            create_playlist script's modes.

    Returns:
        The number of videos written to the playlist.

    Raises:
        ChannelError: If the channel is unknown, the mode is unrecognised, or no
            video files were found (which would otherwise leave an empty
            playlist and a channel that plays nothing).
    """
    path = resolve(name)
    if mode not in ("file-order", "folder-round-robin"):
        raise ChannelError(f"Unknown playlist mode: {mode!r}")

    count = playlist_builder.build(path, path / config.PLAYLIST_FILENAME, mode)
    if count == 0:
        raise ChannelError(
            f"No video files found under {name} - playlist left unchanged."
        )
    return count


def _describe(path: Path) -> Channel:
    """Build a Channel record by inspecting a channel directory."""
    entries = playlist_entries(path)
    settings = read_settings(path)
    volume = settings.get("volume")

    missing = sum(1 for entry in entries if not Path(entry).is_file())

    return Channel(
        name=path.name,
        path=path,
        has_playlist=(path / config.PLAYLIST_FILENAME).is_file(),
        video_count=len(entries),
        volume=int(volume) if isinstance(volume, (int, float)) else None,
        missing_count=missing,
    )
