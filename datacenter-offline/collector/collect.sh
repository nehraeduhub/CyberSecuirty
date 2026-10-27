#!/usr/bin/env bash
# Scheduled network collection into GLPI.
#   collect.sh loop   run every INTERVAL_MINUTES (container default)
#   collect.sh once   run one collection now and exit
set -uo pipefail

CONF=${COLLECTOR_CONF:-/etc/collector/collector.conf}
GLPI_URL=${GLPI_URL:-http://glpi/}
STATUS_DIR=${STATUS_DIR:-/status}
LOCK=/tmp/collect.lock
WORK=

log() { echo "$(date '+%F %T') $*"; }

# Print non-empty, non-comment lines of a multi-line variable ("  # note" at the
# end of a line is a comment too)
lines() { printf '%s\n' "$1" | sed -e 's/[[:space:]][[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v -e '^$' -e '^#' || true; }

json_escape() { sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\n\r'; }

declare -a STEPS=()

# Record one step's result for the dashboard
step() { # name status files sent detail
  STEPS+=("{\"name\":\"$1\",\"status\":\"$2\",\"files\":$3,\"sent\":$4,\"detail\":\"$(printf '%s' "$5" | json_escape)\"}")
}

write_status() { # state started finished
  mkdir -p "$STATUS_DIR"
  local steps
  steps=$(IFS=,; echo "${STEPS[*]:-}")
  cat > "$STATUS_DIR/status.json.tmp" <<JSON
{"state":"$1","started":"$2","finished":"$3","interval_minutes":${INTERVAL_MINUTES:-60},"steps":[${steps}]}
JSON
  mv "$STATUS_DIR/status.json.tmp" "$STATUS_DIR/status.json"
}

# Send every inventory file in a directory to GLPI; echo "files sent"
inject() {
  local dir=$1 files left
  files=$(find "$dir" -type f | wc -l)
  if [ "$files" -gt 0 ]; then
    glpi-injector --recursive --directory "$dir" --url "$GLPI_URL" --remove >/dev/null 2>&1
  fi
  left=$(find "$dir" -type f | wc -l)
  echo "$files $((files - left))"
}

collect_snmp() {
  local creds=() range first last out n=0
  while IFS= read -r c; do creds+=(--credentials "$c"); done < <(lines "${SNMP_CREDENTIALS:-}")
  if [ -n "$(lines "${SNMP_RANGES:-}")" ] && [ ${#creds[@]} -eq 0 ]; then
    step "SNMP" error 0 0 "SNMP_RANGES is set but SNMP_CREDENTIALS is empty in collector.conf"
    log "SNMP skipped: no SNMP_CREDENTIALS configured"
    return 0
  fi
  while IFS= read -r range; do
    n=$((n + 1))
    first=${range%-*}; last=${range#*-}
    out=$WORK/snmp-$n
    mkdir -p "$out"
    log "SNMP discovery $first - $last"
    if glpi-netdiscovery --first "$first" --last "$last" "${creds[@]}" \
        --threads "${THREADS:-16}" --timeout "${SNMP_TIMEOUT:-2}" --inventory --save "$out" >/dev/null 2>"$out.err"; then
      read -r files sent < <(inject "$out")
      log "  $files result file(s), $sent sent to GLPI"
      step "SNMP $range" ok "$files" "$sent" ""
    else
      step "SNMP $range" error 0 0 "$(tail -3 "$out.err")"
      log "  failed: $(tail -1 "$out.err")"
    fi
  done < <(lines "${SNMP_RANGES:-}")
}

# Trust-on-first-use for SSH targets (like StrictHostKeyChecking=accept-new):
# record a host key the first time a server is seen; a changed key later fails
# the connection instead of being silently accepted.
trust_ssh_hosts() {
  local kh=$HOME/.ssh/known_hosts url host port
  mkdir -p "$HOME/.ssh"; touch "$kh"
  for url in $(tr ',' ' ' <<<"$1"); do
    case "$url" in ssh://*) ;; *) continue ;; esac
    host=${url#ssh://}; host=${host#*@}; host=${host%%/*}
    port=22
    if [[ $host =~ ^(.+):([0-9]+)$ ]]; then host=${BASH_REMATCH[1]}; port=${BASH_REMATCH[2]}; fi
    local entry=$host
    [ "$port" = 22 ] || entry="[$host]:$port"
    if ! ssh-keygen -F "$entry" -f "$kh" >/dev/null 2>&1; then
      if ssh-keyscan -T 5 -p "$port" -t ed25519,ecdsa,rsa "$host" >>"$kh" 2>/dev/null; then
        log "  trusted new SSH host key for $entry"
      fi
    fi
  done
}

collect_remotes() {
  local list out
  list=$(lines "${REMOTES:-}" | paste -sd, -)
  [ -n "$list" ] || return 0
  out=$WORK/remote
  mkdir -p "$out"
  log "Agentless inventory of $(tr ',' '\n' <<<"$list" | wc -l) server(s)"
  trust_ssh_hosts "$list"
  glpi-agent --local "$out" --tasks remoteinventory --remote "$list" \
    --remote-workers "${THREADS:-16}" --force >/dev/null 2>"$out.err"
  read -r files sent < <(inject "$out")
  local total
  total=$(tr ',' '\n' <<<"$list" | wc -l)
  if [ "$files" -lt "$total" ]; then
    step "Servers (SSH/WinRM)" warning "$files" "$sent" "$((total - files)) of $total server(s) did not answer: $(grep -i -m2 'error\|fail' "$out.err")"
  else
    step "Servers (SSH/WinRM)" ok "$files" "$sent" ""
  fi
  log "  $files of $total inventoried, $sent sent to GLPI"
}

collect_esx() {
  local host user pass out n=0
  while read -r host user pass; do
    [ -n "${pass:-}" ] || continue
    n=$((n + 1))
    out=$WORK/esx-$n
    mkdir -p "$out"
    log "VMware inventory $host"
    if glpi-esx --host "$host" --user "$user" --password "$pass" --path "$out" --json >/dev/null 2>"$out.err"; then
      read -r files sent < <(inject "$out")
      step "VMware $host" ok "$files" "$sent" ""
    else
      step "VMware $host" error 0 0 "$(tail -2 "$out.err")"
    fi
  done < <(lines "${ESX_HOSTS:-}")
}

run_once() {
  # shellcheck disable=SC1090
  [ -f "$CONF" ] && . "$CONF" || { log "No $CONF - copy collector.conf.example to collector.conf"; }
  STEPS=()
  local started
  started=$(date -u +%FT%TZ)
  write_status running "$started" ""
  WORK=$(mktemp -d /tmp/collect.XXXXXX)
  collect_snmp
  collect_remotes
  collect_esx
  write_status idle "$started" "$(date -u +%FT%TZ)"
  rm -rf "$WORK"
  log "Collection finished"
}

# One collection at a time: "once" waits for a scheduled run in progress
run_locked() {
  exec 9>"$LOCK"
  if ! flock -n 9; then
    log "A collection is already running - waiting for it to finish"
    flock 9
  fi
  run_once
  flock -u 9
}

case "${1:-loop}" in
  once) run_locked ;;
  loop)
    while true; do
      run_locked
      # shellcheck disable=SC1090
      [ -f "$CONF" ] && . "$CONF"
      sleep "$(( ${INTERVAL_MINUTES:-60} * 60 ))"
    done ;;
  *) exec "$@" ;;
esac
