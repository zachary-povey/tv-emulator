"""Filesystem locations the web UI reads and writes.

Every path is overridable via an environment variable so the app can be run
against a fixture tree on a development machine instead of the tablet.
"""
import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

CHANNELS_DIR = Path(os.environ.get("TV_CHANNELS_DIR", HOME / "Channels"))
LIMITS_CONF = Path(os.environ.get("TV_LIMITS_CONF", "/etc/tv-emulator/limits.conf"))
USAGE_DIR = Path(os.environ.get("TV_USAGE_DIR", "/var/lib/tv-emulator"))
MPV_SOCKET = Path(os.environ.get("TV_MPV_SOCKET", "/tmp/mpv-socket"))

PLAYLIST_FILENAME = "playlist.m3u"
SETTINGS_FILENAME = "settings.json"

# Killswitch tick length, mirroring TICK_SECONDS in tv-killswitch.sh. Used to
# convert the usage file's seconds into minutes for display.
TICK_SECONDS = 60

DEFAULT_DAILY_LIMIT_MINUTES = 60
MIN_DAILY_LIMIT_MINUTES = 5
MAX_DAILY_LIMIT_MINUTES = 720

MAX_CREDIT_MINUTES = 240

# Set TV_FAKE_SHUTDOWN=1 in local development so the shutdown and reboot
# endpoints log instead of invoking the real command.
FAKE_SHUTDOWN = os.environ.get("TV_FAKE_SHUTDOWN") == "1"
