#!/usr/bin/env bash
# Install the GLPI Agent on a Linux server from the offline bundle and send a first inventory.
# Copy this script, glpi-agent-*-linux-installer.pl and (HTTPS mode) server-ca.crt
# to the server, then run:
#   sudo ./install-agent-linux.sh https://<glpi-server>/
# With server-ca.crt next to this script, the agent trusts the GLPI certificate.
# Use --type=all on the machine that will run SNMP network discovery.
set -euo pipefail

SERVER=${1:?usage: $0 http://<glpi-server>/ [--type=typical|network|all]}
TYPE=${2:---type=typical}
cd "$(dirname "$0")"

installer=$(ls glpi-agent-*-linux-installer.pl 2>/dev/null | sort -V | tail -1 || true)
if [ -z "$installer" ]; then
  echo "glpi-agent-*-linux-installer.pl not found next to this script (see bundle/agents)." >&2
  exit 1
fi

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }

tls_opt=()
if [ -f server-ca.crt ]; then
  install -m 644 server-ca.crt /etc/ssl/certs/dc-glpi-server-ca.crt
  tls_opt=(--ca-cert-file=/etc/ssl/certs/dc-glpi-server-ca.crt)
fi

perl "$installer" --install --silent --no-question --service --runnow "$TYPE" --server="$SERVER" "${tls_opt[@]}"

echo
echo "GLPI Agent installed. It runs as a service and reports to $SERVER"
echo "Force a new inventory any time with:  sudo glpi-agent --force"
