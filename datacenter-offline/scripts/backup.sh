#!/usr/bin/env bash
# Back up the GLPI database and files (documents, config, plugins) to ./backups
#   ./backup.sh            keep the last 14 backups
#   KEEP=30 ./backup.sh
# Restore: see README.md "Backup and restore".
set -euo pipefail
umask 077  # backups contain the GLPI encryption key and DB password
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
set -a; . ./.env; set +a

KEEP=${KEEP:-14}
stamp=$(date +%Y%m%d-%H%M%S)
dest=backups/$stamp
mkdir -p "$dest"

echo "Dumping database..."
docker compose exec -T db mariadb-dump --single-transaction --routines \
  -u"$GLPI_DB_USER" -p"$GLPI_DB_PASSWORD" "$GLPI_DB_NAME" | gzip > "$dest/glpi-db.sql.gz"

echo "Archiving GLPI files..."
docker compose exec -T glpi tar -C /var/glpi -czf - . > "$dest/glpi-data.tar.gz"

cp .env "$dest/env.backup"
chmod 600 "$dest/env.backup"

ls -1d backups/*/ | sort | head -n -"$KEEP" | xargs -r rm -rf
echo "Backup written to $dest"
