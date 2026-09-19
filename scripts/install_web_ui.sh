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

# mDNS name the UI is reached on: http://${MDNS_NAME}.local:${PORT}
MDNS_NAME=tv
PORT=8080

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
web_ui_dir="${SCRIPT_DIR}/../web_ui"

remote_home="/home/${SSH_USER}"
remote_base="${remote_home}/tv-web"
remote_app="${remote_base}/app"
remote_venv="${remote_base}/venv"

required_clis=(ssh scp)
for cmd in "${required_clis[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo -e "\n${RED}👎 ${cmd} not installed on your machine: this is a pre-requisite${NC}\n"
    exit 1
  fi
done

# --- Dependencies ----------------------------------------------------------
# python3-venv provides ensurepip, which Ubuntu omits from the base python3
# package; without it "python3 -m venv" fails.
echo -e "${YELLOW}Ensuring python3-venv is installed...${NC}"
ssh -t $SSH_HOST "sudo apt-get install -y python3-venv"
echo -e "${GREEN}✅ python3-venv present${NC}"

# --- Application code ------------------------------------------------------
echo -e "${YELLOW}Copying application...${NC}"
# Strip caches so no stale bytecode is shipped to the device.
find "${web_ui_dir}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
ssh $SSH_HOST "rm -rf /tmp/web_ui && mkdir -p /tmp/web_ui"
scp -q -r "${web_ui_dir}/." "${SSH_HOST}:/tmp/web_ui/"
ssh $SSH_HOST "mkdir -p ${remote_app} && rm -rf ${remote_app}/web_ui && \
  mkdir -p ${remote_app}/web_ui && cp -r /tmp/web_ui/. ${remote_app}/web_ui/ && \
  rm -rf /tmp/web_ui"
echo -e "${GREEN}✅ Application copied to ${remote_app}/web_ui${NC}"

# --- Virtualenv ------------------------------------------------------------
# Ubuntu 24.04 marks the system python as externally managed (PEP 668), so the
# dependencies live in a venv rather than being pip-installed system-wide.
echo -e "${YELLOW}Creating/updating the virtualenv (this can take a minute)...${NC}"
ssh $SSH_HOST "test -x ${remote_venv}/bin/python || python3 -m venv ${remote_venv}"
ssh $SSH_HOST "${remote_venv}/bin/pip install -q --upgrade pip && \
  ${remote_venv}/bin/pip install -q -r ${remote_app}/web_ui/requirements.txt"
echo -e "${GREEN}✅ Virtualenv ready at ${remote_venv}${NC}"

# --- Usage state directory ------------------------------------------------
# "Add time for today" rewrites the killswitch's usage file, so the directory is
# owned by the service user. tv-killswitch.sh keeps writing it as root.
echo -e "${YELLOW}Making the usage directory writable by ${SSH_USER}...${NC}"
ssh -t $SSH_HOST "sudo mkdir -p /var/lib/tv-emulator && \
  sudo chown ${SSH_USER}:${SSH_USER} /var/lib/tv-emulator && \
  sudo chmod 755 /var/lib/tv-emulator"
echo -e "${GREEN}✅ /var/lib/tv-emulator writable${NC}"

# --- limits.conf ----------------------------------------------------------
# The UI rewrites this file, so it must be writable by the service user. The
# killswitch installer creates it; create it here too in case this script runs
# first.
echo -e "${YELLOW}Ensuring limits.conf exists and is writable...${NC}"
scp -q "${SCRIPT_DIR}/../killswitch/limits.conf" "${SSH_HOST}:/tmp/limits.conf"
ssh -t $SSH_HOST "sudo mkdir -p /etc/tv-emulator && \
  if [ ! -f /etc/tv-emulator/limits.conf ]; then \
    sudo mv /tmp/limits.conf /etc/tv-emulator/limits.conf; \
  else rm -f /tmp/limits.conf; fi && \
  sudo chown ${SSH_USER}:${SSH_USER} /etc/tv-emulator/limits.conf && \
  sudo chmod 644 /etc/tv-emulator/limits.conf"
echo -e "${GREEN}✅ /etc/tv-emulator/limits.conf writable${NC}"

