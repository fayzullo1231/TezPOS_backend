#!/bin/bash
# Contabo VPS: tez-pos.uz uchun nginx + Let's Encrypt HTTPS
# DNS: tez-pos.uz A yozuvi → shu serverning public IP (masalan 13.140.146.78)
#
#   sudo bash deploy/setup-https-tez-pos.sh
#
set -euo pipefail

DOMAIN="${DOMAIN:-tez-pos.uz}"
WWW="www.${DOMAIN}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EMAIL="${CERTBOT_EMAIL:-admin@${DOMAIN}}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Root sifatida ishga tushiring: sudo bash deploy/setup-https-tez-pos.sh"
    exit 1
fi

echo "==> Paketlar (nginx, certbot)..."
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx

mkdir -p /var/www/certbot

SERVER_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo "==> Server public IP: ${SERVER_IP:-unknown}"
echo "    DNS tekshiruvi: dig +short ${DOMAIN}  →  ${SERVER_IP} bo'lishi kerak"
echo ""

# 1) Vaqtinchalik HTTP (ACME + proxy) — sertifikat olishdan oldin
TEMP_CONF="/etc/nginx/sites-available/${DOMAIN}"
cat > "$TEMP_CONF" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${WWW};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        client_max_body_size 50M;
    }
}
EOF

ln -sfn "$TEMP_CONF" "/etc/nginx/sites-enabled/${DOMAIN}"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl reload nginx

echo "==> Let's Encrypt sertifikat..."
certbot certonly --webroot -w /var/www/certbot \
    -d "$DOMAIN" -d "$WWW" \
    --email "$EMAIL" \
    --agree-tos \
    --non-interactive \
    --keep-until-expiry

# 2) HTTPS conf
if [[ -f "$SCRIPT_DIR/nginx-tez-pos.uz.conf" ]]; then
    cp "$SCRIPT_DIR/nginx-tez-pos.uz.conf" "$TEMP_CONF"
else
    echo "Ogohlantirish: nginx-tez-pos.uz.conf topilmadi — HTTP conf qoladi"
fi

# SSL helper fayllar (certbot odatda yaratadi)
if [[ ! -f /etc/letsencrypt/options-ssl-nginx.conf ]]; then
    curl -fsSL https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf \
        -o /etc/letsencrypt/options-ssl-nginx.conf || true
fi
if [[ ! -f /etc/letsencrypt/ssl-dhparams.pem ]]; then
    openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
fi

nginx -t
systemctl reload nginx

# 3) Django .env — domen ruxsati
ENV_FILE="$INSTALL_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    echo "==> Django ALLOWED_HOSTS / CSRF yangilanmoqda..."
    if grep -q '^ALLOWED_HOSTS=' "$ENV_FILE"; then
        CURRENT="$(grep '^ALLOWED_HOSTS=' "$ENV_FILE" | cut -d= -f2-)"
        NEW="$CURRENT"
        [[ "$NEW" != *"$DOMAIN"* ]] && NEW="${NEW},${DOMAIN},${WWW}"
        [[ -n "$SERVER_IP" && "$NEW" != *"$SERVER_IP"* ]] && NEW="${NEW},${SERVER_IP}"
        sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=${NEW}|" "$ENV_FILE"
    else
        echo "ALLOWED_HOSTS=localhost,127.0.0.1,${SERVER_IP},${DOMAIN},${WWW}" >> "$ENV_FILE"
    fi

    CSRF="https://${DOMAIN},https://${WWW},http://${SERVER_IP}:8000"
    if grep -q '^CSRF_TRUSTED_ORIGINS=' "$ENV_FILE"; then
        sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=${CSRF}|" "$ENV_FILE"
    else
        echo "CSRF_TRUSTED_ORIGINS=${CSRF}" >> "$ENV_FILE"
    fi

    systemctl restart tezpos-backend || true
fi

echo ""
echo "Tayyor!"
echo "  HTTP → HTTPS:  http://${DOMAIN}/check/xusanuz/4/"
echo "  HTTPS:         https://${DOMAIN}/check/xusanuz/4/"
echo ""
echo "Agar sertifikat xato bersa: DNS A yozuvi ${DOMAIN} → ${SERVER_IP} ekanligini tekshiring."
echo "80/443 portlar Contabo firewall da ochiq bo'lishi kerak."
