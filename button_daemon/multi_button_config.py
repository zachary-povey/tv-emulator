#!/usr/bin/env python3
"""
Configuration for Multi-Button Daemon

Hold durations:
- Short press: < SHORT_PRESS_TIME
- Medium press: SHORT_PRESS_TIME to MEDIUM_PRESS_TIME
- Long press: MEDIUM_PRESS_TIME to LONG_PRESS_TIME  
- Extra long: > LONG_PRESS_TIME

Available key codes (common ones):
  KEY_LEFTMETA (125)  - Windows/Super key
  KEY_MENU (139)      - Context menu
  KEY_F1-F12          - Function keys
  KEY_VOLUMEUP (115)  - Volume up
  KEY_VOLUMEDOWN (114)- Volume down
  KEY_MUTE (113)      - Mute
  KEY_ESC (1)         - Escape
"""

from evdev import ecodes

# Keys for each hold duration
SHORT_PRESS_KEY = ecodes.KEY_F11        # Quick tap
MEDIUM_PRESS_KEY = ecodes.KEY_F12      # Medium hold
LONG_PRESS_KEY = ecodes.KEY_MUTE         # Long hold
EXTRA_LONG_KEY = ecodes.KEY_LEFTMETA    # Extra long hold

# Timing boundaries (seconds)
SHORT_PRESS_TIME = 0.5    # Under this = short
MEDIUM_PRESS_TIME = 1.0   # Under this = medium
LONG_PRESS_TIME = 3.0     # Under this = long, over = extra long
