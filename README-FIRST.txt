NehraEduHub Data Centre Kit - offline production deployment
=============================================================

What this is
  GLPI asset management + automatic network collection + DC Viewer (racks,
  inventory dashboard) + Grafana up/down and network/hardware monitoring +
  the GLPI data centre learning library. Runs fully offline on one Linux
  server with Docker.

Start here
  1. Read DEPLOYMENT-GUIDE.html (open it in a browser) or DEPLOYMENT-GUIDE.md.
  2. On a PC WITH internet (Linux + Docker), build the offline bundle:
       SERVER_OS=ubuntu:24.04 ./datacenter-offline/scripts/prepare-offline-bundle.sh
  3. Copy dc-offline-bundle-YYYYMMDD.tar.gz to the OFFLINE server, then:
       sudo mkdir -p /opt/dc && sudo tar -xzf dc-offline-bundle-*.tar.gz -C /opt/dc
       cd /opt/dc/dc-offline-bundle-*/
       sudo ./site/datacenter-offline/scripts/preflight.sh
       sudo SERVER_NAME=dc.yourdomain.lan ./install-offline.sh
       sudo ./site/datacenter-offline/scripts/verify.sh
  4. Connect your equipment: datacenter-offline/EQUIPMENT.md

Contents
  DEPLOYMENT-GUIDE.md / .html     step-by-step production deployment (start here)
  datacenter-offline/             the kit (scripts, dashboards, viewer, configs)
    EQUIPMENT.md                  device setup: Sophos, Radware, HPE SimpliVity/VME,
                                  Accesleron, HP/Dell servers, Cisco/Dell/HP network
    README.md                     full reference
  index.html, glpi-datacenter-library.html, *.jpg   website + learning library

Supported servers: Ubuntu 24.04 / 22.04, Debian 12, RHEL / Rocky / AlmaLinux 9 (x86_64)
