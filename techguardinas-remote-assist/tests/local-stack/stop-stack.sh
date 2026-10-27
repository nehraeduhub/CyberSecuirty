#!/bin/bash
# Stops everything started by start-stack.sh (works from any network namespace: uses signals/pid files).
. "${STACK_ENV:-$(dirname "$0")/stack.env}"
killpat() { for p in $(pgrep -f -- "$1"); do [ "$p" = "$$" ] || [ "$p" = "$PPID" ] || kill "$p" 2>/dev/null; done; }
su postgres -c "$PG_BIN/pg_ctl -D $WORK/pg stop -m fast" >/dev/null 2>&1 || true
[ -f "$WORK/nginx.pid" ] && kill "$(cat "$WORK/nginx.pid")" 2>/dev/null
killpat "redis-server 127.0.0.1:6379"
killpat "node node_modules/meshcentral"
killpat "gunicorn core.wsgi"
killpat "manage.py session_worker"
killpat "user-data-dir=$WORK"
pkill -x meshagent 2>/dev/null
for d in :5 :6; do killpat "Xvfb $d"; done
sleep 2; pkill -9 -x meshagent 2>/dev/null; true
