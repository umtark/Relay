# ═══════════════════════════════════════════════════════════
#  Relay Yayınlama Scripti
#  Kullanım:  .\yayinla.ps1 -Tip minor -Not "Yeni özellik eklendi"
#             .\yayinla.ps1 -Tip patch -Not "Bug fix"
#             .\yayinla.ps1 -Tip major -Not "Büyük güncelleme"
# ═══════════════════════════════════════════════════════════
param(
    [ValidateSet("major","minor","patch")]
    [string]$Tip = "patch",
    [Parameter(Mandatory=$true)]
    [string]$Not
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Git PATH kontrolü
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $gitPath = "C:\Program Files\Git\cmd"
    if (Test-Path $gitPath) { $env:PATH += ";$gitPath" }
    else { Write-Host "  HATA: Git bulunamadi!" -ForegroundColor Red; exit 1 }
}

Write-Host "`n═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Relay Yayinlama" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════`n" -ForegroundColor Cyan

# 1) version.json oku
$vj = Get-Content "version.json" -Raw | ConvertFrom-Json
$parts = $vj.version.Split(".")
$major = [int]$parts[0]; $minor = [int]$parts[1]; $patch = [int]$parts[2]

switch ($Tip) {
    "major" { $major++; $minor = 0; $patch = 0 }
    "minor" { $minor++; $patch = 0 }
    "patch" { $patch++ }
}
$newVer = "$major.$minor.$patch"
Write-Host "  Versiyon: $($vj.version) -> $newVer" -ForegroundColor Yellow

# 2) version.json güncelle
$vj.version = $newVer
$vj.date = (Get-Date).ToString("yyyy-MM-dd")
$vj.changelog = $Not
# BOM'suz UTF-8 yaz
[System.IO.File]::WriteAllText(
    (Join-Path $PSScriptRoot "version.json"),
    ($vj | ConvertTo-Json -Depth 5),
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "  version.json guncellendi" -ForegroundColor Green

# 3) Lokal extension kopyasını güncelle (kendi makinemiz için)
$extRelay = "$env:USERPROFILE\.vscode\extensions\continue.continue-1.2.22-win32-x64\relay"
if (Test-Path $extRelay) {
    foreach ($f in $vj.files) {
        $src = Join-Path $PSScriptRoot $f
        $dst = Join-Path $extRelay (Split-Path $f -Leaf)
        if (Test-Path $src) {
            Copy-Item $src $dst -Force
        }
    }
    Copy-Item "version.json" "$extRelay\version.json" -Force
    Write-Host "  Extension kopyasi guncellendi" -ForegroundColor Green
} else {
    Write-Host "  Extension klasoru bulunamadi (atlanıyor)" -ForegroundColor DarkYellow
}

# 4) Git commit & push
Write-Host "`n  Git'e gonderiliyor..." -ForegroundColor Cyan
git add -A
git commit -m "v$newVer - $Not"
git tag "v$newVer"
git push origin main --tags

Write-Host "`n═══════════════════════════════════════" -ForegroundColor Green
Write-Host "  v$newVer yayinlandi!" -ForegroundColor Green
Write-Host "  Herkes otomatik guncellenecek." -ForegroundColor Green
Write-Host "═══════════════════════════════════════`n" -ForegroundColor Green
