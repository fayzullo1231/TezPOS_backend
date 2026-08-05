#!/bin/bash
# Contabo VPS da tez-pos.uz uchun nginx ni darhol yoqish
# Ishlatish (serverda):
#   sudo bash /opt/tezpos-backend/deploy/fix-domain-check-now.sh
# yoki:
#   curl -fsSL -o /tmp/fix-domain-check-now.sh https://raw.githubusercontent.com/fayzullo1231/TezPOS_backend/main/deploy/fix-domain-check-now.sh
#   sudo bash /tmp/fix-domain-check-now.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN_SETUP="${SCRIPT_DIR}/setup-domain-tez-pos.sh"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Root kerak: sudo bash $0"
  exit 1
fi

echo "==> DNS:"
dig +short tez-pos.uz || true
echo "==> Portlar (hozir):"
ss -tulpn | grep -E ':80|:443|:8000' || true
echo ""

if [[ -f "$DOMAIN_SETUP" ]]; then
  bash "$DOMAIN_SETUP"
else
  echo "setup-domain-tez-pos.sh topilmadi — to'liq repo kerak (/opt/tezpos-backend/deploy)"
  exit 1
fi

echo ""
echo "==> Tashqi tekshiruv (serverdan):"
curl -sI --max-time 5 "http://127.0.0.1/check/xusanuz/1/" -H "Host: tez-pos.uz" | head -n 3 || true
curl -sI --max-time 5 "http://tez-pos.uz/check/xusanuz/1/" | head -n 3 || true
