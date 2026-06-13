# TezPOS Backend

Django REST API — mahsulotlar, sotuvlar, mijozlar va boshqa ma'lumotlar shu yerda saqlanadi.

## Tuzilma

```
TezPOS_backend/
├── apps/              # Django ilovalar (accounts, catalog, sales)
├── tezpos/            # Loyiha sozlamalari
├── data/
│   └── tezpos.db      # SQLite ma'lumotlar bazasi (alohida fayl)
├── media/             # Mahsulot rasmlari
├── manage.py
├── requirements.txt
└── start-backend.ps1
```

## Ishga tushirish

```powershell
cd C:\Users\User\Documents\TezPOS_backend
.\start-backend.ps1
```

API: `http://127.0.0.1:8000`

## Demo kirish

- **Server nomi:** `demo`
- **Login:** `admin`
- **Parol:** `admin123`

## Ma'lumotlar bazasi

Barcha mahsulotlar va sotuvlar `data/tezpos.db` faylida saqlanadi.
Bu faylni zaxiralash uchun nusxa oling.

## Admin panel

```powershell
.\venv\Scripts\python manage.py createsuperuser
```

`http://127.0.0.1:8000/admin/`

## Serverga joylash (production)

Docker bilan: `TezPOS/DEPLOY.md` va `TezPOS/deploy/` papkasidagi `docker-compose.yml`.

```bash
cd TezPOS/deploy
cp .env.example .env
./install.sh
```
