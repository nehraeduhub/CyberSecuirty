#!/usr/bin/env bash
# Backs up the portal database and the MeshCentral data volume (device identities, server keys, events).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bsf-remote}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$BACKUP_DIR/portal-$TS.dump"
docker compose run --rm --no-deps -v "$BACKUP_DIR:/backup" --entrypoint tar meshcentral \
  czf "/backup/meshcentral-data-$TS.tgz" -C /opt/meshcentral meshcentral-data
chmod 600 "$BACKUP_DIR"/*-"$TS".*
( cd "$BACKUP_DIR" && sha256sum *-"$TS".* > "SHA256SUMS-$TS" )
find "$BACKUP_DIR" -type f -mtime "+$RETENTION_DAYS" -delete
echo "Backups written to $BACKUP_DIR (portal-$TS.dump, meshcentral-data-$TS.tgz)"
