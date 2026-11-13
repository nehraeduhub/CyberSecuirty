# Tech Guardians — Reels & Video Ads Plan

Status: **Phase 1 done (2026-11-13)** — template + pipeline built, 3 pilot reels made (12 Firewall, 18 Wireshark, 23 Incident Response).
Waiting for the owner to approve look, voice, music level and length before Phase 2.
Branch: `claude/serene-bohr-hnex32` · Repo: `nehraeduhub/tech-guardians-portal` · Site: https://techguardians.in

This file is the hand-over for a new chat. A new chat cannot see earlier conversations, so everything
needed is written here. Start a new chat with the prompt in **§10**.

---

## 1. Goal

Promote the website with short vertical video ads (Instagram Reels, YouTube Shorts, WhatsApp Status,
Facebook Reels), **30–60 seconds each**, covering:

- every **PDF handbook** (43, Cyber Security Handbook Series, ₹399 → offer ₹199), and
- every **CTF room** (43 rooms, 432 tasks, task 1 of every room free, ₹99/month or ₹999/year),
- plus a few brand reels for the website as a whole.

**Key fact:** the 43 handbooks and the 43 CTF rooms cover the same 43 topics (same order).
So one topic reel sells both: *learn it in the handbook → practise it in the CTF room*.

## 2. Formats

| Item | Spec |
|---|---|
| Video | 1080 × 1920 (9:16), H.264 High, 30 fps, CRF 18–19, `yuv420p`, `+faststart` |
| Audio | AAC 192 kb/s, 48 kHz stereo; original music generated per reel (no copyright claims), peak ≤ −1 dB |
| Length | 30–60 s (topic reels ≈ 45 s, brand reels ≈ 45–60 s) |
| Safe zones | Keep text between y = 220 and y = 1500 px; Instagram covers the bottom ~380 px and right ~140 px |
| Extras per reel | `NN-slug.mp4`, `NN-slug-cover.jpg` (1080×1920 thumbnail), `NN-slug.srt` (captions), `NN-slug.txt` (post caption + hashtags) |
| Optional | 1:1 (1080×1080) cut for Facebook/LinkedIn feed — only if asked |

## 3. Tools (what is really available in the cloud container)

Checked on 2026-11-13 in the session container:

- **ffmpeg 6.1** with `xfade`, `zoompan`, `drawtext`, `gblur`, `vignette`, `lut3d`, `chromakey`, `subtitles`/`ass` (562 filters)
- **ImageMagick** (`convert`), **Python Pillow**
- **Playwright + Chromium** (renders HTML/CSS/canvas animations frame by frame — this is the main animation engine; see `legacy/`)
- Fonts: Inter, Inter Display, JetBrains Mono, Noto Color Emoji, DejaVu
- **Voice-over: Kokoro TTS** (offline, `pip install kokoro-onnx soundfile`; model files `kokoro-v1.0.onnx` +
  `voices-v1.0.bin` from github.com/thewh1teagle/kokoro-onnx releases `model-files-v1.0`, set `KOKORO_DIR`).
  Hindi male voice `hm_omega` (alternative `hm_psi`). Voice script is written in Devanagari (English terms
  written in Devanagari too, e.g. फ़ायरवॉल) so it is pronounced naturally; on-screen captions are Roman Hinglish.
  huggingface.co and Microsoft/Google TTS hosts are blocked in the container; GitHub release downloads work.

Video tools the owner installed **on their own computer** (CapCut, Premiere, etc.) cannot be driven
from the cloud chat. Deliverables are plain MP4 + SRT so they can be opened and polished there.

## 4. Content sources (all inside this repo)

