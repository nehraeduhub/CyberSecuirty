# NehraEduHub Data Centre Kit: Production Deployment Guide (Offline)

This guide takes you from the zip file to a running, verified, backed-up system in your data centre, on a server with **no internet access**. Follow the steps in order. Each step ends with a check.

| | |
|---|---|
| **You get** | GLPI 11 (assets, racks, rooms, tickets), automatic network collection, the DC Viewer (racks, inventory dashboard), Grafana device status and network/hardware health, and the learning library |
| **Time** | About 1 hour to build the bundle, 30 minutes to install, then 1–2 hours to connect your equipment |
| **People** | A Linux administrator (server and install), plus a network engineer to enable SNMP on devices |

```
 Internet PC (Linux + Docker)              USB / internal share               Offline production server
 ┌────────────────────────────┐      ┌───────────────────────────┐       ┌──────────────────────────────┐
 │ Step 2: build the bundle   │ ───► │ dc-offline-bundle-*.tar.gz│ ───►  │ Steps 3–10: preflight,       │
 │ (images, Docker packages,  │      │ (~1.3 GB, with SHA256SUMS)│       │ install, verify, configure,  │
 │  agents, kit)              │      └───────────────────────────┘       │ back up, go live             │
 └────────────────────────────┘                                          └──────────────────────────────┘
```

---

## Step 1: Plan

### 1.1 Server

| Size | Devices | vCPU | RAM | Disk (`/var/lib/docker` + kit) |
|---|---|---|---|---|
| Small | up to 500 | 4 | 8 GB | 100 GB |
| Medium | up to 3,000 | 8 | 16 GB | 250 GB |
| Large | more than 3,000 | 16 | 32 GB | 500 GB, SSD |

- **Operating system** (tested): **Ubuntu Server 24.04 LTS** (recommended), Ubuntu 22.04, Debian 12, RHEL / Rocky / AlmaLinux 9. A minimal install is enough; x86_64 only.
- A VM is fine. Give it a **static IP**, a **DNS name** (e.g. `dc.nehraeduhub.lan`) and **NTP** from your internal time server.

### 1.2 Network access

**Inbound to the server** (from admin and NOC networks only):

| Port | Used for |
|---|---|
| TCP 443 | GLPI (HTTPS) |
| TCP 8443 | DC Viewer, learning library, Grafana (HTTPS) |
| TCP 80 | Redirect to HTTPS, and GLPI Agents if you use HTTP |
| TCP 22 | Your SSH administration |

**Outbound from the server** to your management networks:

| Port | To | Used for |
|---|---|---|
| ICMP | all devices | up/down monitoring |
| UDP 161 | switches, routers, Sophos, Alteon, iLO, iDRAC, PDUs | SNMP collection and monitoring |
| TCP 22 | Linux / VME hosts | agentless inventory |
| TCP 5985/5986 | Windows servers | agentless inventory (WinRM) |
| TCP 443 | vCenter, portals | VMware inventory, HTTPS checks |

### 1.3 Gather beforehand

- [ ] **Read-only SNMPv3 user** (SHA + AES) for network gear, iLO and iDRAC, or an SNMP v2c read community
- [ ] **vCenter read-only user** (for SimpliVity)
- [ ] An **`inventory` account** on Linux/VME hosts (SSH key login; the kit generates the key)
- [ ] A **WinRM account** for Windows servers (if any)
- [ ] An **HTTPS certificate** for the server name from your internal CA: `server.crt` (with the chain) and `server.key`. Without one, the kit makes a self-signed certificate, which works but browsers will warn
- [ ] A **password vault** entry for the GLPI admin, the Grafana admin and the database (step 6)

See **`datacenter-offline/EQUIPMENT.md`** for what to enable on each kind of device (Sophos, Radware Alteon, HPE SimpliVity, HPE VME, HP/Dell servers, Cisco/Dell/HP switches and routers).

---

## Step 2: Build the offline bundle (internet PC)

You need a Linux PC or VM with internet access, **Docker** and about 10 GB of free disk. On Windows, use WSL2 with Docker Desktop.

