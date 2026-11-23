# Cyber Fraud Reel Bot – Cyber Safe Jhunjhunu

## Flow
```
Reel banao  →  reels/ folder me GitHub par push  →  GitHub Action  →  Google Drive folder
```

Reel do tareeke se ban sakti hai:

**A. Claude Code (mobile) se:** Claude ko bolo *"aaj ki cyber fraud reel bana do"*.
Claude latest news dhundhega, script likhega, `reels/` me MP4 banakar push karega.
Push hote hi **"Upload reels to Google Drive"** workflow reel ko Drive me daal dega.

**B. Roz apne aap (GitHub Actions):** Har din subah 7:37 baje **"Daily Cyber Fraud Reel"**
workflow ye sab karta hai: Google News, Claude AI script, Hindi awaaz, reel, `reels/` me commit, aur Drive upload.

Har reel par branding: Cyber Safe Jhunjhunu ka banner (`assets/header_banner.png`),
Tech Guardians ka shield, RJ Nehra aur 1930 helpline.

Har reel ke saath 3 files banti hain (`reels/` folder aur Drive dono me):
- `2026-11-23_Digital_Arrest_Scam_Vizag.mp4`: reel
- `..._caption.txt`: caption, hashtags aur news source
- `..._script.json`: script

---

## Ek baar ka setup (lagbhag 20 minute)

### Step 1: Claude API key (script likhne ke liye)
1. https://console.anthropic.com par account banao aur billing me thode credits daalo
2. **API Keys → Create Key**, phir key copy karo
3. GitHub repo me **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `ANTHROPIC_API_KEY`
   - Value: copy ki hui key

> Key na ho to bhi bot chalega, lekin tab script ek fixed template se banegi.

### Step 2: rclone se Google Drive connect karo (apne laptop par, sirf ek baar)
1. rclone install karo: https://rclone.org/downloads/
2. CMD/Terminal me chalao: `rclone config`
3. Ye jawab do:
   - `n` (new remote), name: **gdrive**
   - Storage: **drive** (Google Drive)
   - client_id / client_secret: khali chhod do (Enter)
   - scope: **1** (full access)
   - Advanced config: **n**, auto config: **y**
4. Browser khulega. Apne Gmail se login karke **Allow** karo
5. Shared Drive: **n**, phir **y** (OK), phir **q** (quit)
6. Config file dekho: `rclone config file`. Is file ka **poora content** copy karo
7. GitHub me ek aur secret banao:
   - Name: `RCLONE_CONF`
   - Value: rclone.conf ka poora content (`[gdrive]` wali line se lekar end tak)

> Ye token aapke Drive ki chaabi hai. Ise kabhi chat, code ya kisi aur jagah share mat karna.

### Step 3: Drive folder ka naam batao
GitHub me **Settings → Secrets and variables → Actions → Variables tab → New variable**:
- Name: `DRIVE_FOLDER`
- Value: aapke Drive folder ka exact naam, jaise `Cyber Safe Jhunjhunu Reels`
  (sub-folder ho to aise likho: `Reels/Daily`)

### Step 4: Test karo
1. Repo me **Actions** tab kholo, phir **Daily Cyber Fraud Reel** chuno
2. **Run workflow** dabao
3. 3–5 minute baad Google Drive folder me nayi reel aa jaayegi ✅
4. Pehle se push hui reels bhejne ke liye: **Upload reels to Google Drive**, phir **Run workflow** dabao

Iske baad bot roz apne aap chalega.

---

## Badlav kaise karein
- **Time badalna:** `.github/workflows/daily-reel.yml` me `cron` line. Time UTC me hota hai, IST = UTC + 5:30
- **Branding, rang, helpline:** `reel_bot/config.py`, logos: `reel_bot/assets/`
- **News ke keywords:** `config.py` me `NEWS_QUERIES`
- **Script ka style:** `reel_bot/make_script.py` me `PROMPT`

## Apne laptop par chalana (optional)
```bash
pip install -r reel_bot/requirements.txt   # ffmpeg bhi installed hona chahiye
python reel_bot/main.py                     # reel reels/ folder me banegi
python reel_bot/main.py --script my.json    # apni likhi script se reel
```

## Zaroori
- Post karne se pehle reel ek baar dekh lo. AI kabhi-kabhi galti kar sakta hai, aur news ka source `_caption.txt` me diya hota hai.
- Kisi news channel ka logo ya clip use mat karo. Bot apne khud ke visuals banata hai.
- Har reel ~4 MB hai. GitHub repo 1 GB se bada na ho, isliye 2–3 mahine baad purani reels
  `reels/` se delete kar sakte ho. Drive me wo surakshit rahengi, kyunki upload sirf copy karta hai, delete nahi.
- Claude Code se bani reels me abhi Hindi awaaz nahi hoti, kyunki wahan Google TTS blocked hai.
  Instagram par post karte waqt trending music jod do. GitHub Actions wali reels me awaaz hoti hai.
