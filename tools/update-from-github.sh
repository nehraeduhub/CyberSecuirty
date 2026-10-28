#!/usr/bin/env bash
# Update the installed kit from GitHub, keeping your settings and data:
# pull the repository, copy the kit over the installed one, re-run the
# installer. .env, collector.conf, SSH keys, TLS certificates, backups,
# GLPI data and the DC Viewer settings are not touched.
#
#   sudo ./update-from-github.sh                    # default branch below
#   sudo BRANCH=main ./update-from-github.sh
#
# Needs git and access to github.com from this server. New container image
# versions (rare) still come with a new offline bundle.
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/nehraeduhub/CyberSecuirty.git}
BRANCH=${BRANCH:-ccr-1e4e396d-l3nt7b}
SRC=${SRC:-/opt/dc/dc-kit-git}

[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
command -v git >/dev/null || { echo "git is not installed (apt install git)." >&2; exit 1; }

# The installed kit: from the running stack, or KIT=/path/to/site/datacenter-offline
KIT=${KIT:-$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' dc-portal-1 2>/dev/null || true)}
[ -n "$KIT" ] && [ -f "$KIT/docker-compose.yml" ] || { echo "Installed kit not found; set KIT=/opt/dc/<bundle>/site/datacenter-offline" >&2; exit 1; }
SITE=$(dirname "$KIT")
BUNDLE=$(dirname "$SITE")
echo "Installed kit: $KIT"

if [ -d "$SRC/.git" ]; then
  git -C "$SRC" fetch --quiet origin "$BRANCH"
  git -C "$SRC" checkout --quiet -B "$BRANCH" "origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$SRC"
fi
echo "Source: $REPO_URL ($BRANCH) at $(git -C "$SRC" log -1 --format='%h %s')"

# Safety copy of what is installed now (small: no data, no images)
snap="$BUNDLE/kit-before-update-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -C "$SITE" --exclude=./datacenter-offline/backups -czf "$snap" .
echo "Previous kit saved to $snap"

# Program folders hold nothing of yours: replace them whole, so files removed
# in the new version (old pages and scripts) disappear too
rm -rf "$KIT/viewer" "$KIT/scripts" "$KIT/manager"
# Kit files, minus everything that is yours
tar -C "$SRC/datacenter-offline" \
  --exclude=./.env --exclude=./collector/collector.conf --exclude=./collector/ssh \
  --exclude=./backups --exclude=./tls -cf - . | tar -C "$KIT" -xf -
# Website, library and guide next to the kit
find "$SRC" -maxdepth 1 -type f \( -name '*.html' -o -name '*.jpg' \) -exec cp {} "$SITE/" \;
cp "$SRC"/DEPLOYMENT-GUIDE.* "$SRC"/README-FIRST.txt "$BUNDLE/" 2>/dev/null || true
cp "$KIT/scripts/install-offline.sh" "$BUNDLE/"
chmod +x "$BUNDLE/install-offline.sh" "$KIT"/scripts/*.sh "$KIT/collector/collect.sh"

echo "Applying the update (re-running the installer, safe to repeat)..."
cd "$BUNDLE"
./install-offline.sh < /dev/null
echo
echo "Updated. Check with: $KIT/scripts/verify.sh   (browser: press Ctrl+F5 once)"
