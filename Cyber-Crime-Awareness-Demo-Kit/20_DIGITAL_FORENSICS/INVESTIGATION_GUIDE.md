<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 20 · Digital Forensics — Investigation Guide
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Introduce how investigators analyse evidence after an incident,
using **fictional** cases and sample evidence — to build respect for evidence
handling and show the audience "what happens next".

**Time Required:** 10–15 minutes (pick 1–2 cases)
**Difficulty:** Intermediate
**Internet:** Mostly offline. **Kali:** ExifTool, Autopsy, (optional) Volatility.

## Golden rule of forensics
> Preserve first. Work on **copies**. Keep a chain of custody. Never alter the
> original evidence.

## The cases (all fictional)
- `CASE_01/` — Phishing email analysis (headers, links, intent).
- `CASE_02/` — Suspicious APK triage (links to demo 13 workflow).
- Case 3 (below) — Stolen document (metadata + authorship).
- Case 4 (below) — Data exfiltration **awareness** (what the traces look like).

## Tools used (read-only analysis)
- **ExifTool** — document/image metadata (author, timestamps, GPS).
- **Autopsy** — disk image browsing, timelines, keyword search (on sample images).
- **Volatility** — memory analysis *concepts* (on sample memory dumps only).

## Case 3 — Stolen document (metadata)
A leaked PDF/DOCX is recovered. Run `exiftool leaked.docx`:
- Author, Company, Created/Modified timestamps, software, revision count.
- Teaching point: documents carry authorship metadata that can identify the
  source of a leak — and that YOUR documents do too.
Prevention: strip metadata before sharing sensitive docs; use "inspect document".

## Case 4 — Data exfiltration (awareness)
Explain the *signs* investigators look for (no live hacking):
- Large outbound transfers at odd hours; data going to unknown cloud/USB.
- Unusual access to bulk records; archives (.zip/.rar) created before transfer.
- Logs, netflow and endpoint alerts tell the story.
Prevention: least-privilege access, DLP, logging, alerting, offboarding controls.

## What the audience learns
Incidents leave traces; evidence is fragile and must be preserved; and the data
*they* create (document metadata, logs) tells a story too.

## Safety Warning
Use only the fictional/sample evidence provided or data you own. Never analyse
someone else's device/data without legal authorisation. **AUTHORISED
DEMONSTRATION ONLY.**
