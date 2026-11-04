#!/usr/bin/env bash
set -u; DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/08_PHISHING_AWARENESS/local_demo"; PORT="${1:-8000}"
echo "LOCAL phishing awareness simulation (stores/sends nothing) — http://127.0.0.1:$PORT/  (Ctrl+C to stop)"
cd "$DIR" || { echo "demo folder missing"; exit 1; }; python3 -m http.server "$PORT" --bind 127.0.0.1