```bash
unzip nehraeduhub-dc-kit-*.zip
cd nehraeduhub-dc-kit

# Set the OS of the PRODUCTION server (Docker packages are downloaded for it):
#   ubuntu:24.04 (default) | ubuntu:22.04 | debian:12 | rockylinux:9 | almalinux:9 (use for RHEL 9)
SERVER_OS=ubuntu:24.04 ./datacenter-offline/scripts/prepare-offline-bundle.sh
```

This takes about 15–30 minutes and produces **`dc-offline-bundle-YYYYMMDD.tar.gz`** (about 1.3 GB), containing:

| Folder | Contents |
|---|---|
| `images/` | 8 container images: GLPI, MariaDB, nginx, collector, Grafana, Prometheus, Blackbox exporter, SNMP exporter |
| `docker/` | Docker Engine + Compose packages for your server's OS, with dependencies |
| `agents/` | GLPI Agent for Linux and Windows, plus install scripts |
| `site/` | The kit, viewer, dashboards and learning library |
| `SHA256SUMS` | Checksums, verified on the server |

**Check:** the script ends with `Bundle ready: …/dc-offline-bundle-YYYYMMDD.tar.gz (1.3G)`.

Copy the file to the server over USB, your internal file share, or `scp` through your jump host. Follow your site's rules for bringing in removable media. To check the copy, run `sha256sum dc-offline-bundle-*.tar.gz` on both machines.

---

## Step 3: Prepare the server

1. Install the OS (minimal), set the static IP, hostname and DNS, and point NTP at your time server:
   ```bash
   sudo hostnamectl set-hostname dc.nehraeduhub.lan
   timedatectl          # "System clock synchronized: yes"
   ```
2. Extract the bundle to a **permanent** location. The extracted folder *is* the installation, so don't use `/tmp`:
   ```bash
   sudo mkdir -p /opt/dc
   sudo tar -xzf dc-offline-bundle-YYYYMMDD.tar.gz -C /opt/dc
   cd /opt/dc/dc-offline-bundle-YYYYMMDD
   ```
3. If you have certificates from your internal CA, put them in place **now**:
   ```bash
   sudo mkdir -p site/datacenter-offline/tls
   sudo cp server.crt site/datacenter-offline/tls/server.crt   # certificate + chain
   sudo cp server.key site/datacenter-offline/tls/server.key
   sudo chmod 600 site/datacenter-offline/tls/server.key
   ```

**Check:** `ls /opt/dc/dc-offline-bundle-*/` shows `images docker agents site install-offline.sh SHA256SUMS`.

---

## Step 4: Pre-flight check

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD
sudo ./site/datacenter-offline/scripts/preflight.sh
```

It checks the OS, CPU, RAM, disk, Docker (or the bundled packages), free ports and NTP, and verifies every bundle file against its checksum. It changes nothing.

**Check:** `Result: ready to install`. Fix every **[FAIL]** first, and read the **[WARN]** items.

---

## Step 5: Install

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD
sudo SERVER_NAME=dc.nehraeduhub.lan ./install-offline.sh
```

`SERVER_NAME` is the name users type in the browser. It goes into links and the certificate. Leave it out to use the IP address.

The installer asks for a **new GLPI super-admin password**, and whether to **disable the demo accounts** (answer **Y**). It then:

1. installs Docker from the bundle if it is missing (nothing is downloaded)
2. checks the bundle and loads the 8 images
3. creates `.env` with random passwords (database, Grafana admin, read-only monitoring account)
4. creates an HTTPS certificate if you didn't supply one, plus `collector/collector.conf` and the collector's SSH key
5. starts the 9 containers and waits for GLPI to install its database (1–3 minutes)
6. configures GLPI: inventory and API on, `url_base` set, API reachable only through this server (login always required), manufacturer rules (Compaq → HPE, Alteon → Radware), read-only `dc-monitor` account

It ends with your URLs:

