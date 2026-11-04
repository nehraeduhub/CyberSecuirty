<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Access Control — Lock the Kit to You

This gives you two layers of protection. Read both so you know exactly how strong
each one is (I will be honest, not oversell).

---

## Default passphrase (CHANGE IT before your first seminar)

```
TechGuardians@1930
```

Change it now:
- **Linux/Mac:** `./set_password.sh`
- **Windows:** double-click `set_password.bat`

Only the salted SHA-256 **hash** is stored in the files — never the passphrase
itself. If you forget it, it cannot be recovered; just set a new one.

---

## Layer 1 — Access gate (convenience lock) ✅ easy, always on

**What it is:** when anyone opens the kit through the launcher, they hit a
**locked login screen** (`LOGIN.html`). Without your passphrase, the dashboard
will not open, and opening `MASTER_DASHBOARD.html` directly just bounces back to
the login.

**How to use it:**
- **Windows:** double-click `RUN_WINDOWS.bat`
- **Mac:** double-click `RUN_MAC_LINUX.command`
- **Linux/Kali:** `./start_secure.sh`

These serve the kit on `http://127.0.0.1` (needed so the lock's crypto runs) and
open the login screen.

**Honest limit:** this stops casual and non-technical users. It does **not** stop
a determined technical person, because the demo files (HTML/Markdown) still exist
on disk — someone could open a `.md` or the raw HTML directly and read content.
For real "cannot run without permission", use Layer 2.

---

## Layer 2 — Encrypted package (strong lock) 🔐 true protection

**What it is:** the entire kit is packed into a **single AES-256 encrypted file**.
Without the password, the contents **cannot be listed, extracted, or run** — the
files simply are not readable. This is the real way to "bind" the kit to you.

**Create it:**
```bash
./make_secure_package.sh
# prefers 7-Zip (AES-256, even filenames hidden); falls back to OpenSSL
```
You get either:
- `Cyber-Crime-Awareness-Demo-Kit.SECURE.7z`, or
- `Cyber-Crime-Awareness-Demo-Kit.SECURE.tar.gz.enc`

**Distribute ONLY that encrypted file.** Share the password separately, and only
with authorised presenters.

**Unlock it to present:**
- **7z file:** open with 7-Zip and your password (or `7z x file.7z`), then run the
  launcher inside.
- **.tar.gz.enc file:** `./unlock.sh Cyber-Crime-Awareness-Demo-Kit.SECURE.tar.gz.enc`
  (decrypts to a temporary folder and launches).

**Best practice:** keep the master copy as the encrypted package. Only decrypt on
the presenting laptop, and delete the decrypted folder afterwards.

---

## Which should I use?

| Goal | Use |
|---|---|
| Quick lock so students/staff can't poke around on the seminar laptop | Layer 1 |
| Stop anyone from running/copying the kit without your password | **Layer 2** |
| Maximum safety | Keep Layer 2 as the master; unlock → present → delete |

---

## What I did NOT add (and why)

- **No hidden "phone-home", no hardware fingerprint lock, no self-deleting
  traps.** Those behave like malware, can damage a presenter's machine, and are
  not appropriate for an awareness kit used in schools and government settings.
- The honest, effective control for software you hand to people is **encryption
  with a password you control** — that is Layer 2.

---

_Tech Guardians · Keep your passphrase safe · Think Like a Hacker — Protect Like a Defender._
