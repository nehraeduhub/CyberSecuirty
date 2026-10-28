# NehraEduHub DC NOC: Production Deployment Guide (Offline)

This guide takes you from the bundle to a running, verified, backed-up network monitor in your data centre, on a server with **no internet access**. Follow the steps in order. Each step ends with a check.

- **You get:** a device list filled by network scans and edited in the browser, a live **Monitor** (online/offline by category), **SSH in a browser tab**, RDP and web shortcuts, Grafana dashboards (up/down history, ports, traffic, hardware health) and the learning library. No sign-in.
- **Time:** about 30 minutes to build the bundle, 15 minutes to install, then about an hour to enable SNMP on your devices and scan.
- **People:** a Linux administrator, plus a network engineer to enable SNMP on devices.

```
 Internet PC (Linux + Docker)              USB / internal share               Offline production server
 ┌────────────────────────────┐      ┌───────────────────────────┐       ┌──────────────────────────────┐
 │ Step 2: build the bundle   │ ───► │ dc-offline-bundle-*.tar.gz│ ───►  │ Steps 3–9: preflight,        │
 │ (images, Docker packages,  │      │ (with SHA256SUMS)         │       │ install, verify, scan,       │
 │  kit)                      │      └───────────────────────────┘       │ back up, go live             │
 └────────────────────────────┘                                          └──────────────────────────────┘
```

---

## Step 1: Plan

### 1.1 Server

| Size | Devices | vCPU | RAM | Disk (`/var/lib/docker` + kit) |
|---|---|---|---|---|
| Small | up to 1,000 | 2 | 4 GB | 40 GB |
| Medium | up to 5,000 | 4 | 8 GB | 100 GB |
| Large | more than 5,000 | 8 | 16 GB | 200 GB, SSD |

- **Operating system** (tested): **Ubuntu Server 24.04 LTS** (recommended), Ubuntu 22.04, Debian 12, RHEL / Rocky / AlmaLinux 9. x86_64 only.
- A VM is fine. Give it a **static IP**, a **DNS name** if you have one, and **NTP** from your internal time server.

### 1.2 Network access

**Inbound to the server** (from admin and NOC networks only — there is no sign-in):

| Port | Used for |
|---|---|
| TCP 443 (`HTTPS_PORT`) | DC NOC: opens the Monitor |
| TCP 8443 (`PORTAL_TLS_PORT`) | DC NOC pages, Grafana, learning library |
| TCP 80 (`HTTP_REDIRECT_PORT`) | Redirect to HTTPS |
| TCP 22 | Your SSH administration of the server |

**Outbound from the server** to your management networks:

| Port | To | Used for |
|---|---|---|
| ICMP | all devices | up/down monitoring, scans |
| UDP 161 | switches, routers, Sophos, Alteon, iLO, iDRAC, PDUs, UPS | SNMP scans and monitoring |
| TCP 22 | devices you open with SSH | browser SSH terminal |
| TCP 5985/5986, 443 | Windows servers, vCenter | optional server / VMware collection |

### 1.3 Gather beforehand

- [ ] **Read-only SNMPv3 user** (SHA + AES) for network gear, iLO and iDRAC, or an SNMP v2c read community
- [ ] The list of your **management networks** (or the IP of your core router: the kit can read them from it)
- [ ] An **HTTPS certificate** from your internal CA (`server.crt` with chain, `server.key`), or accept the self-signed one

See **`datacenter-offline/EQUIPMENT.md`** for what to enable on each kind of device.

---

## Step 2: Build the offline bundle (internet PC)

On a Linux PC with internet and Docker, from the extracted kit:

```bash
cd datacenter-offline
# The OS of the PRODUCTION server (Docker packages are downloaded for it):
#   ubuntu:24.04 (default) | ubuntu:22.04 | debian:12 | rockylinux:9 | almalinux:9 (use for RHEL 9)
SERVER_OS=ubuntu:22.04 ./scripts/prepare-offline-bundle.sh
```

**Check:** `dc-offline-bundle-YYYYMMDD.tar.gz` exists. Copy it to the server (USB stick, internal share).

## Step 3: Prepare the server

```bash
sudo mkdir -p /opt/dc
sudo tar -xzf dc-offline-bundle-YYYYMMDD.tar.gz -C /opt/dc
cd /opt/dc/dc-offline-bundle-YYYYMMDD
```

