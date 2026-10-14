#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Docker is required'; exit 1; }
docker compose version >/dev/null || { echo 'Docker Compose plugin is required'; exit 1; }
mkdir -p deploy/certs deploy/secrets
test -f .env || { cp .env.example .env; echo 'Created .env. EDIT IT BEFORE CONTINUING.'; exit 2; }
test -s deploy/certs/fullchain.pem && test -s deploy/certs/privkey.pem || { echo 'Install your approved TLS certificate in deploy/certs/'; exit 3; }
docker compose config >/dev/null
docker compose pull db redis nginx meshcentral
docker compose build web
docker compose up -d
docker compose ps
echo 'Deployment started. Run: ./deploy/healthcheck.sh'
