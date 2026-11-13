# Cyber Safe Jhunjhunu × TechGuardians: Daily Cyber Crime Reels

Automatic 9:16 reels (1080×1920, 30fps, ~88 sec) for the **CSJ (Cyber Safe Jhunjhunu)** page.
Each reel covers one cyber crime: **कैसे होता है → खतरे के संकेत → कैसे बचें → फोन सेटिंग → 1930 हेल्प → Motto**.

Branding is fixed on every reel:
- **Header:** CSJ logo + "साइबर सेफ झुंझुनूं / शेखावाटी का साइबर प्रहरी" + TechGuardians shield
- **Footer:** RJ NEHRA · Master in AI Cyber Security · TechGuardians · Cyber Fouji, plus a 1930 alert ticker
- **Motto (outro):** "अब हम किसी के साथ कोई साइबर क्राइम नहीं होने देंगे 🇮🇳"

## Reel structure (88 sec)

| Time | Section | Purpose |
|---|---|---|
| 0:00 | 🚨 Hook (glitch + siren) | Stops the scroll |
| 0:05 | Title: "आज का साइबर क्राइम #Day" | "अंत तक देखें: फोन सेटिंग" keeps viewers watching |
| 0:11 | ठगी ऐसे होती है (4 steps + live phone chat demo, OTP theft, ₹ debited) | Story |
| 0:35 | 🚩 खतरे के 3 संकेत | Recognise it |
| 0:45 | 🛡️ ऐसे बचें (4 tips) | Prevention |
| 0:57 | ⚙️ अभी करें ये सेटिंग (3 phone settings, animated tap + toggle) | Practical action |
| 1:14 | 1930 / cybercrime.gov.in / bank block / Chakshu | If it already happened |
| 1:21 | Motto + Follow / Share | Growth |

## Daily use

```bash
cd reels
node tools/render.js            # today's crime (never repeats), marks it used
```
Output in `reels/output/`:
- `YYYY-MM-DD_dayNN_<id>.mp4`: the reel
- `YYYY-MM-DD_dayNN_<id>.txt`: **voiceover script with timings + caption + hashtags**

Other commands:
```bash
node tools/render.js digital-arrest 5   # a specific crime as "Day 05" (rotation untouched)
node tools/pick.js                      # show which crime is next
```
Live preview in a browser: open `template/reel.html?id=digital-arrest&day=5`.

## No repeats + new Rajasthan crimes

- `data/crimes.js` has **32 crimes** (wedding-card APK, digital arrest, fake Fauji on OLX, sextortion, e-challan APK,
  PM Kisan APK, KYC, bijli bill, Telegram task, trading group, QR, AI voice clone, loan app, SIM swap,
  Agniveer bharti, pension/ECHS, AePS, Khatu/Salasar room booking …).
- `data/used.json` records what was posted; the next unused one is picked automatically.
- **New crime in the news today?** Copy any entry from `crimes.js` into `data/breaking/YYYY-MM-DD.json`
  (same fields, JSON format). That day's render uses it instead of the rotation.
  See `data/breaking/_TEMPLATE.json`.

## Voiceover (RJ Nehra's voice)

The reel ships with royalty-free synthesized music + SFX (no copyright strikes).
To add your voice: read the script from the `.txt` file, save it as `voice/<crime-id>.mp3`, run render again;
music is auto-ducked under your voice.

## Requirements
Node 18+, Playwright (Chromium), Python 3 + numpy, ffmpeg. Fonts (Poppins, Baloo 2, Hind) are bundled in `assets/fonts`.
