<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Android Permission Checklist — "Why would THIS app need it?"

| Permission | Legit uses | Why scammers want it |
|---|---|---|
| **READ_SMS / RECEIVE_SMS** | OTP autofill (rare, store apps) | Steal banking OTPs |
| **Accessibility Service** | Assistive tech for disabilities | Read screen, auto-tap, capture input |
| **Display over other apps** | Chat heads, timers | Draw fake login/bank overlays |
| **BIND_DEVICE_ADMIN** | Enterprise MDM | Resist uninstall, lock device |
| **READ_CONTACTS** | Contact-based features | Spread scam to your contacts |
| **Install unknown apps** | App stores | Drop more malware |
| **Notification access** | Smartwatch, automation | Read OTP from notifications |
| **Call log / phone** | Dialer apps | Profile you, intercept calls |

## Danger combinations (big red flags)
- SMS + Accessibility + Overlay = classic OTP-theft / screen-hijack kit.
- Device admin + Install-unknown-apps = sticky, self-spreading malware.

## Rules for the audience
1. Install only from official stores.
2. On install, read permissions: does a torch app really need SMS?
3. Deny permissions unrelated to the app's purpose.
4. Never enable Accessibility for an app you don't fully trust.
5. Review app permissions monthly (Settings → Privacy → Permission manager).
