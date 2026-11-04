<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# APK Analysis — Step-by-Step (read-only, no malware)

> Use a benign/open-source APK or an authorised sample. Analyse on an emulator or
> disposable device, never your personal phone.

## 0. Golden first step
Is it on the official Play Store / App Store? If it arrived as a link or WhatsApp
file and isn't on the store — that's already the answer. Don't install it.

## 1. VirusTotal (Internet required)
- Go to the official VirusTotal site (`../23_ONLINE_TOOLS/URL_ANALYSIS.md`).
- Upload the APK or paste its SHA-256 hash: `sha256sum app.apk`.
- Read: detections across engines, requested permissions, embedded URLs, behaviour.
- Teaching point: a brand-new fake app may have few detections — absence of
  detection is NOT proof of safety.

## 2. MobSF (offline static analysis)
- Start MobSF (see `../22_KALI_TOOLS/ANDROID_ANALYSIS/MOBSF.md`).
- Upload the APK → review: permission list, trackers, hardcoded secrets/URLs,
  insecure settings, risk score.
- Teaching point: map each scary permission to "why would THIS app need it?".

## 3. JADX (offline decompile)
```bash
jadx -d out_app app.apk        # or: jadx-gui app.apk
```
- Browse decompiled Java. Search for SMS APIs, `SmsManager`, `getMessageBody`,
  network calls, and Accessibility service usage.
- Teaching point: show (in a sample) code that reads incoming SMS and forwards it
  — that's how OTP theft works.

## 4. Apktool (offline manifest)
```bash
apktool d app.apk -o out_manifest
sed -n '1,60p' out_manifest/AndroidManifest.xml
```
- List `<uses-permission>` entries and exported components.
- Teaching point: compare declared permissions to the app's claimed purpose.

## What the audience learns
You can SEE what an app wants before trusting it — and a "subsidy" app that wants
to read your SMS and draw over other apps is lying about its purpose.
