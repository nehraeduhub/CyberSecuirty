#!/usr/bin/env bash
# Creates deploy/secrets/mesh_login_key (shared by the portal and MeshCentral) and prints random
# values for .env. The login key is equivalent to MeshCentral administrator access: keep it secret.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p secrets && chmod 700 secrets
if [ ! -s secrets/mesh_login_key ]; then
  openssl rand -hex 80 > secrets/mesh_login_key
  # Readable inside the containers (non-root users); the directory itself stays root-only on the host.
  chmod 444 secrets/mesh_login_key
  echo "Created deploy/secrets/mesh_login_key"
fi
echo "DJANGO_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')"
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '\n/+=')"
echo "BOOTSTRAP_ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '\n/+=')"
