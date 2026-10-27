#!/usr/bin/env bash
# Explain the "Unidentified devices" (GLPI Unmanaged items): addresses that
# answered ping/ARP during the scan but not SNMP. For each one this checks
# SNMP again (your credentials, then "public"), a few TCP ports and the SSH
# banner, and says what the device probably is and what to add to
# collector/collector.conf so it is fully inventoried. Changes nothing.
#
#   sudo ./scripts/check-unidentified.sh            # all unidentified devices
#   sudo ./scripts/check-unidentified.sh 10.10.0.   # only addresses starting with this
#   sudo ./scripts/check-unidentified.sh --csv > unidentified.csv
set -euo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
CONF=$KIT/collector/collector.conf
cd "$KIT"

csv=no prefix=""
for a in "$@"; do
  case "$a" in
    --csv) csv=yes ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) prefix=$a ;;
  esac
done

[ -f .env ] || { echo "No .env: run install-offline.sh first." >&2; exit 1; }
db_val() { grep "^$1=" .env | tail -1 | cut -d= -f2-; }
running=$(docker compose ps --status running --services 2>/dev/null)
for s in db collector; do
  grep -qx "$s" <<<"$running" || { echo "The $s container is not running (docker compose up -d)." >&2; exit 1; }
done

lines() { printf '%s\n' "$1" | sed -e 's/[[:space:]][[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v -e '^$' -e '^#' || true; }
creds=""
if [ -f "$CONF" ]; then
  creds=$( ( set +u; SNMP_CREDENTIALS=""; . "$CONF" >/dev/null 2>&1; lines "$SNMP_CREDENTIALS" ) | paste -sd';' - || true)
fi

# Unidentified items with their IP (from the port's address, or the item's own ip field) and MAC
list=$(docker compose exec -T db mariadb -u"$(db_val GLPI_DB_USER)" -p"$(db_val GLPI_DB_PASSWORD)" "$(db_val GLPI_DB_NAME)" -N -e "
  SELECT COALESCE(MIN(ip.name), NULLIF(u.ip, ''), u.name), COALESCE(MIN(p.mac), '')
  FROM glpi_unmanageds u
  LEFT JOIN glpi_ipaddresses ip ON ip.mainitemtype = 'Unmanaged' AND ip.mainitems_id = u.id
       AND ip.is_deleted = 0 AND ip.version = 4
  LEFT JOIN glpi_networkports p ON p.itemtype = 'Unmanaged' AND p.items_id = u.id AND p.is_deleted = 0
  WHERE u.is_deleted = 0 AND u.hub = 0
  GROUP BY u.id" \
  | awk -F'\t' -v p="$prefix" '$1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && index($1, p) == 1' | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n -u)

if [ -z "$list" ]; then
  echo "No unidentified devices${prefix:+ matching $prefix}."
  exit 0
fi
[ "$csv" = yes ] || echo "Checking $(wc -l <<<"$list") unidentified device(s) (about 15 s each, 8 at a time)..." >&2

# 8 probes in parallel inside the collector (the Perl script is passed as an argument)
out=$(printf '%s\n' "$list" | docker compose exec -T collector sh -c '
  f=$(mktemp -d); cd "$f"; printf "%s\n" "$2" > probe.pl; cat > list; split -n l/8 list part.
  for p in part.*; do perl probe.pl "$1" < "$p" > "$p.out" 2> "$p.err" & done; wait
  cat part.*.out; cat part.*.err | sort -u | sed "s/^/ERR: /"; cd /; rm -rf "$f"' sh "$creds" "$(cat scripts/check-unidentified.pl)" 2>&1) || true
result=$(awk -F'\t' 'NF >= 6 && $1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/' <<<"$out")
if [ -z "$result" ]; then
  echo "The probe gave no results. Output from the collector:" >&2
  printf '%s\n' "$out" | head -20 >&2
  exit 1
fi

result=$(sort -t. -k1,1n -k2,2n -k3,3n -k4,4n <<<"$result")
if [ "$csv" = yes ]; then
  echo "ip,mac,open_ports,ssh_banner,probably,what_to_do"
  awk -F'\t' '{ for (i = 1; i <= NF; i++) { gsub(/"/, "\"\"", $i); printf "%s\"%s\"", (i > 1 ? "," : ""), $i } print "" }' <<<"$result"
  exit 0
fi

while IFS=$'\t' read -r ip mac ports banner what todo; do
  printf '\n%s  (MAC %s, open: %s)\n  probably: %s\n  do:       %s\n' "$ip" "$mac" "$ports" "$what" "$todo"
done <<<"$result"
echo
echo "Summary:"
cut -f5 <<<"$result" | sed 's/ (.*//' | sort | uniq -c | sort -rn | sed 's/^/  /'
echo
echo "After changing collector/collector.conf: docker compose restart collector monitor-sync"
echo "and collect again: docker compose exec collector collect.sh once"
echo "Devices that become identified are merged; delete leftover ones in GLPI under"
echo "Administration > Unmanaged devices (or ignore PCs and phones)."
