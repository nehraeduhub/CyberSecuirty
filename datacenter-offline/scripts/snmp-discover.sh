#!/usr/bin/env bash
# Discover and inventory SNMP devices (switches, routers, firewalls, PDUs, UPS, storage,
# printers) on an IP range and push the results into GLPI.
#
# Runs on any Linux machine that has the GLPI Agent installed with network tasks
# (install-agent-linux.sh <server> --type=network), usually the GLPI server itself.
#
#   ./snmp-discover.sh <first-ip> <last-ip> [glpi-url]
#
# SNMP credentials come from $SNMP_CREDENTIALS, one per line, e.g.
#   export SNMP_CREDENTIALS=$'version:2c,community:dc-readonly\nversion:3,username:glpi,authprotocol:sha,authpassword:XXX,privprotocol:aes,privpassword:YYY'
# Use read-only communities / SNMPv3 users. Default: version:2c,community:public
set -euo pipefail

FIRST=${1:?usage: $0 <first-ip> <last-ip> [glpi-url]}
LAST=${2:?usage: $0 <first-ip> <last-ip> [glpi-url]}
GLPI_URL=${3:-http://localhost/}
THREADS=${THREADS:-10}

for tool in glpi-netdiscovery glpi-injector; do
  command -v "$tool" >/dev/null || { echo "$tool not found: install the GLPI Agent with --type=network" >&2; exit 1; }
done

creds=()
while IFS= read -r line; do
  [ -n "$line" ] && creds+=(--credentials "$line")
done <<<"${SNMP_CREDENTIALS:-version:2c,community:public}"

out=$(mktemp -d /tmp/glpi-snmp.XXXXXX)
trap 'rm -rf "$out"' EXIT

echo "Scanning $FIRST - $LAST ($THREADS threads)..."
glpi-netdiscovery --first "$FIRST" --last "$LAST" "${creds[@]}" \
  --threads "$THREADS" --inventory --save "$out" >/dev/null

found=$(find "$out" -type f | wc -l)
echo "Collected $found discovery/inventory file(s). Sending to $GLPI_URL ..."
if [ "$found" -gt 0 ]; then
  glpi-injector --recursive --directory "$out" --url "$GLPI_URL" --verbose
fi
echo "Done. New devices appear in GLPI under Assets (Network devices, PDUs, Printers...)."
echo "Unknown IPs without SNMP answer are listed under Administration > Inventory > Unmanaged devices."
