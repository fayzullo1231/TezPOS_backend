#!/bin/bash
# Reviziya: mahsulotlarni CSV ga eksport
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

TENANT="${TENANT:-kuloloptom}"
OUT="${OUT:-/tmp/qoldiq.csv}"
PY="./venv/bin/python"

echo "==> Eksport: $OUT ($TENANT)"
sudo -u tezpos $PY manage.py export_stock_csv --tenant "$TENANT" -o "$OUT"
echo ""
echo "1) $OUT ni kompyuterga yuklab oling"
echo "2) yangi_qoldiq ustunini to'ldiring (do'konda sanab)"
echo "3) Serverga qayta yuklang va:"
echo "   sudo -u tezpos $PY manage.py set_product_stock --csv $OUT --dry-run"
echo "   sudo -u tezpos $PY manage.py set_product_stock --csv $OUT"
