# Offline Data Centre Kit (GLPI)

Run GLPI on your own server with **no internet connection**. **See [EQUIPMENT.md](EQUIPMENT.md)** for what to enable on your Sophos firewall, Radware Alteon, HPE SimpliVity, HPE VM Essentials, Accesleron, HP/Dell servers and Cisco/Dell/HP switches and routers.
 A built-in collector **fetches your devices' details from the network automatically** (SNMP, SSH, WinRM, VMware). You see the results in a rack viewer, an inventory dashboard and the full GLPI GUI.

**Step-by-step production deployment: [DEPLOYMENT-GUIDE.md](../DEPLOYMENT-GUIDE.md)** (also included in the zip).

Addresses below are for the default **HTTPS mode** (`TLS=yes` in `.env`). In HTTP mode, GLPI is `http://<server>/` and the portal is `http://<server>:8080/`.

| What | URL on your server | Used for |
|---|---|---|
| **GLPI** | `https://<server>/` | Main GUI: data centres, server rooms, racks, assets, cables, tickets, contracts |
| **DC Viewer – Monitor** (NOC) | `https://<server>:8443/viewer/` | **No sign-in.** Live online/offline counts, availability, every **category** (Firewall, Load balancer, Router, Switch, Wireless, Server, Storage, Management, Power …) with its health, an **Offline now** list with how long, and every device as a tile with **SSH / RDP / Web**. Pinged every 15 s, refreshed every 10 s; full-screen for wall displays |
| **DC Viewer – Manage devices** | `https://<server>:8443/viewer/devices.html` | Rename (click a name), set the **category** per device or for a selection, add devices by IP, delete, CSV export, with brand, model, serial, MAC |
| **DC Viewer – Scan & settings** | `https://<server>:8443/viewer/scan.html` | Networks to scan, SNMP credentials, scan interval, **Scan now** with progress, and switches for every other feature (sign in as a GLPI Admin/Super-Admin to change) |
| DC Viewer – Racks, Inventory, Status (Grafana) | `…/viewer/racks.html`, `inventory.html`, `status.html` | Off by default; turn them on under *Scan & settings → Features* |
| **Learning library** | `https://<server>:8443/glpi-datacenter-library.html` | NehraEduHub GLPI data centre course, works offline |

```
                    ┌──────────────── your offline server (Docker) ────────────────┐
 (GLPI via :443)    │ glpi      (GLPI 11, Apache, cron)  ◄── inventory ◄───────────┼── GLPI Agent on servers (optional)
                    │   ▲                                                           │
                    │   │ results every N minutes                                   │   SNMP: switches, routers, firewalls,
                    │ collector (GLPI Agent tools) ─────── scans your network ──────┼──►      PDUs, UPS, storage, printers
                    │   │ status.json                                               │   SSH / WinRM: Linux & Windows servers
                    │   ▼                                                           │   vSphere API: ESXi hosts, vCenter
 browser :443/8443► │ portal    (nginx) ── /apirest.php ──► glpi                    │
                    │   ├─ /viewer/  Racks + Inventory dashboard                    │
                    │   └─ library pages                                            │
                    │ db        (MariaDB 11.4)                                      │
                    │                                                               │
                    │ monitor-sync ── GLPI devices with an IP ──► ping targets      │
                    │ prometheus ──► blackbox ── ping / TCP / HTTP every 30 s ──────┼──► every monitored device
                    │            └─► snmp-exporter ── SNMP every 60 s ──────────────┼──► switches, routers, firewall,
                    │                                                               │    SLB, iLO, iDRAC
                    │ grafana   (/grafana/, Status tab) ◄── prometheus              │
                    └───────────────────────────────────────────────────────────────┘
```

---


### Devices and scanning from the browser

1. Open `https://<server>:8443/viewer/scan.html` and sign in with a GLPI **Admin** or **Super-Admin** account.
2. **Networks to scan**: add each network (`192.168.15.0/24`), a range or a single IP. *Find networks from a router* reads a router's interfaces and routes over SNMP and offers each network it knows.
3. **SNMP credentials**: add your read-only community (v2c) or SNMPv3 user. With SNMP, devices come in with brand, model, serial number, MAC and ports; without it they are found by ping only and shown as *Unidentified*.
4. **Save changes**, then **Scan now**. Progress shows on the page; each /24 takes about 1–2 minutes.
5. **Monitor** (`/viewer/`, no sign-in) shows everything live by category. **Manage devices** is where you rename devices, set categories (worked out from brand and model at first) and add devices by IP (one `IP name` per line). Turn *Monitor page without sign-in* off under Features to require a GLPI login.

