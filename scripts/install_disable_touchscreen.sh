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

disable_screen_dir="${SCRIPT_DIR}/../disable_screen"

# Copy systemd service file and install/enable/start service (requires sudo password)
scp "${disable_screen_dir}/disable-touchscreen.service" "${SSH_HOST}:/tmp/disable-touchscreen.service" >/dev/null

ssh -t $SSH_HOST "sudo mv /tmp/disable-touchscreen.service /etc/systemd/system/disable-touchscreen.service && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable disable-touchscreen.service && \
  sudo systemctl start disable-touchscreen.service"

echo -e "${GREEN}✅ disable-touchscreen systemd service installed, enabled and started${NC}"

# Show service status
echo -e "${YELLOW}Service status:${NC}"
ssh -t $SSH_HOST "sudo systemctl status disable-touchscreen.service --no-pager" || true
