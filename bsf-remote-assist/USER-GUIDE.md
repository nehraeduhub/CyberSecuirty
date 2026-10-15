# BSF Remote — Installation and User Guide

Version 2.0.0 · Self-hosted remote support on Linux, published across the MPLS network

---

## 1. What you are installing

BSF Remote lets technicians support users' Windows PCs from a web browser, entirely inside your network:

* **Attended support** — the user is at the PC. The technician generates a one-time 9-digit code; the user opens a web page, approves, runs a small support agent and clicks **Connect**; the user is asked again on screen before their desktop, a command prompt or files are opened, and can end the session at any time.
* **Unattended access** — an agent is installed on managed PCs (by GPO). Technicians connect to PCs an administrator has approved and assigned to them, after an MFA code.
* **Remote console in the browser** — screen with mouse and keyboard, multiple monitors, clipboard, file transfer, command terminal, chat, reboot with automatic reconnect.
* **Records** — every session is logged: who, which PC, how it was authorized, what was allowed, start/end, who ended it, outcome.

Everything runs on **one Linux server**: the portal, the remote-control engine (open-source MeshCentral), the relay, the database and the agent downloads. No Internet connection, cloud account or external service is used.

The server is reached by two internal names, for example:

| Name | Used by |
|---|---|
| `remote.bsf.local` | Portal: technicians, administrators, users joining a session |
| `mesh.remote.bsf.local` | Remote engine: the console inside the portal, and the agents on PCs |

Replace `bsf.local` with your internal domain throughout this guide.

---

## 2. Requirements

### Server
| Item | Minimum | Recommended (up to ~2,000 PCs) |
|---|---|---|
| CPU / RAM | 2 vCPU / 4 GB | 4 vCPU / 8 GB |
| Disk | 30 GB | 100 GB (more if session recording is enabled) |
| OS | Ubuntu 22.04/24.04 LTS or RHEL/Rocky/Alma 9 (64-bit) | same |
| Software | Docker Engine + Docker Compose plugin, `openssl`, `curl` | same |
| Network | Static IP reachable from every MPLS site on TCP 443 | same |

### Installing Docker without Internet
On a connected machine with the **same OS version**, download the packages and copy them over:

```bash
# Ubuntu (connected machine, after adding Docker's apt repository)
apt-get download docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# copy the .deb files to the server, then on the server:
sudo apt install ./*.deb && sudo systemctl enable --now docker

# RHEL/Rocky/Alma 9 (connected machine, after adding Docker's dnf repository)
dnf download --resolve docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# on the server:
sudo dnf install ./*.rpm && sudo systemctl enable --now docker
```
Or use your organisation's internal package mirror.

### Client PCs
Windows 10/11 with Edge or Chrome. The **internal CA certificate** must be trusted (section 4.3).

---

## 3. Prepare the installation files

The zip contains the application but **not** the container images (about 2.5 GB). Create them once on any Linux machine that has Docker and Internet access (the "build machine"):

```bash
unzip bsf-remote-assist-setup-2.0.0.zip
cd bsf-remote-assist
./setup.sh build-images
```

This produces `images/bsf-remote-images.tar` and its checksum. Have it scanned by your security team, then copy the **whole `bsf-remote-assist` folder including `images/`** to the server (USB disk, internal file share, `scp`).

> If the server itself may reach your internal package/registry mirrors, you can skip this and run the install with `BUILD_ON_SERVER=1`.

---

## 4. Publish the server on the MPLS network

### 4.1 IP address and routing
Give the server a static IP in a data-centre VLAN that every MPLS site can route to (for example `10.20.30.40`). No NAT is needed. Agents and browsers always connect **to** the server; the server never connects to PCs.

### 4.2 Internal DNS
Create two A records pointing to the server IP, in a zone every site resolves.

On a Windows DNS server (PowerShell, as DNS administrator):
```powershell
Add-DnsServerResourceRecordA -ZoneName "bsf.local" -Name "remote"      -IPv4Address 10.20.30.40
Add-DnsServerResourceRecordA -ZoneName "bsf.local" -Name "mesh.remote" -IPv4Address 10.20.30.40
```
On BIND: `remote IN A 10.20.30.40` and `mesh.remote IN A 10.20.30.40`.

