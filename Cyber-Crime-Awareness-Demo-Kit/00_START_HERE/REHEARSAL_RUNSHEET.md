<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Rehearsal Run-Sheet — test every step before you present

Run `./self_test.sh` first (expects **FAIL: 0**). Then dry-run each demo below once.
For each: the **action**, the **expected result**, and the **offline fallback** if
Wi-Fi or a tool is missing. If every row behaves as described, you are ready.

> Launch everything through the locked login: `./start_secure.sh` (or double-click
> `RUN_WINDOWS.bat` / `RUN_MAC_LINUX.command`) → enter your passphrase.

| # | Demo | Action | Expected result | Fallback |
|---|---|---|---|---|
| 🔒 | Access | Open launcher → login screen | Wrong pass = “Access denied”; right pass opens dashboard | Change pass via `ACCESS_CONTROL/set_password.sh` |
| 00 | Dashboard | Dashboard loads | TG logo in header; all cards clickable | Open `MASTER_DASHBOARD.html` |
| 08 | Phishing | `start_phishing_demo.sh` → type fake creds → Sign in | Reveal: “This was a simulated phishing page” + TG badge | Open `08_.../local_demo/index.html` |
| 02 | People | Tell `STORY.md`, assemble profile | Audience “aha” as facts combine | 100% offline already |
| 03 | Email | Enter YOUR email in Have I Been Pwned | Breach list + leaked data types | `03_.../SCREENSHOTS/` |
| 04 | Username | `sherlock <fictional>` | List of sites the handle exists on | `04_.../SCREENSHOTS/` |
| 05 | Phone | PhoneInfoga on fictional number | Region/carrier metadata | `05_.../SCREENSHOTS/` |
| 06 | Photo | `exiftool sample.jpg` → `-all=` | GPS/camera shown, then stripped clean | `06_.../METADATA_EXAMPLES/` |
| 07 | Location | Read `SAMPLE_SOCIAL_POSTS/posts.md` | Timeline of routine/absence built | Offline already |
| 09 | QR | Walk `SAMPLE_MESSAGES/flows.md` | “PIN = PAY” lands; receive≠scan | Describe flow; `make_qr.sh` optional |
| 10 | WhatsApp | Walk `MOCK_MESSAGES/chats.md` | Takeover chain + 2-step PIN fix | Offline already |
| 11 | Digital arrest | Perform `ROLEPLAY_SCRIPT.md` | Fear built, then “not a real thing” reveal | Offline already |
| 12 | UPI | Walk `MOCK_PAYMENT_SCREENS/screens.md` | Fake refund/collect exposed | Offline already |
| 13 | Fake APK | Show permission checklist / VT workflow | SMS+Accessibility+overlay = red flag | Offline story; tools optional |
| 14 | Passwords | Show `SAMPLE_PASSWORDS.txt` | Weak vs passphrase + MFA | Offline already |
| 15 | Browser | Visit BrowserLeaks / AmIUnique | Fingerprint details shown | `28_MEDIA/SCREENSHOTS/` |
| 16 | URL | Dissect `SAMPLE_URLS.txt`; scan on URLScan | Real domain found; scan verdict | `16_.../INVESTIGATION_FLOW.md` |
| 17 | Domain | `whois`/`dig`/crt.sh on YOUR domain | Subdomains/DNS exposure | Screenshots |
| 18 | Shodan | View stats / your own IP | Exposed-device concept | Screenshots |
| 19 | Network | Open sample PCAP in Wireshark | HTTP readable vs TLS encrypted | Pre-made `demo.pcap` |
| 20 | Forensics | Case 01 `.eml` headers | spf/dmarc=fail spoof markers | Offline already |

## The 60-second pre-talk ritual
1. `./self_test.sh` → see **READY TO PRESENT**.
2. Launch via `./start_secure.sh`, log in, confirm dashboard + logo.
3. Open phishing demo once; see the reveal.
4. Pre-open any online tabs (03/15/16/18) in case venue Wi-Fi is slow.
5. Copy `28_MEDIA/` screenshots to the desktop as backup.

If `self_test.sh` is green and these five steps work, nothing will surprise you
on stage.

_Tech Guardians · Think Like a Hacker — Protect Like a Defender._