```
GLPI (manage assets, racks, rooms):   https://dc.nehraeduhub.lan/
DC Viewer (read-only rack screens):   https://dc.nehraeduhub.lan:8443/viewer/
Inventory dashboard:                  https://dc.nehraeduhub.lan:8443/viewer/inventory.html
Device status (Grafana):              https://dc.nehraeduhub.lan:8443/viewer/status.html
Learning library:                     https://dc.nehraeduhub.lan:8443/glpi-datacenter-library.html
```

Unattended install: `sudo ADMIN_PASSWORD='…' DISABLE_DEMO_USERS=yes SERVER_NAME=… ./install-offline.sh`

---

## Step 6: Verify and secure the credentials

```bash
sudo /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline/scripts/verify.sh
```

It checks all containers, GLPI (locally and through HTTPS), the redirect, the certificate expiry, an API login, the default password, the collector, monitoring sync, Prometheus targets, backups and disk.

**Check:** `Result: all good`. The warnings "Collector has nothing to collect yet" and "No backup yet" are expected at this point. Steps 7 and 9 clear them.

Then:

1. Open `https://dc.nehraeduhub.lan/` and log in as **glpi** with the password from step 5.
2. Open the Status tab and log in to Grafana as **admin**. Its password is `GRAFANA_ADMIN_PASSWORD` in `site/datacenter-offline/.env`.
3. **Store in your vault**: the GLPI admin password, plus `GRAFANA_ADMIN_PASSWORD`, `GLPI_DB_PASSWORD` and `MONITOR_GLPI_PASSWORD` from `.env`. Keep `.env` at `chmod 600`, as the installer sets it.
4. In GLPI, create **named accounts** for your team: **Administration → Users**. Give a read-only profile to people who only need the viewer.

---

## Step 7: Connect your equipment

### 7.1 Enable SNMP / accounts on devices

Follow **`EQUIPMENT.md`** for each device type: Sophos, Alteon, iLO, iDRAC, Cisco, Dell, HP/Aruba, vCenter, VME hosts.

### 7.2 Tell the collector what to scan

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline
sudo nano collector/collector.conf
```

```bash
INTERVAL_MINUTES=60
SNMP_RANGES="
10.10.0.1-10.10.0.254      # network management: switches, routers, Sophos, Alteon
10.10.9.1-10.10.9.254      # out-of-band: iLO, iDRAC
"
SNMP_CREDENTIALS="
version:3,username:dcmon,authprotocol:sha,authpassword:XXXX,privprotocol:aes,privpassword:YYYY
"
REMOTES="
ssh://inventory@10.10.3.21   # HPE VME host 1
ssh://inventory@10.10.3.22   # HPE VME host 2
"
ESX_HOSTS="
10.10.2.10 svc-glpi@vsphere.local ZZZZ   # vCenter (SimpliVity)
"
```

On every Linux or VME host listed in `REMOTES`, authorise the collector's key: `cat collector/ssh/id_ed25519.pub` (EQUIPMENT.md shows how).

```bash
sudo docker compose restart collector monitor-sync
sudo docker compose exec collector collect.sh once     # first collection now (a /24 takes a few minutes)
```

**Check:**
- **Inventory dashboard → Automatic collection** shows each step **OK**.
- **Status → Up / down** lists your devices within 5 minutes.
- **Status → Network & hardware** shows them 1–2 minutes later.

Nothing appearing? See *Troubleshooting* below.

### 7.3 Racks and rooms

Fill in `layout/racks.csv` and `layout/devices.csv`, and **use the real serial numbers**, so collected devices merge with the rack entries instead of duplicating. Then:

```bash
python3 scripts/import_layout.py --url http://127.0.0.1:8081 --user glpi \
    --racks layout/racks.csv --devices layout/devices.csv --dry-run    # preview
python3 scripts/import_layout.py --url http://127.0.0.1:8081 --user glpi \
    --racks layout/racks.csv --devices layout/devices.csv
