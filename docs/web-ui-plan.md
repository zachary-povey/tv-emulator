# Web UI plan

A small LAN-only web UI so the device can be managed without SSH: channel
management, the daily usage limit, and basic device controls. Reachable at
`http://tv.local:8080` via mDNS (Avahi, already running on the tablet).

## Decisions

| Question | Choice |
|---|---|
| Stack | Python + FastAPI, server-rendered Jinja2 HTML, no JS build step |
| Dependencies | venv at `~/tv-web/venv` created by the installer |
| Privileges | Runs as `tv-emulator`; no sudo at runtime |
| Auth | None (LAN only) |
| Hostname | `tv` → `tv.local` |
| Channel reordering | **Out of scope** (never needed; avoids history-key migration) |

## Findings from the live device

- Avahi is already `active`/`enabled` — only the hostname changes.
- `/etc/tv-emulator/limits.conf` is owned by `tv-emulator`, so editing the
  daily limit needs **no sudo**.
- `/var/lib/tv-emulator/usage-<date>` is root-owned 644 (world-readable), so
  *reading* today's usage needs no sudo. Writing it does → see step 2.
- `ensurepip` is **absent** (Ubuntu ships it in `python3-venv`), so the
  installer must `apt install python3-venv` before creating the venv.
- PyPI is reachable from the tablet.
- MPV exposes **no IPC socket** today → device controls need a startup change.
- Ports 8080/8000 are free.
- `multi-user.target` is **active on admin boots**, confirmed on a live
  `tv_admin=1` boot → a `WantedBy=multi-user.target` unit starts on both
  profiles (see step 4).
- Unprivileged poweroff is **not** possible: dbus `CanPowerOff` returns
  `challenge` (polkit wants interactive auth), so shutdown needs a sudoers rule.

## Steps

### 1. MPV IPC socket (`misc/cage-mpv-start.sh`)

Append `--input-ipc-server=/tmp/mpv-socket` to the `exec mpv` line. The socket
is owned by `tv-emulator`, the same user as the web service, so device control
needs no privileges.

Risk: this touches the one script whose failure means the TV doesn't play.
Mitigation: single flag append; MPV still starts if the socket path is
unwritable. Redeploys via the existing `scripts/install_autostart.sh`.

### 2. Make the usage dir writable by `tv-emulator`

`chown tv-emulator:tv-emulator /var/lib/tv-emulator` so "grant extra minutes"
needs no sudo.

Two edits are required or this silently reverts:
- `scripts/install_killswitch.sh` — create the dir with that ownership.
- `killswitch/tv-killswitch.sh` — its `mkdir -p` runs as root each tick; make
  it not reassert root ownership.

**Accepted tradeoff:** the kiosk user can now rewrite its own usage counter,
weakening the killswitch. Currently unreachable in practice (the child has one
physical button and no shell); only matters if he gets keyboard access on a
kiosk boot.

### 3. `web_ui/` — the application

- `app.py` — FastAPI app, routes below.
- `channels.py` — scan `~/Channels/`, read/write `settings.json`, wrap
  `create_playlist` by importing it rather than duplicating its logic.
- `killswitch.py` — parse/rewrite `limits.conf` (rewrite only the
  `DAILY_LIMIT_MINUTES=` line, preserving comments); read/adjust the usage file.
- `mpv_ipc.py` — JSON-over-unix-socket client; every call degrades gracefully
  to "player not running".
- `templates/` — Jinja2: one page per area, big touch-friendly controls, plain
  forms with POST + redirect (no client-side JS framework).

Channel ordering is alphabetical, matching `channel_cycler.lua`'s
`table.sort(files)`; the UI states this so it's not surprising.

### Routes

| Route | Does |
|---|---|
| `GET /` | Status: now playing, current channel, usage today vs limit |
| `GET /channels` | List channels, video counts, per-channel volume |
| `POST /channels/{name}/volume` | Write `settings.json` |
| `POST /channels/{name}/rebuild` | Re-run playlist generation (`--mode` selectable) |
| `GET /limits` | Show limit + today's usage |
| `POST /limits` | Set `DAILY_LIMIT_MINUTES` (validated integer, sane range) |
| `POST /limits/credit` | Grant N extra minutes today (subtract from usage file) |
| `POST /device/channel/{next\|prev}` | `script-binding` via MPV IPC |
| `POST /device/mute` | Toggle mute via MPV IPC |
| `POST /device/shutdown` | Shutdown (confirm step in the UI) |

