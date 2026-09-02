#!/bin/bash
# Qoldiqni avtomatik tiklash — bitta buyruq
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
TENANT="${TENANT:-kuloloptom}"
source deploy/backup-tannarx.sh 2>/dev/null || true

echo "=========================================="
echo "  QOLDIQ TIKLASH (kuloloptom)"
echo "=========================================="

git pull -q 2>/dev/null || true

# Contabo sep2 + current bo'lsa — hybrid tiklash
if [[ -f /root/tezpos_sep2.db && -f /root/tezpos_current.db ]]; then
  SEP2_VAL=$(backup_tannarx /root/tezpos_sep2.db 2>/dev/null || echo 0)
  if [[ "${SEP2_VAL:-0}" -ge 500000000 ]]; then
    echo "==> Contabo zaxira topildi ($(printf "%'d" "$SEP2_VAL") so'm)"
    if YES=1 bash deploy/finish-contabo-sep2.sh --apply; then
      echo "TAYYOR (Contabo). POS Sinxron."
      exit 0
    fi
  fi
fi

echo "==> Barcha zaxiralar solishtirilmoqda..."
sudo -u tezpos $PY manage.py restore_best_stock --tenant "$TENANT" --strategy auto

echo ""
echo "==> Partiyalar moslashtirilmoqda..."
sudo -u tezpos $PY manage.py rebuild_stock_batches --tenant "$TENANT"

echo ""
echo "==> Natija:"
sudo -u tezpos $PY manage.py stock_value_summary --tenant "$TENANT"

FINAL=$(backup_tannarx /opt/tezpos-backend/data/tezpos.db 2>/dev/null || echo 0)
echo ""
if [[ "${FINAL:-0}" -lt 500000000 ]]; then
  echo "DIQQAT: Tannarx hali past ($(printf "%'d" "$FINAL") so'm)."
  echo "1.7 mlrd uchun Contabo panel -> Sep 2 12:43 -> Restore"
  echo "Keyin: sudo bash deploy/finish-contabo-sep2.sh --apply"
else
  echo "TAYYOR. POS da Sinxron tugmasini bosing."
fi
