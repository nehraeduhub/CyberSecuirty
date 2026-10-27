#!/bin/sh
set -eu
cd /opt/meshcentral
mkdir -p meshcentral-data meshcentral-files meshcentral-backups meshcentral-recordings
node render-config.js > meshcentral-data/config.json.new
mv meshcentral-data/config.json.new meshcentral-data/config.json

# Bootstrap the portal's service account once. Its password is random and discarded: the portal
# authenticates with the shared LoginCookieEncryptionKey, so no MeshCentral password exists anywhere.
SVC="${MESH_SERVICE_USER:-tg-portal-svc}"
if [ ! -f meshcentral-data/.techguardinas-service-account ]; then
  node node_modules/meshcentral --createaccount "$SVC" --pass "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" --email "$SVC@techguardinas-remote.invalid" || true
  node node_modules/meshcentral --adminaccount "$SVC"
  touch meshcentral-data/.techguardinas-service-account
fi
exec node node_modules/meshcentral
