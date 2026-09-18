#!/bin/bash
# Daily usage killswitch for the TV emulator.
#
# Run once per minute by tv-killswitch.timer. Accumulates today's powered-on
# minutes in a per-day state file and powers the device off once the configured
# daily allowance is exceeded. Because the state file is keyed by the local
# calendar date and lives on persistent storage, the allowance survives reboots:
# if the device is turned back on the same day it is already over budget and
# shuts down again on the next tick. The allowance resets at local midnight
# (Europe/Madrid).
#
# This script is intentionally inert on "Admin" boots: the systemd unit carries
# ConditionKernelCommandLine=!tv_admin, so it never runs when tv_admin=1 is on
# the kernel command line.
set -euo pipefail

CONFIG_FILE=/etc/tv-emulator/limits.conf
STATE_DIR=/var/lib/tv-emulator
TICK_SECONDS=60

DAILY_LIMIT_MINUTES=30
if [ -r "$CONFIG_FILE" ]; then
    # shellcheck source=/dev/null
    . "$CONFIG_FILE"
fi

if ! [[ "$DAILY_LIMIT_MINUTES" =~ ^[0-9]+$ ]]; then
    echo "tv-killswitch: invalid DAILY_LIMIT_MINUTES='$DAILY_LIMIT_MINUTES'" >&2
    exit 1
fi

limit_seconds=$(( DAILY_LIMIT_MINUTES * 60 ))

# Date in the system's local timezone (configured to Europe/Madrid). The "day"
# therefore rolls over at Spanish midnight.
today=$(date +%F)
state_file="${STATE_DIR}/usage-${today}"

mkdir -p "$STATE_DIR"

# Remove stale per-day files from previous days so the dir doesn't grow forever.
find "$STATE_DIR" -maxdepth 1 -name 'usage-*' ! -name "usage-${today}" -delete 2>/dev/null || true

used_seconds=0
if [ -r "$state_file" ]; then
    used_seconds=$(cat "$state_file")
    [[ "$used_seconds" =~ ^[0-9]+$ ]] || used_seconds=0
fi

used_seconds=$(( used_seconds + TICK_SECONDS ))
echo "$used_seconds" > "$state_file"

if [ "$used_seconds" -ge "$limit_seconds" ]; then
    logger -t tv-killswitch "Daily limit reached (${used_seconds}s >= ${limit_seconds}s) - powering off"
    /sbin/shutdown -h now
fi
