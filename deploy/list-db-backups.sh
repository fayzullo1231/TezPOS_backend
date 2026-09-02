#!/bin/bash
# Barcha tezpos.db zaxiralarini ko'rsatish (sotuvlar soni bilan)
set -euo pipefail

echo "=== tezpos.db zaxiralari (sotuvlar soni | hajm | sana | yo'l) ==="
echo ""

while IFS= read -r -d '' f; do
  size=$(du -h "$f" 2>/dev/null | awk '{print $1}')
  mtime=$(stat -c '%Y %y' "$f" 2>/dev/null | awk '{print $2, $3, $4}' || date -r "$f" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "?")
  sales="?"
  neg="?"
  if command -v sqlite3 >/dev/null 2>&1; then
    sales=$(sqlite3 "$f" "SELECT COUNT(*) FROM sales_sale WHERE status='completed'" 2>/dev/null || echo "?")
    neg=$(sqlite3 "$f" "SELECT COUNT(*) FROM catalog_product WHERE CAST(quantity AS REAL) < 0" 2>/dev/null || echo "?")
  fi
  printf "%6s sotuv | %4s minus | %6s | %s | %s\n" "$sales" "$neg" "$size" "$mtime" "$f"
done < <(find /opt/tezpos-backend/data /opt/tezpos-backend /root /tmp -name 'tezpos.db*' -type f -print0 2>/dev/null | sort -z)

echo ""
echo "To'liq tiklash:"
echo "  sudo bash deploy/restore-sqlite-db.sh /yo'l/eski/tezpos.db"
echo ""
echo "Eng ko'p sotuvli va kerakli sanadagi faylni tanlang."
