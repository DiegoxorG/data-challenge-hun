#!/bin/sh
# Configuración inicial en macOS/Linux/Git Bash, desde la raíz del repo:
#   sh scripts/setup.sh
set -e

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null || true
echo "OK  hooks anti-fuga activados (.githooks)"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "OK  .env creado desde .env.example  -> llénalo con TUS credenciales (no se sube)"
fi

python3 scripts/check_no_data.py --all || python scripts/check_no_data.py --all
echo
echo "Siguiente paso: crea tu carpeta de datos FUERA del repo y ponla en DATA_DIR dentro de .env"
echo "Recomendado: una carpeta que NO esté en iCloud/Drive/OneDrive, p. ej. ~/hun_data"
