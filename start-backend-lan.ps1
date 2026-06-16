# TezPOS Backend - Wi-Fi tarmogidagi boshqa kompyuterlar uchun
# Bu kompyuter server boladi; kassalar API manziliga shu IP ni yozadi.

Set-Location $PSScriptRoot

function Get-LanIPv4 {
    $addrs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Sort-Object -Property InterfaceMetric
    foreach ($a in $addrs) {
        if ($a.IPAddress -match "^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)") {
            return $a.IPAddress
        }
    }
    return ($addrs | Select-Object -First 1).IPAddress
}

if (-not (Test-Path "venv")) {
    Write-Host "Virtual muhit yaratilmoqda..." -ForegroundColor Cyan
    python -m venv venv
}

Write-Host "Kutubxonalar tekshirilmoqda..." -ForegroundColor Cyan
.\venv\Scripts\pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null
New-Item -ItemType Directory -Force -Path "media" | Out-Null

$lanIp = Get-LanIPv4
if (-not $lanIp) {
    Write-Warning "Wi-Fi IP topilmadi. runserver 0.0.0.0 da ishga tushadi."
    $lanIp = "SIZNING-IP"
}

$env:USE_SQLITE = "true"
$env:DEBUG = "true"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1,$lanIp,*"
$env:CSRF_TRUSTED_ORIGINS = "http://localhost,http://127.0.0.1,http://${lanIp}:8000"

$fwRule = "TezPOS Backend TCP 8000"
$existing = Get-NetFirewallRule -DisplayName $fwRule -ErrorAction SilentlyContinue
if (-not $existing) {
    try {
        New-NetFirewallRule -DisplayName $fwRule -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort 8000 -Profile Private,Domain -ErrorAction Stop | Out-Null
        Write-Host "Firewall: port 8000 ochildi." -ForegroundColor Green
    } catch {
        Write-Warning "Firewall qoshilmadi. Administrator sifatida ishga tushiring."
    }
} else {
    Write-Host "Firewall: port 8000 allaqachon ochiq." -ForegroundColor Gray
}

Write-Host "Migratsiya..." -ForegroundColor Cyan
.\venv\Scripts\python manage.py migrate --noinput
.\venv\Scripts\python manage.py seed_demo 2>$null

$apiLan = "http://${lanIp}:8000"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TezPOS BACKEND - Wi-Fi (LAN) rejimi" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Ushbu kompyuter (server):" -ForegroundColor White
Write-Host "    http://127.0.0.1:8000" -ForegroundColor Green
Write-Host ""
Write-Host "  Boshqa kassalar login API manzili:" -ForegroundColor White
Write-Host "    $apiLan" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Boshqa kompyuterda TezPOS login ekranida API maydoniga shu manzilni yozing." -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Toxtatish: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

.\venv\Scripts\python manage.py runserver 0.0.0.0:8000
