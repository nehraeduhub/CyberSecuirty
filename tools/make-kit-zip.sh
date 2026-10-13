#!/usr/bin/env bash
# Build the distributable kit zip from the committed repository content:
#   tools/make-kit-zip.sh            -> dist/nehraeduhub-dc-kit-YYYYMMDD.zip
# Only files tracked by git are included, so local secrets (.env, tls/,
# collector.conf, SSH keys, backups) can never end up in the zip.
set -euo pipefail
cd "$(dirname "$0")/.."

if python3 -c 'import markdown' 2>/dev/null; then
  python3 tools/render_guide.py DEPLOYMENT-GUIDE.md DEPLOYMENT-GUIDE.html
  if ! git diff --quiet -- DEPLOYMENT-GUIDE.html; then
    echo "DEPLOYMENT-GUIDE.html changed: commit it, then run this again." >&2
    exit 1
  fi
fi
if ! git diff --quiet HEAD -- . ':!dist'; then
  echo "Uncommitted changes: commit first (the zip is built from HEAD)." >&2
  exit 1
fi

name=nehraeduhub-dc-kit-$(date +%Y%m%d)
mkdir -p dist
git archive --format=zip --prefix="nehraeduhub-dc-kit/" -o "dist/$name.zip" HEAD -- \
  README-FIRST.txt DEPLOYMENT-GUIDE.md DEPLOYMENT-GUIDE.html \
  index.html glpi-datacenter-library.html ./*.jpg datacenter-offline tools
(cd dist && sha256sum "$name.zip" > "$name.zip.sha256")
echo "Kit: dist/$name.zip ($(du -h "dist/$name.zip" | cut -f1))"
