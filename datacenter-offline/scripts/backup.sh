#!/usr/bin/env bash
# Back up the DC NOC: device list, settings (networks, SNMP credentials),
# SSH host keys, collector.conf, .env and the HTTPS certificate, to ./backups
#   ./backup.sh            keep the last 14 backups
#   KEEP=30 ./backup.sh
# Restore: see README.md "Backup and restore". Prometheus history is not included.
set -euo pipefail
umask 077  # backups contain credentials
cd "$(dirname "$0")/.."

KEEP=${KEEP:-14}
stamp=$(date +%Y%m%d-%H%M%S)
dest=backups/$stamp
mkdir -p "$dest"

echo "Saving the device list and settings..."
docker compose exec -T manager tar -C /settings -czf - . > "$dest/dc-settings.tar.gz"
tar -czf "$dest/kit-config.tar.gz" .env collector/collector.conf collector/ssh tls monitoring/manual 2>/dev/null || true

ls -1d backups/*/ | sort | head -n -"$KEEP" | xargs -r rm -rf
echo "Backup written to $dest"
