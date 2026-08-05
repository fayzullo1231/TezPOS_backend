#!/bin/bash
# Django admin CSS/JS tuzatish (WhiteNoise + collectstatic)
# Serverda: sudo bash deploy/fix-admin-static.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
SERVICE_USER="${SERVICE_USER:-tezpos}"
NO_RESTART=false
for arg in "$@"; do
    [[ "$arg" == "--no-restart" ]] && NO_RESTART=true
done

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Root sifatida ishga tushiring: sudo bash deploy/fix-admin-static.sh"
    exit 1
fi

if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "Xato: $INSTALL_DIR topilmadi"
    exit 1
fi

cd "$INSTALL_DIR"

echo "==> WhiteNoise o'rnatilmoqda..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q 'whitenoise>=6.6,<7.0'

echo "==> settings.py yangilanmoqda..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/python" - <<'PY'
from pathlib import Path

path = Path("tezpos/settings.py")
text = path.read_text(encoding="utf-8")
changed = False

if "whitenoise.middleware.WhiteNoiseMiddleware" not in text:
    needle = '"django.middleware.security.SecurityMiddleware",\n'
    if needle in text:
        text = text.replace(
            needle,
            needle + '    "whitenoise.middleware.WhiteNoiseMiddleware",\n',
            1,
        )
        changed = True
    else:
        raise SystemExit("SecurityMiddleware topilmadi — settings.py qo'lda tekshiring")

if 'STATIC_URL = "static/"' in text:
    text = text.replace('STATIC_URL = "static/"', 'STATIC_URL = "/static/"', 1)
    changed = True

if "STORAGES" not in text and "STATIC_ROOT" in text:
    text = text.replace(
        "STATIC_ROOT = BASE_DIR / \"staticfiles\"\n",
        """STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
""",
        1,
    )
    changed = True

if changed:
    path.write_text(text, encoding="utf-8")
    print("settings.py yangilandi")
else:
    print("settings.py allaqachon to'g'ri")
PY

mkdir -p "$INSTALL_DIR/staticfiles"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/staticfiles"

echo "==> collectstatic..."
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py collectstatic --noinput --clear"

echo "==> Xizmat qayta ishga tushirilmoqda..."
if [[ "$NO_RESTART" != true ]]; then
    systemctl restart tezpos-backend
fi

CSS_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/static/admin/css/base.css || echo 000)"
echo ""
if [[ "$CSS_CODE" == "200" ]]; then
    echo "OK: admin CSS yuklanmoqda (HTTP $CSS_CODE)"
else
    echo "Ogohlantirish: /static/admin/css/base.css -> HTTP $CSS_CODE"
    echo "journalctl -u tezpos-backend -n 30 --no-pager"
fi
echo "Admin: http://$(curl -4 -s --max-time 3 ifconfig.me 2>/dev/null || echo SERVER_IP):8000/admin/"