```

**Check:** **DC Viewer → Racks** shows the floor plan and your rack elevations.

### 7.4 Service checks (optional, recommended)

Copy `monitoring/manual/your-services.yml.disabled` to `your-services.yml`. Fill in the addresses of the Sophos web admin, Alteon VIPs, vCenter, the VME Manager and the Accesleron portal. These are picked up within a minute.

### 7.5 GLPI Agents (optional)

Only needed for servers you don't inventory over SSH or WinRM. Copy `/opt/dc/dc-offline-bundle-*/agents/` to the server. It already contains `server-ca.crt`, so agents trust your HTTPS certificate. Then:

```bash
sudo ./install-agent-linux.sh https://dc.nehraeduhub.lan/       # Linux
install-agent-windows.cmd https://dc.nehraeduhub.lan/           # Windows, as Administrator
```

---

## Step 8: Firewall the server

Allow ports 443, 8443 and 80 only from admin and NOC networks, and port 22 from your admin hosts. On Ubuntu:

```bash
sudo ufw allow from 10.10.100.0/24 to any port 443,8443,80 proto tcp   # admin/NOC network
sudo ufw allow from 10.10.100.0/24 to any port 22 proto tcp
sudo ufw enable
```

Docker publishes container ports through its own iptables rules, which **bypass ufw**. Enforce the restriction on your network firewall as well, or bind the ports to the admin interface only.

---

## Step 9: Backups

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline
sudo ./scripts/backup.sh            # database + GLPI files + .env -> backups/<timestamp>/, keeps 14
```

Schedule it nightly at 02:00:

```bash
echo "0 2 * * * root /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline/scripts/backup.sh >> /var/log/dc-backup.log 2>&1" \
  | sudo tee /etc/cron.d/dc-backup
```

**Copy `backups/` off the server** every day (backup server, NAS). It contains the GLPI encryption key and passwords, so protect it like the server.

**Test a restore once before go-live**, on a test VM: install the same bundle, then follow *Restore* in `datacenter-offline/README.md`.

---

## Step 10: Go-live checklist

- [ ] `verify.sh` → **all good**, no FAIL
- [ ] Internal CA certificate installed; no browser warning
- [ ] GLPI admin password changed, demo accounts disabled, named user accounts created
- [ ] Passwords from `.env` stored in the vault
- [ ] All equipment types appear in GLPI, the Status tab and Network & hardware
- [ ] Rack layout imported; collected devices merged (no duplicates under **Administration → Inventory**)
- [ ] Backups scheduled, copied off the server, and a restore tested
- [ ] Server firewall and network firewall rules in place
- [ ] NOC knows the URLs; the wall screen shows the Status tab (`GRAFANA_ANONYMOUS=true` only on a closed NOC network)
- [ ] This guide and `.env` location recorded in your operations documentation

---

## Day-2 operations

All commands are run in `/opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline` with `sudo`.

| Task | How |
|---|---|
| Health check | `./scripts/verify.sh` (weekly, or after any change) |
| Status of containers | `docker compose ps` |
| Logs | `docker compose logs --tail 100 glpi` (or collector, monitor-sync, portal, grafana…) |
| Collect now | `docker compose exec collector collect.sh once` |
| Change scan ranges / credentials | edit `collector/collector.conf`, then `docker compose restart collector monitor-sync` |
| Add a service check | add a file to `monitoring/manual/` (no restart needed) |
| Replace the HTTPS certificate | copy the new `tls/server.crt` + `tls/server.key`, then `docker compose restart portal`; also copy `server.crt` to the agents' `server-ca.crt` |
| Stop / start everything | `docker compose stop` / `docker compose start` |
| After a server reboot | nothing to do: Docker starts on boot and the containers restart automatically. Run `verify.sh` |
| Disk space | Prometheus keeps 90 days (`PROMETHEUS_RETENTION` in `.env`); backups keep 14 (`KEEP=` for backup.sh) |

### Upgrading

1. Build a new bundle (step 2) on the internet PC. It contains the newer versions set in `.env.example`.
2. On the server, `sudo ./scripts/backup.sh` in the current installation.
3. Extract the new bundle next to the old one: `sudo tar -xzf dc-offline-bundle-NEW.tar.gz -C /opt/dc`
4. In the new folder, run `sudo ./site/datacenter-offline/scripts/preflight.sh`, then `sudo ./install-offline.sh`.
   The installer **finds the running installation and carries over** its `.env`, collector settings, SSH key, certificates, service checks and rack CSVs. Your data stays in the Docker volumes, and GLPI upgrades its database automatically.