Shutdown: **resolved** — dbus `CanPowerOff` returns `challenge` on this device,
so polkit blocks an unprivileged poweroff (it would hang rather than work).
`scripts/install_web_ui.sh` therefore installs
`/etc/sudoers.d/tv-emulator-web` whitelisting exactly
`/sbin/shutdown` NOPASSWD for `tv-emulator`, and nothing else. Written with
`visudo -c` validation so a malformed file can't lock sudo.

### 4. `web_ui/tv-web-ui.service`

Runs `~/tv-web/venv/bin/uvicorn` as `tv-emulator`, `Restart=always`,
`WantedBy=multi-user.target`. Binds `0.0.0.0:8080`.

Carries **no** `ConditionKernelCommandLine=!tv_admin` — unlike the killswitch,
the UI **must** stay reachable on admin boots. This is a hard requirement: when
the daily budget is already spent, the kiosk shuts down within ~1 min of boot,
so raising the limit has to be possible from the admin profile without fighting
a shutdown loop.

This works because the admin/kiosk fork happens late, inside
`cage-mpv-start.sh` (a *session*-level decision), whereas this is a
*system*-level unit ordered under `multi-user.target` — which is active on both
boot paths (verified on a live admin boot). No `tv_admin` handling is needed in
this unit at all.

### 5. `scripts/install_web_ui.sh`

Follows the existing colored-output + `set -e` + scp-to-tmp-then-sudo-mv
pattern:

1. `apt install -y python3-venv` (needed for `ensurepip`).
2. `hostnamectl set-hostname tv`, and update `/etc/hosts` so sudo stops warning
   about an unresolvable host.
3. scp `web_ui/` → `/tmp` → `~/tv-web/app`.
4. Create venv, `pip install fastapi uvicorn jinja2` (pinned in
   `web_ui/requirements.txt`).
5. Install + `daemon-reload` + `enable --now` the unit.
6. Redeploy `cage-mpv-start.sh` for the IPC socket (step 1).
7. Print the URL and `systemctl status`.

## Local development before deploying

All device state is reached through four paths, which are taken from env vars
(`TV_CHANNELS_DIR`, `TV_LIMITS_CONF`, `TV_USAGE_DIR`, `TV_MPV_SOCKET`) and
default to the real device locations. Nothing is hardcoded, so the whole UI can
be developed and exercised on the Mac:

- `dev/make_fixture.py` builds a throwaway tree under the scratchpad: a few
  channel dirs with `playlist.m3u` + `settings.json`, a `limits.conf`, and a
  `usage-<today>` file.
- `dev/fake_mpv.py` listens on a unix socket and speaks the same
  JSON-lines IPC protocol as MPV (`{"command":[...]}` →
  `{"data":...,"error":"success"}`), so the real client code path is exercised
  rather than stubbed out.
- `dev/run_local.sh` points the env vars at the fixture and starts uvicorn with
  `--reload`.

This leaves exactly one thing that can only be confirmed on the tablet: whether
**real** MPV is listening on the socket. Everything else — routing, forms,
validation, `limits.conf` rewriting, usage math, playlist rebuilds, the phone
layout — is testable locally.

## Verification on the device

After install:

1. `curl http://tv.local:8080/` from the Mac → mDNS + service both work.
2. Reboot into the kiosk, confirm video plays (proves step 1 didn't break it)
   and that `/tmp/mpv-socket` exists.
3. Press next-channel in the UI → channel changes on the tablet.
4. Set the limit to a low value, confirm `limits.conf` changed and the killswitch
   still parses it (`journalctl -t tv-killswitch`).
5. Grant extra minutes → usage file decreases, device stays on.
6. Check the UI renders sanely on her phone.
7. Boot **admin** and confirm the UI is still reachable (the escape hatch: the
   budget can be raised from the admin profile with the killswitch inert).

## Notes / risks

- **NordVPN breaks mDNS.** `CLAUDE.md` lists LAN discovery as a manual prereq;
  multicast usually doesn't traverse the tunnel. If `tv.local` fails, test the
  raw IP first to separate "service down" from "mDNS blocked".
- Android resolves `.local` only on 12+; iOS/macOS are fine.
- Renaming the host to `tv` does not affect the `tv-emulator` SSH alias
  (that's a client-side alias to a fixed IP).
- Rebuilding a playlist resets that channel's resume position if the file
  ordering changes — acceptable, but the UI should say so.
