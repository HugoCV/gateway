#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [ ! -x ./venv/bin/python ]; then
  echo "No se encontró venv/bin/python. Prepare el entorno virtual y las dependencias del Gateway." >&2
  exit 1
fi

exec ./venv/bin/python main.py --mode desktop
