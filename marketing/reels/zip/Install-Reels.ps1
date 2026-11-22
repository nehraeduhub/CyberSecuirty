# Tech Guardians reels: copy the new reels (female + male voice, 1x) into the laptop folder.
# Usage:  powershell -ExecutionPolicy Bypass -File Install-Reels.ps1 [-Dest "G:\My Drive\TG Reels"] [-SkipPosted]
# Each <topic>.mp4 / <topic>.jpg replaces the file with the same name, or a renamed one like "✅ posted · <topic>.mp4"
# (that name is kept). -SkipPosted leaves the "posted" files untouched.
param([string]$Dest = "G:\My Drive\TG Reels", [switch]$SkipPosted)

$src = $PSScriptRoot
$zips = Get-ChildItem $src -Filter "TechGuardians-Reels-*.zip"
"ZIP found: $($zips.Count) (expected 19)"
if ($zips.Count -eq 0) { "No ZIP files next to this script."; exit 1 }
if (-not (Test-Path $Dest)) { New-Item -ItemType Directory $Dest | Out-Null }

$tmp = Join-Path $env:TEMP "TG-new"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
$zips | ForEach-Object { Expand-Archive $_.FullName -DestinationPath $tmp -Force }

$replaced = 0; $added = 0; $skipped = 0
$existing = Get-ChildItem $Dest -File
Get-ChildItem $tmp -File | Where-Object { $_.Extension -in '.mp4', '.jpg' } | ForEach-Object {
  $new = $_
  $old = $existing | Where-Object { $_.Name -eq $new.Name -or $_.Name.EndsWith(" · " + $new.Name) }
  if ($SkipPosted -and ($old | Where-Object { $_.Name -ne $new.Name })) { $skipped++; return }
  if ($old) { foreach ($o in $old) { Copy-Item $new.FullName $o.FullName -Force }; $replaced++ }
  else { Copy-Item $new.FullName (Join-Path $Dest $new.Name); $added++ }
}
Remove-Item $tmp -Recurse -Force
"Replaced: $replaced   New: $added   Skipped (posted): $skipped   Total: $($replaced + $added + $skipped) (expected 118)"