The settings live in the `dc_settings` Docker volume (`settings.json`, read by the collector and monitor-sync); they are kept across upgrades and included in `scripts/backup.sh`. Networks and credentials in `collector/collector.conf` still work and are used together with the GUI ones. Servers over SSH/WinRM and VMware are still set in `collector.conf` and switched on under *Features*.

## 1. Build the bundle (on a machine with internet)

Requires Docker and `curl`. Run it from this repository:

```bash
./datacenter-offline/scripts/prepare-offline-bundle.sh
# use the newest GLPI Agent instead of the tested version in .env.example:
AGENT_VERSION=latest ./datacenter-offline/scripts/prepare-offline-bundle.sh
```

This creates `dc-offline-bundle-YYYYMMDD.tar.gz` (about 900 MB). It contains:

- Docker images: `glpi/glpi:11.0.11`, `mariadb:11.4`, `nginx:1.27-alpine`, the network collector `dc-collector:1.17` (built from Ubuntu 24.04 and GLPI Agent 1.17), `grafana/grafana-oss:13.0.2`, `prom/prometheus:v3.5.5`, `prom/blackbox-exporter:v0.28.0` and `prom/snmp-exporter:v0.30.1` (versions set in `.env.example`)
- GLPI Agent installers for Linux (`.pl`) and Windows (`.msi`)
- This kit, the website and the learning library
- `SHA256SUMS` so the server can check the copy wasn't corrupted

Copy the file to the server over USB or an internal share.

### Installing Docker offline

The server needs Docker Engine and the compose plugin. On an offline Ubuntu or Debian server, download these `.deb` files on the online machine from
`https://download.docker.com/linux/<ubuntu|debian>/dists/<codename>/pool/stable/amd64/`:
`containerd.io`, `docker-ce`, `docker-ce-cli`, `docker-buildx-plugin`, `docker-compose-plugin`.
Then on the server run `sudo dpkg -i ./*.deb`.
For RHEL, Rocky or Alma, use the `.rpm` files from `https://download.docker.com/linux/rhel/`.

## 2. Install on the offline server

```bash
tar -xzf dc-offline-bundle-YYYYMMDD.tar.gz
cd dc-offline-bundle-YYYYMMDD
sudo ./install-offline.sh
```

The installer:

1. checks the bundle files against `SHA256SUMS` and loads the Docker images (nothing is downloaded)
2. creates `.env` with a random database password
3. starts GLPI, MariaDB, the portal, the collector and the monitoring (Prometheus, Blackbox, Grafana); on first start GLPI installs its database (1–3 minutes)
4. turns on GLPI inventory and the REST API, and allows API access from the Docker network
5. creates `collector/collector.conf` and an SSH key for agentless inventory, random passwords for Grafana `admin` and the read-only GLPI account `dc-monitor`, and this server's address for links
6. asks for a new password for the `glpi` super-admin and offers to disable the demo accounts `tech`, `normal` and `post-only`

Non-interactive: `sudo ADMIN_PASSWORD='…' DISABLE_DEMO_USERS=yes ./install-offline.sh`

Re-running the installer from a newer bundle is how you **upgrade**. It keeps `.env`, your data and your passwords, and only asks for the admin password on the first install.

Ports are in `site/datacenter-offline/.env` (`GLPI_PORT`, `PORTAL_PORT`). After changing them, run `docker compose up -d` in that folder. Image versions always follow the bundle, so installing a newer bundle upgrades the stack.

## 3. Build your data centre in GLPI

You can enter everything in the GLPI GUI. For many racks, use the CSV import:

1. Edit `layout/racks.csv`: data centre, server room, room grid size, rack name, height in U, grid column/row, which way it faces (N/E/S/W), max power (W), max weight (kg).
2. Edit `layout/devices.csv`: rack, device name, type, model, height in U, bottom U position, `front`/`rear` (or `left`/`right` for 0U PDUs), half-width side, power (W), weight (kg), **serial**.
3. Run the import on the server. It needs only Python 3, no extra packages:

