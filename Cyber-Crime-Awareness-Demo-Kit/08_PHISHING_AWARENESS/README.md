<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 08 · Phishing Awareness — Local Simulation
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

A beautiful, realistic-looking **local** login page for a **fictional** brand
("NimbuPay") that teaches people to recognise phishing — and then reveals itself.

**Objective:** Let the audience experience how convincing a phishing page looks,
then expose the red flags, with zero risk.

**Time Required:** 6–9 minutes
**Difficulty:** Beginner
**Internet:** NOT required. 100% offline.

## Safety guarantees (by design)
- **Never transmits** anything typed (no server, no `fetch`, no form action).
- **Never stores** anything (no localStorage/cookies).
- On "Sign in", it instantly shows **"This was a simulated phishing page."**
- It then explains URL/domain/HTTPS/urgency/social-engineering red flags and
  how to protect yourself.

## How to run
```bash
# from the kit root:
./start_phishing_demo.sh          # http://127.0.0.1:8000  (localhost only)
./start_phishing_demo.sh 9000     # custom port
```
Or simply open `local_demo/index.html` directly in a browser.

## What You Need
- A browser. (Optional) the kit's `start_phishing_demo.sh`.

## Step-by-Step
1. Project the page. Let it look like a normal bank/wallet login.
2. Ask a volunteer to "log in" with a **fake** username/password (never real!).
3. Click **Sign in** → the reveal screen appears.
4. Walk through "How the attacker tricks you" and "How to protect yourself".
5. Point at the fake address bar and read the domain right-to-left together.

## What Audience Sees
A familiar-looking login, then a red "SIMULATED PHISHING PAGE" reveal with a
clear red-flag teardown.

## Presenter Script
"Imagine this link arrives by SMS: 'Your NimbuPay account will be suspended.'
You tap it, you see this. Looks fine, right? Let's log in… *(click)* …and stop.
Look what just happened. In a real attack, your password is now gone. Here's how
you could have spotted it in two seconds."

## Security Lesson
Phishing works on **emotion + a convincing lookalike**, not on technical genius.
The defence is reading the real domain and never logging in from a link.

## Prevention
See the reveal screen and `instructor_notes.md`. Core: don't log in from links,
check the real domain, enable MFA, slow down.

## Questions to Ask
- "What's the REAL domain in that address bar?"
- "What made it feel urgent?"
- "Where should you have gone to log in instead?"

## Safety Warning
Tell the volunteer to type a **fake** password — never a real one. The page
can't capture it anyway, but this builds the right habit. **AUTHORISED
DEMONSTRATION ONLY.**
