# BSF Remote Assist — Stage 4

## Scope
Stage 4 introduces the endpoint lifecycle and connection handoff foundation.

### Implemented
- Device enrollment token is generated only by an administrator.
- Enrollment token is stored as a SHA-256 hash in the portal database.
- Agent heartbeat validates the token and records hostname/IP/OS/version/last-seen.
- Device must still be approved by an administrator before it appears as a usable managed device.
- Offline endpoint callback is supported.
- Device API exposes enrollment and approval state.
- Windows bootstrap PowerShell script writes protected enrollment configuration.
- Minimal Python heartbeat client is included as the agent protocol reference.
- Existing portal RBAC remains authoritative for starting remote sessions.

## Production agent
The Python client is a protocol reference, not a signed production remote-control binary. The production Windows agent should be packaged as a signed MSI/EXE and installed as a Windows service. The actual screen-control transport remains the self-hosted MeshCentral agent/engine.

## Enrollment workflow
1. Administrator creates a device enrollment from BSF Remote.
2. Portal returns a one-time enrollment token.
3. Administrator installs the agent using the token.
4. Agent sends heartbeat to `/api/devices/heartbeat/`.
5. Device appears as pending.
6. Administrator approves the device.
7. RBAC/group permissions determine which technicians can connect.

## Security requirements
- Do not expose agent tokens in tickets, email, screenshots, or source code.
- Use HTTPS only.
- Rotate/revoke enrollment credentials after deployment.
- Production agent configuration must be ACL-protected.
- 3389/445/5985/5986 must not be exposed to the Internet for this product.
- Keep MeshCentral behind the controlled gateway and disable self-service account creation.
