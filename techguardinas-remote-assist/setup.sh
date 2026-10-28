#!/usr/bin/env bash
# TechGuardinas Remote — installer and control script for a Linux server.
#
#   On a machine WITH Internet (build host):   ./setup.sh build-images   -> images/techguardinas-remote-images.tar
#   On the MPLS server (no Internet needed):   sudo ./setup.sh install
#   Day-2:                                     sudo ./setup.sh status | start | stop | restart | logs [svc]
#                                              sudo ./setup.sh backup | export-ca | reset-admin-password | uninstall
#                                              sudo ./setup.sh set-ports --https 7443 --http 8008
#
# Non-interactive install: set PORTAL_HOSTNAME, MESH_HOSTNAME, SERVER_IP (optional), ADMIN_USER,
# HTTPS_PORT / HTTP_PORT (optional) and ASSUME_YES=1 in the environment.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
ROOT=$(pwd)
VERSION=2.0.0
IMAGES=(techguardinas-remote/web:2.0.0 techguardinas-remote/frontend:2.0.0 techguardinas-remote/meshcentral:1.2.5 postgres:17-alpine redis:7-alpine nginx:1.29-alpine)
IMAGE_TAR=images/techguardinas-remote-images.tar

c_ok() { printf '\033[32m✔\033[0m %s\n' "$*"; }
c_info() { printf '\033[36m➜\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die() { printf '\033[31m✘ %s\033[0m\n' "$*" >&2; exit 1; }
ask() { # ask VAR "Question" default
  local __v=$1 q=$2 d=${3:-} a
  if [ -n "${!__v:-}" ]; then return; fi
  if [ "${ASSUME_YES:-0}" = 1 ]; then printf -v "$__v" '%s' "$d"; return; fi
  read -r -p "$q [$d]: " a; printf -v "$__v" '%s' "${a:-$d}"
}
rand() { openssl rand -base64 "$1" | tr -d '\n/+=' | cut -c1-"$1"; }
need_root() { [ "$(id -u)" = 0 ] || die "Run as root: sudo $0 $*"; }
need_install() { # day-2 commands must run in the folder where 'install' was run
  [ -f .env ] && return
  local where
  where=$(docker ps -a --filter label=com.docker.compose.project=techguardinas-remote \
          --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null | sort -u | head -1)
  if [ -n "$where" ]; then
    die "This folder is not the installed copy. The running install is in: $where  ->  cd $where"
  fi
  die "TechGuardinas Remote is not installed from this folder (no .env) and no running install was found. Run: sudo ./setup.sh install"
}
dc() { docker compose "$@"; }

# ------------------------------------------------------------------ build-images (connected host)
build_images() {
  command -v docker >/dev/null || die "Docker is required"
  c_info "Building TechGuardinas Remote images (needs Internet / internal registry mirrors)…"
  [ -f .env ] || { cp .env.example .env; TMP_ENV=1; }
  dc build
  for i in postgres:17-alpine redis:7-alpine nginx:1.29-alpine; do docker pull "$i"; done
  [ "${TMP_ENV:-0}" = 1 ] && rm -f .env
  mkdir -p images
  c_info "Saving images to $IMAGE_TAR (about 1 GB)…"
  docker save -o "$IMAGE_TAR" "${IMAGES[@]}"
  (cd images && sha256sum techguardinas-remote-images.tar > techguardinas-remote-images.tar.sha256)
  c_ok "Done. Copy this whole folder (with images/) to the MPLS server and run: sudo ./setup.sh install"
}

# ------------------------------------------------------------------ install
port_busy() { # true when another program (not our NGINX container) listens on TCP $1
  ss -ltn "( sport = :$1 )" 2>/dev/null | grep -q LISTEN && ! docker ps --format '{{.Names}}' | grep -q techguardinas-remote-nginx
}

pick_port() { # pick_port VAR default fallback label
  local var=$1 def=$2 alt=$3 label=$4
  [ -z "${!var:-}" ] && [ -f .env ] && printf -v "$var" '%s' "$(sed -n "s/^$var=//p" .env)"
  if [ -z "${!var:-}" ]; then
    if port_busy "$def"; then printf -v "$var" '%s' "$alt"; c_warn "TCP $def is in use by another program; using TCP $alt for $label"
    else printf -v "$var" '%s' "$def"; fi
  fi
  export "${var?}"
}

url_for() { # https URL for a host name on HTTPS_PORT (no ":443" when default)
  if [ "${HTTPS_PORT:-443}" = 443 ]; then echo "https://$1"; else echo "https://$1:$HTTPS_PORT"; fi
}

check_host() {
  [ "$(uname -s)" = Linux ] || die "Linux is required"
  command -v docker >/dev/null || die "Docker Engine is not installed. See USER-GUIDE §2 (offline packages for Ubuntu/RHEL)."
  docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is not installed (package docker-compose-plugin)."
  docker info >/dev/null 2>&1 || { systemctl start docker 2>/dev/null || true; docker info >/dev/null 2>&1 || die "Docker daemon is not running"; }
  systemctl enable docker >/dev/null 2>&1 || true
  command -v openssl >/dev/null || die "openssl is required"
  local mem; mem=$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo)
  [ "$mem" -ge 3 ] || c_warn "Only ${mem} GB RAM; 4 GB or more is recommended"
  local free; free=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
  [ "$free" -ge 10 ] || c_warn "Only ${free} GB free disk; 20 GB or more is recommended"
  # HTTPS (everything) defaults to 443, HTTP (redirect only) to 80. If another program already uses
  # one of them, 7443 / 8008 are used instead. Values in .env (earlier install) are kept.
  pick_port HTTPS_PORT 443 7443 "HTTPS"
  pick_port HTTP_PORT 80 8008 "the HTTP redirect"
  [ "$HTTPS_PORT" != "$HTTP_PORT" ] || die "HTTPS_PORT and HTTP_PORT must differ"
  for p in "$HTTPS_PORT" "$HTTP_PORT"; do
    port_busy "$p" && die "TCP port $p is already in use on this server. Choose another: HTTPS_PORT=<port> HTTP_PORT=<port> ./setup.sh install"
  done
  c_ok "Host checks passed (HTTPS port $HTTPS_PORT, HTTP redirect port $HTTP_PORT)"
}

load_images() {
  local missing=0
  for i in "${IMAGES[@]}"; do docker image inspect "$i" >/dev/null 2>&1 || missing=1; done
  if [ $missing = 0 ]; then c_ok "All images already loaded"; return; fi
  if [ -f "$IMAGE_TAR" ]; then
    c_info "Verifying and loading $IMAGE_TAR…"
    [ -f "$IMAGE_TAR.sha256" ] && (cd images && sha256sum -c techguardinas-remote-images.tar.sha256 >/dev/null) || c_warn "No checksum file; skipping verification"
    docker load -i "$IMAGE_TAR" >/dev/null
    c_ok "Images loaded"
  elif [ "${BUILD_ON_SERVER:-0}" = 1 ]; then
    c_warn "Building images on this server (needs Internet or internal mirrors)"
    local tmp_env=0
    [ -f .env ] || { cp .env.example .env; tmp_env=1; }   # compose needs an .env file to parse the project
    dc build
    for i in postgres:17-alpine redis:7-alpine nginx:1.29-alpine; do docker pull "$i"; done
    [ "$tmp_env" = 1 ] && rm -f .env
    c_ok "Images built"
  else
    die "Images not found. Run './setup.sh build-images' on a connected machine and copy images/ here (or set BUILD_ON_SERVER=1)."
  fi
}

write_env() {
  if [ -f .env ]; then
    grep -q '^HTTPS_PORT=' .env || echo "HTTPS_PORT=$HTTPS_PORT" >> .env
    grep -q '^HTTP_PORT=' .env || echo "HTTP_PORT=$HTTP_PORT" >> .env
    c_ok ".env exists — keeping it"; set -a; . ./.env; set +a; return
  fi
  local ip; ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' || true)
  [ -n "$ip" ] || ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  ask PORTAL_HOSTNAME "Portal host name (internal DNS)" "remote.techguardinas.local"
  ask MESH_HOSTNAME "Remote-engine host name (internal DNS)" "mesh.$PORTAL_HOSTNAME"
  ask SERVER_IP "Server IP address reachable over MPLS" "$ip"
  ask ADMIN_USER "First administrator user name" "tgadmin"
  ADMIN_PASSWORD=$(rand 20)
  umask 077
  sed -e "s/^PORTAL_HOSTNAME=.*/PORTAL_HOSTNAME=$PORTAL_HOSTNAME/" \
      -e "s/^MESH_HOSTNAME=.*/MESH_HOSTNAME=$MESH_HOSTNAME/" \
      -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(rand 50)|" \
      -e "s/^DJANGO_ALLOWED_HOSTS=.*/DJANGO_ALLOWED_HOSTS=$PORTAL_HOSTNAME/" \
      -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=$(url_for "$PORTAL_HOSTNAME")|" \
      -e "s|^PORTAL_PUBLIC_URL=.*|PORTAL_PUBLIC_URL=$(url_for "$PORTAL_HOSTNAME")|" \
      -e "s|^MESH_PUBLIC_URL=.*|MESH_PUBLIC_URL=$(url_for "$MESH_HOSTNAME")|" \
      -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand 32)/" \
      -e "s/^BOOTSTRAP_ADMIN_USERNAME=.*/BOOTSTRAP_ADMIN_USERNAME=$ADMIN_USER/" \
      -e "s/^BOOTSTRAP_ADMIN_PASSWORD=.*/BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASSWORD/" \
      .env.example > .env
  echo "SERVER_IP=$SERVER_IP" >> .env
  echo "HTTPS_PORT=$HTTPS_PORT" >> .env
  echo "HTTP_PORT=$HTTP_PORT" >> .env
  chmod 600 .env
  printf 'Portal: %s\nUser: %s\nPassword: %s\n(Change it after first login. Delete this file afterwards.)\n' \
    "$(url_for "$PORTAL_HOSTNAME")" "$ADMIN_USER" "$ADMIN_PASSWORD" > ADMIN-CREDENTIALS.txt
  chmod 600 ADMIN-CREDENTIALS.txt
  set -a; . ./.env; set +a
  c_ok "Configuration written to .env (secrets generated)"
}

make_certs() {
  local d=deploy/certs
  mkdir -p "$d"
  if [ -s $d/fullchain.pem ] && [ -s $d/privkey.pem ] && [ -s $d/ca.crt ]; then
    c_ok "Using the TLS certificate in $d/"; return
  fi
  c_warn "No certificate supplied in $d/ (fullchain.pem, privkey.pem, ca.crt)."
  local gen=y
  [ "${ASSUME_YES:-0}" = 1 ] || read -r -p "Create a self-contained internal CA and server certificate now? [Y/n]: " gen
  case "${gen:-y}" in n|N) die "Place your organisation's certificate files in $d/ and re-run.";; esac
  umask 077
  local san="DNS:$PORTAL_HOSTNAME,DNS:$MESH_HOSTNAME"
  [ -n "${SERVER_IP:-}" ] && san="$san,IP:$SERVER_IP"
  openssl req -x509 -newkey rsa:3072 -nodes -days 3650 -subj "/CN=TechGuardinas Remote Internal CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -keyout $d/ca.key -out $d/ca.crt 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$PORTAL_HOSTNAME" -keyout $d/privkey.pem -out $d/server.csr 2>/dev/null
  printf "subjectAltName=%s\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\nbasicConstraints=CA:FALSE\n" "$san" > $d/server.ext
  openssl x509 -req -in $d/server.csr -CA $d/ca.crt -CAkey $d/ca.key -CAcreateserial -days 825 -extfile $d/server.ext -out $d/server.crt 2>/dev/null
  cat $d/server.crt $d/ca.crt > $d/fullchain.pem
  rm -f $d/server.csr $d/server.ext
  chmod 644 $d/ca.crt $d/fullchain.pem; chmod 600 $d/privkey.pem $d/ca.key
  cp $d/ca.crt "TechGuardinas-Remote-Internal-CA.crt"
  c_ok "Internal CA and certificate created ($san)"
  c_warn "Distribute TechGuardinas-Remote-Internal-CA.crt to every PC by GPO (USER-GUIDE §4). Keep deploy/certs/ca.key offline/safe."
}

