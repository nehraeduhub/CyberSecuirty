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
if [ ! -f .env ]; then
  cp .env.example .env
  pw=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
  sed -i "s/^GLPI_DB_PASSWORD=.*/GLPI_DB_PASSWORD=$pw/" .env
  chmod 600 .env
  echo "Created .env with a random database password."
fi
# Image versions always follow the bundle (this is how upgrades happen)
for key in GLPI_VERSION MARIADB_VERSION NGINX_VERSION AGENT_VERSION; do
  val=$(grep "^$key=" .env.example | cut -d= -f2-)
  if grep -q "^$key=" .env; then
    sed -i "s/^$key=.*/$key=$val/" .env
  else
    echo "$key=$val" >> .env
  fi
done
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

echo "Waiting for GLPI (first start installs the database, ~1-3 minutes)..."
for _ in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${GLPI_PORT:-80}/" || true)
  [ "$code" = 200 ] || [ "$code" = 302 ] && break
  sleep 4
done

./scripts/configure-glpi.sh

console() { docker compose exec -T glpi php bin/console --no-interaction "$@"; }

if [ -z "${ADMIN_PASSWORD:-}" ] && [ -t 0 ]; then
  read -rsp "New password for the GLPI super-admin 'glpi' (empty = keep default, NOT recommended): " ADMIN_PASSWORD; echo
fi
if [ -n "${ADMIN_PASSWORD:-}" ]; then
  console user:reset_password glpi --password="$ADMIN_PASSWORD" >/dev/null
  echo "Password for 'glpi' changed."
else
  echo "WARNING: 'glpi' still uses the default password 'glpi'. Change it at first login."
fi

if [ -z "${DISABLE_DEMO_USERS:-}" ] && [ -t 0 ]; then
  read -rp "Disable the demo accounts tech, normal and post-only? [Y/n] " DISABLE_DEMO_USERS
  DISABLE_DEMO_USERS=${DISABLE_DEMO_USERS:-yes}
fi
case "${DISABLE_DEMO_USERS:-no}" in
  [Yy]*) for u in tech normal post-only; do console user:disable "$u" >/dev/null && echo "Disabled $u"; done ;;
esac

ip=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<MSG

Data centre stack is running.
  GLPI (manage assets, racks, rooms):   http://${ip:-<server-ip>}:${GLPI_PORT:-80}/
  DC Viewer (read-only rack screens):   http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/viewer/
  Inventory dashboard:                  http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/viewer/inventory.html
  Learning library:                     http://${ip:-<server-ip>}:${PORTAL_PORT:-8080}/glpi-datacenter-library.html
  GLPI Agent installers:                $BUNDLE/agents/

Automatic collection: edit $KIT/collector/collector.conf (IP ranges, SNMP,
SSH/WinRM, VMware), then:  cd $KIT && docker compose restart collector
Collect now:               cd $KIT && docker compose exec collector collect.sh once

Next steps: see $KIT/README.md
MSG
