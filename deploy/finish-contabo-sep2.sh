#!/bin/bash
# Contabo Sep 2 restore KEYIN — qoldiqni tiklash
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
source deploy/backup-tannarx.sh

SEP2="/root/tezpos_sep2.db"
CURRENT="/root/tezpos_current.db"
LIVE="/opt/tezpos-backend/data/tezpos.db"
MIN_TANNARX="${MIN_TANNARX:-500000000}"

if [[ ! -f "$CURRENT" ]]; then
  echo "XATO: $CURRENT topilmadi."
  echo "Avval: sudo bash deploy/prepare-contabo-sep2.sh"
  exit 1
fi

echo "==> Contabo restore dan snapshot (LIVE -> sep2)..."
cp -a "$LIVE" "$SEP2"
chmod 644 "$SEP2"

SEP2_VAL=$(backup_tannarx "$SEP2")
echo "Sep 2 snapshot tannarx: $(printf "%'d" "$SEP2_VAL") so'm"

if [[ "$SEP2_VAL" -lt "$MIN_TANNARX" ]]; then
  echo ""
  echo "XATO: Tannarx ${SEP2_VAL} — bu 1.7 mlrd emas!"
  echo "Contabo panelda Sep 2, 2026 12:43 backup Restore qilinganini tekshiring."
  echo "Hozirgi LIVE bazada hali buzilgan qoldiq bo'lishi mumkin."
  rm -f "$SEP2"
  exit 1
fi

echo "==> Joriy sotuvlar bazasi qaytarilmoqda ($CURRENT)..."
systemctl stop tezpos-backend 2>/dev/null || true
cp -a "$CURRENT" "$LIVE"
chown tezpos:tezpos "$LIVE"
chmod 640 "$LIVE"
systemctl start tezpos-backend

git pull 2>/dev/null || true

chmod 644 "$SEP2"
echo ""
sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom --backup-db "$SEP2"

echo ""
sudo bash deploy/restore-stock-from-backup-db.sh "$SEP2"

if [[ "${1:-}" == "--apply" ]]; then
  echo ""
  sudo bash deploy/restore-stock-from-backup-db.sh "$SEP2" --apply
  sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom
  echo "TAYYOR. POS Sinxron."
else
  echo ""
  echo "Tasdiqlash: sudo bash deploy/finish-contabo-sep2.sh --apply"
fi
