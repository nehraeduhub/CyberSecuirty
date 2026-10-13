#!/usr/bin/env bash
# Build the offline bundle on a machine WITH internet access and Docker.
# Produces dc-offline-bundle-<date>.tar.gz containing:
#   - this kit, the NehraEduHub site and learning library
#   - Docker images (GLPI, MariaDB, nginx, network collector, Grafana, Prometheus,
#     Blackbox and SNMP exporters) saved as tar files
#   - GLPI Agent installers for Linux and Windows
# Copy the archive to the data centre server (USB / internal share) and run install-offline.sh.
#
#   ./scripts/prepare-offline-bundle.sh
#   AGENT_VERSION=latest ./scripts/prepare-offline-bundle.sh   # newest GLPI Agent instead of .env.example's
set -euo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
SITE=$(dirname "$KIT")
agent_override=${AGENT_VERSION:-}
# shellcheck disable=SC1091
set -a; . "$KIT/.env.example"; set +a
AGENT_VERSION=${agent_override:-$AGENT_VERSION}

name=dc-offline-bundle-$(date +%Y%m%d)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
out=$work/$name
mkdir -p "$out/images" "$out/agents" "$out/site"

images=("glpi/glpi:$GLPI_VERSION" "mariadb:$MARIADB_VERSION" "nginx:$NGINX_VERSION"
        "grafana/grafana-oss:$GRAFANA_VERSION" "prom/prometheus:$PROMETHEUS_VERSION"
        "prom/blackbox-exporter:$BLACKBOX_VERSION" "prom/snmp-exporter:$SNMP_EXPORTER_VERSION")
for img in "${images[@]}"; do
  echo "Pulling $img ..."
  docker pull -q --platform linux/amd64 "$img"
  file=$(tr '/:' '__' <<<"$img").tar.gz
  docker save "$img" | gzip > "$out/images/$file"
done

if [ "$AGENT_VERSION" = latest ]; then
  AGENT_VERSION=$(curl -fsSL https://api.github.com/repos/glpi-project/glpi-agent/releases/latest \
    | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/') || true
fi
if [ -z "${AGENT_VERSION:-}" ]; then
  echo "Could not detect the latest GLPI Agent version; set AGENT_VERSION=x.y" >&2
  exit 1
fi
echo "Downloading GLPI Agent $AGENT_VERSION ..."
base=https://github.com/glpi-project/glpi-agent/releases/download/$AGENT_VERSION
curl -fSL -o "$out/agents/glpi-agent-$AGENT_VERSION-linux-installer.pl" "$base/glpi-agent-$AGENT_VERSION-linux-installer.pl"
curl -fSL -o "$out/agents/GLPI-Agent-$AGENT_VERSION-x64.msi" "$base/GLPI-Agent-$AGENT_VERSION-x64.msi"
cp "$KIT"/agents/install-agent-* "$out/agents/"

echo "Building network collector image ..."
cp "$out/agents/glpi-agent-$AGENT_VERSION-linux-installer.pl" "$KIT/collector/"
docker build -q --platform linux/amd64 --build-arg AGENT_VERSION="$AGENT_VERSION" \
  -t "dc-collector:$AGENT_VERSION" "$KIT/collector"
rm -f "$KIT/collector/glpi-agent-$AGENT_VERSION-linux-installer.pl"
docker save "dc-collector:$AGENT_VERSION" | gzip > "$out/images/dc-collector_$AGENT_VERSION.tar.gz"

echo "Copying site and kit ..."
cp "$SITE"/*.html "$SITE"/*.jpg "$out/site/" 2>/dev/null || true
mkdir -p "$out/site/datacenter-offline"
tar -C "$KIT" --exclude=./.env --exclude=./backups --exclude=./collector/collector.conf \
  --exclude=./collector/ssh --exclude='./collector/glpi-agent-*' -cf - . | tar -C "$out/site/datacenter-offline" -xf -
sed -i "s/^AGENT_VERSION=.*/AGENT_VERSION=$AGENT_VERSION/" "$out/site/datacenter-offline/.env.example"
cp "$KIT/scripts/install-offline.sh" "$out/"

(cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C "$work" -czf "$name.tar.gz" "$name"
echo
echo "Bundle ready: $(pwd)/$name.tar.gz ($(du -h "$name.tar.gz" | cut -f1))"