| What | Where |
|---|---|
| Handbooks: title, subtitle, description, pages, price, cover, preview pages | `website-classic/public/api/store-books.json`; images in `website-classic/public/images/store/books/` (`<id>-cover.png`, `<id>-feature.png`, …) |
| CTF rooms: number, title, path, difficulty, blurb, task titles, lesson text | `website-classic/public/api/ctf-data/rooms.json` (**never show flags/answers**: fields `h`, `hc`, and anything inside `chal`/`hints` that reveals a flag) |
| CTF prices | `website-classic/public/api/ctf-lib.php` (`TG_CTF_DEFAULT_PLANS`, admin may override) |
| Real website screens | Capture with Playwright from a local copy of the site (see §7) |
| Logo | clean shield: crop from the Diwali poster (see `legacy/launch/`), not `public/tg-logo.png` (has a baked checkerboard) |
| Brand | navy `#0b2a5b`/`#071a33`, saffron `#ff9933`, green `#138808`, gold `#ffcc4d`; tagline "Keep Learning · Keep Sharing" |

## 5. The reel series

### A. Brand reels (5)

| # | Reel | Length | Status |
|---|---|---|---|
| B1 | Website launch / tour (everything in one place) | 45 s | 16:9 launch intro exists → make 9:16 version |
| B2 | How to enroll for the CTF portal (6 steps) | 60 s | **done** (`TG-CTF-How-to-Enroll-Reel.mp4`, see `legacy/reel/`) |
| B3 | PDF Handbook Series — 43 books, look inside before you buy, ₹199 | 45 s | to do |
| B4 | Free cyber tools / Cyber Safety Portal (150+ tools, 1930 helpline) | 45 s | to do |
| B5 | Training programs + coupon offer | 45 s | to do |
| B6 | How to create a student account (request → approval → sign in with password **or email OTP**) | 60 s | **done** (`guides/account.json`, `tools/build-guide.sh`) |

### B. Topic reels (43) — one per topic, handbook + CTF room together

| Path (CTF) / Category (books) | Topics (reel numbers = room numbers) |
|---|---|
| Core Foundations / Security Foundations | 01 Cybersecurity Fundamentals · 02 CIA Triad · 03 Threats, Vulnerabilities & Risks · 04 Security Architecture · 05 Defense in Depth · 06 Zero Trust |
| Networking / Network Security | 07 TCP/IP · 08 Routing & Switching · 09 VLAN & VRF · 10 Network Segmentation · 11 MPLS |
| Perimeter & AppSec | 12 Firewall · 13 Load Balancer & ADC · 14 WAF · 15 Web Server Hosting |
| Detection & Recon | 16 IDS/IPS · 17 Network Monitoring · 18 Wireshark · 19 Nmap |
| SOC & Operations | 20 SOC Architecture · 21 SIEM · 22 Log & Alert Management · 23 Incident Response · 24 Threat Hunting · 25 SOAR · 26 Splunk/ELK/Wazuh/Sigma |
| Windows & Active Directory | 27 Windows Security · 28 Windows Hardening · 29 Active Directory · 30 Group Policy · 31 EDR · 32 PowerShell · 33 Sysinternals |
| Linux Security | 34 Linux Hardening · 35 Linux Monitoring |
| Digital Forensics | 36 Forensics Fundamentals · 37 Forensic Domains · 38 Forensic Tools |
| Threat Intelligence | 39 CTI Foundations · 40 CTI Operations |
| Virtualization & Data Centre | 41 Virtualization · 42 Container Security · 43 Data Centre Security |

### C. Learning-path reels (10, optional, 60 s)
One per path above: "Become a SOC analyst: 7 rooms + 7 handbooks". Make after the topic reels.

**Total: 5 brand + 43 topic (+10 path) = 48–58 reels.**

## 6. Topic reel template (≈45 s, data-driven — same layout, different data)