open_firewall() { # open_firewall [old_https old_http] — opens the current ports (and closes old ones if given)
  local p
  if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    for p in "$@"; do ufw delete allow "$p/tcp" >/dev/null 2>&1 || true; done
    ufw allow "$HTTPS_PORT/tcp" >/dev/null; ufw allow "$HTTP_PORT/tcp" >/dev/null; c_ok "ufw: opened TCP $HTTPS_PORT and $HTTP_PORT"
  elif command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
    for p in "$@"; do firewall-cmd -q --permanent --remove-port="$p/tcp" 2>/dev/null || true; done
    firewall-cmd -q --permanent --add-port="$HTTPS_PORT/tcp" --add-port="$HTTP_PORT/tcp" && firewall-cmd -q --reload
    c_ok "firewalld: opened TCP $HTTPS_PORT and $HTTP_PORT"
  else
    c_info "No active host firewall detected (ufw/firewalld); make sure TCP $HTTPS_PORT is allowed to this server"
  fi
}

wait_healthy() {
  c_info "Waiting for the services to come up…"
  local i code1 code2
  for i in $(seq 1 90); do
    code1=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --cacert deploy/certs/ca.crt --resolve "$PORTAL_HOSTNAME:${HTTPS_PORT:-443}:127.0.0.1" "$(url_for "$PORTAL_HOSTNAME")/api/health/" || true)
    code2=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --cacert deploy/certs/ca.crt --resolve "$MESH_HOSTNAME:${HTTPS_PORT:-443}:127.0.0.1" "$(url_for "$MESH_HOSTNAME")/" || true)
    if [ "$code1" = 200 ] && [ "$code2" = 200 ]; then c_ok "Portal and remote engine are answering on HTTPS"; return 0; fi
    sleep 2
  done
  c_warn "Not healthy after 3 minutes (portal=$code1 engine=$code2). Check: sudo ./setup.sh logs"
  return 1
}

