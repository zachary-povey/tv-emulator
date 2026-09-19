#!/usr/bin/env python3
"""A stand-in for MPV's JSON IPC socket, for local development.

Speaks the same newline-delimited JSON protocol as MPV so the real IPC client is
exercised rather than stubbed: each request is a `{"command": [...]}` line and
each reply carries `data` and `error` fields. Only the properties and commands
the web UI uses are implemented.
"""
import argparse
import json
import os
import socket
import socketserver
from pathlib import Path

STATE = {
    "idle-active": False,
    "media-title": "Bluey S01E02 - Hospital",
    "playlist-path": "/home/tv-emulator/Channels/bluey/playlist.m3u",
    "path": "/home/tv-emulator/Channels/bluey/s01e02.mkv",
    "pause": False,
    "mute": False,
    "volume": 85.0,
    "playlist-pos": 1,
    "playlist-count": 3,
}

CHANNEL_ORDER = ["animalitos", "bluey", "disney"]


class Handler(socketserver.StreamRequestHandler):
    """Serves one IPC connection for as long as the client keeps it open."""

    def handle(self) -> None:
        for raw in self.rfile:
            raw = raw.strip()
            if not raw:
                continue
            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                self._reply(None, "invalid json")
                continue
            self._dispatch(request.get("command") or [])

    def _dispatch(self, command: list) -> None:
        """Handle one command array, replying as MPV would."""
        if not command:
            self._reply(None, "invalid parameter")
            return

        verb, args = command[0], command[1:]

        if verb == "get_property":
            name = args[0]
            if name in STATE:
                self._reply(STATE[name], "success")
            else:
                self._reply(None, "property not found")
        elif verb == "set_property":
            STATE[args[0]] = args[1]
            self._reply(None, "success")
        elif verb == "cycle":
            STATE[args[0]] = not STATE.get(args[0], False)
            self._reply(None, "success")
        elif verb == "script-binding":
            self._script_binding(args[0] if args else "")
        else:
            self._reply(None, f"unknown command {verb}")

    def _script_binding(self, name: str) -> None:
        """Emulate channel_cycler.lua's channel-next / channel-prev bindings."""
        if name not in ("channel-next", "channel-prev"):
            self._reply(None, "unknown script binding")
            return

        current = STATE["playlist-path"].split("/")[-2]
        index = CHANNEL_ORDER.index(current) if current in CHANNEL_ORDER else 0
        step = 1 if name == "channel-next" else -1
        channel = CHANNEL_ORDER[(index + step) % len(CHANNEL_ORDER)]

        STATE["playlist-path"] = f"/home/tv-emulator/Channels/{channel}/playlist.m3u"
        STATE["path"] = f"/home/tv-emulator/Channels/{channel}/episode.mkv"
        STATE["media-title"] = f"{channel} - episode"
        STATE["playlist-pos"] = 0
        print(f"[fake-mpv] {name} -> {channel}")
        self._reply(None, "success")

    def _reply(self, data, error: str) -> None:
        """Write one reply line."""
        self.wfile.write(json.dumps({"data": data, "error": error}).encode() + b"\n")
        self.wfile.flush()


class Server(socketserver.ThreadingUnixStreamServer):
    """Threaded unix-socket server that reuses a stale socket path."""

    daemon_threads = True

    def server_bind(self) -> None:
        path = Path(self.server_address)
        if path.exists():
            path.unlink()
        super().server_bind()
        os.chmod(self.server_address, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("socket_path", help="Unix socket path to listen on.")
    args = parser.parse_args()

    with Server(args.socket_path, Handler) as server:
        print(f"[fake-mpv] listening on {args.socket_path} (ctrl-c to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[fake-mpv] stopped")
        finally:
            Path(args.socket_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
