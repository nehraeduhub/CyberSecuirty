<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# ExifTool (Metadata)
**TOOL PURPOSE:** Read/strip hidden metadata in photos/documents (camera, time,
GPS, author) — privacy and forensics.

**INSTALLATION:**
```bash
sudo apt install libimage-exiftool-perl
```

**OPEN/RUN:**
```bash
exiftool sample.jpg                 # read metadata
exiftool -all= sample.jpg           # strip all metadata
```

**WHAT TO SHOW:** GPS/camera/date in a photo you took; then a clean file after stripping.

**WHAT THE AUDIENCE LEARNS:** Your files carry hidden data; strip it before sharing.

**SAFETY WARNING:** Use your OWN files or provided dummies. AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** `../../06_PHOTO_PRIVACY/` (and the metadata example).

**TROUBLESHOOTING:** No GPS shown? the photo may have none — use the dummy-image
recipe in demo 06 to add fictional tags for teaching.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

