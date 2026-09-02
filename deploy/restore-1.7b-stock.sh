#!/bin/bash
# 1.7 mlrd tannarx jami — Contabo Sep 2 backup dan qoldiqni tiklash
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

TENANT="${TENANT:-kuloloptom}"
BACKUP_DB="${BACKUP_DB:-/root/tezpos_sep2.db}"
BACKUP_AT="${BACKUP_AT:-2026-09-02 12:43}"
ANCHOR="${ANCHOR:-2026-09-02 14:40}"
PY="./venv/bin/python"

echo "==> Hozirgi ombor qiymati"
sudo -u tezpos $PY manage.py stock_value_summary --tenant "$TENANT"

if [[ ! -f "$BACKUP_DB" ]]; then
  echo ""
  echo "XATO: Contabo backup topilmadi: $BACKUP_DB"
  echo ""
  echo "QADAMLAR:"
  echo "  1) scp root@SERVER:/opt/tezpos-backend/data/tezpos.db ./tezpos_current.db"
  echo "  2) Contabo panel: Sep 2 backup (12:43) -> Restore"
  echo "  3) scp root@SERVER:/opt/tezpos-backend/data/tezpos.db ./tezpos_sep2.db"
  echo "  4) scp ./tezpos_current.db root@SERVER:/opt/tezpos-backend/data/tezpos.db"
  echo "  5) scp ./tezpos_sep2.db root@SERVER:$BACKUP_DB"
  echo "  6) sudo bash deploy/restore-1.7b-stock.sh --apply"
  exit 1
fi

echo ""
echo "==> Backup ombor qiymati (kutilgan ~1.7 mlrd)"
sudo -u tezpos $PY manage.py stock_value_summary --tenant "$TENANT" --backup-db "$BACKUP_DB"

if [[ "${1:-}" != "--apply" ]]; then
  echo ""
  echo "Tasdiqlash (14:40 holatiga tiklash):"
  echo "  sudo bash deploy/restore-1.7b-stock.sh --apply"
  exit 0
fi

echo ""
echo "==> Qoldiq tiklanmoqda: backup $BACKUP_AT -> anchor $ANCHOR"
sudo -u tezpos $PY manage.py restore_all_stock_at \
  --tenant "$TENANT" \
  --at "$ANCHOR" \
  --method backup \
  --backup-db "$BACKUP_DB" \
  --backup-at "$BACKUP_AT"

echo ""
echo "==> Tiklangan ombor qiymati"
sudo -u tezpos $PY manage.py stock_value_summary --tenant "$TENANT"
echo ""
echo "TAYYOR. POS da Sinxron bosing."
