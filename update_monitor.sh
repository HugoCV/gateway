#!/bin/bash
set -e

echo "🔄 Actualizando Monitor..."

SRC_DIR="$HOME/Documentos/gateway"
DEST_DIR="/opt/monitor"

echo "Sincronizando archivos nuevos..."
sudo rsync -av --delete "$SRC_DIR/" "$DEST_DIR/"

echo "Limpiando pycache..."
sudo find $DEST_DIR -name "__pycache__" -type d -exec rm -rf {} +
sudo find $DEST_DIR -name "*.pyc" -delete

echo "Actualización completa."
echo "Si la app está abierta, cierra y vuelve a abrir para usar la versión nueva."
