#!/usr/bin/env bash
# Check the running stack end to end, AFTER install-offline.sh (and any time:
# after a reboot, an upgrade, or when something looks wrong). Changes nothing.
#   sudo ./scripts/verify.sh
set -uo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
set -a; . ./.env; set +a

fails=0 warns=0
pass() { printf '  [PASS] %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; warns=$((warns + 1)); }
fail() { printf '  [FAIL] %s\n' "$*"; fails=$((fails + 1)); }
code() { curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null; }
prom() { docker compose exec -T prometheus wget -qO- "http://localhost:9090/api/v1/$1" 2>/dev/null; }

tls=$(tr 'A-Z' 'a-z' <<<"${TLS:-no}")
if [ "$tls" = yes ]; then
  glpi_local="http://127.0.0.1:${GLPI_LOCAL_PORT:-8081}"; glpi_user="https://127.0.0.1:${HTTPS_PORT:-443}"; portal="https://127.0.0.1:${PORTAL_TLS_PORT:-8443}"
else
  glpi_local="http://127.0.0.1:${GLPI_PORT:-80}"; glpi_user="$glpi_local"; portal="http://127.0.0.1:${PORTAL_PORT:-8080}"
fi

echo "Containers"
for svc in db glpi portal collector monitor-sync blackbox snmp-exporter prometheus grafana; do
  state=$(docker compose ps --format '{{.State}} {{.Health}}' "$svc" 2>/dev/null | head -1)
  case "$state" in
    running*unhealthy*) fail "$svc is unhealthy" ;;
    running*) pass "$svc running" ;;
    *) fail "$svc is ${state:-not created} (docker compose logs $svc)" ;;
  esac
done
restarts=$(docker inspect -f '{{.Name}} {{.RestartCount}}' $(docker compose ps -q) 2>/dev/null | awk '$2 > 3 {print $1}' | tr -d / | xargs)
[ -n "$restarts" ] && warn "Restarting repeatedly: $restarts (check docker compose logs)"

echo
echo "Web"
c=$(code "$glpi_local/"); [[ $c =~ ^(200|302)$ ]] && pass "GLPI answers on $glpi_local" || fail "GLPI on $glpi_local returned ${c:-nothing}"
c=$(code "$glpi_user/"); [[ $c =~ ^(200|302)$ ]] && pass "GLPI for users: ${GLPI_PUBLIC_URL:-$glpi_user}" || fail "GLPI for users ($glpi_user) returned ${c:-nothing}"
c=$(code "$portal/viewer/"); [ "$c" = 200 ] && pass "DC Viewer: $portal/viewer/" || fail "DC Viewer returned ${c:-nothing}"
c=$(code "$portal/glpi-datacenter-library.html"); [ "$c" = 200 ] && pass "Learning library" || fail "Learning library returned ${c:-nothing}"
c=$(code "$portal/grafana/api/health"); [ "$c" = 200 ] && pass "Grafana" || fail "Grafana returned ${c:-nothing}"
if [ "$tls" = yes ]; then
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:${HTTP_REDIRECT_PORT:-80}/" 2>/dev/null)
  [ "$c" = 301 ] && pass "HTTP (port ${HTTP_REDIRECT_PORT:-80}) redirects to HTTPS" || warn "HTTP on port ${HTTP_REDIRECT_PORT:-80} returned ${c:-nothing} (expected a redirect)"
  if command -v openssl >/dev/null; then
    end=$(openssl x509 -in tls/server.crt -noout -enddate 2>/dev/null | cut -d= -f2)
  else
    end=$(docker run --rm --user 0:0 -v "$PWD/tls:/t:ro,z" --entrypoint openssl "glpi/glpi:$GLPI_VERSION" x509 -in /t/server.crt -noout -enddate 2>/dev/null | cut -d= -f2)
  fi
  if [ -n "$end" ]; then
    days=$(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
    if [ "$days" -lt 0 ]; then fail "HTTPS certificate expired on $end"
    elif [ "$days" -lt 30 ]; then warn "HTTPS certificate expires in $days days ($end)"
    else pass "HTTPS certificate valid for $days more days"; fi
  fi
fi

echo
echo "GLPI API and accounts"
tok=$(curl -s --max-time 15 -u "dc-monitor:${MONITOR_GLPI_PASSWORD:-}" "$glpi_local/apirest.php/initSession" | sed -n 's/.*"session_token":"\([^"]*\)".*/\1/p')
if [ -n "$tok" ]; then
  pass "REST API login (read-only account dc-monitor)"
  n=$(curl -s -o /dev/null -D - -H "Session-Token: $tok" "$glpi_local/apirest.php/NetworkEquipment?range=0-0" | sed -n 's/^Content-Range: .*\/\([0-9]*\).*/\1/Ip' | tr -d '\r')
  m=$(curl -s -o /dev/null -D - -H "Session-Token: $tok" "$glpi_local/apirest.php/Computer?range=0-0" | sed -n 's/^Content-Range: .*\/\([0-9]*\).*/\1/Ip' | tr -d '\r')
  pass "Inventory: ${m:-0} computers, ${n:-0} network devices"
  curl -s -o /dev/null -H "Session-Token: $tok" "$glpi_local/apirest.php/killSession"
else
  fail "REST API login failed for dc-monitor (scripts/configure-glpi.sh, then re-run install-offline.sh)"
fi
r=$(curl -s --max-time 15 -u glpi:glpi "$glpi_local/apirest.php/initSession")
case "$r" in
  *session_token*) fail "The super-admin 'glpi' still has the default password 'glpi' (change it: DEPLOYMENT-GUIDE step 6)" ;;
  *ERROR_GLPI_LOGIN*|*"Incorrect username or password"*) pass "Default 'glpi' password is changed" ;;
  *) warn "Could not check the 'glpi' password (API not answering yet)" ;;
