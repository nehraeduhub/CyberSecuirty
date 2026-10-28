#!/bin/sh
set -eu
cd /opt/meshcentral
mkdir -p meshcentral-data meshcentral-files meshcentral-backups meshcentral-recordings
node render-config.js > meshcentral-data/config.json.new
mv meshcentral-data/config.json.new meshcentral-data/config.json

# Make sure the portal's service account exists and is an administrator, on EVERY start (idempotent:
# MeshCentral answers "User already exists" for an existing account). Its password is random and
# discarded: the portal authenticates with the shared LoginCookieEncryptionKey.
SVC="${MESH_SERVICE_USER:-tg-portal-svc}"
node node_modules/meshcentral --createaccount "$SVC" --pass "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" --email "$SVC@techguardinas-remote.invalid" >/dev/null 2>&1 || true
if node node_modules/meshcentral --adminaccount "$SVC" 2>&1 | grep -qi "done"; then
  echo "Service account $SVC ready"
else
  echo "WARNING: could not confirm service account $SVC (the portal will report 'noauth')" >&2
fi
exec node node_modules/meshcentral
