# Architecture

```
 Technician browser ──TCP 443──► NGINX ─┬─ remote.<domain>      ─► frontend (static React)  /  web (Django API, gunicorn)
 Remote user browser ─TCP 443──►        │                                                        │   ▲
                                        │                                                        ▼   │ worker (session_worker)
 Technician console iframe ─TCP 443──►  └─ mesh.remote.<domain> ─► MeshCentral (HTTP 4430, TLS offload)
 Endpoint agents ──────────TCP 443──►       (agent.ashx, meshrelay.ashx, meshagents)      ▲
                                                                                         │ control.ashx (wss, via NGINX)
 PostgreSQL ◄── web/worker ──► Redis                      web/worker ──────────────────────┘
```

All components run on one Docker host (or split by zone; see NETWORK-PORTS.md). Agents and browsers
only ever connect *to* the server on TCP 443; nothing connects to endpoints. All remote traffic is
relayed by MeshCentral over that connection (WebRTC is disabled).

## Trust model

| Secret | Held by | Purpose |
|---|---|---|
| `mesh_login_key` (80 random bytes) | portal backend + MeshCentral (Docker secret) | MeshCentral `LoginCookieEncryptionKey`. The portal mints short-lived AES-GCM cookies with it to (a) open the control websocket as the service account and (b) sign a technician into the console for 1 minute. **Equivalent to MeshCentral administrator access.** |
| Django secret, DB password | portal | sessions, CSRF, LDAP bind password encryption |
| TLS certificate (internal CA) | NGINX | both host names; MeshCentral pins its hash for agents (`certUrl`) |

* MeshCentral service account `bsf-portal-svc`: created at first start with a random, discarded password.
* Per technician: MeshCentral account `bsftech-<id>` with site rights *no new groups / no MeshCmd /
  no new devices* and **no device rights**. Rights on one device are added per session:
  remote control + chat always; `NOTERMINAL` / `NOFILES` unless permitted; reset/power only if
  permitted; registry, software inventory and Intel AMT always denied.
* New-account registration in MeshCentral is disabled; technicians never see a MeshCentral password.

## Attended session lifecycle

1. `POST /api/sessions/attended/` — creates MeshCentral group `BSF-ATT-<code>` with consent flags
   *notify + prompt for desktop/terminal/files + connection bar* (`MESH_CONSENT_ATTENDED=127`);
   session `WAITING`, expiry `ATTENDED_CODE_TTL_MINUTES`.
2. Remote user: `POST /api/join/ {code}` → per-browser token (code then cannot be used by anyone else
   once consent is given; attempts are rate-limited per IP) → `POST /api/join/<token>/consent/` records
   name, IP, time → `GET /api/join/<token>/agent/<platform>/` streams the official agent from the internal
   MeshCentral with that group embedded and *InstallFlags=1* (connect only, nothing installed).
3. The worker (and status polls) see the agent online in the group, bind it to the session, remove
   any extra agents, record the device, grant the technician rights on that node → `READY`.
4. `POST /api/sessions/<id>/console/ {view}` → 1-minute login URL for MeshCentral's device view
   (`desktop`/`terminal`/`files`/`events`) embedded in the portal console → `ACTIVE`.
   The agent shows the on-screen Yes/No prompt for each channel.
5. End: technician, administrator, remote user (join page / closing the agent / connection bar), the
   session limit, or revocation. The portal removes the device rights, closes the desktop multiplexer
   and every agent tunnel owned by the technician, closes the technician's web sessions, imports the
   engine event trail (including the user's accept/reject decisions) and deletes the group.

## Unattended session lifecycle

1. Admin creates a portal group → MeshCentral group `BSF-<name>` (`MESH_CONSENT_UNATTENDED=71`:
   notify + connection bar). The group's installer is downloaded from the portal (InstallFlags=2,
   service install) and deployed by GPO.
2. The worker syncs agents from portal-owned groups into the device inventory every 30 s; new devices
   are `approved=False` unless the group is set to auto-approve.
3. `POST /api/sessions/unattended/ {device_id, stepup_grant}` checks, in order: account active and
   portal-enabled and role TECHNICIAN/ADMIN/SUPERADMIN; device approved and present; permission
   (admins: all devices; technicians: device or active group grant); MFA step-up grant (single use, 5
   minutes, TOTP code replay-protected); device online. Then rights on that node only → `READY`.
4. While open, the worker re-checks every few seconds: account still enabled, device still approved,
   permission still present, deadline not passed. Any failure ends the session and revokes access.
5. Reboot: `poweraction` reset; the console shows *Device offline* and reconnects automatically when
   the agent returns (session stays open until its deadline).

## Components

* `backend/remote_bridge/meshapi.py` — MeshCentral control-channel client (cookie minting, groups,
  users, device rights, power, events, agent console, login/messenger URLs).
* `backend/remote_sessions/services.py` — session state machine, authorization, revocation, agent packages.
* `backend/remote_sessions/management/commands/session_worker.py` — reconciler (bind, expire, enforce,
  retry failed revocations, sweep orphaned attended groups, sync devices).
* `backend/devices/services.py` — MeshCentral → portal device inventory sync.
* `meshcentral/render-config.js` — the only source of MeshCentral configuration (rendered at start).
