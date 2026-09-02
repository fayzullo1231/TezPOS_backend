#!/bin/bash
# kuloloptom: barcha qoldiqni 2026-09-02 14:40 holatiga qaytarish
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

AT="${AT:-2026-09-02 14:40}"
TENANT="${TENANT:-kuloloptom}"
PY="./venv/bin/python"

if [[ "${1:-}" == "--apply" ]]; then
  echo "==> Barcha qoldiq qaytarilmoqda: $AT ($TENANT)"
  sudo -u tezpos $PY manage.py restore_all_stock_at --at "$AT" --tenant "$TENANT"
  echo ""
  echo "TAYYOR. POS da Sinxron bosing."
  exit 0
fi

echo "==> Dry-run: $AT ($TENANT)"
sudo -u tezpos $PY manage.py restore_all_stock_at --at "$AT" --tenant "$TENANT" --dry-run
echo ""
echo "Tasdiqlash:"
echo "  sudo bash deploy/restore-stock-at-1440.sh --apply"