| Time | Scene | Content (from data) |
|---|---|---|
| 0–3 s | **Hook** | Big question/myth about the topic (written per topic, e.g. "Can a firewall stop everything?") + topic icon animation |
| 3–12 s | **What you'll learn** | 3 short points taken from the handbook description / room blurb, animated one by one |
| 12–24 s | **Handbook** | Cover in 3D tilt + 2 inside pages sliding (preview images), "53 pages · PDF", price ₹399 crossed → ₹199 |
| 24–36 s | **CTF room** | Real room screen in a phone frame, "Room NN · 10 hands-on tasks · difficulty", 2–3 task titles (no answers), "Task 1 FREE" |
| 36–42 s | **CTA** | "Learn it → Practise it", `techguardians.in`, "PDF Store" + "CTF Portal" buttons |
| 42–45 s | **End card** | Logo, tagline, tricolour |

Per path a different accent colour + music mood (10 moods), so the feed doesn't look repetitive.
Hooks are written by hand per topic (43 lines) and stored in `topics.json` (to be created).

## 7. Production pipeline (to build in Phase 1)

```
marketing/reels/
  PLAN.md                 this file
  topics.json             43 topics: hook line, 3 points, accent, mood (generated from data + hand-edited hooks)
  template/topic.html     data-driven animation (render(t) per frame, like legacy/reel/reel.html)
  tools/capture.js        Playwright: captures CTF room + handbook pages from a local copy of the site
  tools/render.js         Playwright: renders frames at 30 fps
  tools/music.py          original music, mood per path (pure Python, no numpy needed)
  tools/build.sh          one command: build.sh 12  -> out/12-firewall.mp4 (+ cover, srt, caption)
  legacy/                 the earlier CTF reel and the launch intro (working references)
```

Local site for screenshots: copy `website-classic/dist` to a folder, add test data in `api/data/`
(demo student without a plan, e.g. "Arjun Mehta"), run
`php -S 127.0.0.1:8110 -t <site> router.php` (router + licence-skip patch: see `legacy/README.md`).
Outbound hosts are blocked in the container; the local site works offline (news falls back).

Rendering cost: ~2 min of rendering per 60 s reel (1,800 frames) → a batch of 6 reels ≈ 15 min.

## 8. Rules (must keep)

- **No flags or answers** from the CTF in any reel (only titles, topics, lesson ideas).
- Prices and counts come from the data files, not memory (₹199 offer, ₹99/₹999, 43/432).
- Real UI screens only from the local test copy; demo names only; payment QR always blurred.
- No claims the site cannot back (e.g. "certificate" only if the feature exists).
- Original music only; no copyrighted songs, logos of other brands, or real people's faces.
- Every reel: text inside safe zones, readable on a phone (min 34 px body, 64 px headlines).

## 9. Phases

| Phase | What | Output | Owner check |
|---|---|---|---|
| 0 | This plan + tooling saved in repo | `PLAN.md`, `legacy/` | ✅ approve plan, answer §11 |
| 1 ✅ | Build template + pipeline; **3 pilot reels**: 12 Firewall, 18 Wireshark, 23 Incident Response | 3 MP4 + covers + captions | approve look & length |
| 2 | Brand reels B1, B3, B4, B5 | 4 reels | approve |
| 3 | Topic reels in batches of 6 (by path): Core → Networking → Perimeter → Detection → SOC → Windows → Linux/Forensics → CTI/Infra | 43 reels over ~8 batches | spot-check each batch |
| 4 | Optional: 10 learning-path reels, 1:1 cuts | 10 reels | — |
| 5 | Posting kit: 60-day calendar (1 reel/day), captions + hashtags per reel, pinned-comment links | `calendar.csv` | — |

Suggested posting order: brand reels first (B1–B5), then alternate one SOC/Windows topic (high demand)
with one Core/Networking topic; post daily at 7–9 pm IST; reuse each reel on Shorts and WhatsApp Status.

## 10. Start prompt for a new chat

> Continue the Tech Guardians reels project. Read `website-classic/marketing/reels/PLAN.md` on branch
> `claude/serene-bohr-hnex32` first and follow it. Start Phase 1: build the template and pipeline and make
> the 3 pilot reels (Firewall, Wireshark, Incident Response). My answers to §11: …