```bash
cd site/datacenter-offline
python3 scripts/import_layout.py --url http://127.0.0.1:8081 --user glpi \
    --racks layout/racks.csv --devices layout/devices.csv --dry-run   # preview
python3 scripts/import_layout.py --url http://127.0.0.1:8081 --user glpi \
    --racks layout/racks.csv --devices layout/devices.csv
```

On the server itself, the import talks to GLPI at `http://127.0.0.1:8081` in HTTPS mode, or `http://localhost` in HTTP mode. You can run it again whenever the CSVs change. It matches objects by name, updates what changed and moves devices to their new U positions.

Device `type` values: `server`, `storage`, `switch`, `router`, `firewall`, `pdu`, `ups`, `enclosure`, `patchpanel`, `kvm`, or any GLPI itemtype (`Computer`, `NetworkEquipment`, `PDU`, `PassiveDCEquipment`, `Enclosure`, `Peripheral`, `Monitor`).

> **Fill in the serial number.** GLPI links agent and SNMP inventory to existing assets by **serial number / UUID**, not by name. If you import a server without its serial and its agent reports later, GLPI creates a second asset with the same name. With the serial in the CSV, the inventory updates the asset that is already in the rack.
>
> **Models and rack height.** Inventory sets the real model, for example `PowerEdge R750`. GLPI treats a new model as 1U until you size it. If you leave the CSV `model` column empty, the import sets `units`, `power_w` and `weight_kg` on whatever model the device already has. You can also set `model` to the exact name that inventory shows.

## 4. Automatic collection from the network

The `collector` container fetches device information from your network on a schedule and sends it to GLPI. No software is needed on the devices. Tell it what to scan in **`collector/collector.conf`** (created by the installer from `collector.conf.example`; it holds credentials, so keep it `chmod 600`):

| Setting | What it collects | Needs on the device |
|---|---|---|
| `SNMP_RANGES`, `SNMP_CREDENTIALS` | Switches, routers, firewalls, PDUs, UPS, storage, printers, iLO/iDRAC cards: model, serial, firmware, ports, VLANs, connected neighbours (LLDP/CDP) and MAC tables | SNMP v2c read-only community or SNMPv3 user |
| `REMOTES` | Linux/Unix servers over **SSH**, Windows servers over **WinRM**: hardware, OS, software, disks, network cards | An account that can read inventory; for SSH, the collector's public key |
| `ESX_HOSTS` | VMware ESXi hosts / vCenter: hosts and their virtual machines | A read-only vSphere user |
| `INTERVAL_MINUTES` | How often everything runs (default 60) | – |
| `THREADS`, `SNMP_TIMEOUT` | Parallel scans (default 16) and seconds to wait for each SNMP answer (default 2) | – |

```bash
cd site/datacenter-offline
nano collector/collector.conf                    # your ranges and credentials
docker compose restart collector                 # pick up the changes
docker compose exec collector collect.sh once    # collect now (waits if a run is already going)
docker compose logs -f collector                 # watch progress
```

The Inventory dashboard shows each run's result: what ran, how many results reached GLPI, and why something failed.

**SSH servers.** Add the collector's public key to an inventory account on each server:

```bash
cat collector/ssh/id_ed25519.pub     # copy this
# on each Linux server:
sudo useradd -m inventory && sudo -u inventory mkdir -p ~inventory/.ssh
echo '<public key>' | sudo tee -a ~inventory/.ssh/authorized_keys
```

Then list it in `REMOTES` as `ssh://inventory@10.10.1.21`. The first time a server is seen, its host key is recorded in `collector/ssh/known_hosts`. If a key changes later, the connection fails instead of being trusted silently. Some hardware details, such as serial numbers, come from `dmidecode`, which needs root. Without it, the server is still inventoried, just with fewer details.

**Windows servers.** The agent logs in to WinRM with Basic authentication only, so use a **local** account (domain accounts always fail) and turn on Basic: see EQUIPMENT.md, *Windows servers*. List them as `winrm://inventory:password@10.10.1.40`.