install() {
  need_root install
  echo "TechGuardinas Remote $VERSION — installation"
  check_host
  load_images
  write_env
  make_certs
  ./deploy/generate-secrets.sh >/dev/null
  open_firewall
  ./deploy/preflight.sh
  dc up -d --no-build
  wait_healthy || true
  dc exec -T web python manage.py shell -c "from remote_bridge.meshapi import MeshSession
with MeshSession() as s: s.meshes()
print('engine control channel OK')" >/dev/null 2>&1 && c_ok "Portal can control the remote engine" || c_warn "Portal could not reach the engine yet; retry: sudo ./setup.sh status"
  cat <<EOF

────────────────────────────────────────────────────────────────────
 TechGuardinas Remote is running.

 1. Add internal DNS A records (or hosts entries for a first test):
      $PORTAL_HOSTNAME   ->  ${SERVER_IP:-<server IP>}
      $MESH_HOSTNAME     ->  ${SERVER_IP:-<server IP>}
 2. Trust the CA on every PC (GPO): deploy/certs/ca.crt
 3. Firewall: allow TCP $HTTPS_PORT (and optionally $HTTP_PORT) from all sites to this server
 4. Open $(url_for "$PORTAL_HOSTNAME") and sign in with the account in
      $ROOT/ADMIN-CREDENTIALS.txt
 5. Continue with USER-GUIDE §5 (first login and setup).
────────────────────────────────────────────────────────────────────
EOF
}

