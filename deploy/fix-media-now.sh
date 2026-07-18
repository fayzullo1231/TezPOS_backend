#!/bin/bash
# Bir martalik: urls.py ni GitHubdan olib, media serve ni yoqish
# Contabo: sudo bash /tmp/fix-media-now.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
URL="https://raw.githubusercontent.com/fayzullo1231/TezPOS_backend/main/tezpos/urls.py"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Root: sudo bash $0"
  exit 1
fi

cd "$INSTALL_DIR"
echo "==> urls.py yuklanmoqda..."
curl -fsSL "$URL" -o tezpos/urls.py
chown tezpos:tezpos tezpos/urls.py 2>/dev/null || true

echo "==> urls.py da serve bormi?"
grep -n "django.views.static import serve\|media/(?P<path>" tezpos/urls.py || {
  echo "XATO: serve topilmadi"
  exit 1
}

echo "==> media papka:"
ls -la media 2>/dev/null || echo "(media yo'q)"
find media -type f 2>/dev/null | head -n 5 || true

systemctl restart tezpos-backend
sleep 1

echo "==> Tekshiruv:"
curl -sI "http://127.0.0.1:8000/media/does-not-exist.jpg" | head -n 5
SAMPLE="$(find media -type f 2>/dev/null | head -n 1 || true)"
if [[ -n "$SAMPLE" ]]; then
  REL="${SAMPLE#media/}"
  echo "Namuna fayl: /media/$REL"
  curl -sI "http://127.0.0.1:8000/media/$REL" | head -n 5
fi

echo "Tayyor."
