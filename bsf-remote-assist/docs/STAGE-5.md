# Stage 5 — Technician Remote Support

## Scope
Stage 5 adds the technician workflow and backend enforcement for device-scoped and action-scoped permissions.

### Implemented
- Authorized-device filtering for technicians.
- Session creation/start/end lifecycle.
- Per-action permissions: connect, file transfer, terminal, reboot.
- Session action audit records.
- Technician dashboard with Connect and session controls.
- Attended/unattended session model.
- MeshCentral launch URL handoff foundation.
- Admin-only portal user approval remains enforced.

### Security rule
The UI is not trusted. Every privileged operation is checked server-side against the authenticated portal user, device approval status, and TechnicianDevicePermission.

### Stage 5 limitation
The action endpoint authorizes and audits actions but does not yet execute privileged operations directly against MeshCentral. Stage 6 will implement the authenticated MeshCentral integration and step-up MFA.
