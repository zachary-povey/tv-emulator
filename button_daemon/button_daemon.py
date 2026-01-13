#!/usr/bin/env python3
"""
Panasonic FZ-G1 MK4 Tablet Button Daemon
Polls EC memory for button state changes and generates input events.
"""

import os
import sys
import time
import struct

# Button scancodes from DSDT
BUTTONS = {
    0x36: 'A2',      # _Q97
    0x38: 'A1',      # _Q9B  
    0x42: 'Windows', # _QA7
}

EC_PATH = '/sys/kernel/debug/ec/ec0/io'

def read_ec_byte(offset: int) -> int:
    """Read a single byte from EC memory."""
    with open(EC_PATH, 'rb') as f:
        f.seek(offset)
        return f.read(1)[0]

def read_ec_range(start: int, length: int) -> bytes:
    """Read a range of bytes from EC memory."""
    with open(EC_PATH, 'rb') as f:
        f.seek(start)
        return f.read(length)

def scan_for_scancodes(data: bytes, known_codes: set) -> list:
    """Scan data for known button scancodes."""
    found = []
    for i, byte in enumerate(data):
        if byte in known_codes:
            found.append((i, byte))
    return found

def main():
    print(f"Panasonic Button Daemon starting...")
    print(f"Monitoring EC at {EC_PATH}")
    print(f"Looking for scancodes: {BUTTONS}")
    
    if not os.path.exists(EC_PATH):
        print(f"ERROR: {EC_PATH} not found. Run with sudo and ensure ec_sys is loaded.")
        sys.exit(1)
    
    known_codes = set(BUTTONS.keys())
    last_state = {}
    scan_count = 0
    
    # Areas to monitor - focusing on likely button state regions
    monitor_ranges = [
        (0x00, 0x10),  # Status area
        (0x30, 0x10),  # Where we saw 0x36 appear
        (0xA0, 0x20),  # Config area
        (0xC0, 0x20),  # Button config area (ERCx, ERDx)
    ]
    
    print("\nMonitoring... Press Ctrl+C to stop.")
    print("Press tablet buttons to see if they're detected.\n")
    
    try:
        while True:
            scan_count += 1
            
            for start, length in monitor_ranges:
                data = read_ec_range(start, length)
                findings = scan_for_scancodes(data, known_codes)
                
                for offset, code in findings:
                    abs_offset = start + offset
                    key = f"{abs_offset:02x}"
                    
                    if key not in last_state or last_state[key] != code:
                        button_name = BUTTONS.get(code, 'Unknown')
                        print(f"[{scan_count}] Scancode 0x{code:02x} ({button_name}) found at EC offset 0x{abs_offset:02x}")
                        last_state[key] = code
            
            # Also check the HINF buffer area mentioned in DSDT
            # HDAT is at TBTN device - let's check if button codes appear in predictable places
            
            time.sleep(0.05)  # 50ms = 20 samples/sec
            
    except KeyboardInterrupt:
        print(f"\nStopped after {scan_count} scans.")

if __name__ == '__main__':
    main()
