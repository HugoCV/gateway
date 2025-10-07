#!/usr/bin/env bash
set -euo pipefail

APP_NAME="gateway"
INSTALL_DIR="/opt/${APP_NAME}"
DESKTOP_USER="${SUDO_USER:-$(whoami)}"
DESKTOP_HOME="$(eval echo ~${DESKTOP_USER})"
VENV_DIR="${INSTALL_DIR}/venv"
AUTOSTART_DIR="${DESKTOP_HOME}/.config/autostart"
DESKTOP_FILE="${AUTOSTART_DIR}/${APP_NAME}.desktop"

echo "==> Instalando/actualizando ${APP_NAME} para usuario: ${DESKTOP_USER}"

# 1) Copiar proyecto a /opt/miapp
echo "==> Copiando proyecto..."
sudo mkdir -p "${INSTALL_DIR}"
if command -v rsync >/dev/null 2>&1; then
  sudo rsync -a --delete \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "venv" \
    --exclude "__pycache__" \
    ./ "${INSTALL_DIR}/"
else
  sudo cp -R . "${INSTALL_DIR}"
fi
sudo chown -R "${DESKTOP_USER}:${DESKTOP_USER}" "${INSTALL_DIR}"

# 2) Crear venv si no existe
if [ ! -d "${VENV_DIR}" ]; then
  echo "==> Creando venv..."
  sudo -u "${DESKTOP_USER}" -H bash -lc "python3 -m venv '${VENV_DIR}'"
fi

# 3) Instalar/actualizar dependencias
echo "==> Instalando dependencias..."
sudo -u "${DESKTOP_USER}" -H bash -lc "'${VENV_DIR}/bin/pip' install --upgrade pip"
if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
  sudo -u "${DESKTOP_USER}" -H bash -lc "'${VENV_DIR}/bin/pip' install -r '${INSTALL_DIR}/requirements.txt'"
fi

# 4) Copiar .env si existe
if [ -f ".env" ]; then
  echo "==> Copiando .env..."
  sudo cp ".env" "${INSTALL_DIR}/.env"
  sudo chown "${DESKTOP_USER}:${DESKTOP_USER}" "${INSTALL_DIR}/.env"
fi

# 5) Crear autostart en el escritorio
echo "==> Creando autostart..."
sudo -u "${DESKTOP_USER}" -H bash -lc "mkdir -p '${AUTOSTART_DIR}'"
cat <<EOF | sudo tee "${DESKTOP_FILE}" >/dev/null
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Autoarranque de ${APP_NAME}
Exec=${VENV_DIR}/bin/python ${INSTALL_DIR}/main.py --mode gui
Terminal=false
X-GNOME-Autostart-enabled=true
OnlyShowIn=LXDE;LXQt;XFCE;MATE;GNOME;KDE;
EOF
sudo chown "${DESKTOP_USER}:${DESKTOP_USER}" "${DESKTOP_FILE}"

echo
echo "==> Instalación/actualización completada."
echo "   - App en: ${INSTALL_DIR}"
echo "   - venv:   ${VENV_DIR}"
echo "   - Autostart: ${DESKTOP_FILE}"
echo
echo "Reinicia tu Raspberry para validar el arranque automático:"
echo "   sudo reboot"
