<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Domain OSINT Checklist (authorised targets only)

- [ ] WHOIS: registrar, creation/expiry, privacy on? contacts leaked?
- [ ] DNS A/AAAA: where is it hosted?
- [ ] DNS MX: mail provider.
- [ ] DNS TXT: SPF present? DMARC policy (none/quarantine/reject)? DKIM?
- [ ] NS: DNS provider.
- [ ] crt.sh: list historical certs → enumerate subdomains.
- [ ] SecurityTrails/Censys: historical DNS, exposed ports/services.
- [ ] Shodan (demo 18): any exposed devices/services on the org's IPs?
- [ ] Wayback Machine: old pages leaking emails/paths.

## Reduce exposure (defender actions)
- [ ] Enable WHOIS privacy.
- [ ] Enforce DMARC reject + SPF + DKIM.
- [ ] Decommission stale subdomains; remove dangling DNS.
- [ ] Keep dev/staging/admin off the public internet (VPN/allowlist).
- [ ] Monitor CT logs for unexpected certificates.
