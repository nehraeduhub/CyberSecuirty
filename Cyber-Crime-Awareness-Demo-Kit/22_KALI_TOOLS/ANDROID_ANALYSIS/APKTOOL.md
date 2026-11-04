<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Apktool (APK Unpacker)
**TOOL PURPOSE:** Unpack an APK's manifest and resources to list permissions and
components (read-only).

**INSTALLATION:**
```bash
sudo apt install apktool
```

**OPEN/RUN:**
```bash
apktool d app.apk -o out
sed -n '1,60p' out/AndroidManifest.xml
```

**WHAT TO SHOW:** The `<uses-permission>` list vs the app's claimed purpose.

**WHAT THE AUDIENCE LEARNS:** Mismatched permissions expose malicious intent
(demo 13's permission checklist).

**SAFETY WARNING:** Authorised/benign samples only. AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** a benign APK you may inspect.

**TROUBLESHOOTING:** Framework errors? run `apktool empty-framework-dir` and retry.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

