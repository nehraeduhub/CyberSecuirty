#!/usr/bin/env bash
# Change the Tech Guardians access passphrase across ALL gated pages.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$DIR/.." && pwd)"; SALT="TG-KIT-SALT-9f3a"
read -r -s -p "New passphrase: " P1; echo; read -r -s -p "Confirm: " P2; echo
[ "$P1" = "$P2" ] || { echo "Mismatch."; exit 1; }; [ -n "$P1" ] || { echo "Empty not allowed."; exit 1; }
NEW=$(printf '%s' "${SALT}${P1}" | sha256sum | awk '{print $1}')
OLD=$(grep -oE '[0-9a-f]{64}' "$DIR/LOGIN.html" | head -1)
# update every file that carries the old hash
grep -rlE "$OLD" "$ROOT" --include='*.html' 2>/dev/null | while read -r f; do sed -i "s/$OLD/$NEW/g" "$f"; done
echo "Passphrase updated on all gated pages. New hash: $NEW"
echo "If your site is live, re-upload the changed .html files (or rebuild the web zip)."
