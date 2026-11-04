<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# PhoneInfoga (Phone Number OSINT)
**TOOL PURPOSE:** Show what *metadata* a phone number reveals (country, region, carrier,
line type) and how reputation/spam databases flag it — to teach caller-ID risk.

**INSTALLATION:**
```bash
# official binary / docker
docker run --rm -it sundowndev/phoneinfoga scan -n "+91 99999 00001"
```

**OPEN/RUN:** `phoneinfoga scan -n "+91 99999 00001"`  (a FICTIONAL/reserved number)

**WHAT TO SHOW:** The number decoded into country/region/carrier + footprint links.

**WHAT THE AUDIENCE LEARNS:** A number leaks region/carrier; caller-ID is spoofable and
is NOT proof of identity (ties to demo 05 and vishing).

**SAFETY WARNING:** Metadata only. NEVER call/message/OSINT a stranger's number. No OTP/SMS
bombing — ever. AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** reserved numbers in `../../05_PHONE_NUMBER/SAMPLE_DATA/numbers.txt`.

**TROUBLESHOOTING:** Some scanners need API keys; stick to the local/format scan for a demo.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

