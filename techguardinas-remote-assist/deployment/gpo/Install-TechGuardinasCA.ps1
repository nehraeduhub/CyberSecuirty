<#
.SYNOPSIS
  Makes a Windows PC trust the TechGuardinas Remote internal CA (Edge, Chrome AND Firefox).

.DESCRIPTION
  Run as a GPO computer startup script (or once as administrator on a single PC).
  1. Imports the CA certificate into Local Computer > Trusted Root Certification Authorities
     (used by Edge, Chrome and Windows).
  2. Sets the Firefox enterprise policy ImportEnterpriseRoots=1 so Firefox also trusts
     CAs from the Windows store.
  Idempotent: does nothing if already done. No Internet access is used.

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File \\domain\NETLOGON\TechGuardinasRemote\Install-TechGuardinasCA.ps1 `
     -CertPath \\domain\NETLOGON\TechGuardinasRemote\TechGuardinas-Remote-Internal-CA.crt
#>
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$CertPath)
$ErrorActionPreference = 'Stop'

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath)
$existing = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
if ($existing) {
  Write-Host "CA already trusted: $($cert.Subject) ($($cert.Thumbprint))"
} else {
  Import-Certificate -FilePath $CertPath -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
  Write-Host "CA imported into Trusted Root: $($cert.Subject) ($($cert.Thumbprint))"
}

$ff = 'HKLM:\SOFTWARE\Policies\Mozilla\Firefox\Certificates'
New-Item -Path $ff -Force | Out-Null
New-ItemProperty -Path $ff -Name 'ImportEnterpriseRoots' -Value 1 -PropertyType DWord -Force | Out-Null
Write-Host 'Firefox policy set: Certificates\ImportEnterpriseRoots = 1 (restart Firefox)'
