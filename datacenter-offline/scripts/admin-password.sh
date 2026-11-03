#!/usr/bin/env bash
# Set a new password (and optionally user name) for the admin portal (/admin),
# e.g. when it was forgotten. Asks for the password; at least 10 characters.
#   sudo ./scripts/admin-password.sh            # keep the user name
#   sudo ./scripts/admin-password.sh newname    # also rename the user
set -euo pipefail
cd "$(dirname "$0")/.."
read -rsp "New admin password: " p1; echo
read -rsp "Same again: " p2; echo
[ "$p1" = "$p2" ] || { echo "The passwords differ." >&2; exit 1; }
docker compose exec -T -e NEW_PASSWORD="$p1" -e NEW_USER="${1:-}" manager perl /opt/manager.pl --set-admin-password
docker compose restart manager >/dev/null
echo "Done: sign in at /admin with the new password."
