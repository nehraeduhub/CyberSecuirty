<#
.SYNOPSIS
  Removes the TechGuardinas Remote agent. Pass the same installer used for installation (it carries the uninstaller).
#>
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$InstallerPath)
$ErrorActionPreference = 'Stop'
$local = Join-Path $env:TEMP 'TechGuardinasRemoteAgent-uninstall.exe'
Copy-Item -Path $InstallerPath -Destination $local -Force
Start-Process -FilePath $local -ArgumentList '-fulluninstall' -Wait
Remove-Item (Join-Path $env:ProgramData 'TechGuardinasRemote') -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'TechGuardinas Remote agent removed. Remove or revoke the device in TechGuardinas Remote > Device Approval.'
