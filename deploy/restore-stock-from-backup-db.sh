#!/bin/bash
# Contabo backup dan olingan eski tezpos.db dan FAQAT qoldiqlarni tiklash.
# Sotuvlar/chekalar joriy bazada qoladi.
#
# Oldin:
#   1) Joriy bazani kompyuterga saqlang (scp)
#   2) Contabo: Sep 2 backup (12:43) dan tezpos.db ni oling
#   3) Bu faylni serverga yuklang: /root/tezpos_sep2.db
#
# Ishlatish:
#   sudo bash deploy/restore-stock-from-backup-db.sh /root/tezpos_sep2.db
#   sudo bash deploy/restore-stock-from-backup-db.sh /root/tezpos_sep2.db --apply
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"

SRC="${1:-/root/tezpos_sep2.db}"
PY="./venv/bin/python"

if [[ ! -f "$SRC" ]]; then
  echo "Xato: backup DB topilmadi: $SRC"
  echo ""
  echo "Contabo backup dan tezpos.db olish:"
  echo "  1) Joriy bazani saqlang: scp root@SERVER:/opt/tezpos-backend/data/tezpos.db ./tezpos_current.db"
  echo "  2) Contabo panel: Sep 2 12:43 backup -> Restore (butun server)"
  echo "  3) Eski bazani yuklab oling: scp root@SERVER:/opt/tezpos-backend/data/tezpos.db ./tezpos_sep2.db"
  echo "  4) Joriy bazani qaytaring: scp ./tezpos_current.db root@SERVER:/opt/tezpos-backend/data/tezpos.db"
  echo "  5) systemctl restart tezpos-backend"
  echo "  6) sudo bash deploy/restore-stock-from-backup-db.sh /root/tezpos_sep2.db --apply"
  exit 1
fi

chmod 644 "$SRC" 2>/dev/null || true

echo "==> Qoldiq tiklash (faqat quantity): $SRC"
if [[ "${2:-}" == "--apply" ]]; then
  sudo -u tezpos $PY manage.py restore_stock_from_sqlite "$SRC"
else
  sudo -u tezpos $PY manage.py restore_stock_from_sqlite "$SRC" --dry-run
  echo ""
  echo "Tasdiqlash:"
  echo "  sudo bash deploy/restore-stock-from-backup-db.sh $SRC --apply"
fi
