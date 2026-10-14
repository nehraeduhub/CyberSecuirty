# BSF Remote Assist — Go-Live SOP

## Phase A — Pilot
1. Create a dedicated pilot OU with 5–10 non-critical domain PCs.
2. Deploy the Windows/MeshCentral agent through the pilot GPO.
3. Confirm enrollment and heartbeat.
4. Approve each device in BSF Remote.
5. Create one technician account and assign only the pilot device group.
6. Test attended access, unattended access, terminal, file transfer and reboot according to policy.
7. Capture audit records.

## Phase B — Security validation
1. Test unauthorized device access through the UI and API.
2. Test token reuse.
3. Test expired MFA grant.
4. Test disabled AD account.
5. Test portal account without AD access.
6. Verify MeshCentral login-token secret is not exposed to the browser.
7. Run vulnerability assessment against the portal/reverse proxy.
8. Review logs for secrets, passwords and tokens.

## Phase C — Controlled rollout
Roll out by OU/site in batches. After each batch verify online count, heartbeat, MeshCentral node mapping and failed installations before continuing.

## Phase D — Rollback
- Disable the deployment GPO.
- Run the approved uninstall script if required.
- Revoke/disable affected portal device records.
- Revoke MeshCentral access for the affected group.
- Restore the previous application/container image if an application rollback is required.

## Production sign-off
Production approval requires written confirmation from the system owner, security/VAPT authority and operations owner that the acceptance checklist has passed.
