#!/bin/bash
# 2-sentabr eng yuqori qoldiq — mavjud backup fayllarni qidiradi va tiklaydi
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"

echo "=== Serverdagi barcha tezpos.db zaxiralari (tannarx bilan) ==="
bash deploy/list-db-backups.sh

BEST=""
BEST_VAL=0

while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  [[ "$f" == *"/data/tezpos.db" ]] && continue
  val=$(sudo -u tezpos "$PY" - "$f" <<'PY'
import sqlite3, sys
path = sys.argv[1]
try:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = c.cursor()
    for tbl in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT SUM(CAST(quantity AS REAL)*CAST(cost_price AS REAL)) "
                f"FROM {tbl} WHERE is_active=1 OR is_active IS NULL"
            )
            v = cur.fetchone()[0] or 0
            print(int(v))
            break
        except sqlite3.OperationalError:
            continue
    else:
        print(0)
    c.close()
except Exception:
    print(0)
PY
)
  if [[ "${val:-0}" -gt "$BEST_VAL" ]]; then
    BEST_VAL=$val
    BEST=$f
  fi
done < <(find /root /opt/tezpos-backend/data -name 'tezpos*.db' -type f 2>/dev/null | sort -u)

echo ""
if [[ -z "$BEST" || "$BEST_VAL" -lt 100000000 ]]; then
  echo "1.7 mlrd backup topilmadi (eng yuqori: ${BEST_VAL:-0} so'm)."
  echo ""
  echo "Contabo yo'li (server ichida, scp yo'q):"
  echo "  sudo bash deploy/prepare-contabo-sep2.sh"
  echo "  -> Contabo panel: Sep 2 12:43 Restore"
  echo "  sudo bash deploy/finish-contabo-sep2.sh --apply"
  exit 1
fi

echo "Eng yuqori tannarx: $(printf "%'d" "$BEST_VAL") so'm"
echo "Fayl: $BEST"
echo ""

sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom --backup-db "$BEST"

if [[ "${1:-}" == "--apply" ]]; then
  sudo bash deploy/restore-stock-from-backup-db.sh "$BEST" --apply
  sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom
  echo "TAYYOR. POS Sinxron."
else
  echo "Tasdiqlash:"
  echo "  sudo bash deploy/restore-sep2-peak.sh --apply"
fi
