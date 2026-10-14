# BSF Remote Assist — Final Data-Centre Deployment SOP

## 1. Authentication model

The platform starts with **local authentication**. AD/LDAPS is optional and can be configured after launch from **Settings -> Active Directory / LDAPS**.

- No public self-registration.
- Bootstrap `SUPERADMIN` is created from `.env`.
- Administrators create local remote-support users from the GUI.
- Local users authenticate with the portal username/password.
- AD users are never auto-created by a successful AD login.
- To use AD, an administrator configures LDAPS, creates/provisions the AD portal user, and approves it.
- Keep at least one protected local SUPERADMIN as the break-glass account even after AD is enabled.

## 2. Server prerequisites

Use an Ubuntu LTS server in the application/DMZ segment with:

- 4 vCPU minimum for pilot; 8 vCPU recommended for larger deployments.
- 16 GB RAM minimum; 32 GB recommended for production growth.
- SSD-backed storage sized for PostgreSQL, MeshCentral files and backups.
- Static IP and DNS.
- Docker Engine + Compose plugin.
- Approved TLS certificate for the portal and MeshCentral names.

Recommended names:

- `remote.<your-domain>` — portal
- `mesh.<your-domain>` — MeshCentral

## 3. Install

```bash
git/transfer the final package to the server
cd bsf-remote-assist-final
cp .env.example .env
```

Edit `.env` and set strong values for:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `BOOTSTRAP_ADMIN_USERNAME`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `MESH_HOSTNAME`
- MeshCentral secrets

Do not put real secrets into source control.

Install the approved certificate:

```text
deploy/certs/fullchain.pem
deploy/certs/privkey.pem
```

Then:

```bash
./deploy/preflight.sh
./deploy/install.sh
./deploy/healthcheck.sh
```

## 4. First login

Open the portal HTTPS URL and sign in with the bootstrap local administrator.

Immediately:

1. Change/rotate the bootstrap password through your operational password process.
2. Configure MFA.
3. Create one local TECHNICIAN account.
4. Create device groups.
5. Enroll one test Windows endpoint.
6. Approve the endpoint.
7. Test Connect, Terminal, Reboot and permitted actions.

Do not deploy the agent to the whole domain until the pilot succeeds.

## 5. Optional AD/LDAPS configuration

From the portal:

**Settings -> Active Directory / LDAPS**

Enter:

- LDAPS URI, e.g. `ldaps://dc01.example.local:636`
- least-privilege LDAP bind DN
- bind password
- user base DN
- optional group DN
- certificate verification enabled
- Enable AD authentication

The bind password is stored encrypted using authenticated encryption derived from the Django secret.

After enabling AD:

1. Create/provision the AD user in **Technicians**.
2. Set the appropriate role.
3. Approve the portal account.
4. Test the AD user's login.
5. Confirm the local SUPERADMIN break-glass account still works.

Do not use Domain Admin credentials as the LDAP bind account.

## 6. Network policy

Expose only HTTPS through the approved reverse proxy/firewall path.

Do not expose:

- PostgreSQL 5432 to user networks.
- Redis 6379 to user networks.
- Windows RDP 3389 for remote support.
- SMB 445 for remote support.

AD/LDAPS TCP 636 is required only if/when AD authentication is enabled.

## 7. Pilot rollout

```text
Server
  -> MeshCentral test
  -> 1 Windows PC
  -> 5–10 PC pilot OU
  -> security/operations acceptance
  -> controlled GPO batches
```

Keep the local break-glass administrator until the full deployment and AD fallback process have been tested.

## 8. Rollback

If authentication, agent deployment or remote-control behavior is unsafe:

1. Disable new portal users.
2. Disable the affected device group.
3. Stop GPO deployment.
4. Disable AD authentication from Settings if AD is involved.
5. Preserve audit logs.
6. Restore PostgreSQL if database corruption occurred.
7. Roll back the affected application/MeshCentral version using the approved backup.

## 9. Acceptance gate

Production is approved only after:

- Local admin login succeeds.
- Local technician login succeeds.
- MFA succeeds.
- Unauthorized device connection is denied.
- Authorized device connection succeeds.
- Terminal/file/reboot permissions are enforced server-side.
- MeshCentral agent connects.
- Session audit records are present.
- Backup and restore have been tested.
- TLS validation succeeds.
- AD/LDAPS, if enabled, succeeds for an approved AD user and fails for an unapproved AD user.
- Break-glass local admin remains usable.
