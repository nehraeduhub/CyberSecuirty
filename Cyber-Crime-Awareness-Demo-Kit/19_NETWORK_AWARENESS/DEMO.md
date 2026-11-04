<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 19 · Network Awareness — "Encrypted vs plaintext"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Using **sample/pre-recorded** PCAPs, show that unencrypted (HTTP)
traffic is readable while encrypted (HTTPS) is not — making the case for HTTPS,
VPNs on public Wi-Fi, and not trusting open networks.

**Time Required:** 8–10 minutes
**Difficulty:** Intermediate
**Internet:** Not required. **Kali:** Wireshark. Use provided/sample PCAPs only.

## What You Need
- Wireshark. A **sample** PCAP (see `SAMPLE_PCAP_INFO/` for how to make your own
  from your **own** test traffic). Do NOT capture others' traffic.

## Step-by-Step
1. Open a sample PCAP in Wireshark.
2. **DNS:** show a DNS query/response — the site name is visible even over HTTPS.
3. **TCP:** show the handshake (SYN/SYN-ACK/ACK) — how a connection starts.
4. **HTTP (plaintext):** "Follow HTTP Stream" → headers/content readable.
5. **HTTPS (TLS):** "Follow TLS Stream" → encrypted gibberish — content protected.
6. Contrast: on open Wi-Fi, HTTP exposes data; HTTPS protects the content.

## What Audience Sees
Readable text in an HTTP stream vs encrypted noise in a TLS stream — the value of
HTTPS made concrete.

## Presenter Script
"Imagine free airport Wi-Fi. Over plain HTTP, anyone on that network could read
what you send — like a postcard. Over HTTPS, it's a sealed envelope. Watch the
difference in these captures."

## Security Lesson
HTTPS encrypts content (not the fact you visited a site — DNS/SNI can leak that).
Public Wi-Fi is untrusted; prefer HTTPS everywhere and a VPN on open networks.

## Prevention
- Look for HTTPS; let the browser warn you about insecure pages.
- Use a trustworthy **VPN** on public Wi-Fi.
- Avoid sensitive logins on open networks.
- Keep devices patched; turn off auto-join for unknown Wi-Fi.

## Questions to Ask
- "What could someone see if your traffic were plain HTTP here?"
- "Do you log into your bank on café Wi-Fi?"

## Safety Warning
Use only PCAPs of your **own** test traffic or provided samples. **Never** sniff,
capture, or analyse other people's network traffic — that is illegal. **AUTHORISED
DEMONSTRATION ONLY.**
