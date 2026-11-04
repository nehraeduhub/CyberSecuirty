<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Run as a Portable Toolkit (USB / Laptop) — Step by Step

This whole kit is **self-contained and portable**. Copy the folder
`Cyber-Crime-Awareness-Demo-Kit/` to a laptop or USB stick and run it from
anywhere — all links are relative, so nothing is tied to a fixed path.

> Most of the kit is **offline**. You only need Python for the live phishing
> web-server demo, and internet for the few "Internet Required" online lookups.

---

## A. Put it on your laptop / USB

**Step 1.** Copy the entire `Cyber-Crime-Awareness-Demo-Kit` folder to your
laptop (e.g. `Desktop`) or to a USB stick.

**Step 2.** Keep the folder intact — do **not** move files out of it. The
dashboard, logo and demos link to each other by relative paths.

That's it. There is no installer and nothing writes to your system.

---

## B. Open the dashboard (all platforms)

### Windows
- **Double-click `RUN_WINDOWS.bat`** → the Master Dashboard opens in your browser.
- Or just double-click `MASTER_DASHBOARD.html`.

### macOS
- **Double-click `RUN_MAC_LINUX.command`** (first time: right-click → Open to
  approve it), or double-click `MASTER_DASHBOARD.html`.

### Linux (incl. Kali)
```bash
cd Cyber-Crime-Awareness-Demo-Kit
./start_dashboard.sh          # or: ./RUN_MAC_LINUX.command
```
- Or just open `MASTER_DASHBOARD.html` in any browser.

From the dashboard, click any card to open that demo's step-by-step `.md`.

---

## C. Run the phishing awareness demo (local web server)

This demo serves a page on your own machine only (`127.0.0.1`). It **stores and
transmits nothing**.

### Windows
- Double-click **`start_phishing_demo.bat`** (opens the browser automatically).
- Needs Python. If missing, install from python.org and tick
  “Add Python to PATH”.

### macOS / Linux / Kali
```bash
./start_phishing_demo.sh          # http://127.0.0.1:8000
./start_phishing_demo.sh 9000     # pick another port
```

### No Python at all?
Just open `08_PHISHING_AWARENESS/local_demo/index.html` directly in a browser.
The reveal and lesson still work (the server is only for a realistic address bar).

---

## D. Check / install the optional Kali tools

Only needed for the technical demos (OSINT, ExifTool, Wireshark, APK analysis…).

```bash
./check_dependencies.sh     # safe: only reports what's installed
./install_tools.sh          # optional: installs awareness tools on Kali/Debian
```
Missing a tool? Use the **offline screenshot fallback** in `28_MEDIA/` — the
lesson still lands.

---

## E. Pre-seminar portable checklist
- [ ] Whole folder copied; opens via the launcher on the venue laptop.
- [ ] `MASTER_DASHBOARD.html` shows the Tech Guardians logo (assets present).
- [ ] Phishing demo opens locally.
- [ ] Online demos pre-loaded in browser tabs (in case Wi-Fi is slow).
- [ ] Screenshots copied from `28_MEDIA/` as offline backup.
- [ ] Signed authorisation ready (see `SAFETY_RULES.md`).

---

## What makes it portable (for the curious)
- **Relative links only** — the dashboard and every `.md` reference files inside
  the kit, never absolute paths.
- **No install required** for the core (dashboard, scripts, scam demos, handouts).
- **Launchers resolve their own location** (`%~dp0` on Windows, `$BASH_SOURCE`
  on Mac/Linux), so they work from any folder or drive letter.
- **Logo/branding travel with the kit** in `assets/`.

_Tech Guardians · Think Like a Hacker — Protect Like a Defender._
