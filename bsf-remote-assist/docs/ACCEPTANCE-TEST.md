# Acceptance testing

## 1. Automated run on Linux test endpoints (done)

`tests/local-stack/run-offline.sh` starts every component (PostgreSQL, Redis, MeshCentral with the
production config renderer, NGINX with the production template, Django + worker, React build) **inside
a new network namespace that has only a loopback interface** — no default route, no DNS server, no
proxy — plus two X displays acting as the screens of two test PCs. `tests/e2e/run_e2e.py` then drives
the real UI with Chromium as administrator, technician and remote user, runs two real MeshCentral
agents (installed from packages downloaded from the portal), answers the agent's on-screen consent
prompts with `xdotool`, and checks engine-side state directly.

Latest run: **44 passed, 0 failed** — `docs/evidence/linux-offline-run/report.json` and screenshots.

| Area | Verified |
|---|---|
| Offline | test host had 0 routes, Internet unreachable; browsers requested nothing but the two internal names |
| Deployment | group → MeshCentral group; Windows installer from portal embeds `wss://<internal name>:443/agent.ashx`; managed agent registers and shows online |
| Authorization | pending device refused even for admin; unauthorized technician neither sees nor can connect; authorized technician without MFA refused; no technician engine account holds standing rights |
| Unattended | MFA step-up → console; device-scoped rights granted; live desktop; mouse + keyboard reach the PC; terminal command executed; file browser; chat window; reboot command reaches agent; offline overlay and automatic reconnect; end → rights removed, no live tunnels, console cannot reopen; revoking device approval mid-session ends it immediately |
| Attended | 9-digit code + internal link; remote user approves and downloads agent from portal; code cannot be reused; technician sees the PC after **Connect**; on-screen consent **Yes** → desktop; mouse + keyboard; terminal request **rejected** by the user is recorded; user ends from the join page → technician console closes; per-session group deleted; closing the agent ends the session; cancelled and unknown codes rejected |
| Records | session record (technician, device, consent, capabilities, start/end, ended by, outcome) and audit log contain the full lifecycle |

Test-harness-only shims (never used in production): agents run without `CAP_SYS_BOOT` so the reboot
command cannot reboot the shared test host (its delivery to the agent is verified, the restart is
simulated by restarting the agent); a `loginctl` stub and a `utmp` record give the headless X displays
a "logged-in user", which a real PC has.

## 2. Windows acceptance with two PCs (REQUIRED, not yet performed)

Use two domain-joined Windows 10/11 test PCs (PC-A attended user, PC-B unattended) in a pilot OU, the
CA certificate deployed, and the server deployed per DEPLOYMENT.md. Record screenshots and the session
records for each step. Two technician accounts: `tech1` (permitted) and `tech2` (not permitted).

### A. Unattended (PC-B)
1. Admin: create group `PILOT`, download `windows-x64`, deploy with the GPO script; reboot PC-B.
   Expect: service **BSFRemoteAgent** running; PC-B in *Device Approval* as PENDING, online.
2. tech1 tries *Connect* before approval → refused. Admin approves; grants tech1 *Connect, Files, Terminal, Reboot* on `PILOT`.
3. tech2: PC-B not listed; API call refused. tech1 without MFA → refused. tech1 enrolls MFA.
4. tech1 *Connect* + TOTP → console. Check: desktop; mouse/keyboard; **display selector with two
   monitors** (connect a second monitor or use a VM with two displays); Ctrl-Alt-Del; clipboard
   both ways (and blocked when `MESH_CLIPBOARD_*=false`); connection bar visible on PC-B.
5. Terminal (PowerShell/cmd) runs `hostname`; Files: upload and download a test file; Chat opens on both sides.
6. **Reboot** → console shows *Device offline* → PC-B restarts → console reconnects by itself; log in to Windows and continue.
7. End session with an outcome note. Check: console closed, a new console request is refused, session record complete.
8. Open another session; admin disables tech1 (or revokes PC-B approval) → session ends within seconds.
9. Idle 15+ minutes in the console → MeshCentral signs out; session limit (`SESSION_MAX_MINUTES`) ends the session.

### B. Attended (PC-A, user logged on, nothing pre-installed)
1. tech1 *Start Remote Support* → share code by phone/internal chat.
2. On PC-A open `https://remote.<domain>/join`, enter the code, review, approve, download
   **Windows (64-bit)**, run it (SmartScreen/UAC behaviour noted), click **Connect**.
3. tech1 sees PC-A → *Open remote console* → PC-A shows the consent prompt → user clicks **Allow** → control works.
4. Terminal and Files each prompt the user; test one **Deny** → recorded as rejected.
5. Termination, each in a fresh session: (a) technician *End Session*; (b) user *End session* on the join
   page; (c) user closes the agent window; (d) user clicks *Disconnect* on the connection bar.
   Expect access to end immediately and the session record to show who ended it.
6. Code expiry: wait past `ATTENDED_CODE_TTL_MINUTES` before joining → refused.

### C. Internet-disconnected run
Repeat A.4–A.7 and B.1–B.3 with the server, PC-A, PC-B and the technician PC on an isolated
VLAN/switch with **no Internet route and no external DNS** (verify with `Test-NetConnection 8.8.8.8 -Port 443`
and an external name lookup failing). Everything must still work.

### D. Sign-off record
For each step: pass/fail, screenshot, session id. Attach `docker compose logs --since 2h` and an
export of the audit log (*Audit Log* page or `GET /api/audit/`).
