# Deployment (on-premises, offline)

Prerequisites: Linux server with Docker Engine + Compose plugin, images loaded (OFFLINE-IMAGES.md),
internal DNS and internal CA.

1. **DNS** — A records for `remote.<domain>` and `mesh.remote.<domain>` → the server (or the DMZ NGINX).
2. **Certificate** — from the internal CA, SANs for both names. Put `fullchain.pem`, `privkey.pem`
   and the CA certificate `ca.crt` in `deploy/certs/`. The CA certificate must carry
   `keyUsage: keyCertSign` (strict TLS clients reject CAs without it). Distribute the CA to all
   technician PCs and endpoints by GPO.
3. **Secrets** — `./deploy/generate-secrets.sh` creates `deploy/secrets/mesh_login_key` and prints
   random values. `cp .env.example .env` and fill in host names, URLs and the printed values.
4. **Check and start** — `./deploy/preflight.sh` then `./deploy/install.sh`, then `./deploy/healthcheck.sh`.
   On first start MeshCentral generates its keys and creates the `bsf-portal-svc` service account; the
   portal creates the bootstrap administrator from `.env`.
5. **First login** — `https://remote.<domain>` as the bootstrap administrator.
   * *Settings*: enroll MFA for the administrator.
   * *Users*: create technician accounts (local; optional AD/LDAPS under Settings).
   * *Groups & Agents*: create a device group; download its Windows installer.
6. **Pilot** — install the agent on pilot PCs (deployment/gpo/README.md), approve them under *Device
   Approval*, grant technicians under *Permissions*, have technicians enroll MFA, then run the
   acceptance procedure in docs/ACCEPTANCE-TEST.md on two Windows PCs, including the network-isolated run.
7. **Rollout** — extend the GPO to further OUs in batches.

## Operations

* Logs: `docker compose logs web worker meshcentral nginx`.
* Backups: `./deploy/backup-postgres.sh` (portal DB + MeshCentral data); test `restore-postgres.sh`.
* Session recordings (if enabled per group) are written as `.mcrec` files to the `meshrecordings` volume.
  Play them with MeshCentral's built-in player page (`https://mesh.remote.<domain>/player`, open a copied
  `.mcrec` file locally). Access to the volume should be limited to auditors/administrators.
* Emergency stop of all remote access: `docker compose stop meshcentral` (agents disconnect; no
  sessions possible) or disable the technician account (open sessions end within seconds).
* Break-glass: keep the local bootstrap SUPERADMIN; reset it with `BOOTSTRAP_ADMIN_RESET=true` once.

## Policy settings (.env)

| Setting | Default | Meaning |
|---|---|---|
| `ATTENDED_CODE_TTL_MINUTES` | 10 | Invitation validity |
| `SESSION_MAX_MINUTES` | 120 | Hard limit per session (both modes) |
| `MESH_IDLE_TIMEOUT_MINUTES` | 15 | Console signs out after inactivity |
| `UNATTENDED_REQUIRE_MFA` / `ATTENDED_REQUIRE_MFA` | true / false | TOTP step-up per connection |
| `ATTENDED_CAPABILITIES` | desktop,chat,files,terminal | Offered in attended sessions (user approves each on screen) |
| `MESH_CONSENT_ATTENDED` / `MESH_CONSENT_UNATTENDED` | 127 / 71 | MeshCentral consent flags |
| `MESH_CLIPBOARD_GET` / `MESH_CLIPBOARD_SET` | true / true | Clipboard remote→technician / technician→remote (global) |
| `MESH_SESSION_RECORDING` | false | Default for new groups; per group in *Groups & Agents* |
