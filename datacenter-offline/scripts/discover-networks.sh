#!/usr/bin/env bash
# Find every IPv4 network in the data centre and (with --write) add them to
# SNMP_RANGES in collector/collector.conf, so the collector scans them all.
#
# Sources: this server's own subnets, plus the interfaces and routing table of
# your core router(s) / L3 switches / firewall read over SNMP (the credentials
# in collector.conf SNMP_CREDENTIALS, or --community).
#
#   sudo ./scripts/discover-networks.sh                      # ask the default gateway, show only
#   sudo ./scripts/discover-networks.sh 10.10.0.1 10.10.0.2  # ask these routers
#   sudo ./scripts/discover-networks.sh --community dc-ro --write
#
# Options:
#   --community STR  extra SNMP v2c community to try (with --write it is also
#                    saved in SNMP_CREDENTIALS)
#   --write          add the new ranges to collector.conf
#   --max-prefix N   skip networks larger than /N (default 16; 65,534 hosts)
set -euo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
CONF=$KIT/collector/collector.conf
cd "$KIT"

write=no community="" maxprefix=16 routers=()
while [ $# -gt 0 ]; do
  case "$1" in
    --write) write=yes ;;
    --community) community=${2:?--community needs a value}; shift ;;
    --max-prefix) maxprefix=${2:?--max-prefix needs a number}; shift ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Unknown option $1 (see --help)" >&2; exit 1 ;;
    *) routers+=("$1") ;;
  esac
  shift
done

[ -f "$CONF" ] || { echo "No $CONF yet: run install-offline.sh first." >&2; exit 1; }
docker compose ps --status running --services 2>/dev/null | grep -qx collector \
  || { echo "The collector container is not running (docker compose up -d)." >&2; exit 1; }