# --- sudoers rule for power actions ---------------------------------------
# Validated with visudo -c before being moved into place, so a malformed file
# can never lock sudo on the device.
echo -e "${YELLOW}Installing the shutdown sudoers rule...${NC}"
scp -q "${web_ui_dir}/sudoers-tv-web" "${SSH_HOST}:/tmp/sudoers-tv-web"
ssh -t $SSH_HOST "sudo install -m 0440 -o root -g root /tmp/sudoers-tv-web /etc/sudoers.d/tv-emulator-web && \
  if ! sudo visudo -cf /etc/sudoers.d/tv-emulator-web; then \
    sudo rm -f /etc/sudoers.d/tv-emulator-web; echo 'Invalid sudoers file - removed'; exit 1; \
  fi && rm -f /tmp/sudoers-tv-web"
echo -e "${GREEN}✅ /etc/sudoers.d/tv-emulator-web installed and validated${NC}"

# --- mDNS hostname --------------------------------------------------------
# avahi-daemon is already running on the tablet; this only shortens the name the
# UI is reached on. /etc/hosts is updated too so sudo stops warning about an
# unresolvable host.
echo -e "${YELLOW}Setting the hostname to '${MDNS_NAME}' for mDNS discovery...${NC}"
current_host=$(ssh $SSH_HOST "hostnamectl --static")
if [ "$current_host" != "$MDNS_NAME" ]; then
  ssh -t $SSH_HOST "sudo hostnamectl set-hostname ${MDNS_NAME} && \
    sudo sed -i 's/^127\.0\.1\.1.*/127.0.1.1\t${MDNS_NAME}/' /etc/hosts && \
    grep -q '^127\.0\.1\.1' /etc/hosts || echo -e '127.0.1.1\t${MDNS_NAME}' | sudo tee -a /etc/hosts >/dev/null"
  echo -e "${GREEN}✅ Hostname set to ${MDNS_NAME} (was ${current_host})${NC}"
else
  echo -e "${GREEN}✅ Hostname already ${MDNS_NAME}${NC}"
fi
ssh -t $SSH_HOST "sudo systemctl restart avahi-daemon"

# --- MPV IPC socket -------------------------------------------------------
# The UI's player controls talk to MPV over its JSON IPC socket, which
# cage-mpv-start.sh must pass --input-ipc-server to create.
echo -e "${YELLOW}Redeploying cage-mpv-start.sh (adds the MPV IPC socket)...${NC}"
scp -q "${SCRIPT_DIR}/../misc/cage-mpv-start.sh" "${SSH_HOST}:/tmp/cage-mpv-start.sh"
ssh -t $SSH_HOST "sudo mv /tmp/cage-mpv-start.sh /usr/local/bin/cage-mpv-start.sh && \
  sudo chmod +x /usr/local/bin/cage-mpv-start.sh"
echo -e "${GREEN}✅ cage-mpv-start.sh updated (takes effect on the next kiosk boot)${NC}"

# --- systemd service ------------------------------------------------------
scp -q "${web_ui_dir}/tv-web-ui.service" "${SSH_HOST}:/tmp/tv-web-ui.service"
ssh -t $SSH_HOST "sudo mv /tmp/tv-web-ui.service /etc/systemd/system/tv-web-ui.service && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable tv-web-ui.service && \
  sudo systemctl restart tv-web-ui.service"
echo -e "${GREEN}✅ tv-web-ui.service installed, enabled and started${NC}"

# --- Verify ---------------------------------------------------------------
echo -e "\n${YELLOW}Checking the service responds...${NC}"
sleep 2
if ssh $SSH_HOST "curl -fsS -o /dev/null http://127.0.0.1:${PORT}/"; then
  echo -e "${GREEN}✅ The UI is responding on the device${NC}"
else
  echo -e "${RED}👎 The UI did not respond. Recent logs:${NC}"
  ssh $SSH_HOST "journalctl -u tv-web-ui.service -n 30 --no-pager" || true
  exit 1
fi

echo -e "\n${GREEN}Web UI setup complete!${NC}"
echo -e "  • Open:     ${YELLOW}http://${MDNS_NAME}.local:${PORT}${NC}"
echo -e "  • Fallback: http://\$(device IP):${PORT}  (if .local does not resolve)"
echo -e "  • Player controls need a kiosk boot; reboot the tablet to create the"
echo -e "    MPV IPC socket. The time limit works on Admin boots too."
echo -e "${YELLOW}Note:${NC} mDNS (.local) does not traverse a VPN tunnel - if the name"
echo -e "      fails, check NordVPN LAN discovery or use the IP directly."
