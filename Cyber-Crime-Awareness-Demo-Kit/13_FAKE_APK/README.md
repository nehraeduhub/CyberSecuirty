<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 13 · Fake APK — Harmless APK-Analysis Demo
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Teach why installing APKs from links/WhatsApp is dangerous, and
show a **read-only** analysis workflow that reveals what an app really wants —
**without creating any malware**.

**Time Required:** 8–10 minutes
**Difficulty:** Intermediate
**Internet:** VirusTotal needs internet; JADX/Apktool/MobSF work offline.
**Kali tools:** JADX, Apktool, (optional) MobSF. See `../22_KALI_TOOLS/ANDROID_ANALYSIS/`.

## Important
This kit does **NOT** build, modify, or distribute malware. We only **analyse**
an app you are authorised to inspect (e.g. a benign open-source APK or a sample
you own). The point is awareness, not weaponisation.

## The story (fictional)
A WhatsApp forward: "📢 Free electricity subsidy! Install this govt app to claim
₹2,000." The APK isn't on Play Store; it's a direct download. It asks for SMS,
Contacts, Accessibility and "Display over other apps" — permissions a subsidy app
has no reason to want. That combination can read your OTP SMS and overlay fake
screens. See `SAMPLE_APK_INFO/fake_app_story.md`.

## Analysis workflow (read-only)
1. **Source check:** Not on Play Store + sent via link = stop. Most of the lesson
   ends here.
2. **VirusTotal:** upload the APK (or its hash) → multi-engine verdict + behaviour.
3. **MobSF:** static analysis → permissions, trackers, hardcoded URLs, risk score.
4. **JADX:** decompile to read what the code actually does (e.g. forwards SMS).
5. **Apktool:** unpack the manifest to list declared permissions and components.

See `APK_ANALYSIS.md` for the step-by-step and `PERMISSION_CHECKLIST.md` for the
dangerous-permission guide.

## Security Lesson
Install only from official stores. Dangerous permission **combinations** (SMS +
Accessibility + overlay) are how fake apps steal OTPs and hijack the screen.

## Safety Warning
Analyse only an APK you are authorised to inspect. Never run an unknown APK on a
real/personal device — use an emulator or disposable test device. **AUTHORISED
DEMONSTRATION ONLY.**
