#!/usr/bin/env bash
# Starts the stack from images already loaded on this host (no registry or Internet access needed).
set -euo pipefail
cd "$(dirname "$0")/.."
./deploy/preflight.sh
docker compose up -d --no-build
docker compose ps
echo "Started. Check: ./deploy/healthcheck.sh"