## 11. Owner decisions (answered 2026-11-13)

1. Language: **Hinglish headlines + English technical words** (Roman script on screen).
2. Voice: **human-like male Hindi voice-over** (Kokoro `hm_omega`) **with background music clearly audible** —
   music sits ~9 dB under the voice while speaking, full level between lines (`MUSIC_VOL`, default 0.75).
   Voice wording (owner, v2): learn scene says "Humare saath aap seekhenge, kaise …"; the CTA ends with
   "techguardians.in par abhi enroll karo, aur seekhna start karo!".
   CTF scene ends with "CTF access ke liye apna account zaroor bana lein" (v3) + an "Account banayein" card.
7. More animation (v2): diagonal swipe transitions, drifting binary particles + scan line, hook glitch + shake,
   cards sliding in with shine, floating book with shine, karaoke captions, confetti on "Task 1 FREE",
   the enroll button and the logo, pulsing "Abhi Enroll karo" button with tap. Synced sound effects from
   tools/sfx.py (impact, whoosh, pop, sparkle; `SFX_VOL`, default 0.45).
3. Prices: **NOT shown in reels** (no ₹ anywhere; "Task 1 FREE" stays). Post captions also have no prices.
4. Watermark: **techguardians.in** on every reel.
5. Pilots: Firewall, Wireshark, Incident Response — made.
6. File names follow the topic: `NN-Topic-Name.mp4`, `NN-Topic-Name-thumbnail.jpg`, `.srt`, `.txt`;
   each batch is delivered as one zip.

## 12. Phase 1 pipeline — how to run

```
# local site on 127.0.0.1:8110 with demo student arjun.m / Student12345 (see §7 and legacy/README.md)
export KOKORO_DIR=/path/to/kokoro-models  SITE=/path/to/website-classic   # SITE defaults to ../..
tools/build.sh 12 18 23        # -> out/NN-Name/{NN-Name.mp4, -thumbnail.jpg, .srt, .txt}
```
Steps inside build.sh: make-topics.py (topics.json from data + scripts.json) → capture.js (room page cut above
the locked box = no prices; task-1 lesson cut above "Your task" = no answers) → voice.py → timeline.py (scene
times from voice lengths, captions, post caption) → music.py (mood per path) → ffmpeg mix (sidechain ducking,
−14 LUFS) → render.js in 4 parallel slices → H.264 CRF 18 → thumbnail. ≈2.5 min per reel on 4 cores.

To add a topic: write its `hook`, `points`, `vo` (Devanagari), `sub` (Roman) and `tags` in `scripts.json`, pick
`icon` (firewall / packets / siren — add a new canvas drawing in template/topic.html for other topics), run build.sh.

## 11b. Original decision list (for reference; defaults in brackets)

1. Caption language — [Hinglish headlines + English terms], or English only, or Hindi.
2. Voice-over — [none; owner adds voice in app], or install a TTS tool.
3. Prices on screen — [yes: ₹199 handbook, ₹99/₹999 CTF].
4. Watermark/handle — [`techguardians.in` on every reel]; Instagram handle? (unknown)
5. Pilot topics — [Firewall, Wireshark, Incident Response].

## 13. Guide reels (step-by-step how-to)

`guides/<x>.json` describes the steps: title, tip, voice (Devanagari), caption (Roman), and per step the phone
screens with scroll / ring / tap / typing, timed as fractions of that step's voice clip. Screens come from
`tools/capture-<shots>.js` (local site copy; prices hidden automatically). Build:

```
SITE_DATA=<site>/api/data KOKORO_DIR=... tools/build-guide.sh guides/account.json
```
The account capture registers demo student `priya.sharma` (Priya Sharma, priya.s@example.com) in the local copy,
approves it there and shows her dashboard; the email-code request is answered locally (no mail is sent).
Remove that demo user from the local `users.json` before running it again.
