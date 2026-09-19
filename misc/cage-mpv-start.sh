#!/bin/bash
# Startup script for cage-mpv session
# Sets default volume and launches mpv

# Admin override: if the device was booted via the hidden GRUB "Admin" entry
# (which appends tv_admin=1 to the kernel command line), drop into a full GNOME
# desktop instead of the kiosk. The usage killswitch is also disarmed on these
# boots (see tv-killswitch.{service,timer}). Hold SHIFT/ESC at power-on to reach
# the GRUB menu and pick "Admin (GNOME desktop)".
if grep -qw tv_admin=1 /proc/cmdline; then
    exec dbus-run-session -- gnome-session
fi

# Unmute and set volume to 100%
wpctl set-mute @DEFAULT_AUDIO_SINK@ 0
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0

# Launch mpv. --input-ipc-server exposes a JSON IPC socket owned by this user,
# which the management web UI uses for the channel, pause and mute controls.
exec mpv --idle --force-window --fs --input-ipc-server=/tmp/mpv-socket
