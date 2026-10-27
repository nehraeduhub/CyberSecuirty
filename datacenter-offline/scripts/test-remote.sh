#!/usr/bin/env bash
# Test the login to ONE server from REMOTES (SSH or WinRM) and explain why it
# fails. Takes the IP (its line is looked up in collector/collector.conf) or a
# full URL. Changes nothing.
#
#   sudo ./scripts/test-remote.sh 10.10.1.40
#   sudo ./scripts/test-remote.sh 'winrm://inventory:PASSWORD@10.10.1.40'
set -euo pipefail

KIT=$(cd "$(dirname "$0")/.." && pwd)
CONF=$KIT/collector/collector.conf
cd "$KIT"
arg=${1:?usage: $0 <ip | ssh://user@ip | winrm://user:password@ip>}

lines() { printf '%s\n' "$1" | sed -e 's/[[:space:]][[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v -e '^$' -e '^#' || true; }
if [[ "$arg" == *://* ]]; then url=$arg
else
  url=$( ( set +u; REMOTES=""; . "$CONF" >/dev/null 2>&1; lines "$REMOTES" ) | grep -E "@$(sed 's/\./\\./g' <<<"$arg")([:/?]|$)" | head -1 || true)
  [ -n "$url" ] || { echo "$arg is not in REMOTES in collector/collector.conf (or pass the full URL)." >&2; exit 1; }
fi
host=$(sed -E 's#^[a-z+]+://([^@]*@)?([^:/?]+).*#\2#' <<<"$url")
echo "Testing $(sed -E 's#(://[^:@/]*):[^@]*@#\1:****@#' <<<"$url")"

docker compose exec -T collector sh -c '
url=$1 host=$2
case "$url" in
  winrm*)
    port=5985; case "$url" in *mode=ssl*|*:5986*) port=5986;; esac
    # Which logins does the server offer? The GLPI agent can only use Basic.
    perl -MLWP::UserAgent -e "
      my \$ua = LWP::UserAgent->new(timeout => 8, ssl_opts => { verify_hostname => 0, SSL_verify_mode => 0 });
      my \$r = \$ua->post(\"http\" . (\$ARGV[1] == 5986 ? q(s) : q()) . \"://\$ARGV[0]:\$ARGV[1]/wsman\", Content_Type => q(application/soap+xml;charset=UTF-8), Content => q());
      if (\$r->code == 500 && (\$r->header(q(Client-Warning)) // q()) eq q(Internal response)) { print qq(  WinRM port \$ARGV[1]: CLOSED or blocked\n); exit 1 }
      my @a = \$r->header(q(WWW-Authenticate)); my \$a = join q(, ), map { (split / /)[0] } @a;
      print qq(  WinRM port \$ARGV[1]: open, server offers: ), (\$a || q(nothing)), qq(\n);
      exit(\$a =~ /Basic/ ? 0 : 2);
    " "$host" "$port"
    rc=$?
    if [ $rc = 1 ]; then echo "  FIX: on the server run: winrm quickconfig  (and allow TCP $port from this server)"; exit 0; fi
    if [ $rc = 2 ]; then
      echo "  PROBLEM: Basic login is OFF. The GLPI agent can only log in to WinRM with Basic,"
      echo "  so every password looks wrong. Fix on the Windows server (admin PowerShell):"
      echo "    winrm set winrm/config/service/auth @{Basic=\"true\"}"
      [ $port = 5985 ] && echo "    winrm set winrm/config/service @{AllowUnencrypted=\"true\"}"
      echo "  and use a LOCAL account (Basic does not work with domain accounts), see EQUIPMENT.md."
      exit 0
    fi ;;
  ssh*)
    if ! perl -MIO::Socket::INET -e "exit !IO::Socket::INET->new(PeerAddr => \$ARGV[0], PeerPort => 22, Timeout => 5)" "$host"; then
      echo "  SSH port 22: CLOSED or blocked"; exit 0
    fi
    echo "  SSH port 22: open"
    # Trust its host key on first use, as collect.sh does
    kh=$HOME/.ssh/known_hosts; mkdir -p "$HOME/.ssh"; touch "$kh"
    ssh-keygen -F "$host" -f "$kh" >/dev/null 2>&1 || ssh-keyscan -T 5 -t ed25519,ecdsa,rsa "$host" >> "$kh" 2>/dev/null || true ;;
esac
d=$(mktemp -d)
glpi-agent --local "$d" --tasks remoteinventory --remote "$url" --force --debug 2>&1 \
  | grep -i -E "authenticat|denied|wrong|refused|timeout|error|failed|permission|publickey|winrm|ssh" \
  | grep -v -i "iec61850" | sed -E "s#(://[^:@/]*):[^@]*@#\1:****@#g" | head -15 | sed "s/^/  /"
if ls "$d"/* >/dev/null 2>&1; then echo "  RESULT: login OK, inventory works for this server"
else
  echo "  RESULT: no inventory."
  case "$url" in
    ssh*) echo "  Check: the user exists and collector/ssh/id_ed25519.pub is in its ~/.ssh/authorized_keys" ;;
    winrm*) echo "  Check: LOCAL account and password (domain accounts do not work), member of Administrators" ;;
  esac
fi
rm -rf "$d"' sh "$url" "$host"
