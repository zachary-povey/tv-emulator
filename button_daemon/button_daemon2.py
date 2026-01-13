#!/usr/bin/env python3
"""
Panasonic FZ-G1 MK4 Tablet Button Daemon v2
Detects button presses by monitoring EC memory for changes.
"""

import os
import sys
import time

EC_PATH = '/sys/kernel/debug/ec/ec0/io'

# Button scancodes
BUTTONS = {
    0x36: 'A2',
    0x37: 'A2_release',
    0x38: 'A1',
    0x39: 'A1_release',
    0x42: 'Windows',
    0x43: 'Windows_release',
}

def read_ec() -> bytes:
    with open(EC_PATH, 'rb') as f:
        return f.read(256)

def main():
    print("Button Daemon v2 - Monitoring EC changes", flush=True)
    
    prev_ec = read_ec()
    scan = 0
    
    print("Press buttons now...", flush=True)
    
    while True:
        scan += 1
        curr_ec = read_ec()
        
        # Find bytes that changed
        for i in range(len(prev_ec)):
            if prev_ec[i] != curr_ec[i]:
                old_val = prev_ec[i]
                new_val = curr_ec[i]
                
                # Check if new value is a button scancode
                if new_val in BUTTONS:
                    print(f"[{scan}] EC[0x{i:02x}]: 0x{old_val:02x} -> 0x{new_val:02x} ({BUTTONS[new_val]})", flush=True)
                # Also report if old value was a button code (button release?)
                elif old_val in BUTTONS:
                    print(f"[{scan}] EC[0x{i:02x}]: 0x{old_val:02x} ({BUTTONS[old_val]}) -> 0x{new_val:02x}", flush=True)
        
        prev_ec = curr_ec
        time.sleep(0.02)  # 50 samples/sec

if __name__ == '__main__':
    main()
