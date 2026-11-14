<# : ---- batch part: runs the PowerShell code below in this same file ----
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((Get-Content -LiteralPath '%~f0' -Raw))"
echo.
pause
exit /b
#>
# CSJ Reels -> Google Drive
# Downloads every reel set (mp4 + -thumbnail.jpg + -caption.txt) straight from GitHub
# into the Drive folder. Files already in Drive are skipped. Nothing is kept on the PC:
# each file goes to a temp file and is MOVED into Drive (temp copy is gone after the move).
$Dest   = "G:\My Drive\CSJ Reels"
$Repo   = "nehraeduhub/CyberSecuirty"
$Branch = "ccr-c4934e02-cxkggq"
$Path   = "reels/export"

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$drive = Split-Path $Dest -Qualifier
if (-not (Test-Path $drive)) {
  Write-Host "Drive $drive nahi mila. Google Drive for desktop chalu karke login karein." -ForegroundColor Red
  return
}
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

Write-Host "1) GitHub par reels ki list dekh raha hoon..." -ForegroundColor Cyan
try {
  $list = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/contents/$Path`?ref=$Branch" -Headers @{ "User-Agent" = "csj-reels-sync" }
} catch {
  Write-Host "GitHub se list nahi mili. Internet check karein. ($($_.Exception.Message))" -ForegroundColor Red
  return
}
$files = $list | Where-Object { $_.type -eq "file" -and $_.name -match '\.(mp4|jpg|txt)$' } | Sort-Object name
Write-Host "   GitHub par $($files.Count) files hain."

Write-Host "2) '$Dest' mein bhej raha hoon (pehle se maujood skip)..." -ForegroundColor Cyan
$copied = 0; $skipped = 0; $failed = 0
foreach ($f in $files) {
  $target = Join-Path $Dest $f.name
  if (Test-Path -LiteralPath $target) { $skipped++; continue }
  $tmp = Join-Path $env:TEMP ("csj_" + $f.name)
  try {
    Invoke-WebRequest -Uri $f.download_url -OutFile $tmp -UseBasicParsing
    if ((Get-Item -LiteralPath $tmp).Length -ne $f.size) { throw "size mismatch" }
    Move-Item -LiteralPath $tmp -Destination $target
    Write-Host "   + $($f.name)" -ForegroundColor Green
    $copied++
  } catch {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
    Write-Host "   ! $($f.name) fail: $($_.Exception.Message)" -ForegroundColor Yellow
    $failed++
  }
}
Write-Host ""
Write-Host "Ho gaya!  Nayi: $copied  |  Pehle se thi (skip): $skipped  |  Fail: $failed" -ForegroundColor Cyan
Write-Host "Folder: $Dest"
if ($failed -gt 0) { Write-Host "Fail wali files ke liye script dobara chalayein." -ForegroundColor Yellow }
