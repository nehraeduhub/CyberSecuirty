# BSF Remote Assist — Security Ports

| Flow | Source | Destination | Port | Required |
|---|---|---|---:|---|
| Technician -> Portal | User VLAN | NGINX | TCP 443 | Yes |
| Portal/NGINX -> Django | Docker network | web | TCP 8000 | Internal |
| Portal -> PostgreSQL | Docker network | db | TCP 5432 | Internal |
| Portal -> Redis | Docker network | redis | TCP 6379 | Internal |
| NGINX -> MeshCentral | Docker network | meshcentral | TCP 443/HTTP upstream | Internal |
| Windows Agent -> MeshCentral | Endpoint network | MeshCentral | TCP 443 | Yes |
| Portal -> AD/LDAPS | App server | Domain Controller | TCP 636 | Optional |
| Portal -> DNS | App server | DNS | UDP/TCP 53 | As required |
| Portal -> NTP | App server | NTP | UDP 123 | As required |

Do not expose PostgreSQL, Redis or internal container ports to the user network. Do not open RDP/SMB solely for BSF Remote.
