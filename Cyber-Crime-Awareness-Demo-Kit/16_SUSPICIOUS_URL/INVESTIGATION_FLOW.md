<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# URL Investigation Flow

```
Suspicious link
      |
      v
[1] READ it (don't click)
    - Find the REAL domain: label just before the first single "/"
    - Watch for: extra subdomains, misspellings, wrong TLD, @-trick,
      hyphen soup, homoglyphs, shorteners
      |
      v
[2] EXPAND if shortened
    - Use a URL expander / URLScan to reveal the true destination
      |
      v
[3] SCAN (never visit directly)
    - URLScan.io    -> screenshot + what it loads + domains contacted
    - VirusTotal    -> multi-engine reputation
    - PhishTank     -> known phishing?
    - Google Safe Browsing -> flagged?
    - URLVoid       -> domain reputation/age
      |
      v
[4] DECIDE
    - Any red flag -> don't click. Go to the official app / typed address.
    - Report phishing (PhishTank / cybercrime.gov.in for India).
```

## Teaching the "real domain" rule
```
https://  sbi.account-verify.example  /login
          └ subdomain ┘└ REAL DOMAIN ┘
```
Owner = whoever controls `account-verify.example`. "sbi" is just a word they chose.
