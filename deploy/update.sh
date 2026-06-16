#!/bin/bash
# Kod yangilangandan keyin qayta ishga tushirish
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_USER="${SERVICE_USER:-tezpos}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Root sifatida ishga tushiring: sudo bash deploy/update.sh"
    exit 1
fi

echo "==> Kod yangilanmoqda..."
rsync -a --delete \
    --exclude 'venv' \
    --exclude 'data' \
    --exclude 'media' \
    --exclude '.env' \
    --exclude '__pycache__' \
    --exclude '.git' \
    "$REPO_ROOT/" "$INSTALL_DIR/"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo "==> Kutubxonalar..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "==> Migratsiya..."
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py migrate --noinput"
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py collectstatic --noinput" 2>/dev/null || true

systemctl restart tezpos-backend
echo "Yangilandi va qayta ishga tushirildi."
