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
  sans=$(openssl x509 -in deploy/certs/fullchain.pem -noout -ext subjectAltName 2>/dev/null)
  for h in "$PORTAL_HOSTNAME" "$MESH_HOSTNAME"; do echo "$sans" | grep -q "DNS:$h" || err "certificate has no SAN for $h"; done
  openssl verify -CAfile deploy/certs/ca.crt deploy/certs/fullchain.pem >/dev/null 2>&1 || err "fullchain.pem does not verify against deploy/certs/ca.crt"
  # Python 3.13+/OpenSSL 3 strict mode rejects CA certificates without keyUsage.
  openssl x509 -in deploy/certs/ca.crt -noout -ext keyUsage 2>/dev/null | grep -q "Certificate Sign" || err "ca.crt lacks keyUsage keyCertSign (strict X.509 clients will reject it)"
fi
for img in techguardinas-remote/web:2.0.0 techguardinas-remote/frontend:2.0.0 techguardinas-remote/meshcentral:1.2.5 postgres:17-alpine redis:7-alpine nginx:1.29-alpine; do
  docker image inspect "$img" >/dev/null 2>&1 || err "image $img not loaded (see deploy/OFFLINE-IMAGES.md)"
done
docker compose config >/dev/null 2>&1 || err "docker compose config failed"
[ "$fail" -eq 0 ] && echo "Preflight OK." || exit 1
