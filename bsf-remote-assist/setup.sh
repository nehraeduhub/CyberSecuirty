#!/usr/bin/env bash
# BSF Remote — installer and control script for a Linux server.
#
#   On a machine WITH Internet (build host):   ./setup.sh build-images   -> images/bsf-remote-images.tar
#   On the MPLS server (no Internet needed):   sudo ./setup.sh install
#   Day-2:                                     sudo ./setup.sh status | start | stop | restart | logs [svc]
#                                              sudo ./setup.sh backup | export-ca | reset-admin-password | uninstall
#
# Non-interactive install: set PORTAL_HOSTNAME, MESH_HOSTNAME, SERVER_IP (optional), ADMIN_USER and
# ASSUME_YES=1 in the environment.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
ROOT=$(pwd)
VERSION=2.0.0
IMAGES=(bsf-remote/web:2.0.0 bsf-remote/frontend:2.0.0 bsf-remote/meshcentral:1.2.5 postgres:17-alpine redis:7-alpine nginx:1.29-alpine)
IMAGE_TAR=images/bsf-remote-images.tar

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
dc() { docker compose "$@"; }

# ------------------------------------------------------------------ build-images (connected host)
build_images() {
  command -v docker >/dev/null || die "Docker is required"
  c_info "Building BSF Remote images (needs Internet / internal registry mirrors)…"
  [ -f .env ] || { cp .env.example .env; TMP_ENV=1; }
  dc build
  for i in postgres:17-alpine redis:7-alpine nginx:1.29-alpine; do docker pull "$i"; done
  [ "${TMP_ENV:-0}" = 1 ] && rm -f .env
  mkdir -p images
  c_info "Saving images to $IMAGE_TAR (about 1 GB)…"
  docker save -o "$IMAGE_TAR" "${IMAGES[@]}"
  (cd images && sha256sum bsf-remote-images.tar > bsf-remote-images.tar.sha256)
  c_ok "Done. Copy this whole folder (with images/) to the MPLS server and run: sudo ./setup.sh install"
}

# ------------------------------------------------------------------ install
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
  for p in 80 443; do
    if ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN && ! docker ps --format '{{.Names}}' | grep -q bsf-remote-nginx; then
      die "TCP port $p is already in use on this server. Stop that service first."
    fi
  done
  c_ok "Host checks passed"
}

load_images() {
  local missing=0
  for i in "${IMAGES[@]}"; do docker image inspect "$i" >/dev/null 2>&1 || missing=1; done
  if [ $missing = 0 ]; then c_ok "All images already loaded"; return; fi
  if [ -f "$IMAGE_TAR" ]; then
    c_info "Verifying and loading $IMAGE_TAR…"
    [ -f "$IMAGE_TAR.sha256" ] && (cd images && sha256sum -c bsf-remote-images.tar.sha256 >/dev/null) || c_warn "No checksum file; skipping verification"
    docker load -i "$IMAGE_TAR" >/dev/null
    c_ok "Images loaded"
  elif [ "${BUILD_ON_SERVER:-0}" = 1 ]; then
    c_warn "Building images on this server (needs Internet or internal mirrors)"
    dc build && for i in postgres:17-alpine redis:7-alpine nginx:1.29-alpine; do docker pull "$i"; done
  else
    die "Images not found. Run './setup.sh build-images' on a connected machine and copy images/ here (or set BUILD_ON_SERVER=1)."
  fi
}

