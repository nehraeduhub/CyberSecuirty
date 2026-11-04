<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 04 · Username — "One handle, many doors"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Show how reusing one username across platforms lets anyone
correlate your accounts into a single identity.

**Time Required:** 6–8 minutes
**Difficulty:** Beginner
**Internet:** Required for live checks. Offline fallback: `SCREENSHOTS/`.
**Kali tools:** Sherlock, Maigret (see `../22_KALI_TOOLS/OSINT/`).

## What You Need
- A **fictional** username from `SAMPLE_IDENTITIES/`.
- Online: WhatsMyName, Namechk, KnowEm. Kali: Sherlock / Maigret.

## Step-by-Step
1. Pick the fictional handle (e.g. `aarav_rides_demo`).
2. Online: run it through WhatsMyName / Namechk to show where it's registered.
3. Kali (optional): `sherlock aarav_rides_demo` and `maigret aarav_rides_demo`.
4. Show the list of platforms the handle exists on → one person, many profiles.

## What Audience Sees
A single username expanding into a map of accounts — gaming, social, forums.

## Presenter Script
"You picked a cool username once and reused it everywhere. Convenient — for you,
and for anyone building a picture of you. Your gaming profile reveals your age,
your fitness app reveals your route, your old forum post reveals your real name."

## Security Lesson
Username reuse is a free gift to OSINT. Unique, unlinkable handles break the
chain of correlation.

## Prevention
- Use different usernames for sensitive vs casual accounts.
- Don't let your email prefix equal your public username.
- Delete old, forgotten accounts (they leak the most).

## Questions to Ask
- "Type your main username into your head — how many sites use it?"
- "What does your oldest account still say about you?"

## Safety Warning
Run checks only on the **fictional** handle or **your own**. Never enumerate an
audience member's real accounts.
