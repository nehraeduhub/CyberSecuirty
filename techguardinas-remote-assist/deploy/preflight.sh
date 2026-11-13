#!/usr/bin/env bash
# Checks the deployment directory before `docker compose up`. Does not need Internet access.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
err() { echo "ERROR: $*"; fail=1; }
for f in .env deploy/certs/fullchain.pem deploy/certs/privkey.pem deploy/certs/ca.crt deploy/secrets/mesh_login_key; do
  [ -s "$f" ] || err "missing $f"
done
if [ -f .env ]; then
  grep -q '^[^#]*CHANGE-ME' .env && err ".env still contains CHANGE-ME placeholders"
  grep -q '^DJANGO_DEBUG=False' .env || err "DJANGO_DEBUG must be False"
  set -a; . ./.env; set +a
fi
[ -s deploy/secrets/mesh_login_key ] && ! grep -Eq '^[0-9a-f]{160}$' deploy/secrets/mesh_login_key && err "mesh_login_key must be 160 hex characters (run deploy/generate-secrets.sh)"
if [ -s deploy/certs/fullchain.pem ] && [ -n "${PORTAL_HOSTNAME:-}" ]; then
  # Works for exact names and wildcards (a wildcard covers exactly one name label).
  for h in "$PORTAL_HOSTNAME" "$MESH_HOSTNAME"; do
    openssl x509 -in deploy/certs/fullchain.pem -noout -checkhost "$h" 2>/dev/null | grep -q "does match" || err "certificate does not cover $h"
  done
  openssl verify -CAfile deploy/certs/ca.crt -untrusted deploy/certs/fullchain.pem deploy/certs/fullchain.pem >/dev/null 2>&1 \
    || err "fullchain.pem does not verify against deploy/certs/ca.crt (missing intermediate certificate or wrong CA)"
  # Strict X.509 clients reject CA certificates without keyUsage (warning only; some public roots lack it).
  openssl x509 -in deploy/certs/ca.crt -noout -ext keyUsage 2>/dev/null | grep -q "Certificate Sign" || echo "WARNING: first certificate in ca.crt has no keyUsage keyCertSign"
fi
for img in techguardinas-remote/web:2.0.0 techguardinas-remote/frontend:2.0.0 techguardinas-remote/meshcentral:1.2.5 postgres:17-alpine redis:7-alpine nginx:1.29-alpine; do
  docker image inspect "$img" >/dev/null 2>&1 || err "image $img not loaded (see deploy/OFFLINE-IMAGES.md)"
done
docker compose config >/dev/null 2>&1 || err "docker compose config failed"
[ "$fail" -eq 0 ] && echo "Preflight OK." || exit 1
