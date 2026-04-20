<#
.SYNOPSIS
    Relay Dev - Continue Kurulum Kiti
    Format sonrası bu scripti çalıştırınca her şey geri gelir.
    Paketlenmiş extension'ı kopyalar — Python veya internet gerekmez.

.USAGE
    Sağ tık → "PowerShell ile çalıştır"
    veya: powershell -ExecutionPolicy Bypass -File kur.ps1

.NOTES
    Önce paketle.ps1 çalıştırılmış olmalı (continue_ext/ klasörü oluşur).
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceDir = Split-Path -Parent $ScriptDir

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Relay Dev - Continue Kurulum Kiti" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ────────────────────────────────────────────────
# 1. VS Code kurulu mu?
# ────────────────────────────────────────────────
$codePath = Get-Command code -ErrorAction SilentlyContinue
if (-not $codePath) {
    Write-Host "  [!] VS Code bulunamadı. Önce VS Code'u kurun." -ForegroundColor Red
    Write-Host "      https://code.visualstudio.com/download" -ForegroundColor Yellow
    Read-Host "  Devam etmek için Enter'a basın"
    exit 1
}
Write-Host "  [OK] VS Code bulundu" -ForegroundColor Green

# ────────────────────────────────────────────────
# 2. Paketlenmiş extension mevcut mu?
# ────────────────────────────────────────────────
$packagedExt = Join-Path $ScriptDir "continue_ext"
$extNameFile = Join-Path $packagedExt ".ext_name"

if (-not (Test-Path $packagedExt)) {
    Write-Host "  [!] Paketlenmiş extension bulunamadı!" -ForegroundColor Red
    Write-Host "      Önce paketle.ps1 çalıştırın." -ForegroundColor Yellow
    Read-Host "  Enter'a basın"
    exit 1
}

# Extension hedef adını oku
if (Test-Path $extNameFile) {
    $extName = (Get-Content $extNameFile -Raw).Trim()
} else {
    # Fallback: klasör içindeki package.json'dan tahmin et
    $extName = "continue.continue-packaged"
}
Write-Host "  [OK] Paket bulundu: $extName" -ForegroundColor Green

# ────────────────────────────────────────────────
# 3. Extension'ı .vscode/extensions/ altına kopyala
# ────────────────────────────────────────────────
Write-Host ""
$extBase = "$env:USERPROFILE\.vscode\extensions"
if (-not (Test-Path $extBase)) {
    New-Item -ItemType Directory -Path $extBase -Force | Out-Null
}

$targetExt = Join-Path $extBase $extName

# Mevcut Continue extension varsa yedekle
$existingExts = Get-ChildItem $extBase -Directory | Where-Object { $_.Name -like "continue.continue-*" }
foreach ($existing in $existingExts) {
    if ($existing.FullName -ne $targetExt) {
        $backupName = $existing.Name + ".old"
        $backupPath = Join-Path $extBase $backupName
        if (Test-Path $backupPath) { Remove-Item $backupPath -Recurse -Force }
        Rename-Item $existing.FullName $backupPath
        Write-Host "  [--] Eski extension yedeklendi: $($existing.Name) → $backupName" -ForegroundColor DarkGray
    }
}

if (Test-Path $targetExt) {
    Write-Host "  [..] Mevcut extension güncelleniyor..." -ForegroundColor Yellow
    Remove-Item $targetExt -Recurse -Force
}

Write-Host "  [..] Extension kopyalanıyor..." -ForegroundColor Yellow
Write-Host "       Bu biraz sürebilir (~233 MB)..." -ForegroundColor DarkGray

$robocopyArgs = @($packagedExt, $targetExt, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
& robocopy @robocopyArgs | Out-Null

# .ext_name dosyasını hedeften sil (ihtiyaç yok)
$targetExtName = Join-Path $targetExt ".ext_name"
if (Test-Path $targetExtName) { Remove-Item $targetExtName -Force }

Write-Host "  [OK] Extension kuruldu (Türkçe yamalı + Relay gömülü)" -ForegroundColor Green

# ────────────────────────────────────────────────
# 4. ~/.continue/ klasörüne config dosyalarını kopyala
# ────────────────────────────────────────────────
Write-Host ""
Write-Host "  [..] Continue config dosyaları kopyalanıyor..." -ForegroundColor Yellow
$continueDir = Join-Path $env:USERPROFILE ".continue"

if (-not (Test-Path $continueDir)) {
    New-Item -ItemType Directory -Path $continueDir -Force | Out-Null
}

$configSource = Join-Path $ScriptDir "continue_config"
$configFiles = @("config.yaml", ".continuerc.json", "config.ts", "package.json", ".continueignore")

foreach ($file in $configFiles) {
    $src = Join-Path $configSource $file
    $dst = Join-Path $continueDir $file
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "  [OK] $file → ~/.continue/" -ForegroundColor Green
    } else {
        Write-Host "  [!] $file bulunamadı (atlanıyor)" -ForegroundColor Yellow
    }
}

