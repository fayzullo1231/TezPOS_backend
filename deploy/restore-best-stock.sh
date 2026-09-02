#!/bin/bash
# Barcha zaxiralarni solishtir, eng ko'p qoldiqlisidan tikla
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
TENANT="${TENANT:-kuloloptom}"
STRATEGY="${STRATEGY:-max-qty}"

echo "==> Manbalar solishtirilmoqda..."
sudo -u tezpos $PY manage.py restore_best_stock --tenant "$TENANT" --strategy "$STRATEGY" --dry-run

if [[ "${1:-}" == "--apply" ]]; then
  echo ""
  if [[ "${YES:-}" != "1" ]]; then
    read -r -p "Tasdiqlaysizmi? [y/N] " ans
    if [[ "${ans,,}" != "y" && "${ans,,}" != "yes" ]]; then
      echo "Bekor qilindi."
      exit 0
    fi
  fi
  sudo -u tezpos $PY manage.py restore_best_stock --tenant "$TENANT" --strategy "$STRATEGY"
  sudo -u tezpos $PY manage.py stock_value_summary --tenant "$TENANT"
  echo "TAYYOR. POS Sinxron."
else
  echo ""
  echo "Tasdiqlash:"
  echo "  sudo bash deploy/restore-best-stock.sh --apply"
  echo ""
  echo "Butun eng yuqori fayldan (max emas):"
  echo "  STRATEGY=best-file sudo bash deploy/restore-best-stock.sh --apply"
fi
