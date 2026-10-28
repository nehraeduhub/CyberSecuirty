#!/usr/bin/env bash
# Install (or upgrade) the DC NOC monitoring stack on an OFFLINE server from
# the bundle. Installs Docker Engine from the bundle when it is missing.
#
#   tar -xzf dc-offline-bundle-YYYYMMDD.tar.gz
#   cd dc-offline-bundle-YYYYMMDD && sudo ./install-offline.sh
#
# Upgrading from a version with GLPI: the device list is copied out of GLPI,
# then the GLPI and MariaDB containers are removed (their data volumes stay
# until you delete them, see the end of this script's output).
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
  # Only the downloaded payload: kit files under site/ are yours to edit
  echo "Verifying bundle checksums..."
  grep -E '  \./(images|docker)/' SHA256SUMS | sha256sum --quiet -c -
fi

echo "Loading Docker images..."
for f in images/*.tar.gz; do
  [ -e "$f" ] || continue
  gunzip -c "$f" | docker load -q
done

cd "$KIT"

# Bundles built before SNMPv3 AES support: add it to the collector image again
# (loading the bundle's image above replaces a patched one)
bash scripts/patch-collector.sh --no-restart

# Upgrade from a bundle extracted into another folder: carry over that
# installation's settings, keys and certificates (its data lives in Docker volumes)
prev=$(docker inspect dc-portal-1 -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)
if [ -n "$prev" ] && [ "$prev" != "$KIT" ] && [ -f "$prev/.env" ] && [ ! -f .env ]; then
  echo "Existing installation found in $prev - carrying its settings over to this version."
  cp -p "$prev/.env" .env
  [ -f "$prev/collector/collector.conf" ] && cp -p "$prev/collector/collector.conf" collector/
  [ -d "$prev/collector/ssh" ] && cp -rp "$prev/collector/ssh" collector/
  [ -d "$prev/tls" ] && cp -rp "$prev/tls" .
  cp -p "$prev"/monitoring/manual/*.yml monitoring/manual/ 2>/dev/null || true
  echo "  Backups stay in $prev/backups. Keep that folder until this version is verified."
fi

first_install=no
if [ ! -f .env ]; then
  first_install=yes
  cp .env.example .env
  chmod 600 .env
  echo "Created .env."
fi
# Image versions always follow the bundle (this is how upgrades happen)
for key in NGINX_VERSION AGENT_VERSION GRAFANA_VERSION PROMETHEUS_VERSION BLACKBOX_VERSION SNMP_EXPORTER_VERSION; do
  val=$(grep "^$key=" .env.example | cut -d= -f2-)
  if grep -q "^$key=" .env; then
    sed -i "s/^$key=.*/$key=$val/" .env
  else
    echo "$key=$val" >> .env
  fi
done

# A setting added twice (e.g. pasted again) would break the edits below: keep the last one
awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ { last[$1] = NR } { line[NR] = $0; key[NR] = ($0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/) ? $1 : "" }
  END { for (i = 1; i <= NR; i++) if (key[i] == "" || last[key[i]] == i) print line[i] }' .env > .env.tmp \
  && cat .env.tmp > .env && rm -f .env.tmp

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
portal_port=$(grep '^PORTAL_PORT=' .env | cut -d= -f2)
setenv GRAFANA_ADMIN_PASSWORD "$(randpw)"
server_name=${SERVER_NAME:-$(grep "^SERVER_NAME=" .env | cut -d= -f2 || true)}
host=${server_name:-${ip:-localhost}}
setkey() { # key value  (always)
  if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else echo "$1=$2" >> .env; fi
}
envval() { local v; v=$(grep "^$1=" .env | tail -1 | cut -d= -f2 || true); echo "${v:-$2}"; }
# Remember a SERVER_NAME given on the command line for later runs and upgrades
[ -n "$server_name" ] && setkey SERVER_NAME "$server_name"
https_port=$(envval HTTPS_PORT 443)
redirect_port=$(envval HTTP_REDIRECT_PORT 80)
portal_tls_port=$(envval PORTAL_TLS_PORT 8443)
https_suffix() { [ "$1" = 443 ] && echo "" || echo ":$1"; }
# Public URLs follow SERVER_NAME and the ports on every run
if [ "$tls" = yes ]; then
  setkey PUBLIC_URL "https://$host$(https_suffix "$https_port")"
  setkey GRAFANA_ROOT_URL "https://$host:$portal_tls_port/grafana/"
  compose_file=docker-compose.yml:docker-compose.tls.yml
  # nginx redirects must carry the host ports
  printf '# Written by install-offline.sh from HTTPS_PORT\nreturn 301 https://$host%s$request_uri;\n' \
    "$(https_suffix "$https_port")" > nginx/snippets/redirect-https.conf
  printf '# Written by install-offline.sh from PORTAL_TLS_PORT\nerror_page 497 =301 https://$host:%s$request_uri;\n' \
    "$portal_tls_port" > nginx/snippets/redirect-portal.conf
else
  setkey PUBLIC_URL "http://$host$(port_suffix "${portal_port:-8080}")"
  setkey GRAFANA_ROOT_URL "http://$host$(port_suffix "${portal_port:-8080}")/grafana/"
  compose_file=docker-compose.yml
