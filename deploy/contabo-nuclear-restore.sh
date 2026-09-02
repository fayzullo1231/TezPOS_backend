#!/bin/bash
# Contabo Sep 2 restore — BUTUN bazani saqlash (qoldiq to'g'ri, 12:43 dan keyingi sotuvlar yo'qoladi)
#
# FAQAT shu holatda: finish-contabo-sep2 ishlamasa yoki sotuvlar muhim emas bo'lsa.
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
source deploy/backup-tannarx.sh

LIVE="/opt/tezpos-backend/data/tezpos.db"
VAL=$(backup_tannarx "$LIVE")

echo "Hozirgi LIVE tannarx: $(printf "%'d" "$VAL") so'm"

if [[ "$VAL" -lt 500000000 ]]; then
  echo ""
  echo "XATO: Bu hali Contabo restore emas (1.7 mlrd emas)."
  echo "Contabo panel -> Sep 2 12:43 -> Restore qiling, keyin qayta ishga tushiring."
  exit 1
fi

echo ""
echo "==> Contabo bazasi saqlanmoqda (sotuvlar 12:43 holatida qoladi)"
bash deploy/fix-sqlite-env.sh 2>/dev/null || true
sudo -u tezpos $PY manage.py migrate --noinput
systemctl restart tezpos-backend

sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom
echo ""
echo "TAYYOR. POS Sinxron. (12:43 dan keyingi cheklar yo'q — bu normal)"
