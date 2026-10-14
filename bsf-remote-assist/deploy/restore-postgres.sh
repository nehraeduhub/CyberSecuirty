#!/usr/bin/env bash
set -euo pipefail
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
read -r -p "RESTORE will overwrite objects in database '$POSTGRES_DB'. Type RESTORE to continue: " CONFIRM
[[ "$CONFIRM" == "RESTORE" ]] || { echo "Cancelled"; exit 1; }
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
pg_restore -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner "$BACKUP_FILE"
unset PGPASSWORD
echo "Restore completed"
