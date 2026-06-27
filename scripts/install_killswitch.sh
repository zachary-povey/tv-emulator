#!/bin/bash
set -e

# Colors
RED='\033[1;31m'
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
NC='\033[0m' # No Color

# This must be configured in your ~/.ssh/config
SSH_HOST=tv-emulator
SSH_USER=tv-emulator

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
killswitch_dir="${SCRIPT_DIR}/../killswitch"

# Marker comments delimiting the block we manage in /etc/grub.d/40_custom, so
# re-running this script replaces it rather than appending duplicates.
GRUB_BEGIN="### BEGIN tv-emulator admin entry"
GRUB_END="### END tv-emulator admin entry"

# --- Timezone sanity check -------------------------------------------------
# The killswitch keys its per-day state on the device's local date, so the
# timezone must be correct for the "day" to roll over at Spanish midnight.
echo -e "${YELLOW}Checking timezone (expecting Europe/Madrid)...${NC}"
tz=$(ssh $SSH_HOST "timedatectl show -p Timezone --value" 2>/dev/null || echo unknown)
if [ "$tz" != "Europe/Madrid" ]; then
    echo -e "${YELLOW}⚠️  Timezone is '${tz}', not Europe/Madrid. Setting it...${NC}"
    ssh -t $SSH_HOST "sudo timedatectl set-timezone Europe/Madrid"
fi
echo -e "${GREEN}✅ Timezone: $(ssh $SSH_HOST 'timedatectl show -p Timezone --value')${NC}"

# --- Killswitch script -----------------------------------------------------
scp "${killswitch_dir}/tv-killswitch.sh" "${SSH_HOST}:/tmp/tv-killswitch.sh" >/dev/null
ssh -t $SSH_HOST "sudo mv /tmp/tv-killswitch.sh /usr/local/bin/tv-killswitch.sh && sudo chmod +x /usr/local/bin/tv-killswitch.sh"
echo -e "${GREEN}✅ tv-killswitch.sh installed${NC}"

# --- Config file (don't clobber an edited copy already on the device) ------
scp "${killswitch_dir}/limits.conf" "${SSH_HOST}:/tmp/limits.conf" >/dev/null
ssh -t $SSH_HOST "sudo mkdir -p /etc/tv-emulator && \
  if [ -f /etc/tv-emulator/limits.conf ]; then \
    echo 'limits.conf already exists on device - leaving it untouched'; rm -f /tmp/limits.conf; \
  else \
    sudo mv /tmp/limits.conf /etc/tv-emulator/limits.conf; \
  fi"
echo -e "${GREEN}✅ /etc/tv-emulator/limits.conf in place${NC}"

# --- systemd service + timer ----------------------------------------------
scp "${killswitch_dir}/tv-killswitch.service" "${SSH_HOST}:/tmp/tv-killswitch.service" >/dev/null
scp "${killswitch_dir}/tv-killswitch.timer" "${SSH_HOST}:/tmp/tv-killswitch.timer" >/dev/null
ssh -t $SSH_HOST "sudo mv /tmp/tv-killswitch.service /etc/systemd/system/tv-killswitch.service && \
  sudo mv /tmp/tv-killswitch.timer /etc/systemd/system/tv-killswitch.timer && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable --now tv-killswitch.timer"
echo -e "${GREEN}✅ tv-killswitch.timer installed, enabled and started${NC}"

# --- Updated cage-mpv-start.sh (admin-boot fork to GNOME) ------------------
scp "${SCRIPT_DIR}/../misc/cage-mpv-start.sh" "${SSH_HOST}:/tmp/cage-mpv-start.sh" >/dev/null
ssh -t $SSH_HOST "sudo mv /tmp/cage-mpv-start.sh /usr/local/bin/cage-mpv-start.sh && sudo chmod +x /usr/local/bin/cage-mpv-start.sh"
echo -e "${GREEN}✅ cage-mpv-start.sh updated (admin boot -> GNOME desktop)${NC}"

# --- GRUB "Admin" entry + brief visible menu ------------------------------
# Build the entry on the device from the running kernel and root UUID so it
# stays correct, and switch GRUB to a short visible menu (3s, kiosk default) so
# the Admin entry is reachable with only tablet input. The entry appends
# tv_admin=1 to the cmdline. The helper is generated locally and scp'd over
# (rather than piped via stdin) so stdin stays free for the interactive sudo
# prompt. Device-side variables are left unexpanded here and resolved on the tablet.
echo -e "${YELLOW}Adding hidden GRUB 'Admin (GNOME desktop)' entry...${NC}"
grub_helper=$(mktemp)
cat > "$grub_helper" <<REMOTE
#!/bin/bash
set -e
root_uuid=\$(findmnt -no UUID /)
kernel=\$(ls -1 /boot/vmlinuz-* | sort -V | tail -1)
initrd=\$(ls -1 /boot/initrd.img-* | sort -V | tail -1)
base_cmdline=\$(. /etc/default/grub; echo "\$GRUB_CMDLINE_LINUX_DEFAULT \$GRUB_CMDLINE_LINUX")

entry="${GRUB_BEGIN}
menuentry 'Admin (GNOME desktop)' --class ubuntu {
    recordfail
    load_video
    gfxmode \\\$linux_gfx_mode
    insmod gzio
    insmod part_gpt
    insmod ext2
    search --no-floppy --fs-uuid --set=root \$root_uuid
    linux \$kernel root=UUID=\$root_uuid ro \$base_cmdline tv_admin=1
    initrd \$initrd
}
${GRUB_END}"

# Replace any previously-managed block, then append the fresh one.
sed -i '/${GRUB_BEGIN}/,/${GRUB_END}/d' /etc/grub.d/40_custom
printf '%s\n' "\$entry" >> /etc/grub.d/40_custom
chmod +x /etc/grub.d/40_custom

# Show the menu briefly on every boot so the Admin entry is reachable with only
# tablet input (no USB keyboard). The kiosk is the default (GRUB_DEFAULT=0) and
# auto-boots after the timeout if untouched, so a normal boot just shows a short
# menu flash then plays as usual. Touch/press during the countdown to pick Admin.
sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=menu/' /etc/default/grub || true
grep -q '^GRUB_TIMEOUT_STYLE=' /etc/default/grub || echo 'GRUB_TIMEOUT_STYLE=menu' >> /etc/default/grub
sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=3/' /etc/default/grub || true
grep -q '^GRUB_TIMEOUT=' /etc/default/grub || echo 'GRUB_TIMEOUT=3' >> /etc/default/grub

update-grub
REMOTE
scp "$grub_helper" "${SSH_HOST}:/tmp/tv-grub-admin.sh" >/dev/null
rm -f "$grub_helper"
ssh -t $SSH_HOST "sudo bash /tmp/tv-grub-admin.sh && rm -f /tmp/tv-grub-admin.sh"
echo -e "${GREEN}✅ GRUB Admin entry installed${NC}"

echo -e "\n${GREEN}Killswitch setup complete!${NC}"
echo -e "  • Daily limit: edit /etc/tv-emulator/limits.conf (DAILY_LIMIT_MINUTES)"
echo -e "  • Admin boot:  a 3s GRUB menu shows on every boot (kiosk auto-boots if"
echo -e "                 untouched). Tap/press during the countdown to pick"
echo -e "                 'Admin (GNOME desktop)' (killswitch disarmed, full desktop)."
echo -e "${YELLOW}Timer status:${NC}"
ssh -t $SSH_HOST "systemctl status tv-killswitch.timer --no-pager" || true