fi
if grep -q '^COMPOSE_FILE=' .env; then sed -i "s#^COMPOSE_FILE=.*#COMPOSE_FILE=$compose_file#" .env; else echo "COMPOSE_FILE=$compose_file" >> .env; fi
for key in GRAFANA_ANONYMOUS MONITOR_SYNC_MINUTES PROMETHEUS_RETENTION PORTAL_TLS_PORT HTTPS_PORT HTTP_REDIRECT_PORT; do
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
  san="DNS:$(hostname)"
  [ "$fqdn" != "$(hostname)" ] && san="$san,DNS:$fqdn"
  san="$san,IP:127.0.0.1${ip:+,IP:$ip}"
  [ -n "$server_name" ] && san="DNS:$server_name,$san"
  cert_args=(req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes -subj "/CN=${server_name:-$fqdn}"
             -addext "subjectAltName=$san")
  if command -v openssl >/dev/null; then
    openssl "${cert_args[@]}" -keyout tls/server.key -out tls/server.crt 2>/dev/null
  else
    docker run --rm --user 0:0 -v "$KIT/tls:/t:z" --entrypoint openssl "dc-collector:$AGENT_VERSION" \
      "${cert_args[@]}" -keyout /t/server.key -out /t/server.crt 2>/dev/null
  fi
  chmod 600 tls/server.key
  echo "Created a self-signed HTTPS certificate for: $san"
  echo "  (replace tls/server.crt and tls/server.key with one from your internal CA, then: docker compose restart portal)"
fi

# Is something listening on this TCP port (any address, IPv4 or IPv6)?
# Reads /proc directly, so it works even where ss/netstat aren't installed.
port_listening() {
  local files=() f
  for f in /proc/net/tcp /proc/net/tcp6; do [ -r "$f" ] && files+=("$f"); done
  awk -v h="$(printf ':%04X' "$1")" 'FNR > 1 && $4 == "0A" && toupper(substr($2, length($2) - 4)) == h { f = 1 } END { exit !f }' \
    "${files[@]}"
}
port_owner() { { ss -Hltnp "sport = :$1" 2>/dev/null | grep -o 'users:(("[^"]*' | head -1 | cut -d'"' -f2; } || true; }
# Stop here with a clear message if another program holds one of our ports
if [ "$tls" = yes ]; then want="$redirect_port $https_port $portal_tls_port"
else want="${PORTAL_PORT:-8080}"; fi
ours=$(docker ps --filter label=com.docker.compose.project=dc --format '{{.Ports}}' 2>/dev/null)
busy=""
for p in $want; do
  port=${p##*:}
  grep -qE "[:.]$port->" <<<"$ours" && continue      # already ours (re-run / upgrade)
  if port_listening "$port"; then
    who=$(port_owner "$port")
    busy="$busy $port${who:+ ($who)}"
  fi
done
if [ -n "$busy" ]; then
  cat >&2 <<MSG

Ports already in use by another program:$busy
Either stop that program (e.g. systemctl disable --now apache2 nginx), or move this
stack to free ports in $KIT/.env, for example:
  HTTPS_PORT=9443
  HTTP_REDIRECT_PORT=8880
then run ./install-offline.sh again. Nothing was started.
MSG
  exit 1
fi

# Upgrade from a version with GLPI: copy its device list into the DC NOC device
# list before GLPI is removed (only if there is no device list yet)
if docker ps --format '{{.Names}}' | grep -qx dc-glpi-1; then
  echo "Copying the device list out of GLPI (this version no longer uses GLPI)..."
  docker volume create dc_dc_settings >/dev/null
  if ! docker run --rm --network dc_default -e GLPI_PASSWORD="${MONITOR_GLPI_PASSWORD:-}" \
       -v dc_dc_settings:/settings -v "$KIT/scripts/migrate-from-glpi.pl:/m.pl:ro,z" \
       --entrypoint perl "dc-collector:$AGENT_VERSION" /m.pl; then
    echo "WARNING: could not copy the devices from GLPI; scan again from Scan & settings." >&2
  fi
  # Monitoring without passwords, as the rest of the DC NOC
  setkey GRAFANA_ANONYMOUS true
  GRAFANA_ANONYMOUS=true
  glpi_removed=yes
fi

echo "Starting containers..."
# --remove-orphans stops and removes services this version no longer has (GLPI, MariaDB)
docker compose up -d --remove-orphans
# Containers that mount single config files keep the old file after an upgrade
# replaces it; recreate them (they hold no data) so they read the new versions
docker compose up -d --force-recreate --no-deps portal blackbox prometheus monitor-sync snmp-exporter manager collector grafana >/dev/null

if [ "$tls" = yes ]; then portal="https://$host:$portal_tls_port"; noc="https://$host$(https_suffix "$https_port")"
else portal="http://$host:${PORTAL_PORT:-8080}"; noc="$portal"; fi
echo "Waiting for the DC NOC to answer..."
for _ in $(seq 1 30); do
  curl -sk -o /dev/null --max-time 5 "${portal/$host/127.0.0.1}/api/features" && break
  sleep 2
done

cat <<MSG

DC NOC monitoring is running (no sign-in needed: keep these ports on the management network).
  Monitor (live up/down by category):  $noc/viewer/     (also $portal/viewer/)
  Manage devices (edit, add):          $portal/viewer/devices.html
  Scan & settings (networks, SNMP):    $portal/viewer/scan.html
  Grafana dashboards (Status tab):     $portal/grafana/
  Learning library:                    $portal/glpi-datacenter-library.html

Next: open Scan & settings, add your networks and SNMP read-only credential,
Save, then Scan now. Check everything: $KIT/scripts/verify.sh
MSG
if [ "${glpi_removed:-no}" = yes ]; then
  cat <<MSG

GLPI and MariaDB were removed. Their data is still in the Docker volumes
dc_glpi_data and dc_db_data; when you no longer need it:
  docker volume rm dc_glpi_data dc_db_data
MSG
fi
