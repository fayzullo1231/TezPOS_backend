# TezPOS — 80 mm chek tavsiya (asosiy skript TezPOS papkasida)
$ErrorActionPreference = "Stop"

$TezPosRoot = Join-Path (Split-Path $PSScriptRoot -Parent) "TezPOS"
if (-not (Test-Path $TezPosRoot)) {
    $TezPosRoot = Join-Path $PSScriptRoot "..\TezPOS"
}
$InstallScript = Join-Path $TezPosRoot "install-chek-80mm.ps1"

if (-not (Test-Path $InstallScript)) {
    Write-Error "TezPOS topilmadi. Kutilgan: $InstallScript"
}

Write-Host "TezPOS install-chek-80mm.ps1 ishga tushirilmoqda..." -ForegroundColor Cyan
& $InstallScript @args