Type commands one line at a time (pasting several lines can add stray characters such as `^[[200~`).

**Check:** `ls` shows `install-offline.sh`, `images/`, `site/`, `SHA256SUMS`.

## Step 4: Pre-flight check

```bash
sudo ./site/datacenter-offline/scripts/preflight.sh
```

Fix every **FAIL**, then run it again. **WARN** lines are advice.

### If ports 80 or 443 are already in use

Find what uses them with `sudo ss -ltnp | grep -E ':(80|443|8443) '`. Either stop that program (`sudo systemctl disable --now apache2 nginx`), or give this stack other ports:

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline
sudo cp -n .env.example .env
sudo nano .env
#   HTTPS_PORT=9443          the Monitor (change if 443 is taken)
#   HTTP_REDIRECT_PORT=8880  redirect to HTTPS (change if 80 is taken)
#   PORTAL_TLS_PORT=8443     DC NOC pages / Grafana (change too if 8443 is taken)
```

## Step 5: Install

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD
sudo SERVER_NAME=192.168.15.143 ./install-offline.sh     # your server's IP or DNS name
```

It installs Docker from the bundle if needed, checks the bundle, loads the images, creates `.env` and an HTTPS certificate, and starts the containers. At the end it prints the addresses:

```
DC NOC monitoring is running (no sign-in needed: keep these ports on the management network).
  Monitor (live up/down by category):  https://192.168.15.143/viewer/
  Manage devices (edit, add):          https://192.168.15.143:8443/viewer/devices.html
  Scan & settings (networks, SNMP):    https://192.168.15.143:8443/viewer/scan.html
  Grafana dashboards (Status tab):     https://192.168.15.143:8443/grafana/
```

**Upgrading an install that used GLPI:** run the new `install-offline.sh` the same way (or the GitHub updater, Day-2). It copies your devices out of GLPI first, then removes GLPI and MariaDB; their data volumes stay until you delete them.

## Step 6: Verify

```bash
sudo /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline/scripts/verify.sh
```

**Check:** no **FAIL** lines. Open the Monitor address in a browser; with the self-signed certificate, accept the warning once (or install your CA certificate, Day-2).

## Step 7: Scan your networks

### 7.1 Enable SNMP on devices

Follow **`EQUIPMENT.md`** for each device type: Sophos, Alteon, iLO, iDRAC, Cisco, Dell, HP/Aruba. Allow the DC server's IP in each device's SNMP access list.

### 7.2 Scan from the browser

1. Open **Scan & settings** (`https://<server>:8443/viewer/scan.html`).
2. **Networks to scan**: add every network, e.g. `192.168.15.0/24`, `192.168.1.0/24`, `192.168.16.0/24`. Don't know them all? Open *Find networks from a router*, type your core router's IP, and add what it lists.
3. **SNMP credentials**: add your read-only community or SNMPv3 user.
4. **Save changes**, then **Scan now**. The page shows progress; each /24 takes about 1–2 minutes.
5. Open the **Monitor**: live online/offline per category and an *Offline now* list.
6. Under **Manage devices**, **Edit** each important device: name, category, make, model, serial number, location, notes. Devices that only answered ping are in category *Unknown* until you edit them. **Add devices** adds devices by IP (one `IP name` per line).

**Check:** the Monitor shows your devices; firewalls, load balancers, switches and servers are in the right categories (fix any under Manage devices).

### 7.3 Servers and VMware (optional)

For hardware details of servers (Linux over SSH, Windows over WinRM) and VMware hosts, list them in `collector/collector.conf` (`REMOTES`, `ESX_HOSTS`, see the comments in the file and EQUIPMENT.md), then switch on *Collect servers* / *Collect VMware* under **Scan & settings → Features**. Test one server's login with `sudo ./scripts/test-remote.sh <ip>`.

### 7.4 Service checks (optional)

Ping says a device is up; for a web page, VIP or SSH service, add checks in `monitoring/manual/` (see `your-services.yml.disabled`).

## Step 8: Firewall the server

There is no sign-in, so limit who can reach the pages. Example with ufw:

```bash
sudo ufw allow from <admin-network>/24 to any port 443,8443,80 proto tcp
sudo ufw allow from <admin-network>/24 to any port 22 proto tcp
sudo ufw enable
```

## Step 9: Backups

