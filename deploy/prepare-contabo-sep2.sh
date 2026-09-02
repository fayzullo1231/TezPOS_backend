#!/bin/bash
# Contabo restore OLDIN — joriy bazani saqlash (server ichida, scp KERAK EMAS)
set -euo pipefail

DST="/root/tezpos_current_$(date +%Y%m%d_%H%M%S).db"
SRC="/opt/tezpos-backend/data/tezpos.db"

if [[ ! -f "$SRC" ]]; then
  echo "Xato: $SRC topilmadi"
  exit 1
fi

cp -a "$SRC" "$DST"
ln -sf "$(basename "$DST")" /root/tezpos_current.db
echo "SAQLANDI: $DST"
echo "         -> /root/tezpos_current.db (link)"
echo ""
echo "KEYINGI QADAM (Contabo panel):"
echo "  1) Auto Backup -> Sep 2, 2026 12:43 -> Restore"
echo "  2) Server qayta yuklangach SSH qiling"
echo "  3) sudo bash deploy/finish-contabo-sep2.sh"
