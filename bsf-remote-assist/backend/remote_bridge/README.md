# Stage 8 — MeshCentral execution bridge

Django remains the authorization/audit layer. MeshCentral remains the remote-control engine. Stage 8 adds a server-side `meshctrl` bridge for authorized terminal and reboot actions.

## Credentials
Prefer a MeshCentral login-key file for the backend service account. Do not put credentials in frontend code or URLs.

Environment:
- `MESHCTRL_PATH=/opt/meshcentral/node_modules/meshcentral/meshctrl.js`
- `MESHCTRL_URL=wss://remote-gateway.example.local`
- `MESH_LOGIN_KEY_FILE=/etc/bsf-remote/mesh-login-key.txt`
- alternatively `MESH_ADMIN_USER` + `MESH_ADMIN_PASSWORD`

The service account should have only the MeshCentral rights required for the managed device groups.

## Supported bridge actions
- `terminal`: PowerShell command executed by the MeshCentral agent as SYSTEM after Django RBAC validation.
- `reboot`: MeshCentral agent reset/reboot action after Django RBAC validation.
- `file_transfer`: intentionally remains in the interactive MeshCentral console in this stage; file paths and transfer destinations should be added only with explicit policy and audit requirements.

MeshCtrl supports ListDevices, DeviceInfo, RunCommand, DevicePower and other management operations. The exact CLI syntax is version-dependent, so validate with the installed MeshCentral release before production rollout. Official MeshCentral documentation identifies MeshCtrl as the command-line control interface. 
