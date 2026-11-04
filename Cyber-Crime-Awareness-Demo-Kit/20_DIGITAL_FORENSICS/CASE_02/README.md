<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Case 02 — Suspicious APK Triage (FICTIONAL)

## Scenario
A "courier redelivery" APK was received by several staff. Triage it — read-only.

## Evidence
- Use an authorised/benign sample APK (never real malware). See demo 13.

## Analysis steps (summary — full workflow in 13_FAKE_APK/)
1. **Source:** off-store + link delivery = already suspicious.
2. **Hash + VirusTotal:** `sha256sum app.apk` → multi-engine verdict.
3. **MobSF:** permissions, trackers, hardcoded URLs, risk score.
4. **JADX/Apktool:** read what it does; list manifest permissions.
5. **Verdict:** dangerous permission combo (SMS+Accessibility+overlay) → malicious;
   contain (don't install), warn staff, report.

## Teaching point
You can assess an app's intent from its permissions and code before trusting it.
See `../../13_FAKE_APK/` for the detailed, safe workflow.

## Safety
Analyse on an emulator/disposable device. Never run unknown APKs on real phones.
