<!-- TG-BRAND -->
![Tech Guardians](../../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# Nmap (Network Discovery)
**TOOL PURPOSE:** See what hosts/services are reachable — to illustrate how
exposed services look (on YOUR OWN lab/host only).

**INSTALLATION:**
```bash
sudo apt install nmap
```

**OPEN/RUN:**
```bash
nmap -F 127.0.0.1                 # scan your OWN machine (safe)
nmap -F 192.168.56.0/24           # only YOUR OWN lab subnet
```

**WHAT TO SHOW:** Open ports/services on your own host — "this is what's visible".

**WHAT THE AUDIENCE LEARNS:** Services left open are discoverable; close/firewall
what you don't need (ties to Shodan demo 18).

**SAFETY WARNING:** Scan ONLY systems you own or are explicitly authorised to
test. Scanning others is illegal. AUTHORISED DEMONSTRATION ONLY.

**DEMO DATA:** localhost (127.0.0.1) or your own VM lab.

**TROUBLESHOOTING:** Need sudo for some scans; if nothing shows on localhost,
start a test service or scan your own VM.

---
_Tech Guardians · AUTHORISED DEMONSTRATION ONLY · Use only on your own / fictional / authorised targets._

