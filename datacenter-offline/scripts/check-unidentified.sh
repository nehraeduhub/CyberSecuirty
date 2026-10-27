#!/usr/bin/env bash
# Explain the "Unidentified devices" (GLPI Unmanaged items): addresses that
# answered ping/ARP during the scan but not SNMP. For each one this checks
# SNMP again (your credentials, then "public"), a few TCP ports and the SSH
# banner, and says what the device probably is and what to add to
# collector/collector.conf so it is fully inventoried. Changes nothing.
#
#   sudo ./scripts/check-unidentified.sh            # all unidentified devices
#   sudo ./scripts/check-unidentified.sh 10.10.0.   # only addresses starting with this
#   sudo ./scripts/check-unidentified.sh --csv > unidentified.csv
#
# Add what was found to collector.conf (only the kinds you give an account for;
# a missing password is asked for; addresses already listed are skipped):
#   sudo ./scripts/check-unidentified.sh --write --ssh-user inventory \
#        --winrm-user 'CORP\svc-inventory' --esx-user svc-glpi
#     Linux servers -> REMOTES ssh://USER@ip   (authorise collector/ssh/id_ed25519.pub on them)
#     Windows       -> REMOTES winrm://USER:PASSWORD@ip
#     ESXi hosts    -> ESX_HOSTS "ip USER PASSWORD" (or list your vCenter once instead)
set -euo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
CONF=$KIT/collector/collector.conf
cd "$KIT"

csv=no prefix="" write=no ssh_user="" winrm_user="" winrm_pass="" esx_user="" esx_pass=""
while [ $# -gt 0 ]; do
  case "$1" in
    --csv) csv=yes ;;
    --write) write=yes ;;
    --ssh-user) ssh_user=${2:?}; shift ;;
    --winrm-user) winrm_user=${2:?}; shift ;;
    --winrm-pass) winrm_pass=${2:?}; shift ;;
    --esx-user) esx_user=${2:?}; shift ;;
    --esx-pass) esx_pass=${2:?}; shift ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Unknown option $1 (see --help)" >&2; exit 1 ;;
    *) prefix=$1 ;;
  esac
  shift
done
if [ "$write" = yes ]; then
  [ -n "$ssh_user$winrm_user$esx_user" ] || { echo "--write needs at least one of --ssh-user, --winrm-user, --esx-user" >&2; exit 1; }
  [ -f "$CONF" ] || { echo "No $CONF yet: run install-offline.sh first." >&2; exit 1; }
  if [ -n "$winrm_user" ] && [ -z "$winrm_pass" ]; then read -r -s -p "Password for $winrm_user (Windows): " winrm_pass; echo; fi
  if [ -n "$esx_user" ] && [ -z "$esx_pass" ]; then read -r -s -p "Password for $esx_user (ESXi): " esx_pass; echo; fi
fi

[ -f .env ] || { echo "No .env: run install-offline.sh first." >&2; exit 1; }
db_val() { grep "^$1=" .env | tail -1 | cut -d= -f2-; }
running=$(docker compose ps --status running --services 2>/dev/null)
for s in db collector; do
  grep -qx "$s" <<<"$running" || { echo "The $s container is not running (docker compose up -d)." >&2; exit 1; }
done

