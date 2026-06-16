#!/bin/bash
# Contabo / Ubuntu VPS — TezPOS backend ni systemd orqali backgroundda ishga tushirish
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
SERVICE_USER="${SERVICE_USER:-tezpos}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Root sifatida ishga tushiring: sudo bash deploy/install.sh"
    exit 1
fi

echo "==> Tizim paketlari o'rnatilmoqda..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync

echo "==> Foydalanuvchi: $SERVICE_USER"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "==> Loyiha nusxalanmoqda: $REPO_ROOT -> $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude 'data/*.db-journal' \
    "$REPO_ROOT/" "$INSTALL_DIR/"

mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/media" "$INSTALL_DIR/staticfiles"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo "==> Virtual muhit va kutubxonalar..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "==> .env sozlamalari..."
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
fi

SERVER_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
SECRET_KEY="$("$INSTALL_DIR/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')"

# Mavjud qiymatlarni saqlab, kerakli maydonlarni yangilash
grep -q '^DJANGO_SECRET_KEY=' "$ENV_FILE" && sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$SECRET_KEY|" "$ENV_FILE" || echo "DJANGO_SECRET_KEY=$SECRET_KEY" >> "$ENV_FILE"
grep -q '^DEBUG=' "$ENV_FILE" && sed -i 's|^DEBUG=.*|DEBUG=false|' "$ENV_FILE" || echo "DEBUG=false" >> "$ENV_FILE"
grep -q '^USE_SQLITE=' "$ENV_FILE" && sed -i 's|^USE_SQLITE=.*|USE_SQLITE=true|' "$ENV_FILE" || echo "USE_SQLITE=true" >> "$ENV_FILE"

if [[ -n "$SERVER_IP" ]]; then
    if grep -q '^ALLOWED_HOSTS=' "$ENV_FILE"; then
        CURRENT_HOSTS="$(grep '^ALLOWED_HOSTS=' "$ENV_FILE" | cut -d= -f2-)"
        if [[ "$CURRENT_HOSTS" != *"$SERVER_IP"* ]]; then
            sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1,$SERVER_IP|" "$ENV_FILE"
        fi
    else
        echo "ALLOWED_HOSTS=localhost,127.0.0.1,$SERVER_IP" >> "$ENV_FILE"
    fi
fi

chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"

echo "==> Migratsiya va demo ma'lumotlar..."
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py migrate --noinput"
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py collectstatic --noinput" 2>/dev/null || true
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py seed_demo" 2>/dev/null || true

echo "==> systemd xizmati o'rnatilmoqda..."
cp "$SCRIPT_DIR/tezpos-backend.service" /etc/systemd/system/tezpos-backend.service
systemctl daemon-reload
systemctl enable tezpos-backend
systemctl restart tezpos-backend

echo ""
echo "Tayyor! Backend backgroundda ishlayapti."
echo "  Status:  systemctl status tezpos-backend"
echo "  Loglar:  journalctl -u tezpos-backend -f"
echo "  To'xtat: systemctl stop tezpos-backend"
echo "  Qayta:   systemctl restart tezpos-backend"
echo ""
echo "  API: http://${SERVER_IP:-SERVER_IP}:8000"
echo "  Demo: server=demo, login=admin, parol=admin123"
