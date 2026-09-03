#!/bin/bash
# Faqat bitta tenant narxlarini zaxira DBdan tiklash (qoldiqga tegmaydi)
#   sudo bash deploy/restore-prices-one-tenant.sh /root/tezpos_prices.db kuloloptom-2
#   sudo bash deploy/restore-prices-one-tenant.sh /root/tezpos_prices.db kuloloptom-2 --apply
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
cd "$INSTALL_DIR"
PY="./venv/bin/python"

SRC="${1:-}"
TENANT="${2:-}"
MODE="${3:-}"

if [[ -z "$SRC" || -z "$TENANT" ]]; then
  echo "Ishlatish:"
  echo "  sudo bash deploy/restore-prices-one-tenant.sh /yo'l/backup.db kuloloptom-2"
  echo "  sudo bash deploy/restore-prices-one-tenant.sh /yo'l/backup.db kuloloptom-2 --apply"
  echo ""
  echo "Tenantlar:"
  sudo -u tezpos $PY manage.py shell -c "
from apps.accounts.models import Tenant
for t in Tenant.objects.order_by('server_name'):
    print(' ', t.server_name)
" 2>/dev/null || true
  exit 1
fi

if [[ ! -f "$SRC" ]]; then
  echo "Xato: $SRC topilmadi"
  exit 1
fi

chmod 644 "$SRC" 2>/dev/null || true

if [[ "$MODE" == "--apply" ]]; then
  sudo -u tezpos $PY manage.py restore_prices_from_sqlite "$SRC" --tenant "$TENANT"
else
  sudo -u tezpos $PY manage.py restore_prices_from_sqlite "$SRC" --tenant "$TENANT" --dry-run
  echo ""
  echo "Tasdiqlash: sudo bash deploy/restore-prices-one-tenant.sh $SRC $TENANT --apply"
fi
