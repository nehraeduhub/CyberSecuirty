[CmdletBinding()]
param(
  [string]$PortalUrl = 'https://remote.example.local',
  [string]$DeviceId = '',
  [string]$EnrollmentToken = '',
  [string]$AgentVersion = '0.7.0',
  [string]$MeshAgentUrl = '',
  [switch]$InstallMeshAgent
)

$ErrorActionPreference = 'Stop'
$Root = 'C:\ProgramData\BSFRemote'
$Log = Join-Path $Root 'install.log'
New-Item -ItemType Directory -Path $Root -Force | Out-Null
Start-Transcript -Path $Log -Append | Out-Null

try {
  if ([string]::IsNullOrWhiteSpace($DeviceId) -or [string]::IsNullOrWhiteSpace($EnrollmentToken)) {
    throw 'DeviceId and EnrollmentToken are required. Generate them from the BSF Remote administrator portal.'
  }

  $config = @{
    server = $PortalUrl.TrimEnd('/')
    device_id = $DeviceId
    enrollment_token = $EnrollmentToken
    agent_version = $AgentVersion
    heartbeat_seconds = 30
  } | ConvertTo-Json
  Set-Content -Path (Join-Path $Root 'config.json') -Value $config -Encoding UTF8

  # Register the lightweight management heartbeat as a scheduled task.
  # The actual interactive/unattended remote-control capability is provided by MeshCentral.
  $taskName = 'BSF Remote Heartbeat'
  $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
  if ($python) {
    $agent = Join-Path $Root 'bsf_remote_agent.py'
    if (-not (Test-Path $agent)) {
      throw "Missing agent file: $agent"
    }
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$agent`""
    $trigger = New-ScheduledTaskTrigger -AtStartup
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -Force | Out-Null
  } else {
    Write-Warning 'python.exe is not installed. The MeshCentral agent can still be deployed; install the Python heartbeat component separately if required.'
  }

  if ($InstallMeshAgent) {
    if ([string]::IsNullOrWhiteSpace($MeshAgentUrl)) { throw 'MeshAgentUrl is required when -InstallMeshAgent is specified.' }
    $meshInstaller = Join-Path $Root 'mesh-agent.exe'
    Invoke-WebRequest -Uri $MeshAgentUrl -OutFile $meshInstaller -UseBasicParsing
    Unblock-File -Path $meshInstaller -ErrorAction SilentlyContinue
    Start-Process -FilePath $meshInstaller -ArgumentList '/quiet','/norestart' -Wait
  }

  Write-Host 'BSF Remote endpoint deployment completed.'
}
finally {
  Stop-Transcript | Out-Null
}
