Set-Location $PSScriptRoot

if (-not (Test-Path "venv")) {
    Write-Host "Virtual muhit yaratilmoqda..." -ForegroundColor Cyan
    python -m venv venv
}

Write-Host "Kutubxonalar o'rnatilmoqda..." -ForegroundColor Cyan
.\venv\Scripts\pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env yaratildi." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null
New-Item -ItemType Directory -Force -Path "media" | Out-Null

# Lokal ish: faqat Django bazasi (SQLite ORM orqali)
$env:DB_ENGINE = "sqlite"

Write-Host "Migratsiya..." -ForegroundColor Cyan
.\venv\Scripts\python manage.py migrate
if ($LASTEXITCODE -ne 0) { exit 1 }

.\venv\Scripts\python manage.py seed_demo
if ($LASTEXITCODE -ne 0) {
    Write-Host "seed_demo xato berdi, lekin server ishga tushadi." -ForegroundColor Yellow
}

# Tarmoq: boshqa kompyuterlar ham ulana oladi (0.0.0.0)
$env:ALLOWED_HOSTS = "*"

Write-Host ""
Write-Host "TezPOS Backend ishga tushmoqda: http://0.0.0.0:8000" -ForegroundColor Green
try {
    $lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown"
    } | Select-Object -First 1 -ExpandProperty IPAddress)
    if ($lanIp) {
        Write-Host "Boshqa kompyuterlar uchun backend manzil: http://${lanIp}:8000" -ForegroundColor Cyan
    }
} catch {}
Write-Host "Django bazasi: $PSScriptRoot\data\tezpos.db" -ForegroundColor Green
Write-Host "Django Admin: http://127.0.0.1:8000/admin/" -ForegroundColor Green
Write-Host ""
.\venv\Scripts\python manage.py runserver 0.0.0.0:8000 --noreload
