#!/bin/bash
# Contabo: baza tozalash API ni yangilash
#   curl -fsSL -o /tmp/fix-reset.sh https://raw.githubusercontent.com/fayzullo1231/TezPOS_backend/main/deploy/fix-reset-now.sh
#   sudo bash /tmp/fix-reset.sh
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
URL="https://raw.githubusercontent.com/fayzullo1231/TezPOS_backend/main/apps/accounts/tenant_reset_views.py"
DEST="$INSTALL_DIR/apps/accounts/tenant_reset_views.py"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "sudo bash $0"
  exit 1
fi

curl -fsSL -o "$DEST" "$URL"
chown root:root "$DEST" 2>/dev/null || true
systemctl restart tezpos-backend
sleep 1
systemctl is-active tezpos-backend && echo "OK: tezpos-backend restart" || echo "FAIL"
echo "Endi ilovadan yana «Baza tozalash» ni sinab ko'ring."
