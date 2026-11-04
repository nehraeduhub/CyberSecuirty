<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 06 · Photo — "Your picture talks"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Show that a shared photo can reveal location/device via metadata
and can be traced across the web via reverse image search.

**Time Required:** 6–8 minutes
**Difficulty:** Beginner
**Internet:** Reverse search needs internet. **Kali/CLI:** ExifTool (offline).
**Offline fallback:** `METADATA_EXAMPLES/`.

## What You Need
- A sample photo **you took** or a provided dummy image in `SAMPLE_IMAGES/`.
- ExifTool. Online: Google Lens, TinEye.

## Step-by-Step
1. Run `exiftool sample.jpg` — show camera model, date, and (if present) GPS.
2. Explain how GPS tags pin the exact spot a photo was taken.
3. Reverse-search a profile photo (Google Lens / TinEye) to show reuse/tracing.
4. Strip metadata live: `exiftool -all= sample.jpg` → re-check: clean.

## What Audience Sees
Hidden coordinates inside an innocent photo, then the same face found elsewhere
online — followed by the fix.

## Presenter Script
"You post a photo from home. If location tags are on, that JPEG may literally
contain your front-door coordinates. And a profile picture you reuse everywhere
links all your accounts together with one reverse search."

## Security Lesson
Images carry invisible metadata, and faces/pictures are searchable. Sharing a
photo can share far more than you intended.

## Prevention
- Turn off location tagging in your camera app.
- Strip metadata before posting (`exiftool -all=`), or use apps that auto-strip.
- Don't reuse the same profile photo across sensitive and public accounts.
- Be cautious posting photos that reveal home, school, routes or documents.

## Questions to Ask
- "Is location tagging on in your camera right now? Check."
- "Is your profile photo the same on five apps?"

## Safety Warning
Use only photos **you own/took** or the provided dummy images. Never analyse or
reverse-search someone else's photo without consent.
