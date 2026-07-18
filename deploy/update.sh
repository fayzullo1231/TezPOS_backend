#!/bin/bash
# GitHub dan kod tortib, serverni yangilash (Contabo)
# Serverda: sudo bash deploy/update.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tezpos-backend}"
SERVICE_USER="${SERVICE_USER:-tezpos}"
GIT_BRANCH="${GIT_BRANCH:-main}"
GIT_REMOTE="${GIT_REMOTE:-https://github.com/fayzullo1231/TezPOS_backend.git}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Root sifatida ishga tushiring: sudo bash deploy/update.sh"
    exit 1
fi

if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "Xato: $INSTALL_DIR topilmadi."
    echo "Birinchi marta: git clone $GIT_REMOTE $INSTALL_DIR"
    echo "Keyin: sudo bash $INSTALL_DIR/deploy/install.sh"
    exit 1
fi

cd "$INSTALL_DIR"

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    echo "==> .git yo'q — GitHub dan clone qilinmoqda (media/.env saqlanadi)..."
    TMP_CLONE="$(mktemp -d /tmp/tezpos-clone.XXXXXX)"
    git clone --depth 1 --branch "$GIT_BRANCH" "$GIT_REMOTE" "$TMP_CLONE"
    rsync -a --delete \
        --exclude 'venv' \
        --exclude 'data' \
        --exclude 'media' \
        --exclude '.env' \
        --exclude '__pycache__' \
        "$TMP_CLONE/" "$INSTALL_DIR/"
    rm -rf "$TMP_CLONE"
    # Keyingi update lar uchun .git ni qo'yib qo'yamiz
    if [[ ! -d "$INSTALL_DIR/.git" ]]; then
        git clone --depth 1 --branch "$GIT_BRANCH" "$GIT_REMOTE" "$TMP_CLONE"
        mv "$TMP_CLONE/.git" "$INSTALL_DIR/.git"
        rm -rf "$TMP_CLONE"
    fi
else
    echo "==> GitHub dan yangilanmoqda (git pull origin $GIT_BRANCH)..."
    git config --global --add safe.directory "$INSTALL_DIR"
    git -C "$INSTALL_DIR" remote set-url origin "$GIT_REMOTE" 2>/dev/null || \
        git -C "$INSTALL_DIR" remote add origin "$GIT_REMOTE"
    git -C "$INSTALL_DIR" fetch origin "$GIT_BRANCH"
    git -C "$INSTALL_DIR" checkout -B "$GIT_BRANCH" "origin/$GIT_BRANCH"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo "==> Kutubxonalar..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "==> Migratsiya..."
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py migrate --noinput"

echo "==> Static..."
if [[ -f "$INSTALL_DIR/deploy/fix-admin-static.sh" ]]; then
    bash "$INSTALL_DIR/deploy/fix-admin-static.sh" --no-restart || true
else
    sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py collectstatic --noinput" 2>/dev/null || true
fi

echo "==> Django admin ruxsatlari..."
sudo -u "$SERVICE_USER" bash -c "cd '$INSTALL_DIR' && ./venv/bin/python manage.py ensure_django_admin" 2>/dev/null || true

systemctl restart tezpos-backend
echo ""
echo "Tayyor! GitHub dan yangilandi va qayta ishga tushirildi."
echo "Tekshiruv: curl -sI http://127.0.0.1:8000/media/ | head -n 1"
echo "  (fayl bo'lmasa ham 404 OK — lekin Django HTML bo'lishi kerak, connection refused emas)"
echo "  Admin: http://$(curl -4 -s --max-time 3 ifconfig.me 2>/dev/null || echo SERVER_IP):8000/admin/"
