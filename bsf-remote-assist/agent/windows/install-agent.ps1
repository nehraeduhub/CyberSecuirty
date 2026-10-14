[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$PortalUrl,
  [Parameter(Mandatory=$true)][string]$DeviceId,
  [Parameter(Mandatory=$true)][string]$EnrollmentToken,
  [string]$PythonPath = 'python.exe'
)
$ErrorActionPreference='Stop'
$Root='C:\ProgramData\BSFRemote'
New-Item -ItemType Directory -Path $Root -Force | Out-Null
Copy-Item "$PSScriptRoot\bsf_remote_agent.py" "$Root\bsf_remote_agent.py" -Force
@{server=$PortalUrl.TrimEnd('/');device_id=$DeviceId;enrollment_token=$EnrollmentToken;agent_version='0.7.0';heartbeat_seconds=30} | ConvertTo-Json | Set-Content "$Root\config.json" -Encoding UTF8
$action=New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$Root\bsf_remote_agent.py`""
$trigger=New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName 'BSF Remote Heartbeat' -Action $action -Trigger $trigger -RunLevel Highest -Force | Out-Null
Write-Host 'Installed BSF Remote heartbeat task.'
