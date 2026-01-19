#!/usr/bin/env bash
set -euo pipefail

APP_NAME="gateway"
INSTALL_DIR="/opt/${APP_NAME}"
DESKTOP_USER="${SUDO_USER:-$(whoami)}"
DESKTOP_HOME="$(eval echo ~${DESKTOP_USER})"
AUTOSTART_DIR="${DESKTOP_HOME}/.config/autostart"
DESKTOP_FILE="${AUTOSTART_DIR}/${APP_NAME}.desktop"
EXECUTABLE_PATH="/usr/local/bin/${APP_NAME}"

echo "==> Instalando/actualizando ${APP_NAME} para usuario: ${DESKTOP_USER}"

# 1) Copiar proyecto a /opt/gateway
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

# 2) Crear entorno virtual si no existe
VENV_DIR="${INSTALL_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
  echo "==> Creando venv..."
  sudo -u "${DESKTOP_USER}" -H bash -lc "python3 -m venv '${VENV_DIR}'"
fi

# 3) Instalar dependencias
echo "==> Instalando dependencias..."
sudo -u "${DESKTOP_USER}" -H bash -lc "'${VENV_DIR}/bin/pip' install --upgrade pip"
sudo -u "${DESKTOP_USER}" -H bash -lc "'${VENV_DIR}/bin/pip' install pyinstaller"
if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
  sudo -u "${DESKTOP_USER}" -H bash -lc "'${VENV_DIR}/bin/pip' install -r '${INSTALL_DIR}/requirements.txt'"
fi

# 4) Generar ejecutable con PyInstaller
echo "==> Generando ejecutable con PyInstaller..."
sudo -u "${DESKTOP_USER}" -H bash -lc "cd '${INSTALL_DIR}' && '${VENV_DIR}/bin/pyinstaller' --onefile --name ${APP_NAME} main.py"

# 5) Mover ejecutable a /usr/local/bin
echo "==> Instalando ejecutable en /usr/local/bin..."
sudo cp "${INSTALL_DIR}/dist/${APP_NAME}" "${EXECUTABLE_PATH}"
sudo chmod +x "${EXECUTABLE_PATH}"

# 6) Crear autostart en el escritorio
echo "==> Creando autostart..."
sudo -u "${DESKTOP_USER}" -H bash -lc "mkdir -p '${AUTOSTART_DIR}'"
cat <<EOF | sudo tee "${DESKTOP_FILE}" >/dev/null
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Autoarranque de ${APP_NAME}
Exec=${EXECUTABLE_PATH} --mode gui
Terminal=false
X-GNOME-Autostart-enabled=true
OnlyShowIn=LXDE;LXQt;XFCE;MATE;GNOME;KDE;
EOF
sudo chown "${DESKTOP_USER}:${DESKTOP_USER}" "${DESKTOP_FILE}"

# 7) Habilitar el servicio para sistemas basados en systemd
echo "==> Creando servicio systemd..."
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
cat <<EOL | sudo tee "${SERVICE_FILE}" >/dev/null
[Unit]
Description=${APP_NAME} Application
After=network.target

[Service]
ExecStart=${EXECUTABLE_PATH} --mode gui
Restart=always
User=${DESKTOP_USER}

[Install]
WantedBy=multi-user.target
EOL
sudo systemctl daemon-reload
sudo systemctl enable ${APP_NAME}.service

# Limpiar archivos temporales generados por PyInstaller
echo "==> Limpiando archivos temporales..."
sudo rm -rf "${INSTALL_DIR}/build" "${INSTALL_DIR}/dist" "${INSTALL_DIR}/${APP_NAME}.spec"

# Mensaje final
echo
echo "==> Instalación/actualización completada."
echo "   - Ejecutable: ${EXECUTABLE_PATH}"
echo "   - Autostart: ${DESKTOP_FILE}"
echo "   - Servicio: ${SERVICE_FILE}"
echo

# Reinicio sugerido
echo "Reinicia tu sistema para validar el arranque automático:"
echo "   sudo reboot"