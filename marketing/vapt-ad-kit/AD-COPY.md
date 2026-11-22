# Tech Guardians VAPT — Meta Ad Kit

Made by **RJ Nehra · Master in AI Cyber Security**. No prices anywhere in the kit.

## What is in the kit

| File | Size | Where to use it |
|---|---|---|
| `TG-VAPT-Reel-60s.mp4` | 1080×1920, ~60 s | Instagram / Facebook Reels ad, Stories ad, YouTube Shorts, WhatsApp Status |
| `Reel-Cover-1080x1920.png` | 1080×1920 | Cover (thumbnail) of the reel |
| `Feed-Post-4x5-1080x1350.png` | 1080×1350 | **Main feed ad** (Instagram + Facebook feed). Best format for feed. |
| `Feed-Post-Square-1080x1080.png` | 1080×1080 | Feed post, Marketplace, right column |
| `Story-Poster-1080x1920.png` | 1080×1920 | Instagram / Facebook Story (image), WhatsApp Status |
| `Carousel-1.png` … `Carousel-5.png` | 1080×1080 each | Carousel ad / carousel post: Hook → Khatre → Plug-Scan-Report → PDF report → CTA |
| `Link-Ad-Banner-1200x628.png` | 1200×628 | Link-click ad (landscape), website banner, LinkedIn post |
| `Facebook-Cover-1640x624.png` | 1640×624 | Facebook page cover (left side is left free for the profile picture) |
| `LinkedIn-Banner-1584x396.png` | 1584×396 | LinkedIn profile / page banner |
| `Print-Poster-A4.png` | 2480×3508 (A4, 300 dpi) | Print poster, PDF flyer, WhatsApp share |

The reel's voice is AI: a female host and a male host, taking turns. It has background music and Hinglish subtitles burned in, because most people watch reels with the sound off.

## Ads Manager setup (suggested)

- **Objective:**
  - **Engagement → Messages** (Instagram DM + WhatsApp + Messenger). This matches the "DM karo SCAN" CTA.
  - Alternative: **Leads** with an instant form (Name, Phone, Website URL).
- **CTA button:** *Send Message* (Messages objective), or *Learn More* (link to techguardians.in).
- **Placements:** Advantage+ placements. Upload creatives per placement:
  - Feed → 4:5 post.
  - Stories & Reels → the reel, with Story-Poster as an image variant.
  - Right column → square post.
- **Audience (India):** age 23–55.
- **Interests:** Small business owners, Web development, WordPress, Shopify, Digital marketing agencies, Information security, Startups, E-commerce.
- **Job titles:** Founder, Director, IT Manager, Web Developer, Freelancer.
- **Test:** 2 ad sets (Agencies + Freelancers / Business owners) × 3 creatives (Reel, 4:5 post, Carousel). After 3–4 days, keep the cheapest cost per message.

## Primary text (pick one per ad)

**Short**
```
🛡️ Hackers already aapki website scan kar rahe hain. Aap kar rahe ho?
Tech Guardians VAPT — minutes mein poora VA + PT, proof ke saath. DM karo "SCAN" 👉
```

**Medium**
```
🛡️ Aapki website SAFE hai?
SQL Injection, XSS, RCE — zyada tar websites mein ye flaws hote hain, aur pata bhi nahi chalta.

Tech Guardians VAPT minutes mein poora Vulnerability Assessment + Penetration Test karta hai,
real flaws ko proof ke saath confirm karta hai, aur professional PDF report deta hai.

👉 DM karo "SCAN"
```

**Long (organic post caption)**
```
🛡️ Hackers already aapki website scan kar rahe hain. Aap kar rahe ho?

Tech Guardians VAPT minutes mein poora Vulnerability Assessment + Penetration Test karta hai — aur SQL Injection, XSS, RCE jaise real issues ko proof ke saath confirm karta hai. Professional, CERT-In-aligned PDF report, kisi bhi client ke liye ready.

✅ Automated VA + PT
✅ Real vulnerabilities confirm karta hai
✅ Professional branded report
✅ Portable — pendrive se chale

Agencies, freelancers aur businesses ke liye perfect.
👉 DM karo "SCAN" aur shuru karo.

— Made by RJ Nehra, Master in AI Cyber Security
```

## Headlines (≤ 40 characters)

1. Automated VAPT — minutes mein
2. Aapki website SAFE hai?
3. Real flaws. Real proof. Pro report.
4. VA + PT, fully automatic
5. Plug karo. Scan karo. Report lo.

## Descriptions (≤ 30 characters)

- OWASP · CVSS · CERT-In aligned
- Portable · Rebrandable
- Agencies & freelancers ke liye

## Carousel card titles

| # | Headline | Description |
|---|---|---|
| 1 | Hackers scan kar rahe hain | Aap kar rahe ho? |
| 2 | SQLi · XSS · RCE | Chhupe hue khatre |
| 3 | Plug. Scan. Report. | Na setup, na database |
| 4 | Professional PDF report | OWASP · CVSS · CERT-In |
| 5 | Aaj hi website secure karo | DM karo "SCAN" |

## Hashtags (organic posts only; ads don't need them)

```
#cybersecurity #vapt #pentesting #ethicalhacking #infosec #websecurity #OWASP #CERTIn #bugbounty #cybersecurityindia #techguardians #datasecurity #hacking #itsecurity #indianstartups #digitalindia
```

## Pinned comment / auto-reply for "SCAN"

```
Thanks! 🙌 Apna website URL aur WhatsApp number bhejo — Tech Guardians VAPT ka demo scan aur sample report share karenge.
```

## Before you run the ads (Meta review + trust)

- Scan only websites the owner has **permission** to test. Write "authorised testing only" in the DM reply / report. Unauthorised scanning is an offence under the IT Act.
- Use **"aligned with"** CERT-In / RBI / DPDP. Do not write "certified by" or "approved by", unless you hold such a certification. Meta and clients both check this.
- The scanner screen and the report in the creatives are illustrations. Real screenshots of the tool (with the client's name blurred) can replace them later and build more trust.
- Meta does not allow "before/after" shock claims or personal-attribute wording ("*you* are hacked"). The copy above stays general ("aapki website safe hai?"), which is allowed.

## Files to edit

- Static designs: `src/posters.html` (each format is one layout).
  - Render with `node src/posters.js <out dir>`.
- Reel: `src/script.json` holds the voice lines (Devanagari) and on-screen text, and `src/subs.json` holds the subtitles.
  - `src/voice.py` makes the voice-over; `src/reel.html` + `src/render.js` animate it.
  - `src/build-reel.sh` runs everything.
