#!/usr/bin/env bash
# Restores the portal database from a backup-postgres.sh dump. Usage: restore-postgres.sh <portal-*.dump>
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
BACKUP_FILE="${1:?usage: $0 <portal-YYYYmmdd-HHMMSS.dump>}"
read -r -p "RESTORE will overwrite database '$POSTGRES_DB'. Type RESTORE to continue: " CONFIRM
[[ "$CONFIRM" == "RESTORE" ]] || { echo "Cancelled"; exit 1; }
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$BACKUP_FILE"
echo "Restore completed. MeshCentral data is restored by extracting meshcentral-data-*.tgz into the meshdata volume while meshcentral is stopped."
