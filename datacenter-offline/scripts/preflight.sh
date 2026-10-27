#!/usr/bin/env bash
# Check that this server is ready for the offline data centre stack, BEFORE
# install-offline.sh. Changes nothing. Run from the extracted bundle:
#   sudo ./site/datacenter-offline/scripts/preflight.sh
# Exit code 1 when something must be fixed first.
set -uo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
BUNDLE=$(cd "$KIT/../.." && pwd)
fails=0 warns=0

pass() { printf '  [PASS] %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; warns=$((warns + 1)); }
fail() { printf '  [FAIL] %s\n' "$*"; fails=$((fails + 1)); }

echo "Pre-flight checks for the offline data centre stack"
echo

echo "Operating system"
# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
case "${ID:-}:${VERSION_ID%%.*}" in
  ubuntu:22|ubuntu:24|debian:12|rhel:9|rocky:9|almalinux:9) pass "$PRETTY_NAME" ;;
  *) warn "${PRETTY_NAME:-unknown OS}: not a tested OS (Ubuntu 22.04/24.04, Debian 12, RHEL/Rocky/Alma 9)" ;;
esac
[ "$(uname -m)" = x86_64 ] && pass "Architecture x86_64" || fail "Architecture $(uname -m): the bundle images are for x86_64 (amd64)"
if [ -f "$BUNDLE/docker/TARGET" ]; then
  read -r t_id t_ver < "$BUNDLE/docker/TARGET"
  if [ "$t_id" = "${ID:-}" ] && [ "${t_ver%%.*}" = "${VERSION_ID%%.*}" ]; then
    pass "Bundle Docker packages match this OS ($t_id $t_ver)"
  elif ! command -v docker >/dev/null; then
    fail "Bundle Docker packages are for $t_id $t_ver but this server is ${ID:-?} ${VERSION_ID:-?}: rebuild the bundle with SERVER_OS=${ID:-?}:${VERSION_ID:-?}"
  fi
fi
if command -v getenforce >/dev/null && [ "$(getenforce)" = Enforcing ]; then
  pass "SELinux enforcing (the kit labels its bind mounts with :z)"
fi

echo
echo "Hardware"
cpus=$(nproc)
mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024 + 0.5}' /proc/meminfo)
[ "$cpus" -ge 4 ] && pass "$cpus CPU cores" || warn "$cpus CPU cores (4 or more recommended)"
if [ "$mem_gb" -ge 8 ]; then pass "${mem_gb} GB RAM"
elif [ "$mem_gb" -ge 6 ]; then warn "${mem_gb} GB RAM (8 GB recommended)"
else fail "${mem_gb} GB RAM (at least 6 GB, 8 GB recommended)"; fi

docker_root=/var/lib/docker
command -v docker >/dev/null && docker_root=$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
check_disk() { # path min_fail_gb min_warn_gb label
  local p=$1; while [ ! -d "$p" ]; do p=$(dirname "$p"); done
  local free; free=$(df -BG --output=avail "$p" | tail -1 | tr -dc 0-9)
  if [ "$free" -lt "$2" ]; then fail "$4: ${free} GB free on $p (need at least $2 GB)"
  elif [ "$free" -lt "$3" ]; then warn "$4: ${free} GB free on $p ($3 GB recommended)"
  else pass "$4: ${free} GB free on $p"; fi
}
check_disk "$docker_root" 20 50 "Docker data (images, database, history)"
check_disk "$BUNDLE" 5 10 "Bundle folder (backups go next to the kit)"

