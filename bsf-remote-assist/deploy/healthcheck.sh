#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-https://remote.example.mil}"
code=$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 10 "$BASE_URL/health/" || true)
if [[ "$code" != "200" ]]; then
  echo "Portal health check failed: HTTP $code"
  exit 1
fi
echo "Portal health OK: HTTP $code"
