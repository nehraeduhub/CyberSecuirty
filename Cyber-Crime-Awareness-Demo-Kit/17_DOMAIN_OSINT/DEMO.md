<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 17 · Domain OSINT — "What a domain reveals (authorised)"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Show what public information a domain exposes (registration, DNS,
certificates, subdomains) and how an organisation can reduce its exposure.

**Time Required:** 8–10 minutes
**Difficulty:** Intermediate
**Internet:** Required. **Kali:** whois, dig. Offline fallback: screenshots.

## Authorisation
Demonstrate only on a domain **you own** or have **written permission** to
assess, or on a neutral example used for teaching. Never probe third-party
infrastructure.

## What You Need
- whois, dig (Kali/Linux). Online: crt.sh, SecurityTrails, Censys, Shodan
  (`../23_ONLINE_TOOLS/DOMAIN_OSINT.md`).

## Step-by-Step
1. **WHOIS:** `whois yourdomain.example` → registrar, dates, (often redacted) contacts.
2. **DNS:** `dig yourdomain.example ANY` / A, MX, TXT, NS → mail, SPF/DMARC, hosts.
3. **Certificates:** crt.sh → historical certs reveal **subdomains** (e.g. vpn., dev.).
4. **Passive data:** SecurityTrails/Censys → historical DNS, exposed services.
5. Discuss what an attacker learns and how to shrink it.

## What Audience Sees
A single domain unfolding into mail servers, dev/staging subdomains and exposed
services — the organisation's public attack surface.

## Presenter Script
"An attacker starts here, not with hacking. crt.sh quietly lists every subdomain
you ever got a certificate for — including that forgotten `test.` server. That's
where trouble begins."

## Security Lesson
Public records (WHOIS, DNS, certificate transparency) map an organisation's
surface. Reducing and monitoring it is basic defence.

## Prevention (for organisations)
- Use WHOIS privacy; don't leak staff emails in records.
- Retire/secure stale subdomains; monitor certificate transparency logs.
- Publish SPF, DKIM, DMARC to stop email spoofing.
- Don't expose dev/staging/admin to the public internet.
- Periodically run this OSINT on **yourself** to find gaps first.

## Questions to Ask
- "How many subdomains do you think your org exposes?"
- "Is your DMARC set to reject spoofed mail?"

## Safety Warning
Authorised/own domains only. Passive lookups preferred; no intrusive scanning of
others. **AUTHORISED DEMONSTRATION ONLY.**
