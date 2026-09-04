#!/bin/bash
# Contabo dan 3-sentabr (yoki 4-sentabr ertalab) backup olish OLDIN
# Faqat narxlar uchun — joriy bazani saqlaydi
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
echo "         -> /root/tezpos_current.db"
echo ""
echo "KEYINGI QADAM (Contabo panel — brauzer):"
echo "  1) Auto Backup oching"
echo "  2) ENG YAXSHI: Sep 4 backup (Available) -> Restore"
echo "     (3-sentabr oxiri + 4-sentabr ertalab holati)"
echo "     YO'Q BO'LSA: Sep 3, 13:11 (BU-ff2c3bcd) -> Restore"
echo "  3) Server qayta ochilgach SSH:"
echo "     cd /opt/tezpos-backend && git pull"
echo "     sudo bash deploy/finish-contabo-prices-sep3.sh"
echo ""
echo "DIQQAT: Contabo Restore VPS ni vaqtincha eski holatga qaytaradi."
echo "finish skript joriy sotuvlar bazasini qaytaradi, faqat kuloloptom-2 NARXINI oladi."
