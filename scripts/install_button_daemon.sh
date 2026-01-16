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

required_clis=(
  scp
  ssh
)

for cmd in "${required_clis[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo -e "\n${RED}👎 ${cmd} not installed on your machine: this is a pre-requisite${NC}\n"
    exit 1
  fi
done

button_daemon_dir="${SCRIPT_DIR}/../button_daemon"
destination_dir="/home/${SSH_USER}"

# Copy Python daemon files
scp "${button_daemon_dir}/multi_button.py" "${SSH_HOST}:${destination_dir}/multi_button.py" >/dev/null
echo -e "${GREEN}✅ multi_button.py installed\n${NC}"

# Make the main script executable
ssh $SSH_HOST "chmod +x ${destination_dir}/multi_button.py"

# Copy systemd service file and install/enable/start service (requires sudo password)
scp "${button_daemon_dir}/panasonic-multibutton.service" "${SSH_HOST}:/tmp/panasonic-multibutton.service" >/dev/null

ssh -t $SSH_HOST "sudo mv /tmp/panasonic-multibutton.service /etc/systemd/system/panasonic-multibutton.service && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable panasonic-multibutton.service && \
  sudo systemctl restart panasonic-multibutton.service"

echo -e "${GREEN}✅ systemd service installed, enabled and started\n${NC}"

# Copy logind.conf to disable default power button handling
scp "${button_daemon_dir}/logind.conf" "${SSH_HOST}:/tmp/logind.conf" >/dev/null


ssh -t $SSH_HOST "sudo mv /tmp/logind.conf /etc/systemd/logind.conf && \
  sudo systemctl restart systemd-logind"
# make double sure power button does nothing
gsettings set org.gnome.settings-daemon.plugins.power power-button-action 'nothing'

echo -e "${GREEN}✅ logind.conf installed (power button handling disabled)\n${NC}"

# Show service status
echo -e "${YELLOW}Service status:${NC}"
ssh -t $SSH_HOST "sudo systemctl status panasonic-multibutton.service --no-pager" || true
