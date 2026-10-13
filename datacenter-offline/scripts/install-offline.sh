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

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo ./install-offline.sh" >&2; exit 1; }

# Docker Engine from the bundle when the server doesn't have it yet
install_docker() {
  local pkgs="docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
  [ -d "$BUNDLE/docker" ] || { echo "Docker is not installed and the bundle has no docker/ folder (built with SERVER_OS=none)." >&2; exit 1; }
  # shellcheck disable=SC1091
  . /etc/os-release
  read -r t_id t_ver < "$BUNDLE/docker/TARGET"
  if [ "$t_id" != "$ID" ] || [ "${t_ver%%.*}" != "${VERSION_ID%%.*}" ]; then
    echo "WARNING: bundle Docker packages are for $t_id $t_ver, this server is $ID $VERSION_ID." >&2
  fi
  echo "Installing Docker Engine from the bundle..."
  if command -v apt-get >/dev/null; then
    local list=/etc/apt/sources.list.d/dc-offline-docker.list
    echo "deb [trusted=yes] file:$BUNDLE/docker ./" > "$list"
    apt-get update -qq -o Dir::Etc::sourcelist="$list" -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $pkgs
    rm -f "$list"
  elif command -v dnf >/dev/null; then
    # shellcheck disable=SC2086
    dnf install -y -q --disablerepo='*' --repofrompath=dc-offline-docker,"file://$BUNDLE/docker" \
      --enablerepo=dc-offline-docker --nogpgcheck $pkgs
  else
    echo "No apt-get or dnf found: install Docker Engine manually." >&2; exit 1
  fi
  systemctl enable --now docker
}
command -v docker >/dev/null || install_docker
docker compose version >/dev/null || { echo "The docker compose plugin is missing." >&2; exit 1; }
systemctl is-active --quiet docker 2>/dev/null || systemctl start docker 2>/dev/null || true

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

