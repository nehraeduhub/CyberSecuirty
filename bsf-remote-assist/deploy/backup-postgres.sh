#!/usr/bin/env bash
set -euo pipefail
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bsf-remote/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/${POSTGRES_DB}-${TS}.dump"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$OUT"
unset PGPASSWORD
chmod 600 "$OUT"
find "$BACKUP_DIR" -type f -name '*.dump' -mtime "+$RETENTION_DAYS" -delete
sha256sum "$OUT" > "$OUT.sha256"
echo "Created $OUT"
