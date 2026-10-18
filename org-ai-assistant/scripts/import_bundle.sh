#!/usr/bin/env bash
# Run on the OFFLINE data-centre server, from the project folder, after
# copying offline-bundle/ next to it. Verifies checksums, loads images and
# models, and starts the database and LLM server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IN="${1:-$ROOT/offline-bundle}"
cd "$IN"

echo "== Verifying checksums"
sha256sum -c --quiet SHA256SUMS && echo "All files OK"

echo "== Loading Docker images"
for t in images/*.tar; do docker load -i "$t"; done

echo "== Installing models into the ollama volume"
cd "$ROOT"
docker compose create ollama >/dev/null
VOL="$(docker volume ls -q | grep -E '_ollama-models$' | head -1)"
docker run --rm -v "$VOL:/root/.ollama" -v "$IN:/bundle:ro" --entrypoint sh ollama/ollama:latest \
  -c 'tar -C /tmp -xf /bundle/ollama-models.tar && cp -a /tmp/ollama-models/. /root/.ollama/'

echo "== Starting database and LLM server"
docker compose up -d hr-db ollama
sleep 5
docker compose exec ollama ollama list
echo
echo "Next: docker compose run --rm agent python evaluate.py"
