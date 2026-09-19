#!/usr/bin/env python3
"""Build a throwaway copy of the tablet's layout for local development.

Creates channel directories with playlists and settings, a limits.conf and a
usage file, so the web UI can be exercised without touching the real device.
"""
import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

CHANNELS = {
    "animalitos": {"videos": ["lions.mp4", "bears.mp4"], "volume": 70},
    "bluey": {"videos": ["s01e01.mkv", "s01e02.mkv", "s01e03.mkv"]},
    "disney": {"videos": ["moana.mp4"], "volume": 95, "subfolders": True},
    "no_playlist_yet": {"videos": ["orphan.mp4"], "skip_playlist": True},
}


def build(root: Path, limit_minutes: int, used_minutes: int) -> None:
    """Create the fixture tree under *root*, replacing anything already there.

    Args:
        root: Directory to build the fixture in.
        limit_minutes: Daily allowance to write into limits.conf.
        used_minutes: Minutes of usage to pre-record for today.
    """
    if root.exists():
        shutil.rmtree(root)

    channels_dir = root / "Channels"
    for name, spec in CHANNELS.items():
        channel = channels_dir / name
        channel.mkdir(parents=True)

        written = []
        for index, video in enumerate(spec["videos"]):
            if spec.get("subfolders"):
                target = channel / f"part{index + 1}" / video
                target.parent.mkdir(exist_ok=True)
            else:
                target = channel / video
            target.write_bytes(b"\0" * 1024)
            written.append(target)

        if not spec.get("skip_playlist"):
            lines = ["#EXTM3U", *[str(p.resolve()) for p in written]]
            # A deliberately dead entry, so the "missing from disk" count is exercised.
            lines.append(str((channel / "deleted_episode.mp4").resolve()))
            (channel / "playlist.m3u").write_text("\n".join(lines) + "\n")

        if "volume" in spec:
            (channel / "settings.json").write_text(json.dumps({"volume": spec["volume"]}, indent=2) + "\n")

    etc = root / "etc"
    etc.mkdir(parents=True)
    (etc / "limits.conf").write_text(
        "# TV Emulator usage limits (fixture copy).\n"
        "#\n"
        "# Cumulative powered-on minutes allowed per calendar day.\n"
        f"DAILY_LIMIT_MINUTES={limit_minutes}\n"
    )

    usage = root / "var"
    usage.mkdir(parents=True)
    today = dt.date.today().isoformat()
    (usage / f"usage-{today}").write_text(str(used_minutes * 60))

    print(f"Fixture built at {root}")
    print(f"  channels : {channels_dir}")
    print(f"  limits   : {etc / 'limits.conf'} (limit {limit_minutes} min)")
    print(f"  usage    : {usage / f'usage-{today}'} ({used_minutes} min used)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory to build the fixture in.")
    parser.add_argument("--limit", type=int, default=60, help="Daily limit in minutes.")
    parser.add_argument("--used", type=int, default=25, help="Minutes already used today.")
    args = parser.parse_args()
    build(args.root.resolve(), args.limit, args.used)


if __name__ == "__main__":
    main()
