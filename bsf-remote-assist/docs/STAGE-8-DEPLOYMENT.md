# BSF Remote — Stage 8 Deployment

## 1. Purpose
Connect the approved BSF Remote portal session to the self-hosted MeshCentral control plane while preserving portal RBAC and audit as the first authorization gate.

## 2. Required MeshCentral configuration
- Use a currently supported MeshCentral release and review its release/security advisories before deployment.
- Keep `newAccounts` disabled for the portal domain if MeshCentral accounts are not independently administered.
- Use HTTPS/WSS with the internal DNS name and a valid certificate.
- Restrict MeshCentral administration to the management network.
- Do not expose RDP/3389 or SMB/445 for technician remote support.
- If using login-token/embedding features, enable them only after testing the exact installed version and protect the login-token key as a high-value secret.

## 3. Backend bridge
Install Node.js/MeshCentral where `meshctrl.js` is available, or copy the supported `meshctrl.js` entry point to a controlled backend tools directory.

Set:
```
MESHCTRL_PATH=/opt/meshcentral/node_modules/meshcentral/meshctrl.js
MESHCTRL_URL=wss://remote-gateway.example.local
MESH_LOGIN_KEY_FILE=/etc/bsf-remote/mesh-login-key.txt
```

Use a dedicated MeshCentral service identity/login key with minimum required rights. Keep the key outside the application source tree and restrict it to the Django service account.

## 4. Device correlation
For each approved endpoint:
1. MeshCentral agent appears in the managed device group.
2. Record its node ID in `Device.mesh_node_id`.
3. Record its device-group ID in `Device.mesh_group_id`.
4. Confirm the Django device is `approved=True`.
5. Confirm technician/group permission in Django.

## 5. Remote action flow
1. Technician signs into BSF Remote using approved AD identity.
2. Django checks device authorization.
3. Unattended connection requires step-up MFA for non-admin technicians.
4. Django creates/activates the session and records the operator/device.
5. Interactive remote control opens the MeshCentral node console.
6. Terminal/reboot requests go through Django `/api/sessions/<id>/execute/`.
7. Django checks RBAC again.
8. Django invokes MeshCtrl server-side.
9. AuditLog records the action and node ID.

## 6. Pilot testing
Use one test workstation before OU-wide deployment:
- remote desktop works
- terminal command is dispatched only to the selected node
- reboot requires `can_reboot`
- unauthorized technician gets HTTP 403
- expired/used MFA step-up is rejected
- disabled portal user cannot create a session
- unapproved device cannot be accessed
- MeshCentral service credential is never returned to the browser

## 7. Production caution
The bridge should not be considered production-ready until the exact MeshCentral version installed in the data centre has been tested with the configured `meshctrl.js` syntax and rights model. Keep a rollback copy of Stage 7 and the database before enabling Stage 8 actions.
