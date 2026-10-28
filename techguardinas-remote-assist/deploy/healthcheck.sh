#!/usr/bin/env bash
# Verifies the portal API and the MeshCentral engine through NGINX using the internal CA.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
ok=0
c() { curl --noproxy '*' -sS --cacert deploy/certs/ca.crt -o /dev/null -w '%{http_code}' --max-time 10 "$1" || true; }
p=$(c "$PORTAL_PUBLIC_URL/api/health/"); echo "portal  $PORTAL_PUBLIC_URL/api/health/ -> $p"; [ "$p" = 200 ] || ok=1
m=$(c "$MESH_PUBLIC_URL/"); echo "engine  $MESH_PUBLIC_URL/ -> $m"; [ "$m" = 200 ] || ok=1
docker compose exec -T web python manage.py shell -c "from remote_bridge.meshapi import MeshSession
with MeshSession() as s: print('engine control channel OK, groups:', len(s.meshes()))" || ok=1
exit $ok
