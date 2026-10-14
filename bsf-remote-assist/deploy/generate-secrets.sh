#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import secrets
print('DJANGO_SECRET_KEY='+secrets.token_urlsafe(64))
print('POSTGRES_PASSWORD='+secrets.token_urlsafe(32))
PY
