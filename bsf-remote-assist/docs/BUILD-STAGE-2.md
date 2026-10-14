# BSF Remote — Build Stage 2

## Delivered in this stage
- Administrator-only portal provisioning model
- AD/LDAPS configuration placeholders
- Portal authorization remains separate from AD identity
- Device groups and technician-to-device/group permissions
- Admin approve/disable API endpoints
- Audit events for user provisioning/approval/disable
- MeshCentral remote-engine integration container
- Nginx WebSocket reverse-proxy route for remote traffic
- Production-oriented environment variables

## Security rule
AD credentials authenticate identity; `portal_enabled`, role and device/group permission decide authorization. No self-registration is supported.

## Deployment model
Internet/MPLS -> Sophos -> DMZ reverse proxy -> Django/React + MeshCentral -> endpoint agents.

Do not expose 3389/445 to the Internet. Agents should make outbound TLS/WebSocket connections to the gateway.

## Next stage
- Complete django-auth-ldap implementation with LDAPS certificate validation
- MeshCentral API adapter and device ID synchronization
- Agent enrollment token workflow
- Technician Connect flow with short-lived session authorization
- Step-up MFA for unattended access
- File transfer approval and terminal/reboot permissions
- Session recording/audit retention policy
- MSI + GPO deployment package
- Production HA/backup/DR
