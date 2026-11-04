<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 16 · Suspicious URL — "Read the link before you click"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Teach how to dissect a URL and use safe analysis services to judge
a link without visiting it.

**Time Required:** 7–9 minutes
**Difficulty:** Beginner
**Internet:** Required for scanners. Offline fallback: `SAMPLE_URLS.txt` + screenshots.

## What You Need
- `SAMPLE_URLS.txt`, `INVESTIGATION_FLOW.md`.
- Services: URLScan, VirusTotal, URLVoid, PhishTank, Google Safe Browsing
  (`../23_ONLINE_TOOLS/URL_ANALYSIS.md`).

## Step-by-Step
1. Put a sample URL on screen; read the **real domain** together (right-to-left).
2. Spot the trick: lookalike spelling, extra subdomain, wrong TLD, @-trick, shortener.
3. Paste it into **URLScan** / **VirusTotal** to inspect without visiting.
4. Check **PhishTank** / **Google Safe Browsing** status.

## What Audience Sees
A link that "looks like" a bank/govt site revealed as attacker-controlled, and
tools that scan it safely.

## Presenter Script
"The link says 'sbi' — but look: `sbi.account-verify.example`. The real owner is
`account-verify.example`. Anyone can put a trusted word in front of a dot. Let's
scan it safely before anyone clicks."

## Security Lesson
The real domain is the label just before the first single `/`. Everything left of
it can be faked. Scan, don't click.

## Prevention
- Hover/long-press to preview links; read the real domain.
- Don't trust shorteners blindly; expand them with a scanner.
- Type known addresses yourself; use bookmarks for banking.
- When unsure, scan with URLScan/VirusTotal first.

## Questions to Ask
- "What's the REAL domain here?"
- "Would you click this from an SMS?"

## Safety Warning
Analyse links with scanners; do **not** open suspicious links directly. Use the
provided safe samples.