**Login problems.** `scripts/test-remote.sh <ip>` tests one server from `REMOTES` and says what is wrong: port closed, WinRM Basic off, SSH key not authorised, or wrong password.

**Find all subnets automatically.** `scripts/discover-networks.sh [router-ip...] [--community NAME] [--write]` reads this server's networks and the interfaces and routing tables of your routers / L3 switches over SNMP (default: the server's gateway), then prints the ranges to scan. `--write` adds the new ones to `SNMP_RANGES` (backup kept). Networks larger than /16 are skipped (`--max-prefix`).

**Unidentified devices.** Addresses that answer ping/ARP but not SNMP become GLPI *Unmanaged* items ("Unidentified devices" on the dashboard). `scripts/check-unidentified.sh [ip-prefix] [--csv]` probes each one (SNMP, SSH banner, ports 22/80/443/902/3389/5985) and says what it probably is and what to add: `REMOTES` for Linux/Windows servers, `ESX_HOSTS` for ESXi, SNMP for network devices and management cards. Add `--write --ssh-user U --winrm-user U --esx-user U` (any of them; passwords are asked for) to add the Linux, Windows and ESXi ones to `collector.conf` for you.

**Speed.** SNMP discovery checks every address, so a /24 range takes a minute or two. Raise `THREADS` for large networks. Raise `SNMP_TIMEOUT` (default 2 seconds) only for devices behind slow WAN links.

**Network map.** The map is built from the switches' LLDP/CDP neighbour tables and MAC address tables. Enable LLDP or CDP on your switches and include them in `SNMP_RANGES`.

### Optional: GLPI Agent on servers

Instead of SSH/WinRM you can install the agent on each server. It then reports by itself every hour, including installed software and licences.

```bash
sudo ./install-agent-linux.sh http://<glpi-server>/          # Linux (agents/ folder of the bundle)
install-agent-windows.cmd http://<glpi-server>/              # Windows, as Administrator
```

For many Windows hosts, deploy the same `msiexec` command through GPO or SCCM:
`msiexec /i GLPI-Agent-<ver>-x64.msi /quiet SERVER="http://<glpi-server>/" RUNNOW=1 EXECMODE=1`

`scripts/snmp-discover.sh` runs a one-off SNMP scan from any host with the agent installed (`--type=network`), outside the collector.

Collected devices are not placed in racks automatically. Place them in the GLPI GUI (rack → **+** on a free U), or add them to `devices.csv` with the same name and run the import.

## 5. Using the DC Viewer

Open `https://<server>:8443/viewer/` and sign in with your GLPI account. Each user sees only what their GLPI profile allows. **Devices** and **Scan & settings** are always there; Racks, Inventory and Status show when switched on under *Scan & settings → Features*.

### Inventory dashboard

![Inventory dashboard: summary, collection status, charts](docs/inventory-dashboard.png)

- **Filters** (type, last seen, search by name, IP, serial or model) apply to everything on the page.
- **Summary**: device count, share collected automatically, seen in the last 24 hours, **not seen for 7+ days** (devices that may be switched off or removed), and unidentified IPs. Click a tile to filter.
- **Automatic collection**: the latest collector run, step by step, with errors.
- **Charts**: devices by type, last seen, top manufacturers, operating systems, and new devices per day. Click a bar to filter. Each chart has a **Table** view.
- **Network map**: core switch, access switches and what is plugged into them, from collected port connections. Hover for ports and IPs; click a device to open it in GLPI.
- **Devices table**: sortable, with IP, manufacturer, model, serial, OS, rack position and last seen. **Export CSV** saves the filtered list.

![Network map built from switch port connections](docs/network-map.png)

### Racks

![DC Viewer: floor plan, rack elevation and device details](docs/dc-viewer.png)

- **Floor plan**: racks in their grid position. Colour shows how full each rack is, and the arrow shows which way it faces.
- **Rack**: front and rear views. Full-depth equipment mounted on the other side is shown hatched. Side PDUs appear beside the rack. Space, power and weight are shown against the rack's limits.
- **Search**: by name or serial. Matching racks and devices are outlined.
- **Open in GLPI** links take you to the full record. Both views refresh every 5 minutes (`viewer/config.js`).

For a wall screen, create a GLPI user with a read-only profile.

## 6. Device status: up / down (Grafana)