```bash
sudo /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline/scripts/backup.sh
echo '30 2 * * * root /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline/scripts/backup.sh >/dev/null' | sudo tee /etc/cron.d/dc-backup
```

Backups (device list, settings, SSH host keys, `.env`, `collector.conf`, certificate) go to `site/datacenter-offline/backups/`; copy them off the server regularly.

## Step 10: Go-live checklist

- [ ] `verify.sh` shows no FAIL
- [ ] All management networks added and scanned; the Monitor shows the expected number of devices
- [ ] Categories, names and locations of critical devices checked under Manage devices
- [ ] Offline devices explained (blocked ping? add a `tcp_connect` check in `monitoring/manual/`)
- [ ] Server firewall limits access to the admin/NOC networks
- [ ] Daily backup scheduled and copied off the server
- [ ] Wall display: Monitor in full screen (button at the top right)

---

## Day-2 operations

| Task | How |
|---|---|
| Scan now | Scan & settings → **Scan now** (or `docker compose exec collector collect.sh once`) |
| Add / edit / delete devices | Manage devices |
| Change scan networks or SNMP credentials | Scan & settings → Save changes |
| SSH to a device | SSH button on the Monitor or Manage devices (opens a terminal tab) |
| A device was replaced and SSH refuses its new key | Scan & settings → SSH host keys → Remove, after checking why |
| Status of containers / logs | `cd site/datacenter-offline && docker compose ps` / `docker compose logs --tail 100 manager` (or collector, portal, grafana…) |
| Check everything | `scripts/verify.sh` |

### Updating from GitHub

If the server can reach github.com:

```bash
sudo apt install -y git      # once
sudo git clone -b ccr-1e4e396d-l3nt7b https://github.com/nehraeduhub/CyberSecuirty.git /opt/dc/dc-kit-git   # once
sudo bash /opt/dc/dc-kit-git/tools/update-from-github.sh     # every update
```

It saves the current kit (`kit-before-update-*.tar.gz`), copies the new kit over it, keeps your settings and data, and re-runs the installer. Press Ctrl+F5 in the browser afterwards. Without internet on the server, copy a new bundle or zip instead and run `install-offline.sh`.

### Replace the HTTPS certificate

Put `server.crt` (with chain) and `server.key` in `site/datacenter-offline/tls/`, then `docker compose restart portal`.

### Uninstall

```bash
cd /opt/dc/dc-offline-bundle-YYYYMMDD/site/datacenter-offline
sudo docker compose down          # add -v to also delete all data (device list, history)
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Installer: port 80/443/8443 in use | Another web server | Stop it, or set `HTTPS_PORT`, `HTTP_REDIRECT_PORT`, `PORTAL_TLS_PORT` in `.env` (step 4) |
| Browser certificate warning | Self-signed certificate | Install your CA certificate (Day-2) |
| Scan finds devices but no make/model/serial | SNMP blocked or wrong credential | Check the device's SNMP access list allows the server; check the credential under Scan & settings |
| Scan step shows an error | Network unreachable or SNMP problem | The step detail on Scan & settings says why; `docker compose logs collector` |
| Device shows Offline but works | It blocks ping | Add a `tcp_connect` or `http_2xx` check in `monitoring/manual/` |
| SSH tab: "Login failed" | Wrong user/password, or password login disabled on the device | Use the device's local account; enable password login for SSH on the device |
| SSH tab: "host key changed" | Device replaced or reinstalled — or interception | Check with the device owner, then remove the old key under Scan & settings |
| Pages show "Connection lost" / 502 | manager container not running | `docker compose ps`, `docker compose logs manager`, `docker compose up -d` |

## Where things are

```
/opt/dc/dc-offline-bundle-YYYYMMDD/
├── install-offline.sh, DEPLOYMENT-GUIDE.*, README-FIRST.txt
├── images/                     container images (loaded by the installer)
├── docker/                     Docker Engine packages for offline install
└── site/
    ├── index.html, glpi-datacenter-library.html     website and learning library
    └── datacenter-offline/                          the kit
        ├── .env                settings (ports, passwords)  - yours
        ├── collector/collector.conf  optional scan settings / servers / VMware - yours
        ├── tls/                HTTPS certificate - yours
        ├── backups/            backup.sh output
        ├── viewer/  manager/  monitoring/  nginx/  scripts/
        └── docker-compose.yml
Docker volume dc_dc_settings: devices.json, settings.json, SSH host keys
```
