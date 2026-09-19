"""Minimal client for MPV's JSON IPC socket.

MPV is only running during a kiosk session, so every helper here treats an
absent or unresponsive socket as an ordinary condition and reports it rather
than raising: the UI stays usable on admin boots where there is no player.
"""
import json
import socket
from dataclasses import dataclass
from typing import Any

from . import config

_TIMEOUT_SECONDS = 1.0


class MpvUnavailable(RuntimeError):
    """Raised internally when the player socket cannot be reached."""


@dataclass
class PlayerStatus:
    """A snapshot of what the player is doing.

    Attributes:
        running: Whether the IPC socket answered at all.
        media_title: Title of the current file, if any.
        channel: Channel name derived from the playlist path, if any.
        paused: Whether playback is paused.
        muted: Whether audio is muted.
        volume: Current volume, as MPV reports it.
        playlist_pos: Zero-based index within the current playlist.
        playlist_count: Number of entries in the current playlist.
    """

    running: bool
    media_title: str | None = None
    channel: str | None = None
    paused: bool | None = None
    muted: bool | None = None
    volume: float | None = None
    playlist_pos: int | None = None
    playlist_count: int | None = None


def _request(command: list[Any]) -> Any:
    """Send one command to MPV and return its `data` field.

    Args:
        command: The MPV command array, e.g. `["get_property", "volume"]`.

    Returns:
        The value MPV returned for the command, which may be None.

    Raises:
        MpvUnavailable: If the socket is missing, refuses the connection, times
            out, answers with malformed JSON, or reports an error.
    """
    path = config.MPV_SOCKET
    if not path.exists():
        raise MpvUnavailable(f"No MPV socket at {path}")

    payload = json.dumps({"command": command}).encode() + b"\n"

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(_TIMEOUT_SECONDS)
            sock.connect(str(path))
            sock.sendall(payload)

            # MPV may emit asynchronous events on the same connection, so read
            # until a line carrying an "error" field (a command reply) arrives.
            buffer = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    raise MpvUnavailable("MPV closed the connection")
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise MpvUnavailable(f"Malformed reply from MPV: {exc}") from exc
                    if "error" not in message:
                        continue
                    if message["error"] != "success":
                        raise MpvUnavailable(f"MPV rejected {command!r}: {message['error']}")
                    return message.get("data")
    except (OSError, socket.timeout) as exc:
        raise MpvUnavailable(f"Could not talk to MPV: {exc}") from exc


def _try_property(name: str) -> Any:
    """Return an MPV property, or None when it is unavailable."""
    try:
        return _request(["get_property", name])
    except MpvUnavailable:
        return None


def status() -> PlayerStatus:
    """Return a snapshot of the player, or `running=False` when it is absent."""
    try:
        _request(["get_property", "idle-active"])
    except MpvUnavailable:
        return PlayerStatus(running=False)

    return PlayerStatus(
        running=True,
        media_title=_try_property("media-title"),
        channel=current_channel(),
        paused=_try_property("pause"),
        muted=_try_property("mute"),
        volume=_try_property("volume"),
        playlist_pos=_try_property("playlist-pos"),
        playlist_count=_try_property("playlist-count"),
    )


def current_channel() -> str | None:
    """Return the channel name inferred from the loaded playlist, if any.

    The cycler loads `~/Channels/<name>/playlist.m3u`, so the channel is the
    parent directory of the playlist MPV was handed.
    """
    for prop in ("playlist-path", "path"):
        value = _try_property(prop)
        if not value:
            continue
        parts = [p for p in str(value).split("/") if p]
        if config.PLAYLIST_FILENAME in parts:
            index = parts.index(config.PLAYLIST_FILENAME)
            if index > 0:
                return parts[index - 1]
    return None


def script_binding(name: str) -> None:
    """Invoke a binding registered by channel_cycler.lua.

    Args:
        name: The binding name, e.g. `channel-next`.

    Raises:
        MpvUnavailable: If the player cannot be reached.
    """
    _request(["script-binding", name])


def toggle_mute() -> bool:
    """Toggle mute and return the resulting state.

    Raises:
        MpvUnavailable: If the player cannot be reached.
    """
    _request(["cycle", "mute"])
    return bool(_request(["get_property", "mute"]))


def set_volume(volume: float) -> None:
    """Set the player's current volume.

    This affects only the running session; per-channel defaults live in each
    channel's settings file.

    Args:
        volume: The new volume value.

    Raises:
        MpvUnavailable: If the player cannot be reached.
    """
    _request(["set_property", "volume", volume])


def toggle_pause() -> bool:
    """Toggle pause and return the resulting state.

    Raises:
        MpvUnavailable: If the player cannot be reached.
    """
    _request(["cycle", "pause"])
    return bool(_request(["get_property", "pause"]))
