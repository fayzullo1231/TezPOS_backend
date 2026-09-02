#!/bin/bash
# SQLite backup tannarxini o'qish (root fayllar uchun ham)
backup_tannarx() {
  local f="$1"
  "${INSTALL_DIR:-/opt/tezpos-backend}/venv/bin/python3" - "$f" <<'PY'
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
            print(int(cur.fetchone()[0] or 0))
            break
        except sqlite3.OperationalError:
            continue
    else:
        print(0)
    c.close()
except Exception:
    print(0)
PY
}
