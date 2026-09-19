# TV Emulator

Turns an old Panasonic FZ-G1 MK4 Toughpad (Ubuntu 24.04) into a "90s TV" for a
young child: a fixed set of "channels" (video playlists) that he cycles through
with a single physical button. The device is locked into a kiosk (Cage
compositor running MPV fullscreen) so he can't exit the player, skip within a
video, or reach the desktop — he can only change channels.

This repo is **configuration-as-code for that one device**. It does not run
anything locally; everything is deployed to the tablet over SSH by the
`scripts/install_*.sh` scripts.

## How deployment works

- The tablet is reached via an SSH host alias `tv-emulator` that **must exist in
  your `~/.ssh/config`** (host + user `tv-emulator`). Every install script hard-codes
  `SSH_HOST=tv-emulator` / `SSH_USER=tv-emulator`.
- Each `scripts/install_*.sh` is **idempotent** — it `scp`s config/code to the
  tablet, moves files into place with `sudo`, and reloads/restarts the relevant
  systemd service or udev rules. Re-running redeploys after a config change.
- The pattern in every script: copy source file → `scp` to `/tmp` → `ssh -t ... sudo mv`
  into the system location → reload. Preserve this pattern when adding scripts.
- Interactive `ssh -t` is used wherever `sudo` is needed (prompts for the sudo password).

## Components

Source lives in this repo; the table shows where each piece lands on the tablet.

| Area | Source | Installs via | Lands on tablet |
|------|--------|-------------|-----------------|
| Kiosk session (Cage + MPV autostart, GDM autologin) | `misc/` | `scripts/install_autostart.sh` | `/usr/local/bin/cage-mpv-start.sh`, `/usr/share/wayland-sessions/cage-mpv.desktop`, `/etc/gdm3/custom.conf` |
| MPV config + channel-cycling logic | `mpv_config/` | `scripts/configure_mpv.sh` | `~/.config/mpv/` and udev rules in `/etc/udev/` |
| Physical button daemon | `button_daemon/` | `scripts/install_button_daemon.sh` | `~/multi_button.py`, systemd service, `/etc/systemd/logind.conf` |
| Disable touchscreen/stylus + set brightness | `disable_screen/` | `scripts/install_disable_touchscreen.sh` | systemd oneshot service |
| Channel-management helper scripts | `emulator_scripts/` | `scripts/install_emulator_scripts.sh` | `~/Scripts/` (added to PATH) |
| Daily usage killswitch + hidden admin boot | `killswitch/` | `scripts/install_killswitch.sh` | `/usr/local/bin/tv-killswitch.sh`, systemd timer+service, `/etc/tv-emulator/limits.conf`, GRUB entry in `/etc/grub.d/40_custom` |
| LAN management web UI | `web_ui/` | `scripts/install_web_ui.sh` | `~/tv-web/{app,venv}`, `tv-web-ui.service`, `/etc/sudoers.d/tv-emulator-web` |

`scripts/install.sh` is an **unfinished** top-level orchestrator — currently just
a comment list of manual prereq steps (SSH server, brightnessctl, NordVPN LAN
discovery, GNOME cursor-hiding, black background, the `intel_idle.max_cstate=1`
grub fix). It does not yet run the other scripts in order.

## How "channels" work

- A channel is a subdirectory of `~/Channels/` on the tablet containing a
  `playlist.m3u` (and optionally a `settings.json` with e.g. `{"volume": 80}`).
- `mpv_config/channel_cycler.lua` scans `~/Channels/`, cycles between playlists
  on key bindings, loops each playlist forever, and **persists per-channel
  resume position** (file index + time) to `channel_history.json` so switching
  away and back resumes where you left off.
- Channel switching is bound in `mpv_config/mpv_input.conf` to F12/RIGHT/UP
  (next) and F11/LEFT/DOWN (prev). The physical button sends these keys.
- `emulator_scripts/create_playlist` (a Python script, runs on the tablet as
  `create_playlist`) builds a `playlist.m3u` from videos under a directory.
  Supports `--mode file-order` (default) or `--mode folder-round-robin`.

## Daily usage limit & admin boot

- `killswitch/tv-killswitch.sh` runs every minute (via `tv-killswitch.timer`),
  accumulating today's powered-on seconds into `/var/lib/tv-emulator/usage-<date>`
  and `shutdown -h now` once `DAILY_LIMIT_MINUTES` (in
  `/etc/tv-emulator/limits.conf`, default 60) is exceeded. The state file is keyed
  by **local date** (tablet is `Europe/Madrid`), so the budget persists across
  reboots — turning the device back on the same day powers it off again within
  ~1 min — and resets at local midnight. The installer enforces the timezone.
- **Admin override (no SSH race):** a GRUB entry "Admin (GNOME desktop)"
  appends `tv_admin=1` to the kernel cmdline. The decision is made *at boot*. The
  tablet has **no usable keyboard at GRUB time** (the A1 button only works once the
  Linux button daemon is up; the touchscreen/volume buttons reach the Panasonic
  BIOS but not reliably GRUB), so the installer sets a **3s visible GRUB menu**
  (`GRUB_TIMEOUT=3`, `GRUB_TIMEOUT_STYLE=menu`) with the kiosk as default
  (`GRUB_DEFAULT=0`). A normal boot shows a brief menu flash then auto-boots the
  kiosk; tapping/pressing during the countdown lets you pick Admin. On that boot
  the killswitch units are inert
  (`ConditionKernelCommandLine=!tv_admin`) **and** `cage-mpv-start.sh` forks to
  `gnome-session` instead of MPV — so you get a full desktop with no limit. Normal
  boots are unchanged. The GRUB entry is rebuilt from the running kernel/root UUID
  by the installer and delimited by `### BEGIN/END tv-emulator admin entry` markers
  so re-running replaces rather than duplicates it.

