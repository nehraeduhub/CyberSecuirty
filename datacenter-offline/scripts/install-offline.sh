#!/usr/bin/env bash
# Install the data centre stack on an OFFLINE server from the bundle.
# Requires Docker Engine with the compose plugin already installed on the server.
#
#   tar -xzf dc-offline-bundle-YYYYMMDD.tar.gz
#   cd dc-offline-bundle-YYYYMMDD && sudo ./install-offline.sh
#
# Non-interactive: ADMIN_PASSWORD='...' DISABLE_DEMO_USERS=yes sudo -E ./install-offline.sh
set -euo pipefail

BUNDLE=$(cd "$(dirname "$0")" && pwd)
KIT=$BUNDLE/site/datacenter-offline
cd "$BUNDLE"

command -v docker >/dev/null || { echo "Docker is not installed. See README: Installing Docker offline." >&2; exit 1; }
docker compose version >/dev/null || { echo "The docker compose plugin is missing." >&2; exit 1; }

if [ -f SHA256SUMS ]; then
  echo "Verifying bundle checksums..."
  sha256sum --quiet -c SHA256SUMS
fi

echo "Loading Docker images..."
for f in images/*.tar.gz; do
  [ -e "$f" ] || continue
  gunzip -c "$f" | docker load -q
done

cd "$KIT"
first_install=no
if [ ! -f .env ]; then
  first_install=yes
  cp .env.example .env
  pw=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
  sed -i "s/^GLPI_DB_PASSWORD=.*/GLPI_DB_PASSWORD=$pw/" .env
  chmod 600 .env
  echo "Created .env with a random database password."
fi
# Image versions always follow the bundle (this is how upgrades happen)
for key in GLPI_VERSION MARIADB_VERSION NGINX_VERSION AGENT_VERSION GRAFANA_VERSION PROMETHEUS_VERSION BLACKBOX_VERSION SNMP_EXPORTER_VERSION; do
  val=$(grep "^$key=" .env.example | cut -d= -f2-)
  if grep -q "^$key=" .env; then
    sed -i "s/^$key=.*/$key=$val/" .env
  else
    echo "$key=$val" >> .env
  fi
done

# Fill in monitoring settings once: random passwords and this server's address
setenv() { # key value  (only when empty or missing)
  if grep -q "^$1=." .env; then return; fi
  if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else echo "$1=$2" >> .env; fi
}
randpw() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24; }
ip=$(hostname -I 2>/dev/null | awk '{print $1}')
port_suffix() { [ "${1:-80}" = 80 ] && echo "" || echo ":$1"; }
glpi_port=$(grep '^GLPI_PORT=' .env | cut -d= -f2)
portal_port=$(grep '^PORTAL_PORT=' .env | cut -d= -f2)
setenv GRAFANA_ADMIN_PASSWORD "$(randpw)"
setenv MONITOR_GLPI_PASSWORD "$(randpw)"
setenv GLPI_PUBLIC_URL "http://${ip:-localhost}$(port_suffix "$glpi_port")/"
setenv GRAFANA_ROOT_URL "http://${ip:-localhost}$(port_suffix "${portal_port:-8080}")/grafana/"
for key in GRAFANA_ANONYMOUS MONITOR_SYNC_MINUTES PROMETHEUS_RETENTION MONITOR_EXCLUDE_STATES; do
  grep -q "^$key=" .env || grep "^$key=" .env.example >> .env
done
chmod 600 .env

# shellcheck disable=SC1091
set -a; . ./.env; set +a

# Network collector: settings file and SSH key for agentless server inventory
if [ ! -f collector/collector.conf ]; then
  cp collector/collector.conf.example collector/collector.conf
  echo "Created collector/collector.conf - edit it with your IP ranges and credentials."
fi
chmod 600 collector/collector.conf
mkdir -p collector/ssh && chmod 700 collector/ssh
if [ ! -f collector/ssh/id_ed25519 ]; then
  docker run --rm -v "$KIT/collector/ssh:/k" --entrypoint ssh-keygen "dc-collector:${AGENT_VERSION}" \
    -q -t ed25519 -N '' -C dc-collector -f /k/id_ed25519
  echo "Created SSH key for agentless inventory: collector/ssh/id_ed25519.pub"
fi

