# Stage 6 — MFA + MeshCentral secure handoff

## Security
- Portal remains authoritative for user/device/action authorization.
- AD authentication does not create portal accounts.
- Unattended technician sessions require a fresh TOTP step-up grant valid for 5 minutes and consumed once.
- MFA secrets are stored server-side; production deployment should encrypt database/storage and restrict DB access.

## MeshCentral integration
MeshCentral supports short-lived login tokens for embedding/integration. Configure `allowLoginToken` and `allowFraming` only when the portal and MeshCentral are deployed under controlled origins. The portal supports `MESH_NODE_URL_TEMPLATE`, e.g. `https://remote-gateway.example.local/?viewmode=11&hide=15&node={node_id}`.

For a seamless authenticated handoff, configure MeshCentral login-token/SSO integration according to the deployed MeshCentral version. Do not put a MeshCentral administrator password in browser code or URLs.

## Important version/security requirement
Use a current supported MeshCentral release. MeshCentral had a high-severity cross-site WebSocket hijacking issue in versions before 1.1.21; the project advisory recommends patched versions and origin validation. See the official advisory before production deployment.

## Environment variables
- `PORTAL_MFA_ISSUER=BSF Remote`
- `MESH_BASE_URL=https://remote-gateway.example.local`
- `MESH_NODE_URL_TEMPLATE=https://remote-gateway.example.local/?viewmode=11&hide=15&node={node_id}`
- `MESHCTRL_PATH` is reserved for a future server-side MeshCtrl adapter; do not expose it to clients.

## Test cases
1. AD user without portal account -> denied.
2. Portal user pending approval -> denied.
3. Approved technician without MFA -> unattended connect denied.
4. Approved technician with wrong TOTP -> denied.
5. Correct TOTP -> one-time grant accepted.
6. Reusing the same grant -> denied.
7. Technician without device permission -> denied.
8. Technician with device permission -> session created/started.
9. Admin -> can bypass technician step-up only according to policy.
10. Auditor -> cannot create remote sessions.
