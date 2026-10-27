<#
.SYNOPSIS
  Installs the TechGuardinas Remote (official MeshCentral) agent on a Windows endpoint for unattended access.

.DESCRIPTION
  Run as a GPO computer startup script. The installer is the file an administrator downloaded from
  TechGuardinas Remote > Groups & Agents for one device group (TechGuardinas-Remote-Agent-<group>.exe). It already contains
  only the internal server address and the group identity; no enrollment token or password is needed.

  The script copies the installer from an internal share, verifies its SHA-256 hash, and installs the agent
  as a service with `-fullinstall`. It is idempotent: if the service already exists it does nothing.
  No Internet access is used.

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File \\domain\NETLOGON\TechGuardinasRemote\Install-TechGuardinasRemoteAgent.ps1 `
     -InstallerPath \\domain\NETLOGON\TechGuardinasRemote\TechGuardinas-Remote-Agent-HQ-IT.exe -Sha256 <hash>
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$InstallerPath,
  [Parameter(Mandatory = $true)][string]$Sha256,
  [string]$ServiceName = 'TechGuardinasRemoteAgent'
)
$ErrorActionPreference = 'Stop'
$Root = Join-Path $env:ProgramData 'TechGuardinasRemote'
New-Item -ItemType Directory -Path $Root -Force | Out-Null
Start-Transcript -Path (Join-Path $Root 'install.log') -Append | Out-Null
try {
  if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Service $ServiceName already installed; nothing to do."
    return
  }
  $local = Join-Path $Root 'TechGuardinasRemoteAgent-installer.exe'
  Copy-Item -Path $InstallerPath -Destination $local -Force
  $actual = (Get-FileHash -Path $local -Algorithm SHA256).Hash
  if ($actual -ne $Sha256.ToUpperInvariant()) { throw "SHA-256 mismatch: expected $Sha256, got $actual" }
  $sig = Get-AuthenticodeSignature -FilePath $local
  Write-Host "Authenticode status: $($sig.Status) ($($sig.SignerCertificate.Subject))"
  $p = Start-Process -FilePath $local -ArgumentList '-fullinstall' -Wait -PassThru
  Write-Host "Installer exit code: $($p.ExitCode)"
  Start-Sleep -Seconds 5
  if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) { throw "Service $ServiceName not found after install" }
  Write-Host 'TechGuardinas Remote agent installed. The device appears in TechGuardinas Remote > Device Approval and must be approved there.'
} finally {
  Stop-Transcript | Out-Null
}
