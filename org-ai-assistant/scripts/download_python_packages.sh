#!/usr/bin/env bash
# Run on an INTERNET-CONNECTED machine. Downloads the assistant's Python
# packages for the offline server into offline-bundle/python-packages/.
#
# Set PY_VERSION to the server's Python version (run "python3 --version" there):
#   PY_VERSION=3.10 ./scripts/download_python_packages.sh
set -euo pipefail

PY_VERSION="${PY_VERSION:-3.12}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/offline-bundle/python-packages"
mkdir -p "$OUT"

python3 -m pip download -r "$ROOT/agent/requirements.txt" -d "$OUT" \
  --only-binary=:all: --python-version "$PY_VERSION" \
  --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --platform any

(cd "$OUT" && sha256sum *.whl > SHA256SUMS)
echo
echo "Downloaded $(ls "$OUT"/*.whl | wc -l) packages for Python $PY_VERSION into $OUT"
echo "Copy that folder to the server and install with:"
echo "  sha256sum -c SHA256SUMS"
echo "  python3 -m venv ~/hr-agent-venv && source ~/hr-agent-venv/bin/activate"
echo "  pip install --no-index --find-links /path/to/python-packages -r agent/requirements.txt"