# ────────────────────────────────────────────────
# 5. Workspace .vscode/settings.json kopyala
# ────────────────────────────────────────────────
Write-Host ""
Write-Host "  [..] VS Code workspace ayarları kontrol ediliyor..." -ForegroundColor Yellow

$vscodeDir = Join-Path $WorkspaceDir ".vscode"
$settingsSrc = Join-Path $ScriptDir "vscode_settings\settings.json"

if (Test-Path $settingsSrc) {
    if (-not (Test-Path $vscodeDir)) {
        New-Item -ItemType Directory -Path $vscodeDir -Force | Out-Null
    }
    $settingsDst = Join-Path $vscodeDir "settings.json"
    
    if (Test-Path $settingsDst) {
        Write-Host "  [OK] .vscode/settings.json zaten mevcut (üzerine yazılmadı)" -ForegroundColor Green
    } else {
        Copy-Item $settingsSrc $settingsDst -Force
        Write-Host "  [OK] .vscode/settings.json oluşturuldu" -ForegroundColor Green
    }
} else {
    Write-Host "  [!] settings.json kaynağı bulunamadı" -ForegroundColor Yellow
}

# ────────────────────────────────────────────────
# 6. Relay_proxy.py kısayolunu workspace'e kopyala
# ────────────────────────────────────────────────
Write-Host ""
$relayInExt = Join-Path $targetExt "relay"
$relayBat = Join-Path $WorkspaceDir "Relay_Baslat.bat"

if (-not (Test-Path $relayBat)) {
    $batContent = @"
@echo off
title Relay Proxy
echo Relay Proxy baslatiliyor...
set "RELAY_DIR=$relayInExt"
cd /d "%RELAY_DIR%"
python Relay_proxy.py %*
if errorlevel 1 pause
"@
    $batContent | Out-File $relayBat -Encoding ASCII
    Write-Host "  [OK] Relay_Baslat.bat oluşturuldu (workspace kökünde)" -ForegroundColor Green
} else {
    Write-Host "  [OK] Relay_Baslat.bat zaten mevcut" -ForegroundColor Green
}

# ────────────────────────────────────────────────
# 7. Python bağımlılıkları (opsiyonel)
# ────────────────────────────────────────────────
$pythonPath = Get-Command python -ErrorAction SilentlyContinue
if ($pythonPath) {
    Write-Host ""
    Write-Host "  [..] Python bağımlılıkları kontrol ediliyor..." -ForegroundColor Yellow
    $deps = @("selenium", "webdriver-manager")
    foreach ($dep in $deps) {
        $installed = python -c "import importlib; importlib.import_module('$($dep.Replace('-','_'))')" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [..] $dep kuruluyor..." -ForegroundColor Yellow
            python -m pip install $dep --quiet 2>$null
            Write-Host "  [OK] $dep kuruldu" -ForegroundColor Green
        } else {
            Write-Host "  [OK] $dep zaten kurulu" -ForegroundColor Green
        }
    }
} else {
    Write-Host ""
    Write-Host "  [!] Python bulunamadı. Relay_proxy için Python gerekli:" -ForegroundColor Yellow
    Write-Host "      https://www.python.org/downloads/" -ForegroundColor Yellow
}

# ────────────────────────────────────────────────
# 8. Özet
# ────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Kurulum Tamamlandı!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Kurulanlar:" -ForegroundColor White
Write-Host "    - Continue extension (Türkçe yamalı)" -ForegroundColor White
Write-Host "    - Relay_proxy (extension içine gömülü)" -ForegroundColor White
Write-Host "    - Continue config (~/.continue/)" -ForegroundColor White
Write-Host "    - VS Code workspace ayarları" -ForegroundColor White
Write-Host ""
Write-Host "  Yapılacaklar:" -ForegroundColor White
Write-Host "    1. VS Code'u açın (veya Ctrl+Shift+P → Reload Window)" -ForegroundColor White
Write-Host "    2. Relay_Baslat.bat çalıştırın (veya: python Relay_proxy.py)" -ForegroundColor White
Write-Host "    3. Continue panelinden 'Relay 1.2' modelini seçin" -ForegroundColor White
Write-Host ""
Write-Host "  Relay_proxy konumu:" -ForegroundColor DarkGray
Write-Host "    $relayInExt\Relay_proxy.py" -ForegroundColor DarkGray
Write-Host ""
Read-Host "  Çıkmak için Enter'a basın"
