# BSF Remote — Data Centre Ports

Recommended exposure:
- TCP 443: NGINX public/DMZ entry point.
- TCP 80: optional HTTP->HTTPS redirect only.
- Django -> PostgreSQL TCP 5432: internal Docker network only.
- Django -> Redis TCP 6379: internal Docker network only.
- Django -> AD LDAPS TCP 636: internal only.
- Agents -> MeshCentral gateway: HTTPS/WSS over TCP 443.

Do not expose RDP 3389, SMB 445, WinRM 5985/5986, PostgreSQL 5432, Redis 6379, or MeshCentral internal ports directly to the Internet.
