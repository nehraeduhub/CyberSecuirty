<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# DNSRecon (DNS Enumeration)
**TOOL PURPOSE:** Enumerate a domain's DNS records (A, MX, TXT, NS, SRV) and find subdomains —
to show an organisation's public DNS footprint.

**INSTALLATION:** `sudo apt install dnsrecon`

**OPEN/RUN:** `dnsrecon -d yourdomain.example`  (a domain you OWN/authorised)

**WHAT TO SHOW:** Mail servers, SPF/TXT records, name servers, discovered subdomains.

**WHAT THE AUDIENCE LEARNS:** DNS is public and maps your surface; publish SPF/DKIM/DMARC and
retire stale subdomains (ties to demo 17).

**SAFETY WARNING:** Own/authorised domains only; avoid aggressive brute force on others.
AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** your own domain, or screenshots.

**TROUBLESHOOTING:** Zone transfers usually fail (good); focus on standard record enumeration.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

