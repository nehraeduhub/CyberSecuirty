# MeshCentral Agent Integration — Stage 7

Use the administrator's own MeshCentral server to generate/download the official agent for the target device group. The exact command/URL is intentionally not hard-coded because it depends on the deployed MeshCentral version, domain, device group and server configuration.

Recommended flow:

1. Create a dedicated MeshCentral device group for BSF Remote managed endpoints.
2. Generate the official agent from that group in MeshCentral.
3. Verify the downloaded executable's Authenticode signature and SHA-256 hash.
4. Store the approved installer on an internal HTTPS distribution point or SYSVOL/DFS share with suitable access control.
5. Deploy to the pilot OU.
6. Confirm the resulting MeshCentral node ID.
7. Populate `Device.mesh_node_id` and `Device.mesh_group_id` in BSF Remote.
8. Only expose MeshCentral's required HTTPS/WebSocket path; do not expose RDP/SMB to technicians.

The portal's `mesh_node_id` field is the correlation point between the business authorization layer and the remote-control engine.
