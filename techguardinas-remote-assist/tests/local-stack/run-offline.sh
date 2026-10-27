#!/bin/bash
# Runs the whole stack AND the acceptance test inside a new network namespace that only has a
# loopback interface: no default route, no DNS server, no proxy. If anything in the workflow needed
# the Internet (CDN, cloud relay, external auth, npm/module download, code-signing timestamp server),
# it would fail here.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
export STACK_ENV=${STACK_ENV:-$HERE/stack.env}
# Each run starts from an empty work directory (fresh databases, agents and evidence).
. "$STACK_ENV"; export WORK="${WORK}-$(date +%Y%m%d-%H%M%S)"
echo "work directory: $WORK"
exec unshare --net -- bash -c '
  set -euo pipefail
  ip link set lo up
  unset HTTPS_PROXY https_proxy HTTP_PROXY http_proxy NO_PROXY no_proxy ALL_PROXY all_proxy
  . "$STACK_ENV"
  echo "== network inside test namespace"; ip -brief addr; echo "routes: $(ip route | wc -l)"
  "'"$HERE"'/start-stack.sh"
  set -a; . "$WORK/portal.env"; set +a
  . "$VENV/bin/activate"
  export PORTAL_URL=https://$PORTAL_HOST CA_BUNDLE=$PKI/ca.crt ADMIN_PASSWORD EVIDENCE_DIR=$WORK/evidence AGENT_ROOT=$WORK/agents \
         BACKEND_DIR=$REPO/backend CHROMIUM MESH_PUBLIC_URL MESH_LOGIN_KEY_FILE
  python3 "$REPO/tests/e2e/run_e2e.py"
'
