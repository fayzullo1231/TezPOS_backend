#!/bin/bash
# Contabo: chek + qarz kodini majburan yangilash va tekshirish
# sudo bash /tmp/fix-check-debt-now.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
REMOTE="https://github.com/fayzullo1231/TezPOS_backend.git"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Root: sudo bash $0"
  exit 1
fi

cd "$INSTALL_DIR"

echo "==> Kod (git pull yoki clone)..."
if [[ -d .git ]]; then
  git config --global --add safe.directory "$INSTALL_DIR"
  git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"
  git fetch origin main
  git checkout -B main origin/main
else
  TMP="$(mktemp -d /tmp/tezpos-pull.XXXXXX)"
  git clone --depth 1 --branch main "$REMOTE" "$TMP"
  rsync -a --delete \
    --exclude 'venv' --exclude 'data' --exclude 'media' --exclude '.env' --exclude '__pycache__' \
    "$TMP/" "$INSTALL_DIR/"
  rm -rf "$TMP"
fi

chown -R tezpos:tezpos "$INSTALL_DIR"

echo "==> urls.py /check bormi?"
grep -n 'check/<str:server_name>' tezpos/urls.py || { echo "XATO: check route yo'q"; exit 1; }

echo "==> Migratsiya..."
sudo -u tezpos bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py migrate --noinput"

echo "==> Qarzlarni qayta hisoblash..."
sudo -u tezpos bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py recalc_customer_debts" || true

systemctl restart tezpos-backend
sleep 2

echo "==> Tekshiruv /check/ :"
curl -sI "http://127.0.0.1:8000/check/xusanuz/1/" | head -n 5 || true
curl -s "http://127.0.0.1:8000/check/xusanuz/1/" | head -n 5 || true

echo ""
echo "Agar tez-pos.uz ochilmasa (HTTPS):"
echo "  sudo bash deploy/setup-https-tez-pos.sh"
echo "SMS linklari hozircha http://13.140.146.78:8000/check/... ishlatadi."
echo "Tayyor."