Every device in GLPI that has an IPv4 address is **pinged every 30 seconds**. Nothing extra needs configuring: as soon as the collector or an agent adds a device to GLPI, it is monitored within 5 minutes.

Open the **Status** tab in the DC Viewer (`https://<server>:8443/viewer/status.html`). Sign in to Grafana as `admin` with `GRAFANA_ADMIN_PASSWORD` from `.env`.

![Device status dashboard in Grafana](docs/device-status.png)

The **Device status** dashboard shows:

- **Devices monitored / Up / Down**: the Down tile turns red as soon as anything stops answering
- **Availability, last 24 h** and **median round trip**
- **Devices down now**, with how long each has been down. Click a name to open it in GLPI
- **Up / down history**: one row per device, green UP and red DOWN, so you can see outages and flapping
- **All devices**: status, ping time and 24-hour availability, sortable and filterable
- **Ping round-trip time** (median and 95th percentile) and **slowest devices now**
- **Type** and **Rack** filters at the top, and the time range (default: last 6 hours)

Grafana shows a one-time "what's new" popup to each user the first time they open the full Grafana. Close it once; it doesn't appear in the Status tab.

How it fits together: `monitor-sync` reads devices and IPs from GLPI with the read-only `dc-monitor` account and writes Prometheus targets labelled with name, type, rack and GLPI link. Prometheus asks the Blackbox exporter to ping each one and keeps 90 days of history (`PROMETHEUS_RETENTION`).

### Network & hardware dashboard

![Network & hardware dashboard](docs/network-health.png)

Every network device, firewall, load balancer, iLO and iDRAC in GLPI is also **polled over SNMP every minute**, using the credentials in `collector/collector.conf`. For each device, monitor-sync finds the credential that works and reads the vendor from its sysObjectID. It then adds that vendor's health metrics: **Sophos** (HA state, memory, disk, swap, live users), **Cisco** (CPU), **HPE iLO** (power supplies, temperatures, drives), **Dell iDRAC** (global and storage status, temperatures) and **Dell OS10** (CPU, power supplies).

- **Devices**: SNMP answering, **Health** (OK / Warning / Critical; Unknown when the vendor has no health MIB), uptime, ports up and down
- **Ports down**: ports that are enabled but have no link, with how long they've been down. Shut-down spare ports are not counted
- **Port errors, last hour**: usually a bad cable, optic or duplex mismatch
- **Traffic** and **busiest ports**, **firewall (Sophos)** table, **switch & router CPU**, **hottest sensor per server**, and **server components not OK** (e.g. "Power supply bay 2 – Degraded")
- Filter by **Vendor** and **Device**. Switch between the two dashboards in the Status tab, or use the **Dashboards** link in Grafana

**Checks beyond ping.** Put extra checks in `monitoring/manual/*.yml`. They're picked up within a minute, and `example.yml.disabled` shows the format:

```yaml
- targets: ["10.10.1.21:22"]
  labels: { module: ssh_banner, name: "SRV-WEB-01 SSH", type: Service }
- targets: ["https://10.10.0.5"]
  labels: { module: http_2xx, name: "Core switch web UI", type: Service }
```

The modules are `icmp` (the default), `tcp_connect` (any port), `http_2xx` (web page answers) and `ssh_banner`. Define more in `monitoring/blackbox/blackbox.yml`. `your-services.yml.disabled` has ready-made checks for the Sophos web admin, Alteon VIPs, vCenter, the VME Manager and the Accesleron portal: fill in the addresses and rename it to `.yml`.

**Settings in `.env`:**

| Setting | Default | Meaning |
|---|---|---|
| `GRAFANA_ANONYMOUS` | `false` | `true` shows dashboards without logging in (for wall screens on a trusted network) |
| `MONITOR_EXCLUDE_STATES` | empty | GLPI statuses not to monitor, e.g. `Retired,In stock` |
| `MONITOR_UNIDENTIFIED` | `yes` | Also ping unidentified devices (GLPI Unmanaged items); they show in Status with type *Unidentified* |
| `MONITOR_SYNC_MINUTES` | `5` | How often GLPI devices are re-read |
| `PROMETHEUS_RETENTION` | `90d` | How long to keep history |