Check from a PC at a remote site: `nslookup remote.bsf.local` and `nslookup mesh.remote.bsf.local`.

### 4.3 Certificate (HTTPS)
Choose one:

* **Your organisation's CA (preferred)** — request a server certificate with both names as Subject Alternative Names. Before installing, place three files in `deploy/certs/` on the server: `fullchain.pem` (server certificate + intermediates), `privkey.pem` (its key), `ca.crt` (root CA). Your PCs probably trust this CA already.
* **Let the installer create one** — if `deploy/certs/` is empty, `setup.sh` creates a dedicated "BSF Remote Internal CA" and the server certificate. You must then distribute the CA to every PC:
  * Group Policy Management → edit a GPO linked to all computers → *Computer Configuration → Policies → Windows Settings → Security Settings → Public Key Policies → Trusted Root Certification Authorities* → **Import** `BSF-Remote-Internal-CA.crt` (created next to `setup.sh`).
  * Single PC for testing: `certutil -addstore -f Root BSF-Remote-Internal-CA.crt` (administrator prompt).
  * Firefox: enable policy *Certificates → ImportEnterpriseRoots*.
  * Keep `deploy/certs/ca.key` safe (copy it offline and remove it from the server once installation is complete).

### 4.4 Firewall rules
| From | To | Port | Why |
|---|---|---|---|
| All MPLS user and PC subnets | Server | **TCP 443** | Portal, console, agents and relay — everything |
| All MPLS subnets | Server | TCP 80 (optional) | Redirects to HTTPS only |
| Server | Domain controllers | TCP 636 | Only if AD login is enabled |
| Server, PCs | NTP server | UDP 123 | Correct time is required for MFA codes |

Nothing needs to be opened **towards** PCs: no RDP (3389), no SMB (445), no WinRM. The installer opens 443/80 on the server's own firewall (ufw/firewalld) if one is active. Full table: `deploy/NETWORK-PORTS.md`.

If the network team uses a proxy for web traffic, add both names to the proxy **bypass** list on PCs (browsers and agents must connect directly).

---

## 5. Install on the Linux server

```bash
cd bsf-remote-assist
sudo ./setup.sh install
```

You will be asked for:
1. **Portal host name** — e.g. `remote.bsf.local`
2. **Engine host name** — press Enter to accept `mesh.remote.bsf.local`
3. **Server IP** — detected automatically; confirm
4. **Administrator user name** — default `bsfadmin`

The installer then checks the server, loads the images, writes `.env` with random secrets, creates or uses the certificate, generates the engine key, opens the firewall, starts all services and confirms that the portal and engine respond. The first administrator password is written to **`ADMIN-CREDENTIALS.txt`** (readable by root only) — note it, then delete the file.

Unattended example:
```bash
sudo ASSUME_YES=1 PORTAL_HOSTNAME=remote.bsf.local MESH_HOSTNAME=mesh.remote.bsf.local SERVER_IP=10.20.30.40 ./setup.sh install
```

The services restart automatically after a server reboot.

**Verify from a PC at another site:** open `https://remote.bsf.local` — you should see the BSF Remote sign-in page with a valid padlock (no certificate warning). Also open `https://mesh.remote.bsf.local` — a sign-in page must appear (it is never used directly; it proves the second name works).

---

## 6. First-time setup (administrator)

Sign in at `https://remote.bsf.local` with the bootstrap account.

