# BSF Remote — Stage 7: Windows Endpoint Deployment

## Objective

Stage 7 establishes a controlled domain-PC deployment path and separates portal device authorization from the actual remote-control engine.

### Delivered

- One-time enrollment credential model: administrator creates a device record and receives a bootstrap token; the first valid heartbeat converts it into the device credential and clears the bootstrap hash.
- Device heartbeat with hostname, IP, OS and agent version.
- Windows deployment PowerShell scripts.
- GPO deployment procedure and pilot guidance.
- MeshCentral agent deployment integration point.
- MeshCentral device-group/node correlation fields.
- MSI/WiX source skeleton for controlled Windows build/sign pipeline.
- Explicit prohibition against shared enrollment tokens in a domain-wide GPO.

## Architecture

`AD Computer -> GPO -> BSF Remote management component -> Portal heartbeat`

and independently:

`AD Computer -> GPO/software deployment -> official MeshCentral Agent -> MeshCentral Server`

The portal decides **who may connect to which approved device**. MeshCentral performs the remote-control session.

## Deployment sequence

1. Build the Stage 7 backend and run migrations.
2. Configure HTTPS and DNS for the portal.
3. Configure MeshCentral with the supported current release and its own TLS hostname.
4. Create the dedicated MeshCentral device group.
5. Generate the official agent from that group.
6. Verify signature/hash and place the installer on an internal distribution point.
7. Create 5–10 BSF Remote device enrollment records.
8. Deploy the management component and MeshCentral agent to the pilot OU.
9. Verify heartbeat and MeshCentral node identity.
10. Approve each device in BSF Remote.
11. Test technician RBAC + MFA + unattended connection.
12. Expand GPO scope gradually.

## Security controls

- No self-registration.
- Administrator approval remains mandatory.
- Enrollment token is bootstrap-only.
- Device credential is stored as a hash in the portal database.
- HTTPS is mandatory in production.
- Do not expose TCP 3389 or TCP 445 to technicians/internet.
- Do not put secrets in GPO scripts stored in SYSVOL.
- Sign PowerShell and compiled agent packages.
- Keep the MeshCentral server patched and restrict administration separately from technician access.

## Stage 7 limitation

This stage does **not** claim that a custom BSF Remote binary is a replacement for MeshCentral's remote-control agent. The actual remote desktop/terminal/file-transfer capability comes from the official MeshCentral agent. The final SSO/token handoff and action execution must be validated against the exact MeshCentral release deployed in the data centre.
