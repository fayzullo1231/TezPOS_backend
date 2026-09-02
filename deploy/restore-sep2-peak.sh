#!/bin/bash
# 2-sentabr eng yuqori qoldiq — serverdagi backup fayllardan
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"
source deploy/backup-tannarx.sh

echo "=== Zaxiralar ==="
bash deploy/list-db-backups.sh

BEST=""
BEST_VAL=0

while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  [[ "$f" == *"/data/tezpos.db" ]] && continue
  [[ "$f" == *"-shm" || "$f" == *"-wal" ]] && continue
  val=$(backup_tannarx "$f")
  if [[ "${val:-0}" -gt "$BEST_VAL" ]]; then
    BEST_VAL=$val
    BEST=$f
  fi
done < <(find /root /opt/tezpos-backend/data -name 'tezpos*.db' -type f 2>/dev/null | sort -u)

echo ""
if [[ -z "$BEST" || "$BEST_VAL" -lt 100000000 ]]; then
  echo "1.7 mlrd backup topilmadi (eng yuqori: ${BEST_VAL:-0} so'm)."
  echo ""
  echo "Contabo (siz allaqachon prepare qildingiz — keyingi qadam):"
  echo "  Contabo panel -> Sep 2 12:43 -> Restore"
  echo "  SSH qayta: sudo bash deploy/finish-contabo-sep2.sh --apply"
  exit 1
fi

echo "Eng yuqori: $(printf "%'d" "$BEST_VAL") so'm"
echo "Fayl: $BEST"
chmod 644 "$BEST" 2>/dev/null || true

sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom --backup-db "$BEST"

if [[ "${1:-}" == "--apply" ]]; then
  sudo bash deploy/restore-stock-from-backup-db.sh "$BEST" --apply
  sudo -u tezpos $PY manage.py stock_value_summary --tenant kuloloptom
  echo "TAYYOR. POS Sinxron."
else
  echo "Tasdiqlash: sudo bash deploy/restore-sep2-peak.sh --apply"
fi
