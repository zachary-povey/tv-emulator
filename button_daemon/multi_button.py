#!/usr/bin/env python3
"""
Multi-function button daemon for Panasonic FZ-G1 MK4

Makes A1 button work as multiple buttons based on hold duration:
- Short press (<0.5s): Action 1
- Medium press (0.5-1.0s): Action 2
- Long press (1.0-2.0s): Action 3
- Extra long press (>2.0s): Action 4

Edit multi_button_config.py to customize keys and timings.
"""

import os
import time

import evdev
from evdev import UInput, ecodes
import subprocess

# Default configuration
SHORT_PRESS_KEY = ecodes.KEY_F12
MEDIUM_PRESS_KEY = ecodes.KEY_F11
LONG_PRESS_KEY = ecodes.KEY_MUTE

SHORT_PRESS_TIME = 0.5  # Under this = short press
MEDIUM_PRESS_TIME = 2.0  # Under this = medium press
LONG_PRESS_TIME = 5.0  # Under this = long press
# over = extra long - shut down

# Load config file if it exists
config_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "multi_button_config.py"
)
if os.path.exists(config_path):
    print(f"Loading config from {config_path}", flush=True)
    exec(open(config_path).read())


def find_tablet_button_device():
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        if "Panasonic Tablet Button" in dev.name:
            return path
    return None


def send_key(ui, key):
    ui.write(ecodes.EV_KEY, key, 1)
    ui.syn()
    time.sleep(0.05)
    ui.write(ecodes.EV_KEY, key, 0)
    ui.syn()


def main():
    print("Panasonic Multi-Button Daemon", flush=True)

    # Create UInput immediately so it's registered before the GUI starts.
    # The hardware device may take 20-30s to appear, but creating UInput
    # after Cage is running triggers a hotplug event that shows the cursor.
    cap = {
        ecodes.EV_KEY: [
            SHORT_PRESS_KEY,
            MEDIUM_PRESS_KEY,
            LONG_PRESS_KEY,
        ],
        ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
    }
    ui = UInput(cap, name="Panasonic Multi-Button")
    print("UInput device created", flush=True)

    dev_path = find_tablet_button_device()
    while not dev_path:
        print("Device not found, retrying in 1s...", flush=True)
        time.sleep(1)
        dev_path = find_tablet_button_device()

    dev = evdev.InputDevice(dev_path)

    # Nudge the cursor to trigger mpv's cursor auto-hide
    ui.write(ecodes.EV_REL, ecodes.REL_X, 1)
    ui.write(ecodes.EV_REL, ecodes.REL_Y, 1)
    ui.syn()

    print(
        f"Short press (<{SHORT_PRESS_TIME}s): {ecodes.KEY[SHORT_PRESS_KEY]}", flush=True
    )
    print(
        f"Medium press ({SHORT_PRESS_TIME}-{MEDIUM_PRESS_TIME}s): {ecodes.KEY[MEDIUM_PRESS_KEY]}",
        flush=True,
    )
    print(
        f"Long press ({MEDIUM_PRESS_TIME}-{LONG_PRESS_TIME}s): {ecodes.KEY[LONG_PRESS_KEY]}",
        flush=True,
    )
    print(f"Extra long (>{LONG_PRESS_TIME}s): shutting down", flush=True)
    print("Monitoring...", flush=True)

    press_time = None

    try:
        dev.grab()

        for event in dev.read_loop():
            if event.type != ecodes.EV_KEY or event.code != ecodes.KEY_PROG2:
                continue

            if event.value == 1:  # Press
                press_time = time.time()

            elif event.value == 0 and press_time:  # Release
                duration = time.time() - press_time
                press_time = None

                if duration < SHORT_PRESS_TIME:
                    print(
                        f"Short press ({duration:.2f}s) -> {ecodes.KEY[SHORT_PRESS_KEY]}",
                        flush=True,
                    )
                    send_key(ui, SHORT_PRESS_KEY)
                elif duration < MEDIUM_PRESS_TIME:
                    print(
                        f"Medium press ({duration:.2f}s) -> {ecodes.KEY[MEDIUM_PRESS_KEY]}",
                        flush=True,
                    )
                    send_key(ui, MEDIUM_PRESS_KEY)
                elif duration < LONG_PRESS_TIME:
                    print(
                        f"Long press ({duration:.2f}s) -> {ecodes.KEY[LONG_PRESS_KEY]}",
                        flush=True,
                    )
                    send_key(ui, LONG_PRESS_KEY)
                else:
                    print(
                        f"Extra long ({duration:.2f}s) -> shutdown",
                        flush=True,
                    )
                    subprocess.run(["shutdown", "-h", "now"])

    except KeyboardInterrupt:
        print("Stopping...", flush=True)
    finally:
        dev.ungrab()
        ui.close()


if __name__ == "__main__":
    main()