write_env() {
  if [ -f .env ]; then c_ok ".env exists — keeping it"; set -a; . ./.env; set +a; return; fi
  local ip; ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' || true)
  [ -n "$ip" ] || ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  ask PORTAL_HOSTNAME "Portal host name (internal DNS)" "remote.bsf.local"
  ask MESH_HOSTNAME "Remote-engine host name (internal DNS)" "mesh.$PORTAL_HOSTNAME"
  ask SERVER_IP "Server IP address reachable over MPLS" "$ip"
  ask ADMIN_USER "First administrator user name" "bsfadmin"
  ADMIN_PASSWORD=$(rand 20)
  umask 077
  sed -e "s/^PORTAL_HOSTNAME=.*/PORTAL_HOSTNAME=$PORTAL_HOSTNAME/" \
      -e "s/^MESH_HOSTNAME=.*/MESH_HOSTNAME=$MESH_HOSTNAME/" \
      -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(rand 50)|" \
      -e "s/^DJANGO_ALLOWED_HOSTS=.*/DJANGO_ALLOWED_HOSTS=$PORTAL_HOSTNAME/" \
      -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://$PORTAL_HOSTNAME|" \
      -e "s|^PORTAL_PUBLIC_URL=.*|PORTAL_PUBLIC_URL=https://$PORTAL_HOSTNAME|" \
      -e "s|^MESH_PUBLIC_URL=.*|MESH_PUBLIC_URL=https://$MESH_HOSTNAME|" \
      -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand 32)/" \
      -e "s/^BOOTSTRAP_ADMIN_USERNAME=.*/BOOTSTRAP_ADMIN_USERNAME=$ADMIN_USER/" \
      -e "s/^BOOTSTRAP_ADMIN_PASSWORD=.*/BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASSWORD/" \
      .env.example > .env
  echo "SERVER_IP=$SERVER_IP" >> .env
  chmod 600 .env
  printf 'Portal: https://%s\nUser: %s\nPassword: %s\n(Change it after first login. Delete this file afterwards.)\n' \
    "$PORTAL_HOSTNAME" "$ADMIN_USER" "$ADMIN_PASSWORD" > ADMIN-CREDENTIALS.txt
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
  openssl req -x509 -newkey rsa:3072 -nodes -days 3650 -subj "/CN=BSF Remote Internal CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -keyout $d/ca.key -out $d/ca.crt 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$PORTAL_HOSTNAME" -keyout $d/privkey.pem -out $d/server.csr 2>/dev/null
  printf "subjectAltName=%s\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\nbasicConstraints=CA:FALSE\n" "$san" > $d/server.ext
  openssl x509 -req -in $d/server.csr -CA $d/ca.crt -CAkey $d/ca.key -CAcreateserial -days 825 -extfile $d/server.ext -out $d/server.crt 2>/dev/null
  cat $d/server.crt $d/ca.crt > $d/fullchain.pem
  rm -f $d/server.csr $d/server.ext
  chmod 644 $d/ca.crt $d/fullchain.pem; chmod 600 $d/privkey.pem $d/ca.key
  cp $d/ca.crt "BSF-Remote-Internal-CA.crt"
  c_ok "Internal CA and certificate created ($san)"
  c_warn "Distribute BSF-Remote-Internal-CA.crt to every PC by GPO (USER-GUIDE §4). Keep deploy/certs/ca.key offline/safe."
}

open_firewall() {
  if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow 443/tcp >/dev/null; ufw allow 80/tcp >/dev/null; c_ok "ufw: opened TCP 443 and 80"
  elif command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd -q --permanent --add-service=https --add-service=http && firewall-cmd -q --reload; c_ok "firewalld: opened https and http"
  else
    c_info "No active host firewall detected (ufw/firewalld); make sure TCP 443 is allowed to this server"
  fi
}

wait_healthy() {
  c_info "Waiting for the services to come up…"
  local i code1 code2
  for i in $(seq 1 90); do
    code1=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --cacert deploy/certs/ca.crt --resolve "$PORTAL_HOSTNAME:443:127.0.0.1" "https://$PORTAL_HOSTNAME/api/health/" || true)
    code2=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --cacert deploy/certs/ca.crt --resolve "$MESH_HOSTNAME:443:127.0.0.1" "https://$MESH_HOSTNAME/" || true)
    if [ "$code1" = 200 ] && [ "$code2" = 200 ]; then c_ok "Portal and remote engine are answering on HTTPS"; return 0; fi
    sleep 2
  done
  c_warn "Not healthy after 3 minutes (portal=$code1 engine=$code2). Check: sudo ./setup.sh logs"
  return 1
}

install() {
  need_root install
  echo "BSF Remote $VERSION — installation"
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
 BSF Remote is running.

 1. Add internal DNS A records (or hosts entries for a first test):
      $PORTAL_HOSTNAME   ->  ${SERVER_IP:-<server IP>}
      $MESH_HOSTNAME     ->  ${SERVER_IP:-<server IP>}
 2. Trust the CA on every PC (GPO): deploy/certs/ca.crt
 3. Open https://$PORTAL_HOSTNAME and sign in with the account in
      $ROOT/ADMIN-CREDENTIALS.txt
 4. Continue with USER-GUIDE §5 (first login and setup).
────────────────────────────────────────────────────────────────────
EOF
}

status() {
  set -a; . ./.env; set +a
  dc ps
  ./deploy/healthcheck.sh 2>/dev/null || wait_healthy
}

backup() { need_root backup; ./deploy/backup-postgres.sh; }

reset_admin() {
  need_root reset-admin-password
  set -a; . ./.env; set +a
  local pw; pw=$(rand 20)
  dc exec -T -e BOOTSTRAP_ADMIN_PASSWORD="$pw" -e BOOTSTRAP_ADMIN_RESET=true web python manage.py bootstrap_admin >/dev/null
  echo "New password for $BOOTSTRAP_ADMIN_USERNAME: $pw"
}

uninstall() {
  need_root uninstall
  local a=""; read -r -p "Stop and remove BSF Remote containers? Data volumes are KEPT unless you type PURGE: " a
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
  export-ca) cat deploy/certs/ca.crt ;;
  reset-admin-password) reset_admin ;;
  uninstall) uninstall ;;
  *) sed -n 2,11p "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
