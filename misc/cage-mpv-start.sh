#!/bin/bash
# Startup script for cage-mpv session
# Sets default volume and launches mpv

# Unmute and set volume to 100%
wpctl set-mute @DEFAULT_AUDIO_SINK@ 0
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0

# Launch mpv
exec mpv --idle --force-window --fs
