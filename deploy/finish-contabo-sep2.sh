#!/bin/bash
# Contabo Sep 2 restore KEYIN — qoldiqni 1.7 mlrd holatga tiklash
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"

SEP2="/root/tezpos_sep2.db"
CURRENT="/root/tezpos_current.db"
LIVE="/opt/tezpos-backend/data/tezpos.db"

echo "==> Sep 2 snapshot saqlanmoqda..."
if [[ ! -f "$SEP2" ]]; then
  cp -a "$LIVE" "$SEP2"
  echo "Yozildi: $SEP2"
fi

if [[ ! -f "$CURRENT" ]]; then
  echo ""
  echo "XATO: $CURRENT topilmadi."
  echo "Avval prepare-contabo-sep2.sh ishlatilgan bo'lishi kerak."
  echo "Yoki qo'lda: cp /opt/tezpos-backend/data/tezpos.db /root/tezpos_current.db"
  exit 1
fi

echo "==> Joriy sotuvlar bazasi qaytarilmoqda..."
systemctl stop tezpos-backend 2>/dev/null || true
cp -a "$CURRENT" "$LIVE"
chown tezpos:tezpos "$LIVE"
chmod 640 "$LIVE"
systemctl start tezpos-backend

git pull 2>/dev/null || true

echo ""
echo "==> Sep 2 backup tannarx (kutilgan ~1.7 mlrd)"
sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom --backup-db "$SEP2"

echo ""
echo "==> Qoldiqlar tiklanmoqda (dry-run)..."
sudo bash deploy/restore-stock-from-backup-db.sh "$SEP2"

if [[ "${1:-}" == "--apply" ]]; then
  echo ""
  echo "==> APPLY..."
  sudo bash deploy/restore-stock-from-backup-db.sh "$SEP2" --apply
  echo ""
  sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom
  echo ""
  echo "TAYYOR. POS da Sinxron bosing."
else
  echo ""
  echo "Tasdiqlash:"
  echo "  sudo bash deploy/finish-contabo-sep2.sh --apply"
fi
