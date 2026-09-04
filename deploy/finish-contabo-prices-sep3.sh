#!/bin/bash
# Contabo Sep3/Sep4 restore KEYIN — faqat kuloloptom-2 narxlarini olish
# Qoldiq, sotuv, boshqa tenantlarga TEKMAYDI
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"

SNAP="/root/tezpos_sep3_prices.db"
CURRENT="/root/tezpos_current.db"
LIVE="/opt/tezpos-backend/data/tezpos.db"
TENANT="${TENANT:-kuloloptom-2}"

if [[ ! -f "$CURRENT" ]]; then
  echo "XATO: $CURRENT topilmadi."
  echo "Avval: sudo bash deploy/prepare-contabo-prices-sep3.sh"
  exit 1
fi

echo "==> Contabo snapshot saqlanmoqda: $LIVE -> $SNAP"
cp -a "$LIVE" "$SNAP"
chmod 644 "$SNAP"
ls -lh "$SNAP"

echo "==> Joriy baza qaytarilmoqda (sotuvlar/qoldiq saqlansin)..."
systemctl stop tezpos-backend 2>/dev/null || true
cp -a "$CURRENT" "$LIVE"
chown tezpos:tezpos "$LIVE"
chmod 640 "$LIVE"
systemctl start tezpos-backend
sleep 2
systemctl is-active tezpos-backend

git pull origin main 2>/dev/null || true

echo ""
echo "==> Dry-run: faqat $TENANT narxlari"
sudo -u tezpos $PY manage.py restore_prices_from_sqlite "$SNAP" --tenant "$TENANT" --dry-run

if [[ "${1:-}" == "--apply" ]]; then
  echo ""
  echo "==> APPLY: $TENANT narxlari yozilmoqda..."
  sudo -u tezpos $PY manage.py restore_prices_from_sqlite "$SNAP" --tenant "$TENANT"
  echo "TAYYOR. POS da $TENANT uchun Sinxron qiling."
  echo "Boshqa serverlar (kuloloptom, usmon, ...) o'zgarmagan."
else
  echo ""
  echo "Natija to'g'ri bo'lsa:"
  echo "  sudo bash deploy/finish-contabo-prices-sep3.sh --apply"
fi
