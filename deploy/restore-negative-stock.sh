#!/bin/bash
# Partiya + davr bo'yicha minus qoldiq (butun tarix EMAS)
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

SINCE="${SINCE:-2026-09-01}"
ARGS=(--since "$SINCE" --reset-from-batches)

for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) ARGS+=(--dry-run) ;;
    --since=*) SINCE="${arg#*=}"; ARGS=(--since "$SINCE" --reset-from-batches) ;;
  esac
done

echo "==> Minus qoldiq: $SINCE dan keyin, partiyalar asosida"
sudo -u tezpos ./venv/bin/python manage.py restore_negative_stock_from_flow "${ARGS[@]}"

if [[ " ${ARGS[*]} " == *" --dry-run "* ]]; then
  echo ""
  echo "Tasdiqlash:"
  echo "  sudo bash deploy/restore-negative-stock.sh"
  echo "Boshqa sana:"
  echo "  SINCE=2026-09-02 sudo bash deploy/restore-negative-stock.sh --dry-run"
fi
