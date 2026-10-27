#!/bin/sh
# TEST HARNESS ONLY: install the loginctl stub when systemd-logind is not running (containers).
set -e
if [ -S /run/systemd/private ] && pgrep -x systemd-logind >/dev/null; then exit 0; fi
[ -f /usr/bin/loginctl.real ] || { [ -f /usr/bin/loginctl ] && mv /usr/bin/loginctl /usr/bin/loginctl.real || true; }
install -m 0755 "$(dirname "$0")/loginctl" /usr/bin/loginctl
touch /var/run/utmp
