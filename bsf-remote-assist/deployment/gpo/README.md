# Windows deployment of the BSF Remote agent (GPO)

The agent is the **official MeshCentral agent** (`MeshService64.exe`, signed by MeshCentral's code-signing
certificate generated on *your* server), with the device group and internal server address embedded by
your own MeshCentral server. There is no separate BSF heartbeat agent.

1. In BSF Remote, **Groups & Agents → Create group** (e.g. `HQ-IT`). This creates the matching
   MeshCentral device group.
2. Download `windows-x64` for that group. Record its hash: `Get-FileHash BSF-Remote-Agent-HQ-IT.exe -Algorithm SHA256`.
3. Copy the installer and `Install-BSFRemoteAgent.ps1` to `\\<domain>\NETLOGON\BSFRemote\` (read-only for
   Domain Computers, write only for deployment administrators).
4. Create a GPO linked to a **pilot OU** first:
   Computer Configuration → Policies → Windows Settings → Scripts → Startup →
   `powershell.exe` with parameters
   `-NoProfile -ExecutionPolicy Bypass -File \\<domain>\NETLOGON\BSFRemote\Install-BSFRemoteAgent.ps1 -InstallerPath \\<domain>\NETLOGON\BSFRemote\BSF-Remote-Agent-HQ-IT.exe -Sha256 <hash>`
5. Reboot (or `gpupdate /force` and reboot) a pilot PC; check `C:\ProgramData\BSFRemote\install.log`.
6. The PC appears in **Device Approval** as *pending*. Approve it, then grant technicians access to the
   group or device under **Permissions**. Until both happen, nobody can connect to it.
7. Expand the GPO to further OUs in batches.

Each group needs its own installer (the group identity is inside it). The installer contains no secret that
grants access: a device that registers with a copied installer still needs administrator approval.

Agent network requirement: outbound TCP 443 to the MeshCentral host name only. No inbound ports, RDP or SMB
are needed on endpoints.