## The web UI

A small FastAPI app (server-rendered Jinja2, no JS build step) so the device can
be managed from a phone without SSH. Reached at **`http://tv.local:8080`** —
`avahi-daemon` was already running on the tablet, so the installer only shortens
the hostname to `tv`. It offers channel management (per-channel volume,
rebuilding playlists), the daily limit (change the allowance, or grant extra
minutes for today only), and device controls (next/prev channel, pause, mute,
shutdown, reboot).

- **Runs unprivileged** as `tv-emulator`. `limits.conf` and `/var/lib/tv-emulator`
  are owned by that user, so only power actions need root — via a single
  `sudoers.d` rule whitelisting `/sbin/shutdown -h now` and `-r now`.
- **No authentication**, by choice: it is a trusted-LAN tool. Anyone on the
  network can reach it, including the shutdown button.
- **Starts on both boot profiles.** The unit is deliberately *not* conditioned on
  `tv_admin` — once the day's allowance is spent the kiosk powers off within a
  minute of booting, so the limit has to be changeable from the Admin desktop.
  It works because `multi-user.target` is reached on both paths; the kiosk/Admin
  fork happens later, in `cage-mpv-start.sh`.
- **Device controls need MPV's IPC socket**, which is why `cage-mpv-start.sh`
  passes `--input-ipc-server=/tmp/mpv-socket`. The UI treats an absent socket as
  normal (the TV is off, or on an Admin boot) and hides those controls.
- **Granting extra time subtracts from the usage file** rather than raising the
  limit, so tomorrow is unaffected. This is why `/var/lib/tv-emulator` is owned
  by `tv-emulator` — note the tradeoff: the kiosk user could in principle rewrite
  its own usage counter.
- **Local development without the tablet:** all four device paths come from env
  vars (`TV_CHANNELS_DIR`, `TV_LIMITS_CONF`, `TV_USAGE_DIR`, `TV_MPV_SOCKET`).
  `dev/run_local.sh` builds a fixture tree and starts `dev/fake_mpv.py`, which
  speaks the real JSON-IPC protocol. `dev/test_web_ui.py` covers the edge cases.

## The physical button (the hard part)

Only the **A1 button** works on this tablet under Linux — the EC firmware won't
emit ACPI queries for the other buttons. See
[docs/panasonic-fz-g1-mk4-buttons-summary.md](docs/panasonic-fz-g1-mk4-buttons-summary.md)
for the full investigation (read on demand — not auto-loaded).

`button_daemon/multi_button.py` works around this by giving A1 multiple actions
based on **hold duration**, translating them to keypresses MPV understands:

- short (<0.5s) → F12 (next channel)
- medium (0.5–2.0s) → F11 (prev channel)
- long (2.0–5.0s) → KEY_MUTE
- extra-long (>5.0s) → `shutdown -h now`

It grabs the raw `Panasonic Tablet Button` device (which udev hides from
libinput) and re-emits keys via a UInput device. It also creates a virtual mouse
and nudges the cursor on startup — a workaround so MPV's `cursor-autohide` hides
the pointer that Cage shows. `logind.conf` disables systemd's own power-button
handling so the daemon owns it.

## Gotchas / hard-won knowledge

- **Cursor showing in kiosk**: Cage shows a cursor; MPV `cursor-autohide=10`
  only hides it after movement, hence the startup cursor-nudge in the daemon.
  This area has been finicky (see recent git history).
- **Remote/volume keys**: `mpv_config/99-remote-input.rules` and `90-remote.hwdb`
  force a USB remote (vendor 1915, product 1025) to be seen as a keyboard and
  remap its volume scancodes so MPV picks them up.
- **C-state CPU bug**: needs `intel_idle.max_cstate=1` in grub or the processor
  has issues (noted in `install.sh`).
- **mDNS and VPN**: `.local` names do not traverse a VPN tunnel, so `tv.local`
  can fail while NordVPN is up even though the device is reachable by IP. Test
  the raw IP first to tell "service down" from "mDNS blocked".
- **Ubuntu 24.04 is PEP-668 managed**, so the web UI's dependencies live in a
  venv. `python3 -m venv` needs the `python3-venv` package (it provides
  `ensurepip`, which the base `python3` omits) — the installer apt-installs it.
- The MK4 ACPI device ID is `MAT0037`; BIOS V4.00L25 *might* fix button routing
  but requires Windows to flash.

## Conventions

- Python: see global `~/.claude/CLAUDE.md` — minimal comments, type hints,
  Google-style docstrings on public functions/classes.
- Bash install scripts: keep the colored-output + `set -e` + scp-to-tmp-then-sudo-mv
  structure consistent with the existing ones.
- `docs/todo.md` tracks the wishlist (more content, mouse handling, another crack
  at the hardware buttons).
