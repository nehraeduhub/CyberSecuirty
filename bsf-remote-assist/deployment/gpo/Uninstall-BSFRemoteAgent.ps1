[CmdletBinding()]
param([switch]$RemoveMeshAgent)
$ErrorActionPreference = 'SilentlyContinue'
$taskName = 'BSF Remote Heartbeat'
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
if ($RemoveMeshAgent) {
  Get-CimInstance Win32_Product | Where-Object { $_.Name -match 'MeshCentral|Mesh Agent' } | ForEach-Object { $_.Uninstall() }
}
Remove-Item 'C:\ProgramData\BSFRemote' -Recurse -Force
Write-Host 'BSF Remote management component removed.'
