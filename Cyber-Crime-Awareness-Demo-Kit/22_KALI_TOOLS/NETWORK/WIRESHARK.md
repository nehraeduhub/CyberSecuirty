<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Wireshark (Packet Analysis)
**TOOL PURPOSE:** Inspect network traffic to contrast plaintext (HTTP) vs
encrypted (HTTPS) — using sample/own captures.

**INSTALLATION:**
```bash
sudo apt install wireshark        # allow non-root capture if prompted
```

**OPEN/RUN:**
```bash
wireshark demo.pcap &             # open a SAMPLE/own capture
```

**WHAT TO SHOW:** DNS names, TCP handshake, a readable HTTP stream vs encrypted
TLS stream (Follow Stream).

**WHAT THE AUDIENCE LEARNS:** Why HTTPS and VPN-on-public-Wi-Fi matter (demo 19).

**SAFETY WARNING:** Use only captures of YOUR OWN test traffic or provided
samples. Never sniff others' traffic — it's illegal. AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** `../../19_NETWORK_AWARENESS/SAMPLE_PCAP_INFO/` (how to make demo.pcap).

**TROUBLESHOOTING:** No interfaces? add your user to the `wireshark` group and
re-login. For live demos, pre-make the PCAP to avoid Wi-Fi issues.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

