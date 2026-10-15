# Status, unsupported features and open items

## Not yet verified (must be closed before go-live)

| Item | Why open | How to close |
|---|---|---|
| Two-Windows-PC acceptance, including the Internet-disconnected run | No Windows machines in the build environment | docs/ACCEPTANCE-TEST.md §2 |
| Windows connect-only agent UX (Connect button, SmartScreen/UAC prompts for an agent signed by the server's own code-signing certificate) | Windows only | §2 B.2 — consider signing with the organisation's code-signing certificate |
| Windows consent prompt, connection bar *Disconnect*, Ctrl-Alt-Del, UAC secure desktop | Windows only | §2 A.4, B.3, B.5 |
| Multi-monitor selection | MeshCentral provides a display selector for Windows agents; test PCs here had one display | §2 A.4 |
| Real reboot and reconnect | On the shared test host the reboot was intercepted (delivery verified, restart simulated) | §2 A.6 |
| GPO install script and service name `BSFRemoteAgent` | Written for Windows, not executed | §2 A.1 |
| AD/LDAPS login | No directory available | Pilot with a test OU |
| Console idle timeout, session maximum duration | Implemented (MeshCentral `userSessionIdleTimeout`; worker deadline) but not exercised by the automated run (long timers) | §2 A.9 |

Docker deployment: **verified** — `setup.sh install` on a clean copy of the bundle, followed by the full
acceptance test against the containers (44/44, `docs/evidence/docker-install-run/`). `setup.sh build-images`
could not be run end to end in the build environment (its Internet access goes through a TLS-inspecting proxy);
the same Dockerfiles were built with a proxy-CA wrapper.

## Limitations (by design or of the engine)

* **Clipboard policy is global**, not per technician or per session: MeshCentral only offers
  domain-wide `clipboardGet`/`clipboardSet`.
* **The on-demand agent is not closed remotely.** When an attended session ends, all access ends
  immediately (rights removed, tunnels closed, group deleted), but MeshCentral refuses to terminate a
  connect-only agent process from the server, so its window stays open (idle, no access) until the user
  closes it. The join page tells the user to close it. If it reconnects, the worker removes the
  re-created group again.
* **Rebooting during an attended session ends it**: the on-demand agent does not survive a reboot
  (the console warns before reboot). Reboot-and-reconnect applies to unattended (installed) agents.
* **Attended agents**: Windows x64/x86/ARM64 and Linux x64 are offered. macOS is not.
* **Session recording** is MeshCentral's (`.mcrec` files, per group). Playback is in MeshCentral's
  player, not in the portal UI.
* **Console UI** is MeshCentral's device view embedded in the portal (header, footer and navigation
  hidden). Technicians can only see the one device they are authorized for, for the session.
* **MFA** is TOTP (authenticator app). No hardware keys/smart cards.
* **The MeshCentral login key** (`deploy/secrets/mesh_login_key`) is equivalent to engine
  administrator access. Protect it like a domain-admin credential; rotate by replacing the file and
  restarting `meshcentral`, `web` and `worker`.
* **Agent download URLs**: MeshCentral serves a group's agent to anyone who knows the group's random
  identifier. For managed groups this cannot grant access (new devices need approval); attended groups
  exist only for the duration of one session.
* **Database migrations were regenerated.** The migrations in the uploaded package could not apply to
  an empty database (missing parent migration, `security/migrations` was not a package), so this is a
  fresh-install schema. There is no upgrade path from a database created by the old package.

## Changes from the uploaded package (summary)

* Remote engine integration rewritten: direct MeshCentral control-channel client with portal-minted
  cookies instead of `meshctrl.js` subprocesses and `meshcentral --logintoken` CLI calls (the portal
  image had no Node.js or MeshCentral install for those to run).
* Real attended workflow (per-session group, join page, consent, agent download, binding) and real
  unattended authorization with per-session, per-device rights and revocation.
* New session worker; device inventory synced from MeshCentral (legacy Python heartbeat agent removed).
* Offline MeshCentral image and config (no runtime module install, no Internet timestamp server, AMT
  MPS port disabled, WebRTC off, framing restricted to the portal).
* Fixed: NGINX proxied HTTPS to a TLS-offloaded MeshCentral; CSRF header missing from the frontend;
  frontend called non-existent endpoints; unpinned `latest` npm dependencies; MeshCentral version
  1.2.6, which is not published on npm (1.2.5, the latest published, is pinned).
