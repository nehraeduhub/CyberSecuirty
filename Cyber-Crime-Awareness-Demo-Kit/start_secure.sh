#!/usr/bin/env bash
# Tech Guardians — secure launch. Serves the kit on 127.0.0.1 and opens the locked login.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PORT="${1:-8080}"
URL="http://127.0.0.1:${PORT}/ACCESS_CONTROL/LOGIN.html"
echo "TECH GUARDIANS — opening locked login: $URL  (Ctrl+C to stop)"
( sleep 1; command -v xdg-open>/dev/null&&xdg-open "$URL"||command -v open>/dev/null&&open "$URL" ) >/dev/null 2>&1 &
cd "$DIR" || exit 1; python3 -m http.server "$PORT" --bind 127.0.0.1
