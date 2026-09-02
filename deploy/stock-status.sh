#!/bin/bash
# Qoldiq holati — tez diagnostika
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
source deploy/backup-tannarx.sh 2>/dev/null || true

echo "=== KULOLOPTOM QOLDIQ ==="
sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom

echo ""
echo "=== SERVER ZAXIRALARI ==="
bash deploy/list-db-backups.sh

echo ""
echo "=== TEKSHIRUV ==="
for f in /root/tezpos_sep2.db /root/tezpos_current.db /root/tezpos_current_*.db; do
  [[ -f "$f" ]] || continue
  v=$(backup_tannarx "$f" 2>/dev/null || echo 0)
  echo "  $(basename "$f"): $(printf "%'d" "$v") so'm"
done

echo ""
if [[ -f /root/tezpos_sep2.db ]]; then
  v=$(backup_tannarx /root/tezpos_sep2.db)
  if [[ "$v" -lt 500000000 ]]; then
    echo "DIQQAT: tezpos_sep2.db noto'g'ri ($(printf "%'d" "$v") so'm) — Contabo restore qilinmagan."
    echo "  rm /root/tezpos_sep2.db"
    echo "  Contabo panel -> Sep 2 12:43 Restore"
    echo "  sudo bash deploy/finish-contabo-sep2.sh --apply"
  fi
else
  echo "tezpos_sep2.db yo'q — Contabo restore kerak."
fi
