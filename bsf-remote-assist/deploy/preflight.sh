#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
fail=0
for f in .env deploy/certs/fullchain.pem deploy/certs/privkey.pem; do if [ ! -s "$f" ]; then echo "MISSING: $f"; fail=1; fi; done
if grep -q 'CHANGE-ME\|GENERATE-A' .env 2>/dev/null; then echo 'ERROR: .env still contains placeholder secrets'; fail=1; fi
if ! grep -q '^DJANGO_DEBUG=False' .env 2>/dev/null; then echo 'ERROR: DJANGO_DEBUG must be False'; fail=1; fi
docker compose config >/dev/null || fail=1
if [ "$fail" -ne 0 ]; then exit 1; fi
echo 'Preflight OK.'
