# Stage 9 — Seamless MeshCentral Session Handoff

## Purpose

Stage 9 adds the controlled portal-to-MeshCentral handoff. The portal remains the authorization point; MeshCentral remains the remote-control engine.

## Security model

1. AD authenticates the technician.
2. Portal account must be administrator-provisioned and enabled.
3. Device must be approved.
4. Device permission is checked in Django.
5. Unattended technician access requires step-up MFA.
6. Django provisions/uses a least-privilege MeshCentral user scoped to the device's MeshCentral device group.
7. Django requests a short-lived MeshCentral login token on the MeshCentral host.
8. The browser receives only the resulting launch URL; MeshCentral service credentials and login-token key never enter the browser.
9. Session start and SSO failures are audited.

MeshCentral documents `allowLoginToken` + `allowFraming` for short-lived login-token handoff and embedding. Its documentation also warns that the login-token key is a sensitive secret capable of creating impersonation tokens, so it must remain server-side. See the official documentation: https://docs.meshcentral.com/meshcentral/ and https://docs.meshcentral.com/meshcentral/tokens/.

## Required MeshCentral configuration

In the MeshCentral `settings` section:

```json
{
  "allowLoginToken": true,
  "allowFraming": true
}
```

The Stage 9 template contains these settings. Validate the exact spelling/casing accepted by the deployed MeshCentral release before production rollout.

## Required environment variables

```text
MESH_SSO_ENABLED=true
MESH_SERVER_ENTRY=/opt/meshcentral/node_modules/meshcentral/meshcentral.js
MESH_NODE_BIN=node
MESH_SSO_DOMAIN=
```

`MESH_SERVER_ENTRY` must point to the MeshCentral installation on the server where login-token generation is executed.

## Device mapping

Every approved BSF Remote device intended for seamless access must have:

- `mesh_node_id`
- `mesh_group_id`

The MeshCentral device group must contain only the endpoints intended for that authorization boundary.

## Important deployment rule

Do not expose the MeshCentral login-token key, MeshCentral administrator password, or MeshCentral service credentials to React/browser code, URL parameters, logs, or frontend environment variables.

## Pilot test

1. Create one MeshCentral device group for the pilot OU.
2. Register one test Windows endpoint.
3. Approve the endpoint in BSF Remote.
4. Assign the technician only to that device group.
5. Enable Stage 9 SSO in a non-production environment.
6. Connect from the portal.
7. Confirm the MeshCentral login screen is skipped and the correct device opens.
8. Confirm a technician cannot launch an unauthorized device by changing the node ID in the browser.
9. Confirm unattended access without valid step-up MFA is rejected.
10. Confirm the MeshCentral login-token secret never appears in Django/frontend logs.
11. Revoke the technician's portal/device permission and confirm subsequent connections fail.

## Current limitation

This stage is a controlled integration scaffold. It has not been tested against the user's live MeshCentral installation. The exact MeshCentral release must be installed and the `meshctrl`/login-token commands validated in the user's data centre before calling this production-ready.
