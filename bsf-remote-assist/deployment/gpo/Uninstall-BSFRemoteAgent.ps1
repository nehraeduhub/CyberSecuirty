<#
.SYNOPSIS
  Removes the BSF Remote agent. Pass the same installer used for installation (it carries the uninstaller).
#>
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$InstallerPath)
$ErrorActionPreference = 'Stop'
$local = Join-Path $env:TEMP 'BSFRemoteAgent-uninstall.exe'
Copy-Item -Path $InstallerPath -Destination $local -Force
Start-Process -FilePath $local -ArgumentList '-fulluninstall' -Wait
Remove-Item (Join-Path $env:ProgramData 'BSFRemote') -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'BSF Remote agent removed. Remove or revoke the device in BSF Remote > Device Approval.'