# SNMP_CREDENTIALS / SNMP_RANGES from collector.conf, comments stripped
lines() { printf '%s\n' "$1" | sed -e 's/[[:space:]][[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v -e '^$' -e '^#' || true; }
conf_var() { ( set +u; SNMP_CREDENTIALS="" SNMP_RANGES=""; . "$CONF" >/dev/null 2>&1; lines "${!1}" ); }
creds=$(conf_var SNMP_CREDENTIALS)
[ -n "$community" ] && creds=$(printf '%s\n%s\n' "$creds" "version:2c,community:$community")
creds=$(printf '%s\n' "$creds" | grep -v '^$' | paste -sd';' - || true)

hex2ip() { local h=$1; echo "$((16#${h:6:2})).$((16#${h:4:2})).$((16#${h:2:2})).$((16#${h:0:2}))"; } # /proc is little-endian
masklen() { local m; m=$(ip2int "$1") n=0; while [ $n -lt 32 ] && (( m & (1 << (31 - n)) )); do n=$((n + 1)); done; echo $n; }
# Routes of this server, from /proc (no need for the ip command):
# skip loopback and Docker's own bridges
routes() { awk 'NR > 1 && $1 !~ /^(lo|docker|br-|veth|virbr|cni|flannel|cali)/ {print $1, $2, $3, $8}' /proc/net/route; }

ip2int() { local IFS=.; set -- $1; echo $(( ($1 << 24) + ($2 << 16) + ($3 << 8) + $4 )); }
int2ip() { echo "$(( $1 >> 24 & 255 )).$(( $1 >> 16 & 255 )).$(( $1 >> 8 & 255 )).$(( $1 & 255 ))"; }
to_range() { # net/len -> first-last usable address
  local net=${1%/*} len=${1#*/} n size
  n=$(ip2int "$net"); size=$(( 1 << (32 - len) ))
  n=$(( n & ~(size - 1) & 0xFFFFFFFF ))
  if [ "$len" -ge 31 ]; then echo "$(int2ip $n)-$(int2ip $((n + size - 1)))"
  else echo "$(int2ip $((n + 1)))-$(int2ip $((n + size - 2)))"; fi
}

if [ ${#routers[@]} -eq 0 ]; then
  while read -r dev dst gw mask; do
    [ "$dst" = 00000000 ] && [ "$gw" != 00000000 ] && { routers=("$(hex2ip "$gw")"); break; }
  done < <(routes)
fi

found=$(mktemp); trap 'rm -f "$found"' EXIT

echo "This server's own networks:"
while read -r dev dst gw mask; do
  [ "$dst" = 00000000 ] && continue
  printf '%s/%s\t%s\t%s\n' "$(hex2ip "$dst")" "$(masklen "$(hex2ip "$mask")")" "this-server" \
    "$([ "$gw" = 00000000 ] && echo "interface $dev" || echo "route via $(hex2ip "$gw")")"
done < <(routes) | tee -a "$found" | sed 's/^/  /'

if [ ${#routers[@]} -gt 0 ]; then
  if [ -z "$creds" ]; then
    echo
    echo "No SNMP credentials: put your read-only community in SNMP_CREDENTIALS in"
    echo "collector/collector.conf, or pass --community <name>. Only this server's"
    echo "own networks are shown."
  else
    echo
    echo "Asking ${routers[*]} over SNMP:"
    docker compose exec -T collector perl - "$creds" "${routers[@]}" < scripts/discover-networks.pl \
      | tee -a "$found" | sed 's/^/  /' || true
  fi
fi

echo
existing=$(conf_var SNMP_RANGES)
new=() n_skip=0
while IFS=$'\t' read -r cidr from src; do
  len=${cidr#*/}
  if [ "$len" -lt "$maxprefix" ]; then
    echo "  skip $cidr (larger than /$maxprefix; add smaller ranges by hand, or use --max-prefix)"
    n_skip=$((n_skip + 1)); continue
  fi
  r=$(to_range "$cidr")
  printf '%s\n' "$existing" "${new[@]%%  *}" | grep -qxF "$r" && continue
  [ "$len" -lt 22 ] && echo "  note: $cidr has $(( (1 << (32 - len)) - 2 )) addresses: the first scan will take a while"
  new+=("$r  # $cidr from $from ($src)")
done < <(sort -t/ -k1,1V -k2,2n -u "$found")

if [ ${#new[@]} -eq 0 ]; then
  echo "No new ranges: everything found is already in SNMP_RANGES."
  exit 0
fi
echo "New ranges to scan (${#new[@]}):"
printf '  %s\n' "${new[@]}"

if [ "$write" != yes ]; then
  echo
  echo "Nothing changed. Run again with --write to add them to collector/collector.conf."
  exit 0
fi

cp -p "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"
add=$(printf '%s\n' "${new[@]}")
cred_line=""
if [ -n "$community" ] && ! conf_var SNMP_CREDENTIALS | grep -qxF "version:2c,community:$community"; then
  cred_line="version:2c,community:$community"
fi
# Insert right after the opening line of each block (works with any content in it)
ADD=$add CRED=$cred_line awk '
  { print }
  /^SNMP_RANGES="/ && !r { r = 1; if (ENVIRON["ADD"] != "") print ENVIRON["ADD"] }
  /^SNMP_CREDENTIALS="/ && !c { c = 1; if (ENVIRON["CRED"] != "") print ENVIRON["CRED"] }
' "$CONF" > "$CONF.tmp"
grep -q '^SNMP_RANGES="' "$CONF" || printf '\nSNMP_RANGES="\n%s\n"\n' "$add" >> "$CONF.tmp"
if [ -n "$cred_line" ] && ! grep -q '^SNMP_CREDENTIALS="' "$CONF"; then
  printf '\nSNMP_CREDENTIALS="\n%s\n"\n' "$cred_line" >> "$CONF.tmp"
fi
cat "$CONF.tmp" > "$CONF" && rm -f "$CONF.tmp"

echo
echo "Added ${#new[@]} range(s) to collector/collector.conf${cred_line:+ and the community to SNMP_CREDENTIALS} (backup: $(basename "$CONF").bak.*)."
echo "Scan now:"
echo "  docker compose restart collector monitor-sync"
echo "  docker compose exec collector collect.sh once"
