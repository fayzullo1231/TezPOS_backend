#!/bin/bash
# Qoldiqni ombor jurnalidan qayta hisoblash
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

ARGS=()
for a in "$@"; do ARGS+=("$a"); done
if [[ ${#ARGS[@]} -eq 0 ]]; then
  ARGS=(--dry-run)
  echo "Avval dry-run. Tasdiqlash: sudo bash deploy/recalc-stock-ledger.sh --apply"
fi
if [[ "${1:-}" == "--apply" ]]; then
  ARGS=()
fi

sudo -u tezpos ./venv/bin/python manage.py recalc_stock_from_ledger "${ARGS[@]}"
