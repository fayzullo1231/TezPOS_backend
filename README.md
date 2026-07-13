# TezPOS Backend

Barcha ma'lumotlar **faqat Django ORM** orqali yoziladi — alohida JSON fayl yoki frontend localStorage emas.

## Ma'lumotlar bazasi

| Muhit | Django engine |
|-------|----------------|
| Lokal (default) | `django.db.backends.sqlite3` → `data/tezpos.db` |
| Production server | `DB_ENGINE=postgresql` (.env da) |

Bu Django ning o'z bazasi — `manage.py migrate`, modellar, admin panel hammasi shu yerda.

## Ishga tushirish

```powershell
cd C:\Users\User\Documents\TezPOS_backend
.\start-backend.ps1
```

- API: `http://127.0.0.1:8000`
- Admin: `http://127.0.0.1:8000/admin/`

## Demo kirish

| Server | Login | Parol |
|--------|-------|-------|
| demo | demo | demo123 |
| kuloloptom | admin | admin123 |

## Admin

```powershell
.\venv\Scripts\python manage.py createsuperuser
```

## Production (Contabo)

### 1-qadam: Kompyuterdan GitHub ga yuborish (push)

PowerShell da loyiha papkasida:

```powershell
cd C:\Users\User\Documents\TezPOS_backend

git status
git add .
git commit -m "Admin panel static fix va boshqa yangilanishlar"
git push origin main
```

Birinchi marta GitHub login so'rasa — brauzer orqali kirish yoki Personal Access Token ishlating.

---

### 2-qadam: Contabo serverda birinchi marta o'rnatish

SSH orqali serverga kiring, keyin:

```bash
sudo apt update
sudo apt install -y git

sudo git clone https://github.com/fayzullo1231/TezPOS_backend.git /opt/tezpos-backend
cd /opt/tezpos-backend
sudo bash deploy/install.sh
```

Tayyor bo'lgach:
- API: `http://SERVER_IP:8000`
- Admin: `http://SERVER_IP:8000/admin/`

---

### 3-qadam: Keyingi yangilanishlar (har safar kod o'zgarganda)

**Kompyuterda** — yangi kodni GitHub ga yuboring (1-qadam).

**Serverda** — yangi kodni torting (pull):

```bash
cd /opt/tezpos-backend
sudo bash deploy/update.sh
```

Bu skript avtomatik qiladi:
1. `git pull origin main` — GitHub dan yangi kod
2. `pip install` — kutubxonalar
3. `migrate` — bazani yangilash
4. `collectstatic` — admin CSS/JS
5. `systemctl restart tezpos-backend` — xizmatni qayta ishga tushirish

---

### 4-qadam: `tez-pos.uz` HTTPS (elektron chek)

1. **aHOST DNS**: `tez-pos.uz` va `www.tez-pos.uz` **A** yozuvini Contabo IP ga qo‘ying (`13.140.146.78`). Eski aHOST hosting IP emas.
2. Contabo firewall: **80** va **443** ochiq.
3. Serverda (kod yangilangandan keyin):

```bash
cd /opt/tezpos-backend
sudo bash deploy/update.sh
sudo bash deploy/setup-https-tez-pos.sh
```

Tekshiruv:
- `https://tez-pos.uz/check/xusanuz/4/`
- SMS link: `https://tez-pos.uz/check/<server>/<raqam>/`

---

### `.env` sozlamalari (server)

`/opt/tezpos-backend/.env`:

```env
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1,SERVER_IP,domen.uz
CSRF_TRUSTED_ORIGINS=http://SERVER_IP:8000,https://domen.uz
DB_ENGINE=postgresql
DB_NAME=tezpos
DB_USER=postgres
DB_PASSWORD=...
DB_HOST=localhost
```

Foydali buyruqlar:

```bash
systemctl status tezpos-backend    # holat
journalctl -u tezpos-backend -f    # loglar
systemctl restart tezpos-backend   # qo'lda qayta ishga tushirish
```
