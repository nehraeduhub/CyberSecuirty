# Network ports

Two internal DNS names, both resolving to the TechGuardinas Remote server (NGINX):
`remote.<domain>` (portal) and `mesh.remote.<domain>` (remote-control engine). One TLS certificate
from the internal CA with both names as SANs. Endpoints and technician PCs must trust that CA (GPO).

## Required flows

| # | From | To | Port | Purpose |
|---|---|---|---|---|
| 1 | Technician / admin / auditor browsers | portal name | TCP 443 (HTTPS) | Portal UI and API |
| 2 | Technician browsers | engine name | TCP 443 (HTTPS + WSS) | Embedded remote console (desktop/terminal/files), chat window |
| 3 | Remote user browser (attended) | portal name | TCP 443 (HTTPS) | Join page and support-agent download |
| 4 | Endpoint agents (attended and unattended) | engine name | TCP 443 (WSS) | Agent control channel (`/agent.ashx`) **and** relay tunnels (`/meshrelay.ashx`) |
| 5 | Admin workstation | portal name | TCP 443 | Agent installer download for GPO staging |
| 6 | Server | AD domain controllers | TCP 636 (LDAPS) | Only if AD login is enabled |
| 7 | Server, technician PCs | NTP | UDP 123 | TOTP MFA requires correct clocks on server and phones/PCs |
| 8 | Server | internal DNS | UDP/TCP 53 | Name resolution |
| — | Any browser | server | TCP 80 (or `HTTP_PORT`, e.g. 8008) | Optional: redirect to HTTPS only |

**Relay traffic** is flow 4 (agent side) and flow 2 (technician side): MeshCentral relays every
desktop, terminal and file session between the two TLS connections on TCP 443. WebRTC/peer-to-peer
is disabled, so no UDP or high ports are needed between technician and endpoint.

## Inside the Docker host (not exposed)

| From | To | Port |
|---|---|---|
| NGINX | web (gunicorn) | TCP 8000 |
| NGINX | frontend | TCP 80 |
| NGINX | meshcentral | TCP 4430 (HTTP, TLS terminated at NGINX) |
| web, worker | db (PostgreSQL) | TCP 5432 |
| web, worker | redis | TCP 6379 |
| web, worker | NGINX (engine name, internal alias) | TCP 443 — MeshCentral control websocket and agent downloads |
| meshcentral | NGINX (engine name, internal alias) | TCP 443 — reads the served certificate (`certUrl`) |

## Not required — keep closed

RDP 3389, SMB 445, WinRM 5985/5986, any inbound port on endpoints, Intel AMT 16992–16995 and the
MeshCentral MPS port 4433 (disabled in the configuration), PostgreSQL/Redis from outside the host.
No outbound Internet access is needed by the server, the agents or the browsers.

## Optional zoning

Placing NGINX in a DMZ and the containers in an application VLAN is supported: open only TCP 443
from user/endpoint VLANs to NGINX, and the internal flows above between the zones.
