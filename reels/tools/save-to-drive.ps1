# Copies finished reels (mp4 + -thumbnail.jpg + -caption.txt) into Google Drive.
# Files that already exist in the Drive folder are SKIPPED; only new ones are copied.
# Run on your Windows PC: double-click reels\tools\save-to-drive.bat
param([string]$Dest = "G:\My Drive\CSJ Reels")

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$src  = Resolve-Path (Join-Path $PSScriptRoot "..\export")

Write-Host "1) GitHub se nayi reels la raha hoon..." -ForegroundColor Cyan
Push-Location $repo
git pull --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "   git pull fail hua (internet / GitHub login check karein). Jo reels PC par hain wahi copy hongi." -ForegroundColor Yellow }
Pop-Location

if (-not (Test-Path (Split-Path $Dest -Qualifier))) {
  Write-Host "Drive '$(Split-Path $Dest -Qualifier)' nahi mila. Google Drive for desktop chalu karein." -ForegroundColor Red
  exit 1
}
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

Write-Host "2) '$Dest' mein copy kar raha hoon (pehle se maujood files skip)..." -ForegroundColor Cyan
$copied = 0; $skipped = 0
Get-ChildItem $src -File | Where-Object { $_.Extension -in ".mp4",".jpg",".txt" } | Sort-Object Name | ForEach-Object {
  $target = Join-Path $Dest $_.Name
  if (Test-Path $target) { $skipped++ }
  else {
    Copy-Item $_.FullName $target
    Write-Host "   + $($_.Name)" -ForegroundColor Green
    $copied++
  }
}
Write-Host ""
Write-Host "Ho gaya!  Nayi copy: $copied   |   Pehle se thi (skip): $skipped" -ForegroundColor Cyan
Write-Host "Folder: $Dest"