echo
echo "Software"
if command -v docker >/dev/null; then
  v=$(docker version -f '{{.Server.Version}}' 2>/dev/null || echo "")
  if [ -z "$v" ]; then fail "Docker installed but the daemon is not running (systemctl start docker)"
  elif [ "${v%%.*}" -lt 24 ]; then fail "Docker $v is too old (24 or newer needed)"
  else pass "Docker $v"; fi
  if cv=$(docker compose version --short 2>/dev/null); then
    if [ "$(printf '%s\n' 2.24.4 "${cv#v}" | sort -V | head -1)" = 2.24.4 ]; then pass "Docker Compose $cv"
    else fail "Docker Compose $cv is too old (2.24.4 or newer needed)"; fi
  else
    fail "Docker Compose plugin missing (docker-compose-plugin package)"
  fi
elif [ -d "$BUNDLE/docker" ]; then
  pass "Docker not installed yet: install-offline.sh installs it from the bundle"
else
  fail "Docker not installed and the bundle has no docker/ folder"
fi
for c in curl tar gzip sha256sum awk sed; do
  command -v $c >/dev/null || fail "Command '$c' is missing"
done
pass "Basic tools (curl, tar, gzip, sha256sum)"
command -v python3 >/dev/null && pass "python3 (for import_layout.py)" || warn "python3 missing: needed only for the rack CSV import"

echo
echo "Network"
# Settings from .env (after a first run) or the defaults in .env.example
setting() {
  local v
  v=$(cat "$KIT/.env" "$KIT/.env.example" 2>/dev/null | grep "^$1=" | head -1 | cut -d= -f2)
  echo "${v:-$2}"
}
tls=$(setting TLS yes)
if [ "$tls" = yes ]; then ports="$(setting HTTP_REDIRECT_PORT 80) $(setting HTTPS_PORT 443) $(setting PORTAL_TLS_PORT 8443)"
else ports="$(setting GLPI_PORT 80) $(setting PORTAL_PORT 8080)"; fi
# Is something listening on this TCP port (any address, IPv4 or IPv6)?
# Reads /proc directly, so it works even where ss/netstat aren't installed.
port_listening() {
  local files=() f
  for f in /proc/net/tcp /proc/net/tcp6; do [ -r "$f" ] && files+=("$f"); done
  awk -v h="$(printf ':%04X' "$1")" 'FNR > 1 && $4 == "0A" && toupper(substr($2, length($2) - 4)) == h { f = 1 } END { exit !f }' \
    "${files[@]}"
}
port_owner() { { ss -Hltnp "sport = :$1" 2>/dev/null | grep -o 'users:(("[^"]*' | head -1 | cut -d'"' -f2; } || true; }
for p in $ports; do
  if port_listening "$p"; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^dc-portal-1$'; then pass "Port $p in use by this stack (upgrade)"
    else
      who=$(port_owner "$p")
      fail "Port $p is already in use${who:+ by '$who'}: stop it, or set other ports in .env (DEPLOYMENT-GUIDE, step 4)"
    fi
  else
    pass "Port $p free"
  fi
done
ip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$ip" ] && pass "Server address $ip" || warn "Could not detect the server IP address"
if command -v timedatectl >/dev/null; then
  timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes && pass "Clock synchronised (NTP)" \
    || warn "Clock not NTP-synchronised: point it at your internal NTP server (affects charts and certificates)"
fi

echo
echo "Bundle"
if [ -f "$BUNDLE/SHA256SUMS" ]; then
  (cd "$BUNDLE" && grep -E '  \./(images|docker|agents)/' SHA256SUMS | sha256sum --quiet -c - 2>/dev/null) \
    && pass "Images, Docker packages and agents intact (SHA256SUMS)" \
    || fail "Bundle files damaged: copy the archive again"
else
  warn "No SHA256SUMS found next to the bundle"
fi
n=$(ls "$BUNDLE"/images/*.tar.gz 2>/dev/null | wc -l)
[ "$n" -ge 8 ] && pass "$n container images in the bundle" || fail "Only $n container images in $BUNDLE/images (expected 8)"

echo
if [ "$fails" -gt 0 ]; then
  echo "Result: $fails problem(s) to fix, $warns warning(s). Fix the FAIL items, then run this again."
  exit 1
fi
echo "Result: ready to install ($warns warning(s)). Next: sudo ./install-offline.sh"
