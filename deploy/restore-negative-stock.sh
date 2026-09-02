#!/bin/bash
# Kirim/sotuv tarixidan minus qoldiqlarni tiklash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

DRY="${1:-}"
ARGS=()
if [[ "$DRY" == "--dry-run" || "$DRY" == "-n" ]]; then
  ARGS+=(--dry-run)
fi

echo "==> Minus qoldiq hisoblash (kirim - sotuv + qaytarish)..."
sudo -u tezpos ./venv/bin/python manage.py restore_negative_stock_from_flow "${ARGS[@]}"

if [[ " ${ARGS[*]} " == *" --dry-run "* ]]; then
  echo ""
  echo "Natija yoqdi. Tasdiqlash uchun:"
  echo "  sudo bash deploy/restore-negative-stock.sh"
fi
