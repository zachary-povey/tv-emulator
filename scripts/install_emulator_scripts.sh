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

# Determine the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

required_clis=(
  scp
)

for cmd in "${required_clis[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo -e "\n${RED}👎 ${cmd} not installed on your machine: this is a pre-requisite${NC}\n"
    exit 1
  fi
done

source_script_dir="${SCRIPT_DIR}/../emulator_scripts"
destination_script_dir="/home/${SSH_USER}/Scripts"
scripts=$(ls $source_script_dir 2>/dev/null)

for script in "${scripts[@]}"; do
  scp "${source_script_dir}/${script}" "${SSH_HOST}:${destination_script_dir}/${script}" >/dev/null
  echo -e "${GREEN}✅ ${script} installed\n${NC}"
done

PATH_INSTALL='export PATH="${HOME}/Scripts:${PATH}"'
PATH_INSTALL_FOUND=$(ssh $SSH_HOST "grep '${PATH_INSTALL}' ~/.bashrc" || true)

if [[ -z $PATH_INSTALL_FOUND ]]; then
  ssh $SSH_HOST "echo -e '# Ensure emulator management scripts on PATH\n${PATH_INSTALL}' >> ~/.bashrc"
  echo -e "${GREEN}✅ Script dir installed into PATH\n${NC}"
else
  echo -e "${GREEN}✅ Script dir already in PATH\n${NC}"
fi