5. Run `sudo ./site/datacenter-offline/scripts/verify.sh`. Update the backup cron path to the new folder.
6. Keep the old folder (and its `backups/`) until you're satisfied, then delete it.

**Rollback:** run `install-offline.sh` from the **old** folder, then restore the backup from step 2 (see README *Restore*). A database that GLPI has already upgraded can't be used by the older version without that restore.

### Switching between HTTP and HTTPS

Set `TLS=yes` or `TLS=no` in `.env`, and clear `GLPI_PUBLIC_URL=` and `GRAFANA_ROOT_URL=` so they're recalculated. Then re-run `sudo ./install-offline.sh` from the bundle folder.

### Uninstall

```bash
sudo docker compose down          # stop and remove containers (data volumes are kept)
sudo docker compose down -v       # ALSO deletes all data: database, files, history
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `preflight.sh`: port 80/443/8443 in use | Another web server is installed | Stop or remove it (`systemctl disable --now apache2 nginx`) or change `PORTAL_TLS_PORT` |
| Install stops at "Waiting for GLPI" | Database still initialising on slow disk | `docker compose logs glpi db`; re-run `install-offline.sh` (safe to repeat) |
| Browser certificate warning | Self-signed certificate | Install your internal CA certificate (Day-2: Replace the HTTPS certificate) |
| Device not in GLPI | SNMP blocked or wrong credentials | Inventory dashboard → collection errors; test from the server: `docker compose exec collector glpi-netinventory --host <ip> --credentials version:2c,community:<c>` |
| Device in **Administration → Inventory → Refused equipment** | Device reports no serial and no MAC over SNMP | Widen the device's SNMP view (ENTITY-MIB, IF-MIB) |
| Same device twice in GLPI | Imported from CSV without a serial, then collected | Put the serial in `devices.csv`, delete the duplicate, re-run the import |
| Device "Not answering SNMP" in Network & hardware | Credential works for collection but not from monitoring | The first matching credential in `SNMP_CREDENTIALS` is used. Check the device's SNMP ACL allows the server |
| Server shows DOWN but works | ICMP blocked by its firewall | Allow ping from the server, or replace it with a `tcp_connect` check and exclude its GLPI status (`MONITOR_EXCLUDE_STATES`) |
| HPE iLO health "Unknown" | Agentless Management not enabled | Enable AMS in iLO (EQUIPMENT.md) |
| Grafana asks to log in inside the Status tab | Separate Grafana account | Log in as admin once, or create Grafana viewer accounts; `GRAFANA_ANONYMOUS=true` for NOC screens |
| `verify.sh`: "glpi still has the default password" | Password never changed | `docker compose exec glpi php bin/console user:reset_password glpi` |
| `verify.sh`: container restarting | Configuration error | `docker compose logs <service>`; most often a typo in `collector.conf` or `monitoring/manual/*.yml` |

---

## Where things are

```
/opt/dc/dc-offline-bundle-YYYYMMDD/
├── install-offline.sh              installer (also used for upgrades)
├── SHA256SUMS                      bundle checksums
├── images/  docker/  agents/       container images, Docker packages, GLPI Agents (+ server-ca.crt)
└── site/
    ├── index.html, glpi-datacenter-library.html     website and learning library
    └── datacenter-offline/                          the installation
        ├── .env                    settings and generated passwords (chmod 600)
        ├── tls/                    HTTPS certificate and key
        ├── collector/collector.conf, collector/ssh/   what to scan, SSH key
        ├── layout/*.csv            rack layout for import_layout.py
        ├── monitoring/manual/      extra service checks
        ├── backups/                nightly backups (copy off the server!)
        ├── scripts/                preflight, verify, backup, import, configure
        ├── EQUIPMENT.md            device-side setup
        └── README.md               full reference
```
