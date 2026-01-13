# Panasonic FZ-G1 MK4 Tablet Buttons - Linux Support

## Overview

Attempted to get tablet buttons (A1, A2, Windows, Volume) working on a Panasonic FZ-G1 MK4 Toughpad running Ubuntu 24.04 (kernel 6.14.0-37-generic).

**Result**: Only A1 button works. Other buttons require EC firmware changes that appear to need a BIOS update or reverse-engineering the Windows driver. A workaround daemon was created to give A1 multiple functions.

---

## Hardware Details

- **Device**: Panasonic FZ-G1 MK4 Toughpad
- **OS**: Ubuntu 24.04
- **Kernel**: 6.14.0-37-generic
- **BIOS**: V4.00L15 (V4.00L25 available)
- **ACPI Device ID**: MAT0037 (TBTN - Tablet Buttons)
- **Buttons**: A1, A2, Windows key, Volume Up/Down, Rotation Lock, Power

## What Was Tried

### 1. Driver Modification (Partially Successful)

Modified the community `panasonic-hbtn` driver from https://github.com/cyberpunkcoder/panasonic-hbtn:

**Changes made to `/home/tv-emulator/panasonic-hbtn/panasonic-hbtn.c`:**

```c
// Added MAT0037 device ID
static const struct acpi_device_id pcc_device_ids[] = {
    { "MAT001F", 0},
    { "MAT0020", 0},
    { "MAT0037", 0},  /* FZ-G1 MK4 */
    { "", 0},
};

// Added FZ-G1 button scancodes to keymap
static const struct key_entry panasonic_keymap[] = {
    { KE_KEY, 0x0, { KEY_RESERVED } },
    { KE_KEY, 0x4, { KEY_SCREENLOCK } },
    { KE_KEY, 0x6, { KEY_MSDOS } },
    { KE_KEY, 0x8, { KEY_ESC } },
    { KE_KEY, 0xA, { KEY_MENU } },
    { KE_KEY, 0x36, { KEY_PROG1 } },     /* A2 button */
    { KE_KEY, 0x38, { KEY_PROG2 } },     /* A1 button */
    { KE_KEY, 0x42, { KEY_LEFTMETA } },  /* Windows button */
    { KE_END, 0 }
};

// Fixed scancode masking (was & 0xe, now & ~1UL)
pressed = !(result & 0x1);
scancode = result & ~1UL;
```

**Driver location**: `/lib/modules/6.14.0-37-generic/kernel/drivers/panasonic-hbtn/panasonic-hbtn.ko`

### 2. DSDT Analysis

Decompiled ACPI tables at `/tmp/dsdt.dsl`. Found button EC query mappings:

| EC Query | Scancode | Button |
|----------|----------|--------|
| _Q97/_Q98 | 0x36/0x37 | A2 press/release |
| _Q9B/_Q9C | 0x38/0x39 | A1 press/release (WORKS) |
| _QA7/_QA8 | 0x42/0x43 | Windows press/release |

### 3. EC Register Configuration

Found button enable registers in EC memory (ERD0-ERD5, ERD9, ERDA, ERE6). Set them all to 0x82 (enabled state) via:

```bash
# Write to EC registers
printf "\x82" | sudo dd of=/sys/kernel/debug/ec/ec0/io bs=1 seek=208 count=1 conv=notrunc
# Then call CTTB to initialize
echo "\\_SB.PCI0.LPCB.EC0.CTTB" | sudo tee /proc/acpi/call
```

### 4. Manual ACPI Testing

Verified driver works correctly by manually triggering EC queries:

```bash
# This generates correct button events
echo "\\_SB.PCI0.LPCB.EC0._Q97" | sudo tee /proc/acpi/call
```

**Key finding**: Manual ACPI calls work perfectly, proving the driver is correct. The issue is the EC firmware not generating queries for buttons other than A1.

### 5. Other Attempts

- Various `acpi_osi` kernel parameters (already had `acpi_osi=Windows 2012`)
- ASRV EC commands (0x13, 0x14, 0x15, 0x18)
- EC4F initialization
- I2C/SMBus scanning
- GPIO investigation
- EC memory polling for button state changes

---

## Root Cause

The Embedded Controller (EC) firmware only generates ACPI query 0x9B when the A1 button is pressed. Other buttons don't trigger their respective EC queries (0x97, 0xA7, etc.), even though:

1. The driver correctly handles all button codes
2. EC registers are configured to "enabled" state
3. Buttons worked in Windows before Ubuntu was installed

The EC firmware has internal button-to-query routing that we cannot modify from software. This likely requires:
- A BIOS update (V4.00L25 available, but requires Windows to install)
- Reverse-engineering the Windows Panasonic driver's initialization sequence

---

## Workaround: Multi-Function Button Daemon

Created a Python daemon that makes A1 work as three different buttons using gestures:

### Files Created

| File | Purpose |
|------|---------|
| `/home/tv-emulator/multi_button.py` | Main daemon |
| `/home/tv-emulator/multi_button_config.py` | Configuration |
| `/etc/systemd/system/panasonic-multibutton.service` | Systemd service |

### Gesture Mapping (Default)

| Gesture | Action |
|---------|--------|
| Short tap (<0.5s) | KEY_LEFTMETA (Windows key) |
| Long press (>0.5s) | KEY_MENU (Context menu) |
| Double tap (<0.7s between taps) | KEY_F12 |

### Configuration

Edit `/home/tv-emulator/multi_button_config.py`:

```python
from evdev import ecodes

SHORT_PRESS_KEY = ecodes.KEY_F11
LONG_PRESS_KEY = ecodes.KEY_MUTE
DOUBLE_TAP_KEY = ecodes.KEY_F12

LONG_PRESS_TIME = 0.5   # seconds
DOUBLE_TAP_TIME = 0.7   # seconds between taps
```

### Service Management

```bash
sudo systemctl status panasonic-multibutton   # Check status
sudo systemctl restart panasonic-multibutton  # After config changes
sudo systemctl stop panasonic-multibutton     # Stop daemon
sudo journalctl -u panasonic-multibutton -f   # Watch logs
```

---

## Key Technical Findings

1. **MAT0037** is the ACPI device ID for FZ-G1 MK4 tablet buttons (older CF-18/19 use MAT001F/MAT0020)

2. **EC Query Mechanism**: Button presses should trigger GPE17 → EC query → ACPI _Qxx method → driver notification

3. **TBTN vs HKEY**: Two separate ACPI devices handle different buttons:
   - TBTN (MAT0037): Tablet-specific buttons
   - HKEY (MAT0019): Laptop hotkeys (Fn combinations)

4. **Scancode Format**: Bit 0 = press/release flag (0=press, 1=release), remaining bits = button ID

5. **EC Registers**: ERD0-ERD5, ERD9, ERDA, ERE6 at offsets 0xD0-0xE6 control button availability (0x82=enabled, 0x9F=disabled)

---

## References

- Original driver repo: https://github.com/cyberpunkcoder/panasonic-hbtn
- FZ-G1 Mk3 ACPI article: https://wmealing.github.io/toughpad-fz-g1-buttons-acpi.html
- Panasonic driver download: https://global-pc-support.connect.panasonic.com/dldocs/84081

---

## Future Options

1. **BIOS Update**: If you can get Windows running (live USB?), update to V4.00L25 which may fix EC button routing

2. **Reverse Engineer Windows Driver**: Extract and analyze the Panasonic Windows driver to find the EC initialization commands

3. **Use A1 Workaround**: The multi-button daemon gives you 3 functions from 1 button

4. **On-screen Buttons**: Use software buttons for functions you can't access physically
