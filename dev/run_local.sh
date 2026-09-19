#!/bin/bash
# Run the web UI locally against a fixture tree instead of the tablet.
#
# Usage: dev/run_local.sh [fixture_dir] [port]
#
# Builds the fixture if it is missing, starts the fake MPV IPC server in the
# background, and serves the app with auto-reload. Power actions are simulated.
set -e

REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
FIXTURE="${1:-${REPO_DIR}/.dev-fixture}"
PORT="${2:-8080}"
VENV="${TV_VENV:-${REPO_DIR}/.venv}"

if [ ! -x "${VENV}/bin/uvicorn" ]; then
    echo "Creating venv at ${VENV}..."
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install -q -r "${REPO_DIR}/web_ui/requirements.txt"
fi

if [ ! -d "${FIXTURE}" ]; then
    python3 "${REPO_DIR}/dev/make_fixture.py" "${FIXTURE}"
fi

export TV_CHANNELS_DIR="${FIXTURE}/Channels"
export TV_LIMITS_CONF="${FIXTURE}/etc/limits.conf"
export TV_USAGE_DIR="${FIXTURE}/var"
export TV_MPV_SOCKET="${FIXTURE}/mpv-socket"
export TV_CREATE_PLAYLIST="${REPO_DIR}/emulator_scripts/create_playlist"
export TV_FAKE_SHUTDOWN=1

python3 "${REPO_DIR}/dev/fake_mpv.py" "${TV_MPV_SOCKET}" &
FAKE_MPV_PID=$!
trap 'kill ${FAKE_MPV_PID} 2>/dev/null || true' EXIT

echo "Serving on http://127.0.0.1:${PORT}  (fixture: ${FIXTURE})"
cd "${REPO_DIR}"
"${VENV}/bin/uvicorn" web_ui.app:app --host 127.0.0.1 --port "${PORT}" --reload
