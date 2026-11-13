# Cyber Safe Jhunjhunu × TechGuardians: Daily Cyber Crime Reels

Automatic 9:16 reels (1080×1920, 30fps, 50 sec to 2 min, Hindi voiceover) for the **CSJ (Cyber Safe Jhunjhunu)** page.
Each reel covers one cyber crime: **कैसे होता है → खतरे के संकेत → कैसे बचें → फोन सेटिंग → 1930 हेल्प → Motto**.

Branding on every reel:
- **Header:** CSJ logo (left) · "साइबर सेफ झुंझुनूं / शेखावाटी का साइबर प्रहरी / 📍 झुंझुनूं, राजस्थान" · TechGuardians shield (right)
- **Footer:** RJ NEHRA · Master in AI Cyber Security · 🎙️ live voice equalizer | **1930 साइबर हेल्पलाइन** | Cyber Fouji, plus the alert ticker
- **Motto (outro):** "अब हम किसी के साथ कोई साइबर क्राइम नहीं होने देंगे 🇮🇳"

**Voice + effects:** offline neural Hindi voiceover (Piper, radio EQ/compression), with the animation timed to the voice,
music that ducks under the voice, synthesized SFX, camera zoom, glitch transitions, light leaks, bokeh particles,
matrix rain, and a cinematic color grade + film grain (ffmpeg).

## Reel structure (~1:45, every part is timed to the voice)

| Time | Section | Purpose |
|---|---|---|
| 0:00 | 🚨 Hook (glitch + siren) | Stops the scroll |
| ~0:05 | Title: "आज का साइबर क्राइम #Day" | "अंत तक देखें: फोन सेटिंग" keeps viewers watching |
| ~0:16 | ठगी ऐसे होती है (4 steps + live phone chat demo, OTP theft, ₹ debited) | Story |
| ~0:40 | 🚩 खतरे के 3 संकेत | Recognise it |
| ~0:52 | 🛡️ ऐसे बचें (4 tips) | Prevention |
| ~1:07 | ⚙️ अभी करें ये सेटिंग (3 phone settings, animated tap + toggle) | Practical action |
| ~1:26 | 1930 / cybercrime.gov.in / bank block / Chakshu | If it already happened |
| ~1:36 | Motto + Follow / Share | Growth |

## Daily use

```bash
cd reels
bash tools/get-voices.sh        # one time: downloads the Hindi voices
node tools/render.js            # today's crime (never repeats), marks it used
```
Output, a same-name set in `reels/export/`:
- `CSJ-Day01-Wedding-Invitation-APK-Fraud.mp4`: the reel (50 sec to 2 min)
- `CSJ-Day01-Wedding-Invitation-APK-Fraud-thumbnail.jpg`: cover image
- `CSJ-Day01-Wedding-Invitation-APK-Fraud-caption.txt`: SEO caption, trending hashtags, YouTube Shorts title/tags

Options: `VOICE=pratham` or `VOICE=priyamvada` (female), `SPEED=0.8` (faster), `node tools/render.js digital-arrest 5` (specific crime).

**Save to Google Drive (`G:\My Drive\CSJ Reels`):** on your Windows PC, double-click `reels\tools\save-to-drive.bat`.
It pulls the latest reels and copies the new files into that folder.

## No repeats + new Rajasthan crimes

- `data/crimes.js` has **31 crimes** (wedding-card APK, digital arrest, fake Fauji on OLX, sextortion, e-challan APK,
  PM Kisan APK, KYC, bijli bill, Telegram task, trading group, QR, AI voice clone, loan app, SIM swap,
  Agniveer bharti, pension/ECHS, AePS, Khatu/Salasar room booking …).
- `data/used.json` records what was posted; the next unused one is picked automatically.
- **New crime in the news today?** Copy any entry from `crimes.js` into `data/breaking/YYYY-MM-DD.json`
  (same fields, JSON format). That day's render uses it instead of the rotation.
  See `data/breaking/_TEMPLATE.json`.

## Your own voice instead of AI

Read the script from `output/.work/<name>/voiceover-script.txt`, save it as `voice/<crime-id>.mp3`, render again:
your recording replaces the AI voice and the music ducks under it automatically.

## Requirements
Node 18+, Playwright (Chromium), Python 3 + numpy, ffmpeg. Fonts (Poppins, Baloo 2, Hind) are bundled in `assets/fonts`.
