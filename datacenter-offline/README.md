# Offline Data Centre Kit (GLPI)

Run GLPI on your own server with **no internet connection**. A built-in collector **fetches your devices' details from the network automatically** (SNMP, SSH, WinRM, VMware). You see the results in a rack viewer, an inventory dashboard and the full GLPI GUI.

| What | URL on your server | Used for |
|---|---|---|
| **GLPI** | `http://<server>/` | Main GUI: data centres, server rooms, racks, assets, cables, tickets, contracts |
| **DC Viewer – Racks** | `http://<server>:8080/viewer/` | Read-only screen for the NOC or a wall display: floor plan, rack fronts and backs, space/power/weight, device search |
| **DC Viewer – Inventory** | `http://<server>:8080/viewer/inventory.html` | Everything collected from the network: summary, collection status, charts, network map, device table with CSV export |
| **Learning library** | `http://<server>:8080/glpi-datacenter-library.html` | NehraEduHub GLPI data centre course, works offline |

```
                    ┌──────────────── your offline server (Docker) ────────────────┐
 browser ──:80────► │ glpi      (GLPI 11, Apache, cron)  ◄── inventory ◄───────────┼── GLPI Agent on servers (optional)
                    │   ▲                                                           │
                    │   │ results every N minutes                                   │   SNMP: switches, routers, firewalls,
                    │ collector (GLPI Agent tools) ─────── scans your network ──────┼──►      PDUs, UPS, storage, printers
                    │   │ status.json                                               │   SSH / WinRM: Linux & Windows servers
                    │   ▼                                                           │   vSphere API: ESXi hosts, vCenter
 browser ──:8080──► │ portal    (nginx) ── /apirest.php ──► glpi                    │
                    │   ├─ /viewer/  Racks + Inventory dashboard                    │
                    │   └─ library pages                                            │
                    │ db        (MariaDB 11.4)                                      │
                    └───────────────────────────────────────────────────────────────┘
```

---

## 1. Build the bundle (on a machine with internet)

Requires Docker and `curl`. Run it from this repository:

```bash
./datacenter-offline/scripts/prepare-offline-bundle.sh
# use the newest GLPI Agent instead of the tested version in .env.example:
AGENT_VERSION=latest ./datacenter-offline/scripts/prepare-offline-bundle.sh
```

This creates `dc-offline-bundle-YYYYMMDD.tar.gz` (about 650 MB). It contains:

- Docker images: `glpi/glpi:11.0.11`, `mariadb:11.4`, `nginx:1.27-alpine`, and the network collector `dc-collector:1.17`, which is built from Ubuntu 24.04 and GLPI Agent 1.17 (versions set in `.env.example`)
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
3. starts GLPI, MariaDB, the portal and the collector; on first start GLPI installs its database (1–3 minutes)
4. turns on GLPI inventory and the REST API, and allows API access from the Docker network
5. creates `collector/collector.conf` and an SSH key for agentless inventory
6. asks for a new password for the `glpi` super-admin and offers to disable the demo accounts `tech`, `normal` and `post-only`

Non-interactive: `sudo ADMIN_PASSWORD='…' DISABLE_DEMO_USERS=yes ./install-offline.sh`

Ports are in `site/datacenter-offline/.env` (`GLPI_PORT`, `PORTAL_PORT`). After changing them, run `docker compose up -d` in that folder. Image versions always follow the bundle, so installing a newer bundle upgrades the stack.

## 3. Build your data centre in GLPI

You can enter everything in the GLPI GUI. For many racks, use the CSV import:

1. Edit `layout/racks.csv`: data centre, server room, room grid size, rack name, height in U, grid column/row, which way it faces (N/E/S/W), max power (W), max weight (kg).
2. Edit `layout/devices.csv`: rack, device name, type, model, height in U, bottom U position, `front`/`rear` (or `left`/`right` for 0U PDUs), half-width side, power (W), weight (kg), **serial**.
3. Run the import on the server. It needs only Python 3, no extra packages:

```bash
cd site/datacenter-offline
python3 scripts/import_layout.py --url http://localhost --user glpi \
    --racks layout/racks.csv --devices layout/devices.csv --dry-run   # preview
python3 scripts/import_layout.py --url http://localhost --user glpi \
    --racks layout/racks.csv --devices layout/devices.csv
```

You can run the import again whenever the CSVs change. It matches objects by name, updates what changed and moves devices to their new U positions.

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

**Windows servers.** Enable WinRM (`winrm quickconfig`) and list them as `winrm://inventory:password@10.10.1.40` (a local account with read access).

**Speed.** SNMP discovery checks every address, so a /24 range takes a few minutes. Raise `THREADS` for large networks.

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

Open `http://<server>:8080/viewer/` and sign in with your GLPI account. Each user sees only what their GLPI profile allows. Switch between **Racks** and **Inventory** at the top.

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

## 6. Backup and restore

```bash
./scripts/backup.sh                 # writes backups/<timestamp>/, keeps 14
```

Copy `backups/` off the server. It contains the database, the GLPI encryption key and `.env`, so keep it as protected as the server.

Restore onto a fresh install:

```bash
gunzip -c backups/<ts>/glpi-db.sql.gz | docker compose exec -T db sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"'
docker compose exec -T glpi tar -C /var/glpi -xzf - < backups/<ts>/glpi-data.tar.gz
docker compose restart glpi
```

## 7. Security checklist

- [ ] `glpi` password changed and demo accounts disabled (the installer offers both)
- [ ] Server firewall allows ports 80/8080 only from admin and NOC networks
- [ ] HTTPS: put your internal CA certificate on a reverse proxy in front of ports 80 and 8080
- [ ] To use the import script from an admin PC, set `API_ADMIN_RANGE_START/END` in `.env`, then run `scripts/configure-glpi.sh`
- [ ] Read-only SNMP credentials, and a dedicated low-privilege inventory account for SSH/WinRM/vSphere
- [ ] `collector/collector.conf` stays `chmod 600` (it holds credentials)
- [ ] `backup.sh` scheduled, and backups copied off the server
- [ ] To update GLPI: build a new bundle with a newer `GLPI_VERSION`, run `backup.sh`, then `install-offline.sh` (GLPI updates its database automatically)

## Files

| Path | Purpose |
|---|---|
| `docker-compose.yml`, `.env.example` | The stack and its settings |
| `nginx/default.conf` | Portal: library, viewer, API proxy |
| `viewer/` | DC Viewer: Racks (`index.html`) and Inventory (`inventory.html`), plain HTML/JS/CSS with no external libraries |
| `collector/` | Network collector image (`Dockerfile`, `collect.sh`) and `collector.conf.example` |
| `scripts/prepare-offline-bundle.sh` | Build the bundle (online machine) |
| `scripts/install-offline.sh` | Install from the bundle (offline server) |
| `scripts/configure-glpi.sh` | Turn on inventory and the API, allow API clients |
| `scripts/import_layout.py` | CSV → GLPI data centres, rooms, racks, devices |
| `scripts/snmp-discover.sh` | One-off SNMP scan → GLPI (outside the collector) |
| `scripts/backup.sh` | Database and files backup |
| `agents/` | Agent install scripts for Linux and Windows |
| `layout/*.csv` | Example layout to edit |
| `docs/` | Screenshots |
