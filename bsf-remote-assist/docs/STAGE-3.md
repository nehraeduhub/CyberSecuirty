# Stage 3 — Functional Control Plane

## Delivered
- AD/LDAPS authentication via django-auth-ldap.
- `AUTH_LDAP_NO_NEW_USERS=True`: AD accounts cannot auto-create portal accounts.
- Admin-only portal provisioning and approval.
- Portal roles: SUPERADMIN, ADMIN, TECHNICIAN, AUDITOR.
- Device enrollment token + heartbeat.
- Admin device approval.
- Device/group permission checks before remote session creation.
- Session start/end audit events.
- MeshCentral launch integration point.
- Browser login with CSRF-protected session login.

## Identity workflow
1. Create an AD account normally through AD administration.
2. BSF Remote administrator provisions the matching AD username.
3. Account remains PENDING.
4. Administrator approves the portal account.
5. User authenticates against AD/LDAPS.
6. Portal RBAC controls what devices/actions are allowed.

AD membership alone never grants portal access.

## Important production point
MeshCentral is the remote-control engine. Its own account creation is disabled. The BSF Remote portal is the authorization/control plane. Full single-sign-on into the MeshCentral UI is a separate integration step; the current Connect action launches the controlled MeshCentral endpoint.

## Final handover
The final package must include DNS, certificates, Sophos rules, Docker installation, AD/LDAPS values, break-glass admin creation, GPO/MSI agent deployment, device enrollment/approval, backup/restore, upgrade/rollback and verification procedures.
