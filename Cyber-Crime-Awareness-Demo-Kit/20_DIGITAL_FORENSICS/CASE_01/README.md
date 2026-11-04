<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Case 01 — Phishing Email Analysis (FICTIONAL)

## Scenario
An employee reports a suspicious "IT Helpdesk" email. Investigate its headers,
links and intent — on the provided sample, read-only.

## Evidence
- `sample_email.eml` — a fictional phishing email (safe, inert).

## Analysis steps
1. **Headers:** inspect `Received:`, `Return-Path:`, `From:` vs `Reply-To:`.
   - Mismatch between display name and actual address? Odd sending server?
   - Check SPF/DKIM/DMARC result lines (fail = spoofing likely).
2. **Links:** extract URLs WITHOUT clicking; read the real domain; scan via
   URLScan/VirusTotal (demo 16).
3. **Intent:** urgency, credential request, attachment lure.
4. **Verdict & actions:** report, block sender/domain, warn staff, reset if anyone
   interacted.

## Teaching point
The "From" name is free text; the headers reveal the truth. DMARC alignment and
link analysis quickly expose spoofed mail.
