<!-- TG-BRAND -->
![Tech Guardians](assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Project Guide — Everything in One Place
**Cyber Crime Awareness Live Demo Kit · Tech Guardians · Rj Nehra (Master in Cyber Security)**
**Theme:** *Think Like a Hacker — Protect Like a Defender.*

This file answers the 8 practical questions: the tree, install, launch, how to
run each demo, and what needs internet / Kali / is fully offline, plus the safety
policy.

---

## 1. Complete project tree

```
Cyber-Crime-Awareness-Demo-Kit/
├── MASTER_DASHBOARD.html         # open this: buttons to every demo
├── README.md
├── PROJECT_GUIDE.md              # this file
├── check_dependencies.sh         # see what's installed (changes nothing)
├── install_tools.sh              # optional Kali/Debian tool install
├── start_dashboard.sh            # open the dashboard
├── start_phishing_demo.sh        # serve the local phishing simulation (127.0.0.1)
│
├── 00_START_HERE/                README, QUICK_START, DEMO_FLOW, SAFETY_RULES, CHECKLIST
├── 01_SEMINAR_GUIDE/             30/60/90-min run sheets + opening/closing/interaction
├── 02_PEOPLE_EXPOSURE/           DEMO, STORY, CHECKLIST
├── 03_EMAIL_BREACH/              DEMO + SAMPLE_DATA + SCREENSHOTS
├── 04_USERNAME_OSINT/            DEMO + SAMPLE_IDENTITIES + SCREENSHOTS
├── 05_PHONE_NUMBER/              DEMO + SAMPLE_DATA + SCREENSHOTS
├── 06_PHOTO_PRIVACY/             DEMO + SAMPLE_IMAGES + METADATA_EXAMPLES
├── 07_LOCATION_EXPOSURE/         DEMO + SAMPLE_SOCIAL_POSTS
├── 08_PHISHING_AWARENESS/        README, instructor_notes, local_demo/ (index/style/script), screenshots/
├── 09_QR_CODE_SCAM/              DEMO + SAMPLE_QR (make_qr.sh) + SAMPLE_MESSAGES
├── 10_WHATSAPP_SCAM/             DEMO, INSTRUCTOR_SCRIPT + MOCK_MESSAGES
├── 11_DIGITAL_ARREST/            STORY, ROLEPLAY_SCRIPT, RED_FLAGS + SAMPLE_NOTICE
├── 12_UPI_FRAUD/                 DEMO, SAFETY_RULES + MOCK_PAYMENT_SCREENS
├── 13_FAKE_APK/                  README, APK_ANALYSIS, PERMISSION_CHECKLIST + SAMPLE_APK_INFO
├── 14_PASSWORD_AWARENESS/        DEMO, SAMPLE_PASSWORDS.txt, PASSWORD_SAFETY
├── 15_BROWSER_PRIVACY/           DEMO, PRIVACY_CHECKLIST
├── 16_SUSPICIOUS_URL/            DEMO, SAMPLE_URLS.txt, INVESTIGATION_FLOW
├── 17_DOMAIN_OSINT/              DEMO, INVESTIGATION_CHECKLIST
├── 18_SHODAN_AWARENESS/          DEMO, SAFETY_GUIDELINES
├── 19_NETWORK_AWARENESS/         DEMO + SAMPLE_PCAP_INFO
├── 20_DIGITAL_FORENSICS/         INVESTIGATION_GUIDE + CASE_01 (phishing .eml) + CASE_02 (APK)
├── 21_INDIAN_CYBER_CRIMES/       24 scam sheets (Digital Arrest … Fake Trading App)
├── 22_KALI_TOOLS/                OSINT/ NETWORK/ WEB_SECURITY/ FORENSICS/ ANDROID_ANALYSIS/ PHISHING_AWARENESS/
├── 23_ONLINE_TOOLS/              8 categorised directories of legitimate services
├── 24_SAMPLE_DATA/               fictional emails/phones/usernames/messages/QR/docs/credentials
├── 25_INCIDENT_RESPONSE/         FIRST_15_MINUTES, FIRST_HOUR, EVIDENCE_COLLECTION, REPORTING_IN_INDIA
├── 26_HANDOUTS/                  10 rules + student/govt/senior handouts
├── 27_PRESENTATION/              SLIDE_OUTLINE, SPEAKER_NOTES, DEMO_ORDER
└── 28_MEDIA/                     SCREENSHOTS/ SAMPLE_IMAGES/ QR/ POSTER_CONTENT/
```

---

## 2. Installation commands

```bash
# Enter the kit
cd Cyber-Crime-Awareness-Demo-Kit

# See what you already have (safe, read-only)
./check_dependencies.sh

# Optional: install the beginner-friendly tools (Kali/Debian). Reviews first.
./install_tools.sh
```

Manual equivalents (only what you'll actually demo):
```bash
sudo apt install libimage-exiftool-perl nmap wireshark whatweb qrencode \
                 theharvester jadx apktool
pipx install sherlock-project maigret spiderfoot volatility3
# Larger/optional: sudo apt install zaproxy autopsy ; MobSF via Docker ;
# Gophish from getgophish.com (authorised campaigns only)
```

---

## 3. How to launch the dashboard

```bash
./start_dashboard.sh
# or simply double-click MASTER_DASHBOARD.html in a file manager
```
The dashboard is a dark, projector-friendly control panel with a button for every
demo category. It works **100% offline**.

---

## 4. How to run every demonstration

Open the dashboard and click a card, or open the folder's `DEMO.md`. Each demo
page has: Objective · Time · Difficulty · What You Need · Step-by-Step · What
Audience Sees · Presenter Script · Security Lesson · Prevention · Questions · Safety.

| # | Demo | How to run |
|---|---|---|
| 02 | People exposure | Tell `STORY.md`; assemble the profile live |
| 03 | Email breach | Enter YOUR email at HIBP/Mozilla Monitor (`DEMO.md`) |
| 04 | Username OSINT | `sherlock <fictional>` / WhatsMyName |
| 05 | Phone | PhoneInfoga metadata on a fictional number |
| 06 | Photo | `exiftool sample.jpg` → strip; reverse-search dummy |
| 07 | Location | Read `SAMPLE_SOCIAL_POSTS/posts.md`; build timeline |
| 08 | Phishing | `./start_phishing_demo.sh` → http://127.0.0.1:8000 |
| 09 | QR scam | `SAMPLE_MESSAGES/flows.md`; optional `make_qr.sh` |
| 10 | WhatsApp | Walk `MOCK_MESSAGES/chats.md` + INSTRUCTOR_SCRIPT |
| 11 | Digital arrest | Perform `ROLEPLAY_SCRIPT.md`; show fake notice |
| 12 | UPI fraud | `MOCK_PAYMENT_SCREENS/screens.md`; "PIN = PAY" |
| 13 | Fake APK | Read-only VirusTotal/MobSF/JADX/Apktool workflow |
| 14 | Passwords | Show `SAMPLE_PASSWORDS.txt`; passphrase + MFA |
| 15 | Browser privacy | Visit BrowserLeaks/AmIUnique in your browser |
| 16 | Suspicious URL | Dissect `SAMPLE_URLS.txt`; scan via URLScan |
| 17 | Domain OSINT | `whois`/`dig`/crt.sh on YOUR domain |
| 18 | Shodan | View stats / your own IP (look, don't touch) |
| 19 | Network | Open sample PCAP in Wireshark; HTTP vs TLS |
| 20 | Forensics | Case 01 `.eml` headers; Case 02 APK triage |

To run the phishing demo on a custom port: `./start_phishing_demo.sh 9000`.

---

## 5. Which demonstrations require Internet

- **03** Email breach, **15** Browser privacy, **16** URL analysis,
  **18** Shodan — need internet for the live online services.
- **04** Username, **05** Phone, **06** Photo (reverse search), **17** Domain —
  richer with internet, but have CLI/offline parts too.
- Every one of these ships an **offline screenshot fallback** (`28_MEDIA/` and each
  demo's `SCREENSHOTS/`), so the seminar never depends on venue Wi-Fi.

## 6. Which require Kali (or installed) tools

- **04** Sherlock/Maigret · **05** PhoneInfoga · **06** ExifTool ·
  **13** JADX/Apktool/MobSF · **17** whois/dig · **19** Wireshark ·
  **20** Autopsy/Volatility/ExifTool · (optional) WhatWeb/ZAP, Gophish.
- These are all **defensive / read-only OSINT / forensics** tools. If a tool is
  missing, use the screenshot fallback — the lesson still lands.

## 7. Which are completely offline (no internet, no special tools)

- **07** Location, **08** Phishing (local), **09** QR, **10** WhatsApp,
  **11** Digital arrest, **12** UPI, **14** Passwords, plus **21** crime sheets,
  **24** sample data, **25** incident response, **26** handouts, **27**
  presentation, **28** media, and the **dashboard** itself.

---

## 8. Complete safety / authorisation policy

Full text in `00_START_HERE/SAFETY_RULES.md`. Summary:

1. **Fictional / dummy / your-own / authorised data ONLY.** Never a real third
   party's accounts, devices, Wi-Fi or data.
2. **Never capture real secrets** — no real credentials, OTPs, cookies, tokens,
   card numbers or Aadhaar. The phishing page stores and transmits **nothing**.
3. **No malware** is built or shipped. APK work is **read-only analysis** of
   authorised/benign samples only.
4. **No SMS/OTP bombing, no DoS, no mass targeting, no detection-evasion.**
5. **Offensive/dual-use tools** (ZAP, Gophish, Nmap, Shodan) are used **only** on
   your own / purpose-built / explicitly authorised targets and are labelled
   **"AUTHORISED DEMONSTRATION ONLY."**
6. **Online lookups** (breach/OSINT) run only on your own data or the fictional
   samples — never on an audience member without explicit consent.
7. **Respect the law** (incl. the Indian IT Act and DPDP Act). When unsure, use
   the sample data in `24_SAMPLE_DATA/`.
8. **Purpose test:** if a demo teaches attacking rather than protecting, don't do
   it. The goal is always protection.
9. **Real victims:** don't investigate anyone's live accounts on stage — direct
   them to `25_INCIDENT_RESPONSE/` and **1930 / cybercrime.gov.in**.
10. For institutional events, keep a **signed authorisation** (checklist in
    `SAFETY_RULES.md`).

---

_Tech Guardians · Rj Nehra — Master in Cyber Security · Think Like a Hacker — Protect Like a Defender._
