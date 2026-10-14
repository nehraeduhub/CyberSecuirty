# Stage 10 — Production Hardening & End-to-End Test Plan

Stage 10 is the production-readiness layer for BSF Remote Assist. It does not claim that a deployment is production-ready until the checks below pass in the actual data-centre environment.

## 1. Security baseline

- Run the latest supported MeshCentral release approved by the organisation. Do not deploy versions affected by published security advisories.
- Pin application/container versions; do not use `latest` in production.
- Keep MeshCentral login-token key only on the server side. Never place it in React, browser JavaScript, URLs generated for logs, or source control.
- Enable `AllowLoginToken` and `AllowFraming` only if the portal integration is required. Restrict framing to the BSF Remote origin at the reverse-proxy/security layer.
- Use HTTPS end-to-end or TLS offload only on a trusted reverse proxy segment.
- Use strict session cookie policy where compatible with the chosen embedding flow.
- Disable MeshCentral self-registration (`newAccounts=false`) for the controlled portal deployment.
- Use separate admin, technician and service identities. Never use a shared administrator account for normal support work.
- Enable MFA for privileged portal users and retain step-up MFA for unattended access.
- Store Django `SECRET_KEY`, database credentials, MeshCentral login-token key and service credentials in a secret store or protected environment file with least-privilege filesystem permissions.

## 2. Network zones

Recommended flow:

Internet/BSF WAN (if required) -> Sophos XGS -> DMZ reverse proxy -> BSF Remote/MeshCentral services -> management VLAN -> domain endpoints.

Do not expose RDP 3389 or SMB 445 to the Internet. Endpoints should make outbound agent connections to the approved MeshCentral endpoint. Restrict administrative interfaces to the management network.

## 3. Reverse proxy

NGINX must:
- terminate TLS using an approved certificate;
- redirect HTTP to HTTPS;
- support long-lived WebSocket connections;
- preserve `Host` and `X-Forwarded-*` headers;
- apply request-size and rate limits appropriate to the portal;
- send security headers without breaking the approved MeshCentral iframe/session flow.

Test the WebSocket path before production approval.

## 4. AD/LDAPS

- Use LDAPS with certificate validation.
- Use a dedicated read-only directory bind account.
- Do not store a domain administrator credential in the portal.
- Portal account creation remains administrator-controlled; AD authentication alone must not create a portal account.
- Test disabled AD accounts, expired passwords, locked accounts and removed portal accounts.

## 5. Database and backups

PostgreSQL must be backed up daily at minimum, with encrypted off-host copies. Test restoration, not just backup creation.

Minimum recovery tests:
1. Restore PostgreSQL to an isolated server.
2. Restore application configuration/secrets from the approved secret backup procedure.
3. Restore MeshCentral data according to the selected MeshCentral database/storage configuration.
4. Verify devices, portal users, permissions and audit records.
5. Perform a test connection to a non-production endpoint.

## 6. Monitoring

Monitor:
- portal HTTP errors and authentication failures;
- MFA failures;
- device heartbeat/offline transitions;
- MeshCentral service health;
- WebSocket disconnects;
- PostgreSQL availability and storage;
- Redis availability;
- TLS certificate expiry;
- CPU/RAM/disk;
- failed privileged actions;
- repeated failed connection attempts.

Forward security/audit events to the organisation's approved SIEM where possible.

## 7. Mandatory acceptance tests

### Identity
- [ ] AD user with no portal account is denied.
- [ ] Admin-approved user can sign in.
- [ ] Disabled portal user is denied.
- [ ] Disabled/locked AD user is denied.
- [ ] Technician cannot administer portal users.
- [ ] Auditor cannot initiate a remote session.

### Device authorization
- [ ] Technician sees only assigned devices/groups.
- [ ] Direct API call against an unauthorized device is denied.
- [ ] Reboot/terminal/file operations enforce the same permission checks as the UI.
- [ ] Unattended access requires the configured step-up MFA grant.
- [ ] A step-up grant cannot be reused.

### MeshCentral
- [ ] Approved device is online in MeshCentral.
- [ ] Portal device maps to the correct MeshCentral node.
- [ ] Portal Connect launches only the authorized node.
- [ ] Token is short-lived and is never stored in application logs.
- [ ] MeshCentral login-token key is absent from browser/network response bodies.
- [ ] WebSocket connection succeeds through NGINX/Sophos.
- [ ] Remote desktop works on a pilot endpoint.
- [ ] Terminal works only when permitted.
- [ ] File transfer works only when permitted.
- [ ] Reboot works only when permitted.
- [ ] Disconnect closes the portal session record.

### Endpoint/GPO
- [ ] Agent deployment works on a pilot OU.
- [ ] Endpoint enrolls only with a valid bootstrap token.
- [ ] Bootstrap token cannot be reused after enrollment.
- [ ] Heartbeat changes device status to online.
- [ ] Offline timeout marks stale devices offline.
- [ ] GPO deployment can be rolled back.

### Recovery
- [ ] Portal database restore tested.
- [ ] MeshCentral data restore tested.
- [ ] NGINX/TLS configuration restore tested.
- [ ] Complete service restart tested.
- [ ] DNS failure procedure documented.
- [ ] Sophos rule rollback documented.

## 8. Security advisories

Before every production upgrade, check the MeshCentral security advisory page and the exact release notes. In particular, do not deploy versions affected by known high-severity issues. CVE-2024-26135 affected MeshCentral versions before 1.1.21; later advisories must also be checked before each upgrade.

## 9. Go-live gate

Do not mark BSF Remote Assist production-ready until:
- all mandatory acceptance tests pass;
- backup restoration has been demonstrated;
- TLS/DNS/Sophos rules are approved;
- MeshCentral version is approved;
- the Windows endpoint pilot is successful;
- security testing/VAPT has no unresolved critical/high findings;
- rollback and DR procedures have been exercised.
