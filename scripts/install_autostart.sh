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

misc_dir="${SCRIPT_DIR}/../misc"
destination_dir="/home/${SSH_USER}"

# Install cage compositor if not already installed
echo -e "${YELLOW}Installing cage compositor...${NC}"
ssh -t $SSH_HOST "sudo apt-get install -y cage" || {
    echo -e "${RED}Failed to install cage. Please install manually: sudo apt install cage${NC}"
    exit 1
}
echo -e "${GREEN}✅ cage compositor installed${NC}"

# Install cage-mpv startup script (requires sudo)
scp "${misc_dir}/cage-mpv-start.sh" "${SSH_HOST}:/tmp/cage-mpv-start.sh" >/dev/null
ssh -t $SSH_HOST "sudo mv /tmp/cage-mpv-start.sh /usr/local/bin/cage-mpv-start.sh && sudo chmod +x /usr/local/bin/cage-mpv-start.sh"
echo -e "${GREEN}✅ cage-mpv-start.sh installed${NC}"

# Install cage-mpv session file (requires sudo)
scp "${misc_dir}/cage-mpv.desktop" "${SSH_HOST}:/tmp/cage-mpv.desktop" >/dev/null
ssh -t $SSH_HOST "sudo mv /tmp/cage-mpv.desktop /usr/share/wayland-sessions/cage-mpv.desktop"
echo -e "${GREEN}✅ cage-mpv.desktop session installed${NC}"

# Clean up old autostart entries (no longer needed with cage session)
ssh $SSH_HOST "rm -f ${destination_dir}/.config/autostart/mpv-autostart.desktop" 2>/dev/null || true
ssh $SSH_HOST "rm -f ${destination_dir}/.config/autostart/default-volume-autostart.desktop" 2>/dev/null || true
echo -e "${YELLOW}ℹ️  Removed old autostart entries (replaced by cage session)${NC}"

# Install GDM custom.conf (requires sudo)
scp "${misc_dir}/custom.conf" "${SSH_HOST}:/tmp/custom.conf" >/dev/null
ssh -t $SSH_HOST "sudo mv /tmp/custom.conf /etc/gdm3/custom.conf"
echo -e "${GREEN}✅ GDM custom.conf installed (automatic login to cage-mpv session)${NC}"

echo -e "\n${GREEN}Setup complete!${NC}"
echo -e "The system will now auto-login to the TV Mode (Cage + MPV) session."
echo -e "To access GNOME, press Ctrl+Alt+F2 for a TTY, or log out and select 'GNOME' at the login screen."