status() {
  need_install
  set -a; . ./.env; set +a
  dc ps
  wait_healthy
}

backup() { need_root backup; need_install; ./deploy/backup-postgres.sh; }

set_ports() {
  need_root set-ports
  [ -f .env ] || die "Not installed yet. Use: HTTPS_PORT=<port> HTTP_PORT=<port> ./setup.sh install"
  set -a; . ./.env; set +a
  local old_https=${HTTPS_PORT:-443} old_http=${HTTP_PORT:-80} new_https="" new_http=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --https) new_https=${2:-}; shift 2 ;;
      --http) new_http=${2:-}; shift 2 ;;
      *) die "Usage: sudo ./setup.sh set-ports [--https <port>] [--http <port>]" ;;
    esac
  done
  new_https=${new_https:-$old_https}; new_http=${new_http:-$old_http}
  for p in "$new_https" "$new_http"; do [[ "$p" =~ ^[0-9]+$ ]] && [ "$p" -ge 1 ] && [ "$p" -le 65535 ] || die "Invalid port: $p"; done
  [ "$new_https" != "$new_http" ] || die "HTTPS and HTTP ports must differ"
  [ "$new_https" = "$old_https" ] && [ "$new_http" = "$old_http" ] && { c_ok "Ports unchanged (HTTPS $old_https, HTTP $old_http)"; return; }
  for p in "$new_https" "$new_http"; do
    if [ "$p" != "$old_https" ] && [ "$p" != "$old_http" ] && ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN; then die "TCP $p is already in use"; fi
  done
  if [ "$new_https" != "$old_https" ]; then
    c_warn "Changing the HTTPS port from $old_https to $new_https."
    c_warn "Agents already installed on PCs have the old port built in and will go offline:"
    c_warn "re-download the installers (Groups & Agents) and reinstall them (or keep the old port)."
    local a=y; [ "${ASSUME_YES:-0}" = 1 ] || read -r -p "Continue? [y/N]: " a
    case "$a" in y|Y|yes) ;; *) die "Cancelled" ;; esac
  fi
  HTTPS_PORT=$new_https; HTTP_PORT=$new_http
  local portal mesh; portal=$(url_for "$PORTAL_HOSTNAME"); mesh=$(url_for "$MESH_HOSTNAME")
  sed -i -e '/^HTTPS_PORT=/d' -e '/^HTTP_PORT=/d' \
      -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=$portal|" \
      -e "s|^PORTAL_PUBLIC_URL=.*|PORTAL_PUBLIC_URL=$portal|" \
      -e "s|^MESH_PUBLIC_URL=.*|MESH_PUBLIC_URL=$mesh|" .env
  printf 'HTTPS_PORT=%s\nHTTP_PORT=%s\n' "$HTTPS_PORT" "$HTTP_PORT" >> .env
  export HTTPS_PORT HTTP_PORT
  open_firewall "$old_https" "$old_http"
  dc up -d --no-build
  wait_healthy || true
  c_ok "Ports now: HTTPS $HTTPS_PORT, HTTP redirect $HTTP_PORT. Portal: $portal"
}

