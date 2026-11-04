<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Making a safe sample PCAP (your OWN traffic only)

Capture only traffic you generate on your own test machine. Never capture a
network you don't own/administer.

## Option A — generate your own tiny capture
```bash
# 1) start a capture on your loopback/own interface
sudo tcpdump -i any -w demo.pcap &
TPID=$!
# 2) generate benign traffic YOU control
curl -s http://neverssl.com/ >/dev/null      # a deliberately HTTP test site
curl -s https://example.com/   >/dev/null      # an HTTPS test site
dig example.com >/dev/null
# 3) stop
sudo kill $TPID
```
Open `demo.pcap` in Wireshark.

## What to show in Wireshark (filters)
- `dns`            — DNS queries/responses (site names visible)
- `tcp.flags.syn==1` — TCP handshakes
- `http`           — plaintext HTTP (Follow > HTTP Stream = readable)
- `tls`            — HTTPS/TLS (Follow > TLS Stream = encrypted)

## If you can't capture
Many public, legal sample captures exist (e.g. the Wireshark SampleCaptures
wiki). Use only clearly-licensed teaching samples, and never real personal data.
Store your `demo.pcap` beside this file.

## Absolute rule
No capturing of other people's traffic, no "man-in-the-middle" against anyone.
This demo is about understanding encryption, not intercepting people.
