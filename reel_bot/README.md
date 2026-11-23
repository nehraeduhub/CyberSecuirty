# Daily Cyber Fraud Reel Bot – Cyber Safe Jhunjhunu

Ye bot **roz subah 7:37 baje** apne aap ye kaam karta hai:

1. Google News se aaj ki cyber crime / fraud khabrein laata hai
2. Claude AI se 5-slide Hinglish script aur Hindi voiceover likhwata hai
3. Hindi awaaz (Google TTS) aur 1080×1920 vertical reel (MP4) banata hai,
   branding ke saath: Cyber Safe Jhunjhunu, Tech Guardians, RJ Nehra, 1930 helpline
4. Reel, caption aur hashtags **Google Drive folder** me upload karta hai

Output files (roz):
- `2026-11-23_Digital_Arrest_Scam.mp4`: reel
- `..._caption.txt`: Instagram/YouTube caption, hashtags aur news source links
- `..._script.json`: poori script

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

Iske baad bot roz apne aap chalega.

---

## Badlav kaise karein
- **Time badalna:** `.github/workflows/daily-reel.yml` me `cron` line. Time UTC me hota hai, IST = UTC + 5:30
- **Branding, rang, helpline:** `reel_bot/config.py`
- **News ke keywords:** `config.py` me `NEWS_QUERIES`
- **Script ka style:** `reel_bot/make_script.py` me `PROMPT`

## Apne laptop par chalana (optional)
```bash
pip install -r reel_bot/requirements.txt   # ffmpeg bhi installed hona chahiye
python reel_bot/main.py                     # reel output/ folder me banegi
rclone copy output "gdrive:Cyber Safe Jhunjhunu Reels" --exclude "_work/**"
```

## Zaroori
- Post karne se pehle reel ek baar dekh lo. AI kabhi-kabhi galti kar sakta hai, aur news ka source `_caption.txt` me diya hota hai.
- Kisi news channel ka logo ya clip use mat karo. Bot apne khud ke visuals banata hai.
