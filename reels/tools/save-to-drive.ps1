# Copies finished reels (mp4 + -thumbnail.jpg + -caption.txt) into Google Drive.
# Run on your Windows PC from the repo folder:  powershell -ExecutionPolicy Bypass -File reels\tools\save-to-drive.ps1
param([string]$Dest = "G:\My Drive\CSJ Reels")
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $repo
git pull --quiet
Pop-Location
$src = Join-Path $PSScriptRoot "..\export"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Get-ChildItem $src -File | Where-Object { $_.Extension -in ".mp4",".jpg",".txt" } | ForEach-Object {
  $target = Join-Path $Dest $_.Name
  if (-not (Test-Path $target) -or (Get-Item $target).Length -ne $_.Length) {
    Copy-Item $_.FullName $target -Force
    Write-Host "saved  $($_.Name)"
  }
}
Write-Host "Done -> $Dest"