# Upgrade from a bundle extracted into another folder: carry over that
# installation's settings, keys and certificates (its data lives in Docker volumes)
prev=$(docker inspect dc-glpi-1 -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)
if [ -n "$prev" ] && [ "$prev" != "$KIT" ] && [ -f "$prev/.env" ] && [ ! -f .env ]; then
  echo "Existing installation found in $prev - carrying its settings over to this version."
  cp -p "$prev/.env" .env
  [ -f "$prev/collector/collector.conf" ] && cp -p "$prev/collector/collector.conf" collector/
  [ -d "$prev/collector/ssh" ] && cp -rp "$prev/collector/ssh" collector/
  [ -d "$prev/tls" ] && cp -rp "$prev/tls" .
  cp -p "$prev"/monitoring/manual/*.yml monitoring/manual/ 2>/dev/null || true
  for f in "$prev"/layout/*.csv; do [ -f "$f" ] && cp -p "$f" layout/; done
  echo "  Backups stay in $prev/backups. Keep that folder until this version is verified."
fi

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

# Installs made before HTTPS support keep plain HTTP until you switch (see guide)
grep -q '^TLS=' .env || echo "TLS=no" >> .env
tls=$(grep '^TLS=' .env | cut -d= -f2 | tr 'A-Z' 'a-z')

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
server_name=${SERVER_NAME:-$(grep "^SERVER_NAME=" .env | cut -d= -f2)}
host=${server_name:-${ip:-localhost}}
if [ "$tls" = yes ]; then
  setenv GLPI_PUBLIC_URL "https://$host/"
  setenv GRAFANA_ROOT_URL "https://$host:$(grep '^PORTAL_TLS_PORT=' .env | cut -d= -f2 | grep . || echo 8443)/grafana/"
  compose_file=docker-compose.yml:docker-compose.tls.yml
else
  setenv GLPI_PUBLIC_URL "http://$host$(port_suffix "$glpi_port")/"
  setenv GRAFANA_ROOT_URL "http://$host$(port_suffix "${portal_port:-8080}")/grafana/"
  compose_file=docker-compose.yml
fi
if grep -q '^COMPOSE_FILE=' .env; then sed -i "s#^COMPOSE_FILE=.*#COMPOSE_FILE=$compose_file#" .env; else echo "COMPOSE_FILE=$compose_file" >> .env; fi
for key in GRAFANA_ANONYMOUS MONITOR_SYNC_MINUTES PROMETHEUS_RETENTION MONITOR_EXCLUDE_STATES GLPI_LOCAL_PORT PORTAL_TLS_PORT; do
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
  docker run --rm -v "$KIT/collector/ssh:/k:z" --entrypoint ssh-keygen "dc-collector:${AGENT_VERSION}" \
    -q -t ed25519 -N '' -C dc-collector -f /k/id_ed25519
  echo "Created SSH key for agentless inventory: collector/ssh/id_ed25519.pub"
fi

# HTTPS certificate: use tls/server.crt + tls/server.key if you put your own
# there (internal CA), else generate a self-signed one for this server
if [ "$tls" = yes ] && { [ ! -s tls/server.crt ] || [ ! -s tls/server.key ]; }; then
  mkdir -p tls
  fqdn=$(hostname -f 2>/dev/null || hostname)
  san="DNS:$(hostname),DNS:$fqdn,IP:127.0.0.1${ip:+,IP:$ip}"
  [ -n "$server_name" ] && san="DNS:$server_name,$san"
  cert_args=(req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes -subj "/CN=${server_name:-$fqdn}"
             -addext "subjectAltName=$san")
  if command -v openssl >/dev/null; then
    openssl "${cert_args[@]}" -keyout tls/server.key -out tls/server.crt 2>/dev/null
  else
    docker run --rm --user 0:0 -v "$KIT/tls:/t:z" --entrypoint openssl "glpi/glpi:$GLPI_VERSION" \
      "${cert_args[@]}" -keyout /t/server.key -out /t/server.crt 2>/dev/null
  fi
  chmod 600 tls/server.key
  echo "Created a self-signed HTTPS certificate for: $san"
  echo "  (replace tls/server.crt and tls/server.key with one from your internal CA, then: docker compose restart portal)"
fi

# Agents installed on servers need to trust the HTTPS certificate
if [ "$tls" = yes ] && [ -d "$BUNDLE/agents" ]; then
  cp tls/server.crt "$BUNDLE/agents/server-ca.crt" 2>/dev/null || true
fi

# "Open in GLPI" links in the DC Viewer
if [ "$tls" = yes ]; then
  glpi_url="'https://' + location.hostname"
else
  glpi_url="'http://' + location.hostname"
  [ "${GLPI_PORT:-80}" != "80" ] && glpi_url="$glpi_url + ':$GLPI_PORT'"
fi
sed -i "s#^  glpiUrl: .*#  glpiUrl: $glpi_url,#" viewer/config.js

echo "Starting containers..."
docker compose up -d
# Containers that mount single config files keep the old file after an upgrade
# replaces it; recreate them (they hold no data) so they read the new versions
docker compose up -d --force-recreate --no-deps portal blackbox prometheus monitor-sync snmp-exporter >/dev/null

echo "Waiting for GLPI (first start installs the database, ~1-3 minutes)..."
if [ "$tls" = yes ]; then local_glpi="http://127.0.0.1:${GLPI_LOCAL_PORT:-8081}"; else local_glpi="http://127.0.0.1:${GLPI_PORT:-80}"; fi
for _ in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$local_glpi/" || true)
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

if [ "$tls" = yes ]; then
  glpi_link="https://$host/"; portal="https://$host:${PORTAL_TLS_PORT:-8443}"
else
  glpi_link="http://$host$(port_suffix "${GLPI_PORT:-80}")/"; portal="http://$host:${PORTAL_PORT:-8080}"
fi
cat <<MSG

Data centre stack is running.
  GLPI (manage assets, racks, rooms):   $glpi_link
  DC Viewer (read-only rack screens):   $portal/viewer/
  Inventory dashboard:                  $portal/viewer/inventory.html
  Device status (Grafana):              $portal/viewer/status.html
      Grafana login: admin / password in $KIT/.env (GRAFANA_ADMIN_PASSWORD)
  Learning library:                     $portal/glpi-datacenter-library.html
  GLPI Agent installers:                $BUNDLE/agents/
  GLPI for scripts on this server:      $local_glpi

Automatic collection: edit $KIT/collector/collector.conf (IP ranges, SNMP,
SSH/WinRM, VMware), then:  cd $KIT && docker compose restart collector
Collect now:               cd $KIT && docker compose exec collector collect.sh once
Check everything:          $KIT/scripts/verify.sh

Next steps: see DEPLOYMENT-GUIDE.md
MSG
