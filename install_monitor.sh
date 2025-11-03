#!/bin/bash
set -e

echo "🚀 Instalando Monitor..."

SRC_DIR="$HOME/Documents/gateway"
DEST_DIR="/opt/monitor"
DESKTOP_FILE="$HOME/.config/autostart/monitor.desktop"

echo "🗑️ Eliminando instalación previa (si existe)..."
sudo rm -rf $DEST_DIR

echo "📁 Creando carpeta destino..."
sudo mkdir -p $DEST_DIR
sudo chown -R $USER:$USER $DEST_DIR

echo "📦 Copiando código al destino..."
sudo rsync -av --delete "$SRC_DIR/" "$DEST_DIR/"

echo "🐍 Creando entorno virtual con Python 3.11..."
cd $DEST_DIR
python3.11 -m venv venv

echo "📍 Instalando dependencias..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

echo "🧹 Limpiando pycache..."
sudo find $DEST_DIR -name "__pycache__" -type d -exec rm -rf {} +
sudo find $DEST_DIR -name "*.pyc" -delete

echo "⚙️ Creando autostart..."
mkdir -p $HOME/.config/autostart

cat <<EOF > $DESKTOP_FILE
[Desktop Entry]
Type=Application
Name=Monitor
Exec=$DEST_DIR/venv/bin/python $DEST_DIR/main.py
Comment=Inicia monitor en modo GUI
X-GNOME-Autostart-enabled=true
EOF

echo "Instalación completada."
echo "Reinicia el sistema para que arranque automáticamente."
