# Windows Firewall — port 8000 (boshqa kompyuterlar ulanishi uchun)
# PowerShell ni ADMINISTRATOR sifatida ishga tushiring

$ruleName = "TezPOS Backend TCP 8000"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Enable-NetFirewallRule -DisplayName $ruleName | Out-Null
    Write-Host "Firewall qoidasi allaqachon bor — yoqildi." -ForegroundColor Green
} else {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 8000 -Profile Private,Domain,Public | Out-Null
    Write-Host "Firewall: port 8000 ochildi (Private + Public)." -ForegroundColor Green
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -match "^192\.168\." } | Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "Boshqa kassalarda API manzili:" -ForegroundColor Yellow
if ($ip) {
    Write-Host "  http://${ip}:8000" -ForegroundColor Cyan
} else {
    Write-Host "  http://SIZNING-WIFI-IP:8000" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "Tekshirish (boshqa kompyuter brauzerida):" -ForegroundColor Gray
Write-Host "  http://${ip}:8000/api/auth/health/" -ForegroundColor Gray
