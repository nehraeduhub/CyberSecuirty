#!/usr/bin/env bash
# Configure a fresh GLPI for the offline data centre kit:
#   - enable native inventory (GLPI Agent + SNMP results)
#   - enable the REST API with login by credentials (used by DC Viewer and import_layout.py)
#   - allow the API from the Docker network (portal + this host) and an optional admin LAN range
# Safe to run more than once.
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
set -a; . ./.env; set +a

compose() { docker compose "$@"; }
console() { compose exec -T glpi php bin/console --no-interaction "$@"; }
sql() { compose exec -T db mariadb -u"$GLPI_DB_USER" -p"$GLPI_DB_PASSWORD" "$GLPI_DB_NAME" -N -e "$1"; }

ip2int() { awk -F. '{ printf "%.0f", (($1*256+$2)*256+$3)*256+$4 }' <<<"$1"; }

# Convert a CIDR (a.b.c.d/nn) to "start end" integers
cidr_range() {
  local ip=${1%/*} bits=${1#*/} base size
  base=$(ip2int "$ip")
  size=$(awk -v b="$bits" 'BEGIN { printf "%.0f", 2^(32-b) }')
  base=$(awk -v x="$base" -v s="$size" 'BEGIN { printf "%.0f", x - (x % s) }')
  echo "$base $(awk -v x="$base" -v s="$size" 'BEGIN { printf "%.0f", x + s - 1 }')"
}

upsert_client() {
  local name=$1 start=$2 end=$3
  local id
  id=$(sql "SELECT id FROM glpi_apiclients WHERE name='$name' LIMIT 1")
  if [ -n "$id" ]; then
    sql "UPDATE glpi_apiclients SET is_active=1, ipv4_range_start=$start, ipv4_range_end=$end, date_mod=NOW() WHERE id=$id"
  else
    sql "INSERT INTO glpi_apiclients (entities_id, is_recursive, name, is_active, ipv4_range_start, ipv4_range_end, dolog_method, date_creation, date_mod)
         VALUES (0, 1, '$name', 1, $start, $end, 0, NOW(), NOW())"
  fi
  echo "  API client '$name' allowed: $start - $end"
}

echo "Waiting for GLPI to finish installing..."
for _ in $(seq 1 60); do
  if console config:set --help >/dev/null 2>&1 && [ -n "$(sql "SHOW TABLES LIKE 'glpi_apiclients'" 2>/dev/null)" ]; then
    break
  fi
  sleep 5
done

echo "Enabling inventory and REST API..."
console config:set --context=inventory enabled_inventory 1
console config:set enable_api 1
console config:set enable_api_login_credentials 1
console config:set enable_api_login_external_token 1

echo "Allowing API access..."
subnet=$(docker network inspect "$(compose ps -q glpi | xargs docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')" \
  -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' | tr ' ' '\n' | grep -m1 '\.')
read -r s e < <(cidr_range "$subnet")
upsert_client "DC kit - docker network ($subnet)" "$s" "$e"

if [ -n "${API_ADMIN_RANGE_START:-}" ] && [ -n "${API_ADMIN_RANGE_END:-}" ]; then
  upsert_client "DC kit - admin LAN" "$(ip2int "$API_ADMIN_RANGE_START")" "$(ip2int "$API_ADMIN_RANGE_END")"
fi

# Manufacturer names: SNMP reports HPE iLO as "Compaq" and Radware Alteon as
# "Nortel"/"Alteon" (legacy owners of those OID ranges). Dictionary rules fix the
# name for new inventory; replaying them fixes what is already in GLPI.
add_manufacturer_rule() { # uuid name regex new-name
  local id
  id=$(sql "SELECT id FROM glpi_rules WHERE uuid='$1'")
  if [ -z "$id" ]; then
    sql "INSERT INTO glpi_rules (entities_id, sub_type, ranking, name, description, \`match\`, is_active, comment,
           is_recursive, uuid, \`condition\`, date_creation, date_mod)
         VALUES (0, 'RuleDictionnaryManufacturer', 0, '$2', '', 'AND', 1, 'Added by the DC kit', 1, '$1', 0, NOW(), NOW())"
    id=$(sql "SELECT id FROM glpi_rules WHERE uuid='$1'")
    sql "INSERT INTO glpi_rulecriterias (rules_id, criteria, \`condition\`, pattern) VALUES ($id, 'name', 6, '$3')"
    sql "INSERT INTO glpi_ruleactions (rules_id, action_type, field, value) VALUES ($id, 'assign', 'name', '$4')"
    echo "  manufacturer rule: $2"
  fi
}
echo "Manufacturer name rules..."
add_manufacturer_rule dckit-manufacturer-hpe 'HPE: Compaq (iLO) -> Hewlett Packard Enterprise' '/^(Compaq|HPE)$/i' 'Hewlett Packard Enterprise'
add_manufacturer_rule dckit-manufacturer-radware 'Radware: Alteon/Nortel -> Radware' '/^(Alteon|Nortel)$/i' 'Radware'
console rules:replay_dictionnary_rules --dictionnary=Manufacturer >/dev/null 2>&1 || true

echo "GLPI configured."
