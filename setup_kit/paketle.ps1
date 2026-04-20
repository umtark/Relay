<#
.SYNOPSIS
    Relay Dev - Paketleme Scripti
    Yamalı Continue extension + Relay_proxy'yi setup_kit'e paketler.
    Format sonrası sadece KUR.bat çalıştırarak her şey geri gelir.

.USAGE
    powershell -ExecutionPolicy Bypass -File paketle.ps1
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Relay Dev - Paketleme" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ────────────────────────────────────────────────
# 1. Yamalı Continue extension'ı bul
# ────────────────────────────────────────────────
$extBase = "$env:USERPROFILE\.vscode\extensions"
$extDir = Get-ChildItem $extBase -Directory | Where-Object { $_.Name -like "continue.continue-*" } | Select-Object -First 1

if (-not $extDir) {
    Write-Host "  [!] Continue extension bulunamadı!" -ForegroundColor Red
    Read-Host "  Enter'a basın"
    exit 1
}

$extName = $extDir.Name
Write-Host "  [OK] Extension bulundu: $extName" -ForegroundColor Green

# ────────────────────────────────────────────────
# 2. Hedef klasörü hazırla
# ────────────────────────────────────────────────
$targetDir = Join-Path $ScriptDir "continue_ext"

if (Test-Path $targetDir) {
    Write-Host "  [..] Eski paket siliniyor..." -ForegroundColor Yellow
    Remove-Item $targetDir -Recurse -Force
}

Write-Host "  [..] Extension kopyalanıyor ($extName)..." -ForegroundColor Yellow
Write-Host "       Bu biraz sürebilir (~233 MB)..." -ForegroundColor DarkGray

# Robocopy ile hızlı kopyalama
$robocopyArgs = @($extDir.FullName, $targetDir, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
& robocopy @robocopyArgs | Out-Null

# Extension klasör adını bir dosyaya yaz (kurulumda kullanılacak)
$extName | Out-File (Join-Path $targetDir ".ext_name") -Encoding UTF8 -NoNewline

Write-Host "  [OK] Extension kopyalandı" -ForegroundColor Green

# ────────────────────────────────────────────────
# 3. Relay_proxy.py'yi extension içine göm
# ────────────────────────────────────────────────
$relayDir = Join-Path $targetDir "relay"
New-Item -ItemType Directory -Path $relayDir -Force | Out-Null

$relayProxy = Join-Path $ProjectDir "Relay_proxy.py"
if (Test-Path $relayProxy) {
    Copy-Item $relayProxy (Join-Path $relayDir "Relay_proxy.py") -Force
    Write-Host "  [OK] Relay_proxy.py → continue_ext/relay/" -ForegroundColor Green
} else {
    Write-Host "  [!] Relay_proxy.py bulunamadı ($relayProxy)" -ForegroundColor Red
}

# ────────────────────────────────────────────────
# 4. Relay başlatma BAT dosyasını oluştur
# ────────────────────────────────────────────────
$batContent = @'
@echo off
title Relay Proxy
echo ═══════════════════════════════════════════════
echo   Relay Proxy Baslatiliyor...
echo ═══════════════════════════════════════════════
echo.

:: Extension içindeki relay klasöründen çalıştır
set "RELAY_DIR=%~dp0"
cd /d "%RELAY_DIR%"

:: Python kontrolü
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python bulunamadi!
    echo     https://www.python.org/downloads/
    pause
    exit /b 1
)

python Relay_proxy.py %*
if errorlevel 1 pause
'@
$batContent | Out-File (Join-Path $relayDir "Relay_Baslat.bat") -Encoding ASCII
Write-Host "  [OK] Relay_Baslat.bat oluşturuldu" -ForegroundColor Green

# ────────────────────────────────────────────────
# 5. Backup dosyalarını paketten çıkar (gereksiz)
# ────────────────────────────────────────────────
$backups = Get-ChildItem $targetDir -Recurse -Filter "*.backup_original"
foreach ($b in $backups) {
    Remove-Item $b.FullName -Force
    Write-Host "  [--] Backup silindi: $($b.Name)" -ForegroundColor DarkGray
}

# ────────────────────────────────────────────────
# 6. Boyut raporu
# ────────────────────────────────────────────────
$totalSize = (Get-ChildItem $targetDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
$fileCount = (Get-ChildItem $targetDir -Recurse -File).Count

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Paketleme Tamamlandı!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Klasör : setup_kit\continue_ext\" -ForegroundColor White
Write-Host "  Boyut  : $([math]::Round($totalSize, 1)) MB ($fileCount dosya)" -ForegroundColor White
Write-Host "  İçerik :" -ForegroundColor White
Write-Host "    - Continue extension (Türkçe yamalı)" -ForegroundColor White
Write-Host "    - relay\Relay_proxy.py" -ForegroundColor White
Write-Host "    - relay\Relay_Baslat.bat" -ForegroundColor White
Write-Host ""
Write-Host "  Şimdi KUR.bat ile kurulum test edilebilir." -ForegroundColor Yellow
Write-Host ""
Read-Host "  Çıkmak için Enter'a basın"
