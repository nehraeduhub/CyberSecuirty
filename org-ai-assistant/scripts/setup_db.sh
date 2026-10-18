#!/usr/bin/env bash
# Creates the dummy HR database on a PostgreSQL server installed directly
# on the host (no Docker). Run as a user that can connect as a superuser,
# e.g.:  sudo -u postgres ./scripts/setup_db.sh
set -euo pipefail

DB_NAME="${DB_NAME:-org_hr}"
DIR="$(cd "$(dirname "$0")/../database" && pwd)"

echo "Recreating database ${DB_NAME} ..."
dropdb --if-exists "$DB_NAME"
createdb "$DB_NAME"

for f in 01_schema.sql 02_seed_dummy_data.sql 03_security_roles.sql; do
  echo "Running $f"
  psql -q -v ON_ERROR_STOP=1 -d "$DB_NAME" -f "$DIR/$f"
done

echo
echo "Done. Test the AI's read-only login with:"
echo "  PGPASSWORD=change_me_ai_readonly psql -h localhost -U ai_readonly -d $DB_NAME \\"
echo "    -c \"SET app.user_role='hr_admin'\" -f $DIR/04_sample_questions.sql"