esac

echo
echo "Collection and monitoring"
st=$(docker compose exec -T portal cat /usr/share/nginx/html/collector/status.json 2>/dev/null)
if [ -z "$st" ]; then
  warn "Collector has not finished a run yet"
else
  steps=$(grep -o '"name"' <<<"$st" | wc -l)
  errs=$(grep -o '"status":"error"' <<<"$st" | wc -l)
  fin=$(sed -n 's/.*"finished":"\([^"]*\)".*/\1/p' <<<"$st")
  if [ "$steps" -eq 0 ]; then warn "Collector has nothing to collect yet: edit collector/collector.conf"
  elif [ "$errs" -gt 0 ]; then warn "Collector: $errs of $steps step(s) failed on the last run (Inventory dashboard shows why)"
  else pass "Collector: last run finished ${fin:-?}, $steps step(s) OK"; fi
fi
sync=$(docker compose logs --tail 20 monitor-sync 2>/dev/null | grep -E "synced|failed" | tail -1)
case "$sync" in
  *synced*) pass "Monitoring targets: $(sed 's/.*synced/synced/' <<<"$sync")" ;;
  *failed*) fail "Monitoring target sync: $(sed 's/.*sync failed: //' <<<"$sync")" ;;
  *) warn "Monitoring target sync has not run yet" ;;
esac
count_by_job() { # up-state -> "job count" lines
  prom "query?query=count%20by%20(job)%20(up%3D%3D$1)" | grep -oE '"job":"[^"]+"\},"value":\[[0-9.]+,"[0-9]+"' \
    | sed -E 's/"job":"([^"]+)".*,"([0-9]+)"$/\1 \2/'
}
ok_jobs=$(count_by_job 1); bad_jobs=$(count_by_job 0)
[ -z "$ok_jobs$bad_jobs" ] && warn "Prometheus has no targets yet"
while read -r job cnt; do [ -n "$job" ] && pass "Prometheus $job: $cnt target(s) scraped"; done <<<"$ok_jobs"
while read -r job cnt; do [ -n "$job" ] && warn "Prometheus $job: $cnt target(s) not answering"; done <<<"$bad_jobs"
down=$(prom 'query?query=count(probe_success%7Bjob%3D%22device%22%7D%3D%3D0)' | sed -n 's/.*"value":\[[0-9.]*,"\([0-9]*\)".*/\1/p')
[ -n "$down" ] && [ "$down" != 0 ] && warn "$down monitored device(s) currently DOWN (Status tab)"

echo
echo "Housekeeping"
last=$(ls -1d backups/*/ 2>/dev/null | sort | tail -1)
if [ -z "$last" ]; then warn "No backup yet: run scripts/backup.sh and schedule it (guide, step 9)"
else
  age=$(( ( $(date +%s) - $(stat -c %Y "$last") ) / 3600 ))
  [ "$age" -le 36 ] && pass "Last backup $last (${age} h ago)" || warn "Last backup is ${age} hours old ($last)"
fi
root=$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
use=$(df --output=pcent "$root" | tail -1 | tr -dc 0-9)
[ "$use" -lt 85 ] && pass "Disk ${use}% used ($root)" || warn "Disk ${use}% used ($root)"

echo
if [ "$fails" -gt 0 ]; then echo "Result: $fails problem(s), $warns warning(s)"; exit 1; fi
echo "Result: all good ($warns warning(s))"
