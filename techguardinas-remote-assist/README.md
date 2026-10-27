# TechGuardinas Remote — self-hosted remote support (MeshCentral engine)

TechGuardinas Remote is an on-premises remote-support portal with a Zoho Assist–like workflow, built on the
open-source **MeshCentral 1.2.5** remote-control engine. The portal does identity, authorization,
consent, session lifecycle and audit; MeshCentral does the remote desktop, terminal, file transfer,
chat, power actions and relaying. Everything runs inside the MPLS network: no cloud relay, no
external authentication, no CDN, no Internet access at run time.

No Zoho code, branding or service is used.

## What it does

**Attended support** — technician clicks *Start Remote Support* → a one-time 9-digit code and an
internal link (`https://<portal>/join/<code>`, valid 10 min by default) → the user opens it, sees who is
asking and for what, approves, downloads the on-demand agent *from the internal portal*, runs it and
clicks **Connect** → the technician sees the computer and opens the console → the user gets an
on-screen **Yes/No** prompt for the desktop, and again for terminal and files → either side can end it
at any time (portal button, user's join page, closing the agent, or the connection bar on the PC).

**Unattended access** — administrators create device groups; each has an official agent installer
served by the internal portal (GPO deployable). New endpoints register as **pending** and cannot be
reached until an administrator approves them *and* grants a technician permission for the group or
device. Connecting checks account status, role, device approval and permission, and a **TOTP step-up**
(MFA) by policy. Only then does the server grant the technician's engine account rights on that
one device, for that one session.

**Remote console** — browser console embedded in the portal: remote desktop with keyboard/mouse
(MeshCentral's multi-display selector, Ctrl-Alt-Del, clipboard), terminal and file transfer (only if
permitted), chat, reboot with automatic reconnect, device events, session timer, end session.

**Records** — every session stores technician, target device (name/OS/IP), how it was authorized
(remote-user consent or permission + MFA), the remote user's on-screen decisions, enabled
capabilities, created/opened/ended times, who ended it and why, and the technician's outcome note;
plus a full audit log and the engine's own event trail. Optional session recording per group.

## How access is enforced

Technicians never hold standing rights in MeshCentral. Each portal user has a least-privilege
MeshCentral account with **no device rights**; the portal adds rights on exactly one device when a
session is authorized and, when it ends (or is revoked, expires, or the account/device is disabled),
removes the rights, closes the live desktop/terminal/file tunnels on the agent and closes the
technician's console. The portal signs the console in with a one-minute token; no MeshCentral
password exists for technicians or for the portal's service account.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

* The complete attended and unattended workflows were run end to end with **two real MeshCentral
  agents on Linux test endpoints**, through the real browser UI, inside a network namespace with **no
  route to the Internet**: 44/44 acceptance checks passed. The same test also passed 44/44 against the
  Docker deployment created by `setup.sh install`. Evidence: [docs/evidence/](docs/evidence/).
* **Not yet done: the two-Windows-PC acceptance.** No Windows machines were available in the build
  environment. The procedure and checklist are in [docs/ACCEPTANCE-TEST.md](docs/ACCEPTANCE-TEST.md).
  Do not treat the system as accepted until that has passed.
* Known limitations and untested items: [docs/STATUS-AND-LIMITATIONS.md](docs/STATUS-AND-LIMITATIONS.md).

## Deploy

**Start here: [USER-GUIDE.md](USER-GUIDE.md)** — `./setup.sh build-images` on a connected machine, then
`sudo ./setup.sh install` on the Linux server; publishing on the MPLS (DNS, certificate, firewall) is in §4.

Reference documents:

1. [deploy/OFFLINE-IMAGES.md](deploy/OFFLINE-IMAGES.md) — build the images on a connected build host and load them on the server.
2. [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md) — DNS, internal certificate, secrets, `.env`, start, first login.
3. [deploy/NETWORK-PORTS.md](deploy/NETWORK-PORTS.md) — firewall rules (browser, agent and relay traffic).
4. [deployment/gpo/README.md](deployment/gpo/README.md) — Windows agent rollout.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Django API: accounts/MFA, devices, permissions, sessions, audit, MeshCentral client (`remote_bridge/meshapi.py`), session worker |
| `frontend/` | React portal: technician, administrator and remote-user (`/join`) pages, remote console |
| `meshcentral/` | Pinned offline MeshCentral image, config renderer, service-account bootstrap |
| `deploy/` | NGINX template, scripts (secrets, preflight, install, health, backup) and deployment docs |
| `deployment/gpo/` | Windows agent GPO scripts |
| `tests/e2e/`, `tests/local-stack/` | Acceptance test and the isolated local stack used to run it |
