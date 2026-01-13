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

mpv_config_dir="${SCRIPT_DIR}/../mpv_config"

# Install channel_cycler.lua script to mpv scripts directory
scp "${mpv_config_dir}/channel_cycler.lua" "${SSH_HOST}:~/.config/mpv/scripts/channel_cycler.lua"
echo -e "${GREEN}✅ channel_cycler.lua installed\n${NC}"

# Install mpv input config
scp "${mpv_config_dir}/mpv_input.conf" "${SSH_HOST}:~/.config/mpv/input.conf"
echo -e "${GREEN}✅ mpv input config installed\n${NC}"
