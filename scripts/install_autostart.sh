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

# Ensure autostart directory exists
ssh $SSH_HOST "mkdir -p ${destination_dir}/.config/autostart"

# Install mpv-autostart.desktop to user autostart directory
scp "${misc_dir}/mpv-autostart.desktop" "${SSH_HOST}:${destination_dir}/.config/autostart/mpv-autostart.desktop"
echo -e "${GREEN}✅ mpv-autostart.desktop installed\n${NC}"

scp "${misc_dir}/default-brightness-autostart.desktop" "${SSH_HOST}:${destination_dir}/.config/autostart/default-brightness-autostart.desktop"
echo -e "${GREEN}✅ default-brightness-autostart.desktop installed\n${NC}"

# Install GDM custom.conf (requires sudo)
scp "${misc_dir}/custom.conf" "${SSH_HOST}:/tmp/custom.conf" >/dev/null

ssh -t $SSH_HOST "sudo mv /tmp/custom.conf /etc/gdm3/custom.conf"
echo -e "${GREEN}✅ GDM custom.conf installed (automatic login enabled)\n${NC}"