reset_admin() {
  need_root reset-admin-password
  need_install
  set -a; . ./.env; set +a
  local pw; pw=$(rand 20)
  dc exec -T -e BOOTSTRAP_ADMIN_PASSWORD="$pw" -e BOOTSTRAP_ADMIN_RESET=true web python manage.py bootstrap_admin >/dev/null
  echo "New password for $BOOTSTRAP_ADMIN_USERNAME: $pw"
}

uninstall() {
  need_root uninstall
  local a=""; read -r -p "Stop and remove TechGuardinas Remote containers? Data volumes are KEPT unless you type PURGE: " a
  if [ "$a" = PURGE ]; then dc down -v; c_ok "Removed containers and ALL data"; else dc down; c_ok "Removed containers (data kept)"; fi
}

case "${1:-}" in
  build-images) build_images ;;
  install) install ;;
  status) status ;;
  start) need_root start; dc up -d --no-build ;;
  stop) need_root stop; dc stop ;;
  restart) need_root restart; dc restart ;;
  logs) shift; dc logs --tail=200 -f "$@" ;;
  backup) backup ;;
  set-ports) shift; set_ports "$@" ;;
  export-ca) cat deploy/certs/ca.crt ;;
  reset-admin-password) reset_admin ;;
  uninstall) uninstall ;;
  *) sed -n 2,12p "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