# "Open in GLPI" links in the DC Viewer
glpi_url="'http://' + location.hostname"
[ "${GLPI_PORT:-80}" != "80" ] && glpi_url="$glpi_url + ':$GLPI_PORT'"
sed -i "s#^  glpiUrl: .*#  glpiUrl: $glpi_url,#" viewer/config.js

echo "Starting containers..."
docker compose up -d
# Containers that mount single config files keep the old file after an upgrade
# replaces it; recreate them (they hold no data) so they read the new versions
docker compose up -d --force-recreate --no-deps portal blackbox prometheus monitor-sync snmp-exporter >/dev/null

echo "Waiting for GLPI (first start installs the database, ~1-3 minutes)..."
for _ in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${GLPI_PORT:-80}/" || true)
  [ "$code" = 200 ] || [ "$code" = 302 ] && break
  sleep 4
done

./scripts/configure-glpi.sh

console() { docker compose exec -T glpi php bin/console --no-interaction "$@"; }
sql() { docker compose exec -T db mariadb -u"$GLPI_DB_USER" -p"$GLPI_DB_PASSWORD" "$GLPI_DB_NAME" -N -e "$1"; }

# Admin password and demo accounts: asked on first install; on upgrades only
# when ADMIN_PASSWORD / DISABLE_DEMO_USERS are given explicitly
if [ -z "${ADMIN_PASSWORD:-}" ] && [ "$first_install" = yes ] && [ -t 0 ]; then
  read -rsp "New password for the GLPI super-admin 'glpi' (empty = keep default, NOT recommended): " ADMIN_PASSWORD; echo
fi
if [ -n "${ADMIN_PASSWORD:-}" ]; then
  if console user:reset_password glpi --password="$ADMIN_PASSWORD" >/dev/null 2>&1; then
    echo "Password for 'glpi' changed."
  else
    echo "Password for 'glpi' not changed (GLPI refused it: already in use or too recent)."
  fi
elif [ "$first_install" = yes ]; then
  echo "WARNING: 'glpi' still uses the default password 'glpi'. Change it at first login."
fi

if [ -z "${DISABLE_DEMO_USERS:-}" ] && [ "$first_install" = yes ] && [ -t 0 ]; then
  read -rp "Disable the demo accounts tech, normal and post-only? [Y/n] " DISABLE_DEMO_USERS
  DISABLE_DEMO_USERS=${DISABLE_DEMO_USERS:-yes}
fi

# Read-only GLPI account the monitoring uses to list devices and their IPs
if [ -z "$(sql "SELECT id FROM glpi_users WHERE name='dc-monitor'")" ]; then
  console user:create dc-monitor --password="$MONITOR_GLPI_PASSWORD" >/dev/null
fi
profile=$(sql "SELECT id FROM glpi_profiles WHERE name IN ('Read-Only','Observer') ORDER BY name='Read-Only' DESC LIMIT 1")
granted=$(sql "SELECT pu.id FROM glpi_profiles_users pu JOIN glpi_users u ON u.id=pu.users_id
               WHERE u.name='dc-monitor' AND pu.profiles_id=${profile:-0} AND pu.entities_id=0 LIMIT 1")
if [ -n "$profile" ] && [ -z "$granted" ]; then
  console user:grant dc-monitor --profile="$profile" --entity=0 --recursive >/dev/null
fi
docker compose restart monitor-sync >/dev/null
echo "Monitoring account 'dc-monitor' (read-only) ready."

case "${DISABLE_DEMO_USERS:-no}" in
  [Yy]*) for u in tech normal post-only; do console user:disable "$u" >/dev/null && echo "Disabled $u"; done ;;
esac

cat <<MSG

Data centre stack is running.
  GLPI (manage assets, racks, rooms):   http://${ip:-<server-ip>}:${GLPI_PORT:-80}/
  DC Viewer (read-only rack screens):   http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/viewer/
  Inventory dashboard:                  http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/viewer/inventory.html
  Device status (Grafana):              http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/viewer/status.html
      Grafana login: admin / password in $KIT/.env (GRAFANA_ADMIN_PASSWORD)
  Learning library:                     http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/glpi-datacenter-library.html
  GLPI Agent installers:                $BUNDLE/agents/

Automatic collection: edit $KIT/collector/collector.conf (IP ranges, SNMP,
SSH/WinRM, VMware), then:  cd $KIT && docker compose restart collector
Collect now:               cd $KIT && docker compose exec collector collect.sh once

Next steps: see $KIT/README.md
MSG
