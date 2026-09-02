#!/bin/bash
# Barcha vaqt/zaxira qoldiqlarini CSV ga eksport
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
TENANT="${TENANT:-kuloloptom}"
OUT="${OUT:-/tmp/barcha_qoldiq.csv}"
SUMMARY="${SUMMARY:-/tmp/qoldiq_manbalar.csv}"

git pull -q 2>/dev/null || true

echo "==> Barcha qoldiqlar eksport qilinmoqda..."
sudo -u tezpos $PY manage.py export_all_stock_snapshots \
  --tenant "$TENANT" \
  -o "$OUT" \
  --summary "$SUMMARY"

echo ""
echo "Fayllar:"
echo "  $OUT          — barcha mahsulot + har zaxira ustuni"
echo "  $SUMMARY      — qaysi ustun qaysi fayl/vaqt"
echo ""
echo "Kompyuterga yuklab olish:"
echo "  scp root@SERVER:$OUT ."
echo ""
echo "Tanlaganingizdan keyin serverga qaytarish:"
echo "  scp ./barcha_qoldiq.csv root@SERVER:$OUT"
echo "  sudo -u tezpos $PY manage.py set_product_stock --csv $OUT --dry-run"
echo "  sudo -u tezpos $PY manage.py set_product_stock --csv $OUT"
