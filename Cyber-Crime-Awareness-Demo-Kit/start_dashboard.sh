#!/usr/bin/env bash
set -u; DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
F="$DIR/MASTER_DASHBOARD.html"; echo "Opening $F"
command -v xdg-open>/dev/null&&xdg-open "$F"||command -v open>/dev/null&&open "$F"||echo "Open manually: $F"
