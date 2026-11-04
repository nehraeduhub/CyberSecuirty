<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Steghide (Steganography Awareness)
**TOOL PURPOSE:** Show how data can be *hidden inside* an image/audio file — so the audience
learns that innocent-looking files can carry concealed content.

**INSTALLATION:** `sudo apt install steghide`

**OPEN/RUN:**
```bash
steghide embed -cf cover.jpg -ef secret.txt   # hide (your OWN files)
steghide extract -sf cover.jpg                 # reveal
```

**WHAT TO SHOW:** Hide a harmless text note in a photo, then extract it — "the file looked normal".

**WHAT THE AUDIENCE LEARNS:** Attackers can smuggle data/malware config in media; be cautious with
unexpected files (ties to forensics demo 20).

**SAFETY WARNING:** Use your OWN sample files only; never conceal or move real sensitive data.
AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** a dummy photo + a harmless text file you create.

**TROUBLESHOOTING:** Use JPEG/WAV covers; a passphrase is required to extract.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

