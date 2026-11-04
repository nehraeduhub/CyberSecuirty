<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Quick Start

## Requirements
- A laptop (Kali Linux recommended, but any Linux/Mac/Windows works for most demos).
- A web browser.
- Optional: the Kali tools listed in `../22_KALI_TOOLS/` for the technical demos.

## Three steps
```bash
cd Cyber-Crime-Awareness-Demo-Kit

# 1. See what you already have (changes nothing)
./check_dependencies.sh

# 2. Optional: install recommended awareness tools (Kali/Debian)
./install_tools.sh

# 3. Open the dashboard
./start_dashboard.sh
```

If `start_dashboard.sh` can't auto-open a browser, just double-click
`MASTER_DASHBOARD.html`.

## Run the phishing awareness demo
```bash
./start_phishing_demo.sh          # serves on http://127.0.0.1:8000 (localhost only)
./start_phishing_demo.sh 9000     # choose a different port
```
This page is a **simulation**. It never stores or transmits anything typed in.

## Your first 5-minute demo (no internet, no tools)
1. Open `../14_PASSWORD_AWARENESS/DEMO.md`.
2. Show the four sample passwords.
3. Ask the audience which they use. (Hands go up — that's the hook.)
4. Explain reuse + breach + MFA + passphrase.
Done. You've run a complete awareness demo with zero setup.

## Before a real seminar
- Test the projector with the dark dashboard (it's designed for projectors).
- Pre-load any online demos in browser tabs in case the venue Wi-Fi is slow.
- Keep `../28_MEDIA/` screenshots ready as offline fallback.

## Secure launch (locked to you)
The kit is now protected by a passphrase. Launch through the lock:
```bash
./start_secure.sh            # opens the locked login, then the dashboard
```
- Windows: double-click `RUN_WINDOWS.bat` · Mac: `RUN_MAC_LINUX.command`
- **Default passphrase:** `TechGuardians@1930` — change it immediately with
  `ACCESS_CONTROL/set_password.sh` (or `.bat`).
- For true "nobody can run it without me" protection, build the encrypted
  package: `ACCESS_CONTROL/make_secure_package.sh`. See `ACCESS_CONTROL/README.md`.

## Before every seminar
```bash
./self_test.sh               # must say: READY TO PRESENT (FAIL: 0)
```
Then follow `00_START_HERE/REHEARSAL_RUNSHEET.md`.
