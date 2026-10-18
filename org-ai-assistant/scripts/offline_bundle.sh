#!/usr/bin/env bash
# Run on an INTERNET-CONNECTED staging machine (Linux x86_64 with Docker).
# Produces ./offline-bundle/ containing everything the data-centre server
# needs: Docker images, LLM model files and SHA-256 checksums.
# Move it in through your approved transfer process, then run import_bundle.sh.
#
#   MODELS="qwen2.5-coder:7b qwen2.5-coder:14b" ./scripts/offline_bundle.sh
set -euo pipefail

MODELS="${MODELS:-qwen2.5-coder:7b qwen2.5-coder:14b}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/offline-bundle"
mkdir -p "$OUT/images"

echo "== Pulling base images"
docker pull postgres:16
docker pull ollama/ollama:latest
OLLAMA_VERSION="$(docker run --rm --entrypoint /bin/ollama ollama/ollama:latest --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo unknown)"
echo "Ollama version: $OLLAMA_VERSION" | tee "$OUT/VERSIONS.txt"

echo "== Building the agent image (Python packages are installed inside it)"
docker build -t org-hr-agent:pilot "$ROOT/agent"

echo "== Saving images"
docker save postgres:16          -o "$OUT/images/postgres16.tar"
docker save ollama/ollama:latest -o "$OUT/images/ollama.tar"
docker save org-hr-agent:pilot   -o "$OUT/images/org-hr-agent.tar"

echo "== Downloading models: $MODELS"
mkdir -p "$OUT/ollama-models"
docker rm -f bundle-ollama >/dev/null 2>&1 || true
docker run -d --name bundle-ollama -v "$OUT/ollama-models:/root/.ollama" ollama/ollama:latest >/dev/null
sleep 3
for m in $MODELS; do
  docker exec bundle-ollama ollama pull "$m"
done
docker exec bundle-ollama ollama list | tee -a "$OUT/VERSIONS.txt"
docker rm -f bundle-ollama >/dev/null
tar -C "$OUT" -cf "$OUT/ollama-models.tar" ollama-models
rm -rf "$OUT/ollama-models"

echo "== Checksums"
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
du -sh "$OUT"
echo "Done. Scan $OUT with your antivirus, then copy it (and this project folder) to the server."