1. **Settings → Configure authenticator.** Scan the QR code with an authenticator app (Microsoft Authenticator, Google Authenticator, FreeOTP — all work offline) and enter the 6-digit code.
2. **Users → Create local user** for each technician (role *TECHNICIAN*), auditor (*AUDITOR*) and further administrators. Passwords must be at least 12 characters. *Optional:* Settings → Active Directory/LDAPS, then *Provision AD user* and *Enable*.
3. **Groups & Agents → Create group**, e.g. `HQ-IT`, `Branch-Delhi`. Tick *Record sessions* if your policy requires recordings. Each group has its own agent installer.
4. **Deploy the agent** to the PCs of each group — see section 7.
5. **Device Approval** — PCs appear here as *PENDING* once their agent is running. Check the name/IP and click **Approve**. Unapproved PCs can never be accessed.
6. **Permissions** — choose a technician and a group (or a single device), tick what they may do (*Connect, File transfer, Terminal, Reboot*) and **Save**.
7. Ask every technician to enrol MFA (Settings) before their first unattended connection.

---

## 7. Deploying the agent to Windows PCs

1. **Groups & Agents → windows-x64** next to the group: downloads `BSF-Remote-Agent-<group>.exe`. It contains only the server's internal address and the group identity.
2. Record its hash: `Get-FileHash .\BSF-Remote-Agent-HQ-IT.exe -Algorithm SHA256`.
3. Copy it with `deployment/gpo/Install-BSFRemoteAgent.ps1` to `\\<domain>\NETLOGON\BSFRemote\`.
4. GPO (link to a pilot OU first): *Computer Configuration → Policies → Windows Settings → Scripts → Startup → PowerShell*:
   ```
   -NoProfile -ExecutionPolicy Bypass -File \\<domain>\NETLOGON\BSFRemote\Install-BSFRemoteAgent.ps1 -InstallerPath \\<domain>\NETLOGON\BSFRemote\BSF-Remote-Agent-HQ-IT.exe -Sha256 <hash>
   ```
5. Reboot a pilot PC; it appears under **Device Approval**. Log: `C:\ProgramData\BSFRemote\install.log`.
6. Single PC by hand (administrator prompt): `BSF-Remote-Agent-HQ-IT.exe -fullinstall`.

Removal: `Uninstall-BSFRemoteAgent.ps1 -InstallerPath <same exe>`, then *Revoke* the device in the portal.

---

## 8. Technician guide

### 8.1 Attended support (user is at the PC)
1. **Start Remote Support → Generate session code.** A 9-digit code and a link appear (valid for 10 minutes, single use).
2. Give the user the **code** (phone) or the **link** (internal chat/e-mail).
3. Watch the progress list: *user approved → agent connecting → Connected: PC name*.
4. Click **Open remote console**. The user sees *"<your name> requesting remote desktop access. Grant access?"* and clicks **Yes**.
5. Work in the console (8.3). Terminal and Files each ask the user again.
6. Click **End Session** and type the outcome (e.g. *Resolved — printer driver reinstalled*).

### 8.2 Unattended access (managed PC)
1. **Unattended Access** lists only the PCs you are permitted to use, with Online/Offline status.
2. Click **Connect** next to an online PC and enter your current **6-digit MFA code**.
3. The console opens. A connection bar on the PC shows that a session is in progress.
4. **End Session** when finished, with an outcome note.

### 8.3 The remote console
| Control | What it does |
|---|---|
| **Remote Desktop** | Click *Connect* inside the view. Move the mouse over the screen to type into it. Toolbar below: Ctrl+Alt+Del, clipboard, display selection (multiple monitors), full screen. |
| **Terminal** | Command prompt on the remote PC (if permitted). |
| **Files** | Browse, upload and download files (if permitted). |
| **Device Events** | The engine's event list for the PC. |
| **Chat** | Opens a chat window with the user. |
| **Reboot** | Restarts the PC (if permitted). Unattended: the console shows *Device offline* and reconnects automatically. Attended: the session ends (the user must reconnect). |
| **End Session** | Ends access immediately and records the outcome. |

The top bar shows the PC, mode, session code, online status, elapsed time and the session's end time (sessions are limited to 2 hours by default; the console signs out after 15 minutes of inactivity).

---

## 9. Remote user guide (print and share)

> **Getting help from BSF IT**
> 1. The technician tells you a **9-digit code** or sends a link.
> 2. Open **https://remote.bsf.local/join** and type the code (or click the link).
> 3. Check the technician's name, type your name, tick **I authorize this remote support session**, click **Approve**.
> 4. Click **Download**, open the downloaded file and click **Connect**. Nothing is installed.
> 5. When the technician wants to see your screen, a box asks **Grant access?** — click **Yes**. You will be asked again for a command prompt or files.
> 6. To stop at any time: click **End session** on the web page, or close the support agent window, or click **Disconnect** on the bar at the top of your screen.
> When the session ends the technician has no further access. Close the support agent window.

---

## 10. Auditor guide
* **Sessions → All technicians** lists every session; **Details** shows the full record: technician, PC, how access was authorized (user consent or permission + MFA), the user's on-screen answers, allowed features, times, who ended it and why, outcome, the audit trail and the engine's own events.
* **Audit Log** lists every sign-in, failed sign-in, permission change, device approval, session step and denial, searchable by user or detail.
* Session recordings (if enabled) are kept on the server; see `deploy/DEPLOYMENT.md`.

---

## 11. Operating the server

All commands run in the `bsf-remote-assist` folder on the server.

| Task | Command |
|---|---|
| Status and health | `sudo ./setup.sh status` |
| Stop / start / restart | `sudo ./setup.sh stop` · `start` · `restart` |
| Logs (all, or one service) | `sudo ./setup.sh logs` · `sudo ./setup.sh logs web` |
| Backup (database + engine data) | `sudo ./setup.sh backup` (to `/var/backups/bsf-remote`; set `BACKUP_DIR=` to change) |
| Restore database | `sudo ./deploy/restore-postgres.sh /var/backups/bsf-remote/portal-<date>.dump` |
| Print the CA certificate | `./setup.sh export-ca` |
| Reset the bootstrap admin password | `sudo ./setup.sh reset-admin-password` |
| Emergency: stop all remote access | `sudo docker compose stop meshcentral` |
| Remove (keeps data unless you type PURGE) | `sudo ./setup.sh uninstall` |

Schedule a nightly backup: `echo '30 1 * * * root cd /opt/bsf-remote-assist && ./setup.sh backup' | sudo tee /etc/cron.d/bsf-remote` (adjust the path), and copy the backups off the server.

**Policy settings** (session length, code validity, MFA, clipboard, consent, recording) are in `.env`; after editing run `sudo ./setup.sh restart`. They are explained in `deploy/DEPLOYMENT.md`.

**Updating:** build new images on the build machine (`./setup.sh build-images` with the new version), back up, copy `images/` to the server, `sudo docker load -i images/bsf-remote-images.tar`, `sudo ./setup.sh restart`.

---

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| Browser shows a certificate warning | The CA is not trusted on that PC (4.3), or you opened the IP instead of the host name. |
| Page does not open from a remote site | DNS record (`nslookup`), routing/firewall to TCP 443, proxy bypass for both names. |
| Console area stays blank | `mesh.remote…` blocked or not resolving from the technician's PC. |
| PC never appears in Device Approval | On the PC: service *BSFRemoteAgent* running? `Test-NetConnection mesh.remote.bsf.local -Port 443`. |
| "MFA is required" / "Invalid MFA code" | Enrol in Settings; check the phone's and server's clock (NTP). |
| "You are not authorized for this device" | Device not approved, or no permission for the technician (Permissions page). |
| Attended code "not valid or has expired" | Codes are single-use and valid 10 minutes; generate a new one. |
| Session ends by itself | Two-hour limit, the device was un-approved, the technician account was disabled, or the user ended it — see the session record. |
| Anything else | `sudo ./setup.sh status` and `sudo ./setup.sh logs web worker meshcentral nginx` |

---

## 13. Before going live

The system has been tested end to end on Linux test PCs, including a fully network-isolated run and a run of this installer's Docker deployment. **The two-Windows-PC acceptance test has not yet been performed.** Complete `docs/ACCEPTANCE-TEST.md` §2 on a pilot OU before rolling the agent out widely, and read `docs/STATUS-AND-LIMITATIONS.md` (notably: clipboard policy is global; the attended agent window must be closed by the user after the session; Windows-specific behaviour still to be confirmed).