lines() { printf '%s\n' "$1" | sed -e 's/[[:space:]][[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v -e '^$' -e '^#' || true; }
creds=""
if [ -f "$CONF" ]; then
  creds=$( ( set +u; SNMP_CREDENTIALS=""; . "$CONF" >/dev/null 2>&1; lines "$SNMP_CREDENTIALS" ) | paste -sd';' - || true)
fi

# Unidentified items with their IP (from the port's address, or the item's own ip field) and MAC
list=$(docker compose exec -T db mariadb -u"$(db_val GLPI_DB_USER)" -p"$(db_val GLPI_DB_PASSWORD)" "$(db_val GLPI_DB_NAME)" -N -e "
  SELECT COALESCE(MIN(ip.name), NULLIF(u.ip, ''), u.name), COALESCE(MIN(p.mac), '')
  FROM glpi_unmanageds u
  LEFT JOIN glpi_ipaddresses ip ON ip.mainitemtype = 'Unmanaged' AND ip.mainitems_id = u.id
       AND ip.is_deleted = 0 AND ip.version = 4
  LEFT JOIN glpi_networkports p ON p.itemtype = 'Unmanaged' AND p.items_id = u.id AND p.is_deleted = 0
  WHERE u.is_deleted = 0 AND u.hub = 0
  GROUP BY u.id" \
  | awk -F'\t' -v p="$prefix" '$1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && index($1, p) == 1' | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n -u)

if [ -z "$list" ]; then
  echo "No unidentified devices${prefix:+ matching $prefix}."
  exit 0
fi
[ "$csv" = yes ] || echo "Checking $(wc -l <<<"$list") unidentified device(s) (about 15 s each, 8 at a time)..." >&2

# 8 probes in parallel inside the collector (the Perl script is passed as an argument)
out=$(printf '%s\n' "$list" | docker compose exec -T collector sh -c '
  f=$(mktemp -d); cd "$f"; printf "%s\n" "$2" > probe.pl; cat > list; split -n l/8 list part.
  for p in part.*; do perl probe.pl "$1" < "$p" > "$p.out" 2> "$p.err" & done; wait
  cat part.*.out; cat part.*.err | sort -u | sed "s/^/ERR: /"; cd /; rm -rf "$f"' sh "$creds" "$(cat scripts/check-unidentified.pl)" 2>&1) || true
result=$(awk -F'\t' 'NF >= 6 && $1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/' <<<"$out")
if [ -z "$result" ]; then
  echo "The probe gave no results. Output from the collector:" >&2
  printf '%s\n' "$out" | head -20 >&2
  exit 1
fi

result=$(sort -t. -k1,1n -k2,2n -k3,3n -k4,4n <<<"$result")
if [ "$csv" = yes ]; then
  echo "ip,mac,open_ports,ssh_banner,probably,what_to_do"
  awk -F'\t' '{ for (i = 1; i <= NF; i++) { gsub(/"/, "\"\"", $i); printf "%s\"%s\"", (i > 1 ? "," : ""), $i } print "" }' <<<"$result"
  exit 0
fi

while IFS=$'\t' read -r ip mac ports banner what todo; do
  printf '\n%s  (MAC %s, open: %s)\n  probably: %s\n  do:       %s\n' "$ip" "$mac" "$ports" "$what" "$todo"
done <<<"$result"
echo
echo "Summary:"
cut -f5 <<<"$result" | sed 's/ (.*//' | sort | uniq -c | sort -rn | sed 's/^/  /'
errs=$(grep '^ERR: ' <<<"$out" | sort -u || true)
if [ -n "$errs" ]; then
  echo
  echo "Problems with your SNMP_CREDENTIALS (these credentials could not be used):"
  sed 's/^ERR: /  /' <<<"$errs"
fi

# ---- Lines for collector.conf
urlenc() { local s=$1 out="" c i; for ((i = 0; i < ${#s}; i++)); do c=${s:i:1}
  case "$c" in [A-Za-z0-9._~-]) out+=$c ;; *) out+=$(printf '%%%02X' "'$c") ;; esac; done; printf '%s' "$out"; }
dq() { printf '%s' "$1" | sed 's/[\\$`"]/\\&/g'; }   # safe inside "..." in collector.conf
already=$( [ -f "$CONF" ] && grep -v '^[[:space:]]*#' "$CONF" || true)
listed() { grep -qE "(@|^|[[:space:]])$(sed 's/\./\\./g' <<<"$1")([[:space:]:/]|$)" <<<"$already"; }
ips_of() { awk -F'\t' -v w="$1" 'index($5, w) == 1 {print $1}' <<<"$result"; }
remotes=() esx=()
su=${ssh_user:-inventory}
for ip in $(ips_of "Linux/Unix server"); do listed "$ip" || remotes+=("ssh://$su@$ip"); done
if [ -n "$winrm_user" ]; then wu="$(urlenc "$winrm_user"):$(dq "$(urlenc "$winrm_pass")")"; else wu="inventory:PASSWORD"; fi
for ip in $(ips_of "Windows server"); do listed "$ip" || remotes+=("winrm://$wu@$ip"); done
for ip in $(ips_of "VMware ESXi host"); do
  listed "$ip" || esx+=("$ip ${esx_user:-USER} $( [ -n "$esx_user" ] && dq "$esx_pass" || echo PASSWORD)")
done

if [ "$write" != yes ]; then
  if [ ${#remotes[@]} -gt 0 ] || [ ${#esx[@]} -gt 0 ]; then
    echo
    echo "To add these servers automatically (accounts asked for, nothing else changes):"
    echo "  sudo ./scripts/check-unidentified.sh --write --ssh-user inventory --winrm-user 'DOMAIN\\user' --esx-user root"
    echo "  (leave out the kinds you don't want; --help for details)"
  fi
else
  add_r=() add_e=()
  for r in "${remotes[@]}"; do
    case "$r" in ssh://*) [ -n "$ssh_user" ] && add_r+=("$r") ;; winrm://*) [ -n "$winrm_user" ] && add_r+=("$r") ;; esac
  done
  [ -n "$esx_user" ] && add_e=("${esx[@]}")
  if [ ${#add_r[@]} -eq 0 ] && [ ${#add_e[@]} -eq 0 ]; then
    echo; echo "Nothing new to add to collector.conf."
  else
    cp -p "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"
    R=$(printf '%s  # found by check-unidentified\n' "${add_r[@]}" | grep -v '^  #' || true)
    E=$(printf '%s  # found by check-unidentified\n' "${add_e[@]}" | grep -v '^  #' || true)
    R=$R E=$E awk '
      { print }
      /^REMOTES="/ && !r { r = 1; if (ENVIRON["R"] != "") print ENVIRON["R"] }
      /^ESX_HOSTS="/ && !e { e = 1; if (ENVIRON["E"] != "") print ENVIRON["E"] }
    ' "$CONF" > "$CONF.tmp"
    grep -q '^REMOTES="' "$CONF" || [ -z "$R" ] || printf '\nREMOTES="\n%s\n"\n' "$R" >> "$CONF.tmp"
    grep -q '^ESX_HOSTS="' "$CONF" || [ -z "$E" ] || printf '\nESX_HOSTS="\n%s\n"\n' "$E" >> "$CONF.tmp"
    cat "$CONF.tmp" > "$CONF" && rm -f "$CONF.tmp"
    echo
    echo "Added to collector/collector.conf: ${#add_r[@]} server(s) to REMOTES, ${#add_e[@]} ESXi host(s) to ESX_HOSTS (backup: collector.conf.bak.*)."
    [ -n "$ssh_user" ] && echo "Linux servers: put this key in ~$ssh_user/.ssh/authorized_keys on each: $(cat collector/ssh/id_ed25519.pub 2>/dev/null || echo 'collector/ssh/id_ed25519.pub')"
  fi
fi

echo
echo "After changing collector/collector.conf: docker compose restart collector monitor-sync"
echo "and collect again: docker compose exec collector collect.sh once"
echo "Devices that become identified are merged; delete leftover ones in GLPI under"
echo "Assets > Unmanaged devices (or ignore PCs and phones)."
