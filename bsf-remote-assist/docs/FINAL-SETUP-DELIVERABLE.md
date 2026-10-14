# Final hosting handover checklist

This file is intentionally a checklist; production values must be supplied by the data-centre administrator.

1. DNS: create `remote.<internal-domain>` and, if external access is required, publish only the approved gateway FQDN.
2. Sophos: permit HTTPS 443 to the reverse proxy; do not publish 3389/445. Permit endpoint-to-gateway outbound HTTPS/WSS.
3. TLS: install the organization's trusted certificate chain under `deploy/certs/`.
4. AD: create a read-only LDAP bind/service account; use LDAPS 636 and validate the DC CA certificate.
5. Portal: set `.env`; create the initial Django superuser; disable self-registration.
6. MeshCentral: set a stable FQDN; disable new accounts; persist meshcentral-data and files; keep its admin path restricted.
7. GPO: deploy the signed endpoint agent only to approved computer OUs/groups.
8. Test: login -> admin approval -> device enrollment -> technician permission -> attended session -> unattended session -> audit -> disable technician -> verify connection denied.
9. Backup: PostgreSQL, Django secrets, MeshCentral data and certificates; test restore.
10. HA/DR: add a second gateway/application node only after the single-node pilot is stable.

The final handover should include exact Sophos rules, DNS records, Docker commands, AD/GPO steps, certificates, backup commands, health checks, rollback and troubleshooting.
