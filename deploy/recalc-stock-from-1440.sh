#!/bin/bash
# 14:40 (Toshkent) dan hozirgacha qoldiqni qayta hisoblash
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

ANCHOR="${ANCHOR:-2026-09-02 14:40}"
PY="./venv/bin/python"

if [[ "${1:-}" == "--apply" ]]; then
  echo "==> Qoldiq yangilanmoqda (anchor: $ANCHOR)..."
  sudo -u tezpos $PY manage.py recalc_stock_from_ledger --anchor "$ANCHOR"
  echo ""
  echo "Tayyor. POS da Sinxron bosing."
  exit 0
fi

echo "==> Dry-run (anchor: $ANCHOR)..."
sudo -u tezpos $PY manage.py recalc_stock_from_ledger --anchor "$ANCHOR" --dry-run --only-changed
echo ""
echo "Tasdiqlash:"
echo "  sudo bash deploy/recalc-stock-from-1440.sh --apply"
echo "Boshqa vaqt:"
echo "  ANCHOR='2026-09-02 12:40' sudo bash deploy/recalc-stock-from-1440.sh --apply"
