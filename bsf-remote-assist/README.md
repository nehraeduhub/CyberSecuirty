# BSF Remote Assist — Final Deployment

## Authentication model

**Local authentication is the default. Active Directory is optional.** The first administrator is created from `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` during deployment. There is no public self-registration. Administrators create local remote-support users from the portal and assign roles.

After first login, a SUPERADMIN/ADMIN can configure **Active Directory / LDAPS** from **Settings → Active Directory / LDAPS**. AD accounts still require a portal user record and administrator approval; AD authentication does not auto-create portal accounts.

Recommended first deployment sequence:
1. Copy `.env.example` to `.env`.
2. Set strong PostgreSQL, Django and bootstrap-admin passwords.
3. Keep AD disabled/blank initially.
4. Run `./deploy/preflight.sh`.
5. Run `./deploy/install.sh`.
6. Log in with the bootstrap local administrator.
7. Create a local technician/remote user.
8. Configure devices/MeshCentral and test one Windows PC.
9. Optionally configure LDAPS from the GUI, provision AD users, approve them, and test AD login.
10. Only after pilot validation deploy the endpoint agent through the pilot GPO.

## Security

Do not expose PostgreSQL or Redis to the user network. Do not expose Windows RDP/SMB for remote support. Keep MeshCentral and portal HTTPS-only through the reverse proxy. Store production secrets outside source control.

The bootstrap admin password is not reset on every container restart. Set `BOOTSTRAP_ADMIN_RESET=true` only for an intentional recovery/reset operation, then return it to `false`.

The package is a deployment candidate and must be validated against the actual server, TLS certificate, DNS, firewall and MeshCentral version before production rollout.
# BSF Remote Assist — FINAL DEPLOYMENT PACKAGE

Self-hosted remote-support portal for an AD-controlled environment. The portal provides administrator-controlled accounts, RBAC, device approval, MFA/step-up authorization, audit records and a MeshCentral remote-management engine.

## Important status
This is the consolidated deployment package, not a guarantee of production readiness without site validation. Do not deploy directly to the full endpoint population. First complete the pilot checklist in `deploy/FINAL-DEPLOYMENT-SOP.md` on 5–10 domain PCs.

The package deliberately does NOT contain:
- your AD password or service-account secret
- TLS private keys
- MeshCentral login-token signing secret
- production database data
- a fabricated MeshCentral agent binary

Those must be generated/provisioned in your data centre.

## Architecture
- `remote.inet.gov.in` — BSF Remote React portal + Django API
- `mesh.remote.inet.gov.in` — MeshCentral remote engine
- PostgreSQL — portal database
- Redis — application cache/session infrastructure
- NGINX — TLS reverse proxy
- AD/LDAPS — authentication source; portal accounts remain administrator-controlled
- Windows endpoints — official MeshCentral agent + BSF endpoint heartbeat/enrollment where required

MeshCentral supports Docker deployments, reverse-proxy configuration and login-token/framing features. Pin the exact tested release rather than using a floating `latest` image. Official Docker documentation lists versioned image tags. See the deployment references in `docs/REFERENCES.md`.

## Deployment order
1. Prepare Ubuntu LTS server/VM and Docker Engine + Compose.
2. Create DNS A/AAAA records for `remote.inet.gov.in` and `mesh.remote.inet.gov.in`.
3. Place the approved wildcard/SAN TLS certificate and private key under `deploy/certs/`.
4. Copy `.env.example` to `.env` and replace every placeholder.
5. Verify LDAPS from the server to the domain controller.
6. Run `./deploy/preflight.sh`.
7. Run `./deploy/install.sh`.
8. Complete initial MeshCentral administrator setup using the controlled bootstrap procedure.
9. Configure the BSF Remote administrator account and provision only approved AD users.
10. Create/approve the first device group and enroll 5–10 pilot endpoints.
11. Test attended/unattended connection, MFA, terminal, reboot, file transfer policy, audit and disconnect.
12. Only after acceptance, deploy the Windows agent through a pilot GPO OU.
13. Expand GPO deployment in controlled batches.

## TLS
Use a certificate trusted by all managed endpoints. The certificate SANs must cover at least:
- `remote.inet.gov.in`
- `mesh.remote.inet.gov.in`

Do not commit private keys to Git or copy them into the Docker images.

## Sophos / firewall principle
Keep the service inside the data-centre/DMZ design approved by your security team. Do not expose RDP 3389 or SMB 445 to the Internet. Permit only the portal/remote service traffic required by the approved architecture and the AD/LDAPS, PostgreSQL and management dependencies on their respective internal networks.

See:
- `deploy/DATA-CENTRE-PORTS.md`
- `deploy/SECURITY-PORTS.md`

## Backup
Run:
```bash
./deploy/backup-postgres.sh
```

Test restoration before production rollout:
```bash
./deploy/restore-postgres.sh <backup-file>
```

Also back up the persistent MeshCentral data/files/backups volumes according to your DC/DR policy.

## Upgrade rule
Never run `docker compose pull` followed by an uncontrolled production restart for MeshCentral. Review the exact release, security advisories, compatibility, backup and rollback plan first. Update `MESHCENTRAL_IMAGE` to the tested version, validate in pilot, then roll forward.

## Validation
```bash
python3 -m compileall backend
./deploy/preflight.sh
./deploy/healthcheck.sh
```

For application tests, activate the deployment environment and run Django checks/migrations as described in `deploy/FINAL-DEPLOYMENT-SOP.md`.