After changing them, run `docker compose up -d`. `GRAFANA_ADMIN_PASSWORD` only applies the first time Grafana starts; change it later inside Grafana.

Devices that block ping (some firewalls) show as DOWN. Give them a `tcp_connect` or `http_2xx` check in `monitoring/manual/`, and set their GLPI status to one in `MONITOR_EXCLUDE_STATES` to skip the ping.

## 7. Backup and restore

```bash
./scripts/backup.sh                 # writes backups/<timestamp>/, keeps 14
```

Monitoring history (Prometheus) is not included, and Grafana's dashboards are recreated from `monitoring/` on start.

Copy `backups/` off the server. It contains the database, the GLPI encryption key and `.env`, so keep it as protected as the server.

Restore onto a fresh install:

```bash
gunzip -c backups/<ts>/glpi-db.sql.gz | docker compose exec -T db sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"'
docker compose exec -T glpi tar -C /var/glpi -xzf - < backups/<ts>/glpi-data.tar.gz
docker compose restart glpi
# DC Viewer settings (networks, SNMP credentials, features)
docker compose exec -T manager sh -c 'cat > /settings/settings.json' < backups/<ts>/dc-settings.json
```

## 8. Security checklist

- [ ] `glpi` password changed and demo accounts disabled (the installer offers both)
- [ ] Server firewall allows ports 80, 443 and 8443 (HTTP mode: 80 and 8080) only from admin and NOC networks
- [ ] Grafana `admin` password kept safe; leave `GRAFANA_ANONYMOUS=false` unless the portal is only reachable from the NOC
- [ ] HTTPS on (`TLS=yes`, the default) with a certificate from your internal CA in `tls/server.crt` and `tls/server.key`. The self-signed one is only a start
- [ ] To use the import script from an admin PC, set `API_ADMIN_RANGE_START/END` in `.env`, then run `scripts/configure-glpi.sh`
- [ ] Read-only SNMP credentials, and a dedicated low-privilege inventory account for SSH/WinRM/vSphere
- [ ] `collector/collector.conf` stays `chmod 600` (it holds credentials); SNMP credentials entered in the DC Viewer are stored in the `dc_settings` volume, readable only by root on the server
- [ ] Only GLPI Admin/Super-Admin accounts can change the DC Viewer settings; give NOC staff a Read-Only GLPI profile
- [ ] `backup.sh` scheduled, and backups copied off the server
- [ ] To update GLPI: build a new bundle with a newer `GLPI_VERSION`, run `backup.sh`, then `install-offline.sh` (GLPI updates its database automatically)

## Files

| Path | Purpose |
|---|---|
| `docker-compose.yml`, `.env.example` | The stack and its settings |
| `nginx/default.conf` | Portal: library, viewer, API proxy |
| `viewer/` | DC Viewer: Devices (`index.html`), Scan & settings (`scan.html`), Racks (`racks.html`), Inventory (`inventory.html`) and Status (`status.html`, embeds Grafana); plain HTML/JS/CSS with no external libraries |
| `manager/manager.pl` | DC Viewer management API behind `/api/`: settings (`dc_settings` volume), device status from Prometheus, Scan now |
| `collector/` | Network collector image (`Dockerfile`, `collect.sh`) and `collector.conf.example` |
| `monitoring/` | Prometheus, Blackbox and Grafana config, the Device status and Network & hardware dashboards, the GLPI → ping/SNMP target sync (`targets/glpi-targets.pl`) and extra checks (`manual/`) |
| `EQUIPMENT.md` | Per-device setup for your Sophos, Radware, HPE SimpliVity/VME, Accesleron, HP/Dell servers and Cisco/Dell/HP network gear |
| `scripts/prepare-offline-bundle.sh` | Build the bundle (online machine) |
| `scripts/install-offline.sh` | Install from the bundle (offline server) |
| `scripts/configure-glpi.sh` | Turn on inventory and the API, allow API clients |
| `scripts/import_layout.py` | CSV → GLPI data centres, rooms, racks, devices |
| `scripts/snmp-discover.sh` | One-off SNMP scan → GLPI (outside the collector) |
| `scripts/backup.sh` | Database and files backup |
| `agents/` | Agent install scripts for Linux and Windows |
| `layout/*.csv` | Example layout to edit |
| `docs/` | Screenshots |
