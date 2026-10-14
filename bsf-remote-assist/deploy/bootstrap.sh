#!/usr/bin/env bash
set -euo pipefail
cp -n .env.example .env || true
chmod 600 .env
docker compose pull db redis meshcentral nginx
docker compose build web
docker compose up -d db redis meshcentral web nginx
docker compose exec web python manage.py migrate
echo "Create the first local break-glass administrator with: docker compose exec web python manage.py createsuperuser"
