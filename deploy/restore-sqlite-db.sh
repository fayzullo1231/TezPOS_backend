#!/bin/bash
# Eski tezpos.db ni tiklash
# Ishlatish: sudo bash deploy/restore-sqlite-db.sh /yo'l/eski/tezpos.db
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
SERVICE_USER="${SERVICE_USER:-tezpos}"
DATA_DIR="$INSTALL_DIR/data"
TARGET="$DATA_DIR/tezpos.db"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "sudo bilan ishga tushiring"
  exit 1
fi

BACKUP_SRC="${1:-}"
if [[ -z "$BACKUP_SRC" || ! -f "$BACKUP_SRC" ]]; then
  echo "Eski bazani topish..."
  for candidate in \
    "$DATA_DIR/tezpos.db.bak" \
    "$DATA_DIR/tezpos.db.backup" \
    "/root/tezpos.db" \
    "/root/tezpos.db.bak" \
    "/root/settings.py.bak/../data/tezpos.db"; do
    if [[ -f "$candidate" ]]; then
      BACKUP_SRC="$candidate"
      break
    fi
  done
fi

if [[ -z "$BACKUP_SRC" || ! -f "$BACKUP_SRC" ]]; then
  echo "Xato: eski tezpos.db topilmadi."
  echo "Ishlatish: sudo bash deploy/restore-sqlite-db.sh /to'liq/yo'l/tezpos.db"
  echo ""
  echo "Qidiruv:"
  find /opt/tezpos-backend /root -name 'tezpos.db*' -type f 2>/dev/null | head -20
  exit 1
fi

echo "==> .env SQLite"
bash "$INSTALL_DIR/deploy/fix-sqlite-env.sh"

echo "==> Zaxira: joriy baza"
mkdir -p "$DATA_DIR"
if [[ -f "$TARGET" ]]; then
  cp -a "$TARGET" "$TARGET.before-restore.$(date +%Y%m%d_%H%M%S)"
fi

echo "==> Tiklash: $BACKUP_SRC -> $TARGET"
systemctl stop tezpos-backend 2>/dev/null || true
cp -a "$BACKUP_SRC" "$TARGET"
chown "$SERVICE_USER:$SERVICE_USER" "$TARGET"
chmod 640 "$TARGET"

echo "==> Migratsiya (sxema yangilansa, ma'lumot saqlanadi)"
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py migrate --noinput"

echo "==> Qoldiqlar (namuna 5 ta):"
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py shell -c \"
from apps.catalog.models import Product
for p in Product.objects.filter(is_active=True).order_by('-updated_at')[:5]:
    print(p.name[:40], '=>', p.quantity)
print('Jami:', Product.objects.filter(is_active=True).count(), 'ta mahsulot')
\""

systemctl start tezpos-backend
echo ""
echo "TAYYOR. POS da Sinxron tugmasini bosing yoki dasturni qayta oching."
