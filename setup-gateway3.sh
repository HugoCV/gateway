#!/usr/bin/env bash
set -euo pipefail

APP_NAME="gateway"
REPO_URL="${GATEWAY_REPO_URL:-https://github.com/HugoCV/gateway.git}"
REPO_BRANCH="${GATEWAY_BRANCH:-test}"
INSTALL_DIR="${GATEWAY_INSTALL_DIR:-/opt/${APP_NAME}}"
DESKTOP_USER="${SUDO_USER:-$(whoami)}"
DESKTOP_HOME="$(eval echo ~"${DESKTOP_USER}")"
AUTOSTART_DIR="${DESKTOP_HOME}/.config/autostart"
DESKTOP_FILE="${AUTOSTART_DIR}/${APP_NAME}.desktop"
LOG_FILE="${GATEWAY_SETUP_LOG:-/tmp/setup-gateway3.log}"
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  echo "$@" | tee -a "${LOG_FILE}"
}

run_as_user() {
  sudo -u "${DESKTOP_USER}" -H bash -lc "$1"
}

: > "${LOG_FILE}"

log "[1/7] Installing system dependencies..."
sudo apt-get update | tee -a "${LOG_FILE}"
sudo apt-get install -y git python3 python3-venv python3-pip python3-tk | tee -a "${LOG_FILE}"

log "[2/7] Cloning or updating repository in ${INSTALL_DIR} from ${REPO_BRANCH}..."
sudo mkdir -p "${INSTALL_DIR}"
sudo chown -R "${DESKTOP_USER}:${DESKTOP_USER}" "${INSTALL_DIR}"

if [ -d "${INSTALL_DIR}/.git" ]; then
  run_as_user "cd '${INSTALL_DIR}' && git fetch origin '${REPO_BRANCH}'"
  if run_as_user "cd '${INSTALL_DIR}' && ! git diff --quiet --ignore-submodules --"; then
    STASH_NAME="setup-gateway-backup-$(date +%s)"
    log "[2/7] Local changes detected; stashing before reset: ${STASH_NAME}"
    run_as_user "cd '${INSTALL_DIR}' && git stash push -u -m '${STASH_NAME}'"
  fi
  run_as_user "cd '${INSTALL_DIR}' && git checkout -B '${REPO_BRANCH}' 'origin/${REPO_BRANCH}'"
  run_as_user "cd '${INSTALL_DIR}' && git reset --hard 'origin/${REPO_BRANCH}'"
else
  sudo rm -rf "${INSTALL_DIR:?}/"*
  run_as_user "git clone --branch '${REPO_BRANCH}' --single-branch '${REPO_URL}' '${INSTALL_DIR}'"
fi

log "[3/7] Copying .env from installer to ${INSTALL_DIR} ..."
if [ -f "${INSTALLER_DIR}/.env" ]; then
  sudo cp "${INSTALLER_DIR}/.env" "${INSTALL_DIR}/.env"
else
  log "Warning: no .env found beside setup script."
fi

log "[4/7] Fixing ownership..."
sudo chown -R "${DESKTOP_USER}:${DESKTOP_USER}" "${INSTALL_DIR}"

log "[5/7] Creating venv and installing Python dependencies..."
run_as_user "python3 -m venv '${INSTALL_DIR}/.venv'"
run_as_user "'${INSTALL_DIR}/.venv/bin/pip' install --upgrade pip"

if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
  run_as_user "'${INSTALL_DIR}/.venv/bin/pip' install -r '${INSTALL_DIR}/requirements.txt'"
elif [ -f "${INSTALL_DIR}/pyproject.toml" ]; then
  run_as_user "cd '${INSTALL_DIR}' && '${INSTALL_DIR}/.venv/bin/pip' install ."
elif [ -f "${INSTALL_DIR}/setup.py" ]; then
  run_as_user "cd '${INSTALL_DIR}' && '${INSTALL_DIR}/.venv/bin/pip' install ."
else
  log "Error: no requirements.txt, pyproject.toml or setup.py found in ${INSTALL_DIR}."
  exit 1
fi

log "[6/7] Creating startup wrapper..."
if [ ! -f "${INSTALL_DIR}/main.py" ]; then
  log "Error: no entrypoint found at ${INSTALL_DIR}/main.py."
  exit 1
fi

cat <<EOF | sudo tee "${INSTALL_DIR}/start.sh" >/dev/null
#!/usr/bin/env bash
set -euo pipefail
cd "${INSTALL_DIR}"
exec "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/main.py" --mode "\${GATEWAY_MODE:-gui}"
EOF
sudo chmod +x "${INSTALL_DIR}/start.sh"
sudo chown "${DESKTOP_USER}:${DESKTOP_USER}" "${INSTALL_DIR}/start.sh"

log "[7/7] Creating autostart entry..."
run_as_user "mkdir -p '${AUTOSTART_DIR}'"
cat <<EOF | sudo tee "${DESKTOP_FILE}" >/dev/null
[Desktop Entry]
Type=Application
Name=Gateway
Comment=Gateway autostart
Exec=${INSTALL_DIR}/start.sh
Terminal=false
X-GNOME-Autostart-enabled=true
OnlyShowIn=LXDE;LXQt;XFCE;MATE;GNOME;KDE;
EOF
sudo chown "${DESKTOP_USER}:${DESKTOP_USER}" "${DESKTOP_FILE}"

log "Setup completed. Branch: ${REPO_BRANCH}. Log file: ${LOG_FILE}"
log "Start manually with: sudo -u ${DESKTOP_USER} DISPLAY=:0 XAUTHORITY=${DESKTOP_HOME}/.Xauthority ${INSTALL_DIR}/start.sh"
