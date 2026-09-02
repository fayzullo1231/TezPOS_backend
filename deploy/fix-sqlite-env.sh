#!/bin/bash
# .env ni SQLite uchun to'g'rilash (PostgreSQL xatosi bo'lmasin)
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
ENV_FILE="$INSTALL_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Xato: $ENV_FILE topilmadi"
  exit 1
fi

cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"

# Eski USE_SQLITE o'chirish — endi DB_ENGINE ishlatiladi
sed -i '/^USE_SQLITE=/d' "$ENV_FILE"
sed -i '/^DB_ENGINE=postgresql/d' "$ENV_FILE"
grep -q '^DB_ENGINE=' "$ENV_FILE" \
  && sed -i 's|^DB_ENGINE=.*|DB_ENGINE=sqlite|' "$ENV_FILE" \
  || echo "DB_ENGINE=sqlite" >> "$ENV_FILE"

echo "OK: DB_ENGINE=sqlite"
grep '^DB_ENGINE=' "$ENV_FILE"
