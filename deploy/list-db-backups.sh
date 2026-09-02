#!/bin/bash
# Barcha tezpos.db zaxiralarini ko'rsatish (sotuvlar soni bilan)
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
PY="${INSTALL_DIR}/venv/bin/python3"

db_stats() {
  local f="$1"
  if [[ -x "$PY" ]]; then
    "$PY" - "$f" <<'PY'
import sqlite3, sys
path = sys.argv[1]
try:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = c.cursor()
    sales = "?"
    neg = "?"
    tannarx = "?"
    for tbl in ("sales_sale",):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE status='completed'")
            sales = str(cur.fetchone()[0])
            break
        except sqlite3.OperationalError:
            pass
    for tbl in ("catalog_product", "products_product"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE CAST(quantity AS REAL) < 0")
            neg = str(cur.fetchone()[0])
            break
        except sqlite3.OperationalError:
            pass
    for tbl in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT SUM(CAST(quantity AS REAL)*CAST(cost_price AS REAL)) "
                f"FROM {tbl} WHERE is_active=1 OR is_active IS NULL"
            )
            v = cur.fetchone()[0]
            tannarx = str(int(v or 0))
            break
        except sqlite3.OperationalError:
            pass
    print(f"{sales}|{neg}|{tannarx}")
    c.close()
except Exception:
    print("?|?|?")
PY
  elif command -v sqlite3 >/dev/null 2>&1; then
    local sales neg
    sales=$(sqlite3 "$f" "SELECT COUNT(*) FROM sales_sale WHERE status='completed'" 2>/dev/null || echo "?")
    neg=$(sqlite3 "$f" "SELECT COUNT(*) FROM catalog_product WHERE CAST(quantity AS REAL) < 0" 2>/dev/null || echo "?")
    echo "${sales}|${neg}|?"
  else
    echo "?|?|?"
  fi
}

echo "=== tezpos.db zaxiralari (sotuv | minus | tannarx | hajm | sana | yo'l) ==="
echo ""

declare -A seen=()
while IFS= read -r -d '' f; do
  inode=$(stat -c '%i' "$f" 2>/dev/null || echo "$f")
  [[ -n "${seen[$inode]:-}" ]] && continue
  seen[$inode]=1

  size=$(du -h "$f" 2>/dev/null | awk '{print $1}')
  mtime=$(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1 || echo "?")
  IFS='|' read -r sales neg tannarx < <(db_stats "$f")
  printf "%6s sotuv | %4s minus | %12s so'm | %6s | %s | %s\n" "$sales" "$neg" "$tannarx" "$size" "$mtime" "$f"
done < <(
  find /opt/tezpos-backend/data /opt/tezpos-backend /root /var/backups /home -name 'tezpos.db*' -type f -print0 2>/dev/null \
    | sort -z -u
)

echo ""
echo "Joriy server bazasi (Django):"
if [[ -x "$PY" ]] && [[ -f "$INSTALL_DIR/manage.py" ]]; then
  sudo -u tezpos bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py shell -c \"
from apps.sales.models import Sale
from apps.catalog.models import Product
print('  Sotuvlar:', Sale.objects.filter(status='completed').count())
print('  Minus qoldiq:', Product.objects.filter(quantity__lt=0).count())
print('  Mahsulotlar:', Product.objects.filter(is_active=True).count())
\"" 2>/dev/null || echo "  (Django tekshiruvi xato — xizmat ishlayaptimi?)"
fi

echo ""
echo "Sep 2 eng yuqori qoldiq:"
echo "  sudo bash deploy/restore-sep2-peak.sh"
echo "  sudo bash deploy/restore-sep2-peak.sh --apply"
echo ""
echo "Contabo Sep 2 12:43 (1.7 mlrd):"
echo "  sudo bash deploy/prepare-contabo-sep2.sh"
echo "  -> Contabo Restore -> sudo bash deploy/finish-contabo-sep2.sh --apply"
