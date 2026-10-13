# Network collector: GLPI Agent with network discovery/inventory, remote (SSH/WinRM)
# and ESX tasks, run on a schedule by collect.sh. Built on the online machine by
# prepare-offline-bundle.sh, then shipped as an image in the offline bundle.
FROM ubuntu:24.04

ARG AGENT_VERSION
COPY glpi-agent-${AGENT_VERSION}-linux-installer.pl /tmp/glpi-agent-installer.pl

RUN apt-get update \
 && apt-get install -y --no-install-recommends perl ca-certificates openssh-client iputils-ping \
 && perl /tmp/glpi-agent-installer.pl --install --type=all --silent --no-question --service=0 --cron=0 \
 && rm -f /tmp/glpi-agent-installer.pl \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY collect.sh /usr/local/bin/collect.sh
RUN chmod 755 /usr/local/bin/collect.sh

ENTRYPOINT ["/usr/local/bin/collect.sh"]
CMD ["loop"]
