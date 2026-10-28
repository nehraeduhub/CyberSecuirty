#!/usr/bin/env bash
# Add the Ubuntu packages in collector/patches/*.deb to the collector image
# that is already on this server, without internet. Bundles built before the
# fix lack libcrypt-rijndael-perl, so SNMPv3 with AES privacy fails
# ("Crypt::Rijndael perl module needs to be installed"). Safe to repeat.
#
#   sudo ./scripts/patch-collector.sh               (restarts the collector)
#   sudo ./scripts/patch-collector.sh --no-restart  (used by install-offline.sh)
set -euo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
cd "$KIT"
# .env does not exist yet on a first install: fall back to the kit's default
ver=$(cat .env .env.example 2>/dev/null | grep '^AGENT_VERSION=' | head -1 | cut -d= -f2 || true)
image=dc-collector:${ver:-1.17}

docker image inspect "$image" >/dev/null 2>&1 || { echo "Image $image not found: run install-offline.sh first." >&2; exit 1; }
ls collector/patches/*.deb >/dev/null 2>&1 || { echo "No packages in collector/patches/." >&2; exit 1; }

if docker run --rm --entrypoint perl "$image" -MCrypt::Rijndael -e1 2>/dev/null; then
  [ "${1:-}" = --no-restart ] || echo "$image already has Crypt::Rijndael (SNMPv3 AES works). Nothing to do."
  exit 0
fi

ctx=$(mktemp -d); trap 'rm -rf "$ctx"' EXIT
cp collector/patches/*.deb "$ctx/"
cat > "$ctx/Dockerfile" <<EOF
FROM $image
COPY *.deb /tmp/patches/
RUN dpkg -i /tmp/patches/*.deb && rm -rf /tmp/patches
EOF
# --pull=false: build from the local image only (no internet needed)
docker build --pull=false -q -t "$image" "$ctx" >/dev/null
docker run --rm --entrypoint perl "$image" -MCrypt::Rijndael -e1
echo "Patched $image: SNMPv3 with AES now works."

[ "${1:-}" = --no-restart ] && exit 0
docker compose up -d collector monitor-sync manager
echo "Collector restarted. Collect again: docker compose exec collector collect.sh once"
