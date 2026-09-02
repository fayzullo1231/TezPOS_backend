#!/bin/bash
# 02.09.2026 14:40 holatiga qoldiqni qaytarish
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

AT="${AT:-2026-09-02 14:40}"
TENANT="${TENANT:-kuloloptom}"
BACKUP_DB="${BACKUP_DB:-/root/tezpos_sep2.db}"
BACKUP_AT="${BACKUP_AT:-2026-09-02 12:43}"
PY="./venv/bin/python"

EXTRA_ARGS=()
if [[ -f "$BACKUP_DB" ]]; then
  echo "==> Contabo backup topildi: $BACKUP_DB"
  EXTRA_ARGS+=(--method backup --backup-db "$BACKUP_DB" --backup-at "$BACKUP_AT")
else
  echo "==> Backup yo'q — unwind usuli (14:40 dan keyingi sotuvlar asosida)"
  echo "    Aniqroq: Contabo Sep 2 backup dan tezpos.db ni /root/tezpos_sep2.db ga qo'ying"
  EXTRA_ARGS+=(--method unwind)
fi

if [[ "${1:-}" == "--apply" ]]; then
  echo "==> Qoldiq tiklash: $AT ($TENANT)"
  sudo -u tezpos $PY manage.py restore_all_stock_at \
    --at "$AT" --tenant "$TENANT" "${EXTRA_ARGS[@]}"
  echo ""
  echo "TAYYOR. POS da Sinxron bosing."
  exit 0
fi

echo "==> Dry-run: $AT ($TENANT)"
sudo -u tezpos $PY manage.py restore_all_stock_at \
  --at "$AT" --tenant "$TENANT" --dry-run "${EXTRA_ARGS[@]}"
echo ""
echo "Tasdiqlash:"
echo "  sudo bash deploy/restore-stock-at-1440.sh --apply"
