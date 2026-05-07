# Suisho5 (水匠5) 評価関数の取得スクリプト
#
# 配布元: https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5
# ライセンス: Apache License, Version 2.0
#
# 使い方(PowerShell):
#   .\fetch.ps1
#
# 前提:
#   - 7z (p7zip) が利用可能なこと
#     例) MSYS2 環境: pacman -S p7zip → /c/msys64/usr/bin/7z
#     例) Windows 標準: tar コマンドでは .7z 非対応のため別途必要

$ErrorActionPreference = "Stop"

$Url      = "https://github.com/yaneurao/YaneuraOu/releases/download/suisho5/Suisho5.7z"
$Sha256   = "768068f0d534a0603a5d38bcd143de6bbca820d5f1c95a14d40863e5b7892d76"  # nn.bin (展開後)の SHA-256
$ScriptDir = $PSScriptRoot
$ArchivePath = Join-Path $ScriptDir "Suisho5.7z"
$NnBinPath   = Join-Path $ScriptDir "nn.bin"

if (Test-Path $NnBinPath) {
    Write-Host "[fetch] nn.bin already exists at $NnBinPath"
    Write-Host "[fetch] (delete it manually to re-fetch)"
    exit 0
}

Write-Host "[fetch] Downloading $Url ..."
Invoke-WebRequest -Uri $Url -OutFile $ArchivePath

# 7z の場所を解決
$Sevenzip = $null
foreach ($candidate in @(
    "C:\msys64\usr\bin\7z.exe",
    "C:\Program Files\7-Zip\7z.exe",
    "C:\Program Files (x86)\7-Zip\7z.exe",
    "7z.exe"
)) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $Sevenzip = $candidate
        break
    }
    if (Test-Path $candidate) {
        $Sevenzip = $candidate
        break
    }
}

if (-not $Sevenzip) {
    Write-Error "7z not found. Install p7zip via MSYS2 (pacman -S p7zip) or 7-Zip from https://www.7-zip.org/"
}

Write-Host "[fetch] Extracting via $Sevenzip ..."
& $Sevenzip x -y -o"$ScriptDir" $ArchivePath | Out-Null

if (-not (Test-Path $NnBinPath)) {
    Write-Error "Extraction failed: nn.bin not found at $NnBinPath"
}

# Verify SHA-256
$actual = (Get-FileHash $NnBinPath -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $Sha256) {
    Write-Error "SHA-256 mismatch! expected=$Sha256 actual=$actual"
}

Write-Host "[fetch] OK: nn.bin saved at $NnBinPath (SHA-256 verified)"
Remove-Item $ArchivePath
Write-Host "[fetch] (cleanup) removed Suisho5.7z"

Write-Host ""
Write-Host "Next: copy or symlink nn.bin into engine/bin/eval/, e.g."
Write-Host "  Copy-Item $NnBinPath ../../engine/bin/eval/nn.bin"
Write-Host "And set FV_SCALE=24 in the engine options."
