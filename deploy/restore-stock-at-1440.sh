#!/bin/bash
# DIQQAT: avtomatik tiklash 14:40 da DB zaxirasi yo'qligi sababli 100% aniq emas.
# Tavsiya: deploy/export-stock-csv.sh + qo'lda reviziya
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

AT="${AT:-2026-09-02 14:40}"
TENANT="${TENANT:-kuloloptom}"
METHOD="${METHOD:-unwind}"
PY="./venv/bin/python"

if [[ "${1:-}" == "--apply" ]]; then
  echo "==> Qoldiq tiklash: $AT ($TENANT) method=$METHOD"
  echo "    (Eski reviziya ishlatilmaydi. 100% aniq: export-stock-csv.sh)"
  sudo -u tezpos $PY manage.py restore_all_stock_at --at "$AT" --tenant "$TENANT" --method "$METHOD"
  echo ""
  echo "TAYYOR. POS da Sinxron bosing."
  exit 0
fi

echo "==> Dry-run: $AT ($TENANT) method=$METHOD"
sudo -u tezpos $PY manage.py restore_all_stock_at --at "$AT" --tenant "$TENANT" --method "$METHOD" --dry-run
echo ""
echo "Tasdiqlash:"
echo "  sudo bash deploy/restore-stock-at-1440.sh --apply"
echo ""
echo "100% aniq qoldiq uchun:"
echo "  sudo bash deploy/export-stock-csv.sh"
