<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Instructor Notes — Phishing Simulation

## Before you click "Sign in"
Say this out loud so the lesson sticks: *"I'm going to type a FAKE password.
Never type a real one into a page you reached from a link — even this one."*

## The 5 red flags to point at (in order)
1. **The domain.** Read the address bar right-to-left. The real domain is the
   label just before the first single `/`. Here: `verify-account.example`.
   "NimbuPay" is only a decorative subdomain word the attacker chose.
2. **http:// (no padlock).** No encryption. (But stress: HTTPS ≠ safe — criminals
   get certificates too. HTTPS protects the pipe, not the destination.)
3. **Urgency / countdown.** "Suspended in 10:00." Fear makes people skip checks.
4. **Authority & branding.** Logo + colours manufacture trust.
5. **Password on a linked page.** Legit services push you to their app, not a form.

## How to teach "read the domain"
Write on the board:
```
https://  nimbupay-secure-login.verify-account.example  /login
          └── subdomains (attacker-chosen words) ──┘└─ REAL DOMAIN ─┘
```
The REAL owner is whoever controls `verify-account.example`. Anyone can put the
word "nimbupay" in front of a dot.

## Common audience questions
- *"But it had https and a lock!"* → A lock means the connection is encrypted to
  **that site**, which may be the criminal's site. Verify the name, not just the lock.
- *"How did the link reach me?"* → SMS (smishing), email, WhatsApp, ad, QR code.
- *"What if I already entered my password?"* → Change it immediately on the REAL
  site, enable MFA, watch for transactions, report (see `../25_INCIDENT_RESPONSE/`).

## Variations by audience
- **Students:** make it a "free game currency / verify your gaming account" page.
- **Govt staff:** frame as a fake internal portal / KYC verification.
- **Seniors:** frame as a bank "re-verify KYC or account blocked" page.
(You can edit the brand text in `local_demo/index.html` — keep it fictional.)

## Absolute rules
- Never host this on a public URL to collect anything — it collects nothing by
  design, and you must keep it that way.
- Never adapt it to target a real brand's customers or capture real data.
- Serve it on `127.0.0.1` only (the provided script does this).
