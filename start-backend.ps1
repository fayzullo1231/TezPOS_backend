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

$env:USE_SQLITE = "true"
Write-Host "Migratsiya..." -ForegroundColor Cyan
.\venv\Scripts\python manage.py migrate
.\venv\Scripts\python manage.py seed_demo
if ($LASTEXITCODE -ne 0) {
    Write-Host "seed_demo xato berdi, lekin server ishga tushadi." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "TezPOS Backend ishga tushmoqda: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Ma'lumotlar bazasi: $PSScriptRoot\data\tezpos.db" -ForegroundColor Green
Write-Host ""
.\venv\Scripts\python manage.py runserver 127.0.0.1:8000
