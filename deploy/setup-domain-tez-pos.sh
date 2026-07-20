#!/bin/bash
# Contabo: tez-pos.uz domenini nginx orqali Django (gunicorn) ga ulang
# DNS: tez-pos.uz A → 13.140.146.78 (shu server)
#
#   cd /opt/tezpos-backend
#   curl -fsSL -o /tmp/setup-domain-tez-pos.sh https://raw.githubusercontent.com/fayzullo1231/TezPOS_backend/main/deploy/setup-domain-tez-pos.sh
#   sudo bash /tmp/setup-domain-tez-pos.sh
#
set -euo pipefail

DOMAIN="${DOMAIN:-tez-pos.uz}"
WWW="www.${DOMAIN}"
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
EMAIL="${CERTBOT_EMAIL:-admin@${DOMAIN}}"
SITE_NAME="tez-pos"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Root: sudo bash $0"
  exit 1
fi

SERVER_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo "==> Public IP: ${SERVER_IP:-unknown}"
echo "==> DNS: dig +short ${DOMAIN}"
dig +short "$DOMAIN" 2>/dev/null || true
echo ""

echo "==> Paketlar..."
apt-get update -qq
apt-get install -y -qq nginx curl dnsutils
# certbot ixtiyoriy (HTTPS)
apt-get install -y -qq certbot python3-certbot-nginx 2>/dev/null || true

mkdir -p /var/www/certbot
mkdir -p "$INSTALL_DIR/media" "$INSTALL_DIR/staticfiles"

# ---------- Django .env ----------
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Xato: $ENV_FILE topilmadi"
  exit 1
fi

echo "==> ALLOWED_HOSTS / CSRF..."
HOSTS="localhost,127.0.0.1,${SERVER_IP},${DOMAIN},${WWW}"
CSRF="http://localhost,http://127.0.0.1,http://${SERVER_IP}:8000,http://${DOMAIN},https://${DOMAIN},http://${WWW},https://${WWW}"

if grep -q '^ALLOWED_HOSTS=' "$ENV_FILE"; then
  sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=${HOSTS}|" "$ENV_FILE"
else
  echo "ALLOWED_HOSTS=${HOSTS}" >> "$ENV_FILE"
fi
if grep -q '^CSRF_TRUSTED_ORIGINS=' "$ENV_FILE"; then
  sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=${CSRF}|" "$ENV_FILE"
else
  echo "CSRF_TRUSTED_ORIGINS=${CSRF}" >> "$ENV_FILE"
fi
if grep -q '^DEBUG=' "$ENV_FILE"; then
  sed -i 's|^DEBUG=.*|DEBUG=false|' "$ENV_FILE"
else
  echo "DEBUG=false" >> "$ENV_FILE"
fi

# ---------- Gunicorn: localhost + tashqi IP (POS 8000 ham ishlasin) ----------
# Nginx domen uchun 127.0.0.1:8000 ga ulanadi; 0.0.0.0 POS ilovasi uchun
SERVICE_FILE="/etc/systemd/system/tezpos-backend.service"
if [[ -f "$SERVICE_FILE" ]]; then
  echo "==> Gunicorn bind 0.0.0.0:${BACKEND_PORT} (nginx + IP:8000)..."
  if grep -q -- '--bind' "$SERVICE_FILE"; then
    sed -i "s|--bind [^ ]*|--bind 0.0.0.0:${BACKEND_PORT}|" "$SERVICE_FILE"
  fi
  systemctl daemon-reload
fi

systemctl enable tezpos-backend 2>/dev/null || true
systemctl restart tezpos-backend
sleep 1

# ---------- Nginx HTTP (80) — http://tez-pos.uz ----------
CONF="/etc/nginx/sites-available/${SITE_NAME}"
cat > "$CONF" <<EOF
# TezPOS — ${DOMAIN}
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${WWW};

    client_max_body_size 50M;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location /media/ {
        alias ${INSTALL_DIR}/media/;
        access_log off;
        expires 7d;
    }

    location /static/ {
        alias ${INSTALL_DIR}/staticfiles/;
        access_log off;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF

ln -sfn "$CONF" "/etc/nginx/sites-enabled/${SITE_NAME}"
# Eski nomlar
ln -sfn "$CONF" "/etc/nginx/sites-enabled/${DOMAIN}" 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default

echo "==> nginx -t"
nginx -t
systemctl enable nginx
systemctl reload nginx

# ---------- HTTPS (ixtiyoriy) ----------
if command -v certbot >/dev/null 2>&1; then
  echo "==> Let's Encrypt (HTTPS)..."
  if certbot --nginx -d "$DOMAIN" -d "$WWW" \
      --email "$EMAIL" \
      --agree-tos \
      --non-interactive \
      --redirect 2>/dev/null; then
    echo "HTTPS OK"
  else
    echo "Ogohlantirish: certbot muvaffaqiyatsiz (DNS yoki 80-port)."
    echo "HTTP ishlashi mumkin: http://${DOMAIN}/"
  fi
else
  echo "certbot yo'q — faqat HTTP"
fi

systemctl restart tezpos-backend
systemctl reload nginx

echo ""
echo "========== HOLAT =========="
systemctl is-active nginx && echo "nginx: active" || echo "nginx: FAIL"
systemctl is-active tezpos-backend && echo "tezpos-backend: active" || echo "gunicorn: FAIL"
ss -tulpn | grep -E ':80|:443|:8000' || true
echo ""
echo "Tekshiruv:"
curl -sI "http://127.0.0.1:${BACKEND_PORT}/admin/login/" | head -n 2 || true
curl -sI "http://${DOMAIN}/admin/login/" | head -n 3 || true
curl -sI "http://${DOMAIN}/check/xusanuz/1/" | head -n 3 || true
echo ""
echo "Tayyor!"
echo "  http://${DOMAIN}/"
echo "  https://${DOMAIN}/   (agar certbot o'tgan bo'lsa)"
echo "  API (POS): http://${SERVER_IP}:8000  yoki  https://${DOMAIN}"
echo ""
echo "Agar domen ochilmasa Contabo firewall da 80 va 443 ochiqligini tekshiring."
