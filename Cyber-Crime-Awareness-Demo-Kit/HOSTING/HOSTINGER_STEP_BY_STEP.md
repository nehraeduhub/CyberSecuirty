<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Host the Kit on Hostinger (Shared / Unlimited Web Hosting) — Step by Step

Your **unlimited web hosting** plan is perfect for this — the kit is all static
files, so **no VPS is needed**. These steps use Hostinger's **hPanel**.

Upload file: **`Cyber-Crime-Awareness-WEB-UPLOAD.zip`** (hardened for the web —
it excludes the password PDF and all scripts).

> You will handle **two passwords**:
> 1. **Directory password** (server-side Basic Auth) — you set this in hPanel. Strongest lock.
> 2. **Dashboard passphrase** (the kit's own login) — default `TechGuardians@1930`.

---

## Step 1 — Choose your subdomain
Pick something like **`awareness.yourdomain.com`** (replace `yourdomain.com` with
your real domain). You can also use `cyber.yourdomain.com`, `demo.yourdomain.com`, etc.

## Step 2 — Create the subdomain in hPanel
1. Log in to **hpanel.hostinger.com**.
2. Open your website → **Domains → Subdomains**.
3. In **Create a new subdomain**, type the prefix (e.g. `awareness`) → **Create**.
4. Note the **document root** it shows, usually:
   `public_html/awareness`  (or `domains/yourdomain.com/public_html/awareness`).

## Step 3 — Upload the web zip
1. Go to **Files → File Manager**.
2. Open the subdomain folder from Step 2 (e.g. `public_html/awareness`).
3. Click **Upload (↑)** → upload `Cyber-Crime-Awareness-WEB-UPLOAD.zip`.

## Step 4 — Extract into the subdomain root
1. Right-click the uploaded zip → **Extract**.
2. Extract **into the current folder** (the subdomain root).
3. **Important:** `index.html` must sit directly in the subdomain root
   (e.g. `public_html/awareness/index.html`). If extraction created a subfolder,
   open it, **select all**, and **Move** everything up one level into the root.
4. You can delete the zip afterwards.

## Step 5 — Turn on HTTPS (free SSL)
1. **Security → SSL** → ensure SSL is **active** for the subdomain (install if offered).
2. The kit's `.htaccess` already **forces HTTPS**. HTTPS is required for the
   login gate's security to work.

## Step 6 — Password-protect the folder (server-side lock) 🔒
1. **Advanced → Directory Privacy** (sometimes **Files → Directory Privacy** or
   “Password Protect Directories”).
2. Select your subdomain folder (e.g. `awareness`).
3. Set a **username** and a **strong password** → **Save/Protect**.
4. Now anyone visiting the site must pass this login **before** they even see the kit.

## Step 7 — Open and test (live!)
Visit **`https://awareness.yourdomain.com`** and check, in order:
1. **Directory password** prompt (Step 6) → enter it.
2. **Tech Guardians Secure Access** screen → enter the dashboard passphrase
   (`TechGuardians@1930`).
3. **Master Dashboard** loads with your logo.
4. Click **▶ Start Live Walkthrough** → demos present **one by one** (Next /
   Previous / Auto-play).
5. Click the **Phishing** card → the live simulation opens and reveals itself.
6. Click a few demo cards → they render as clean pages in the in-browser viewer.

If all six work, you are **live and ready to show**.

---

## The "one-by-one, like a human" experience
- **Live Walkthrough** (`walkthrough.html`) steps through the whole seminar in order:
  a progress bar, one demo per screen, **Auto-play** (advances every ~9s) or manual
  **Next/Previous**, and content that reveals section-by-section. Use arrow keys too.
- Every card on the dashboard opens in the **in-browser viewer** (`view.html`), so
  Markdown renders beautifully — no downloads, no raw text.

## Change the dashboard passphrase (recommended)
On your computer (before/after hosting), run `ACCESS_CONTROL/set_password.sh`
(or `.bat`). It updates `LOGIN.html`, `MASTER_DASHBOARD.html`, `view.html` and
`walkthrough.html`. Then **re-upload those 4 files** (or rebuild and re-upload the zip).
You can also edit them directly in File Manager if you know the new hash.

## Security notes (please read)
- The **phishing page is a safe simulation** (stores/sends nothing), but a public
  phishing-styled page can be mis-flagged. Keep **Directory Privacy ON** (Step 6)
  and the included `robots.txt` (no indexing) in place.
- The web zip **excludes** the password PDF and all scripts. Do **not** upload
  `Tech_Guardians_User_Guide.pdf` or the SECURE zip to the server.
- `.htaccess` also denies `.sh/.bat/.command/.zip` and the guide PDF as defence in depth.
- Keep the directory password and dashboard passphrase private; share only with
  authorised presenters.

## Alternative upload: FTP (optional)
hPanel → **Files → FTP Accounts** gives host/username/password. Use **FileZilla**:
connect, open the subdomain folder, and drag the extracted files in. (File Manager
is easier for most people.)

## Troubleshooting
- **Blank page / redirect loop:** make sure `index.html` is in the subdomain root
  and SSL is active.
- **Cards show raw text:** you opened a `.md` directly — use the dashboard cards
  (they route through `view.html`). On a server this always renders.
- **500 error after upload:** your host may lack a module referenced in `.htaccess`;
  it is already wrapped in `<IfModule>` guards, but if needed, rename `.htaccess`
  to test, then re-add rules one by one.
- **Walkthrough empty:** confirm `manifest.json` uploaded to the root.

_Tech Guardians · Think Like a Hacker — Protect Like a Defender._
