<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 18 · Shodan Awareness — "The search engine for exposed devices"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Show that internet-connected devices (cameras, routers, databases,
industrial systems) are indexed and findable — and how to avoid being one.

**Time Required:** 6–8 minutes
**Difficulty:** Intermediate
**Internet:** Required. Offline fallback: screenshots in `../28_MEDIA/`.

## What You Need
- A browser and the official Shodan site (`../23_ONLINE_TOOLS/`).

## Step-by-Step
1. Explain what Shodan does: scans the internet, indexes open services/banners.
2. Search by **general category** (e.g. a device type or default-login banner) to
   show how many are publicly exposed — **as statistics**, not to access any.
3. Look up **your own** public IP / an **authorised** org IP to see what's visible.
4. Discuss why these got exposed (defaults, no firewall, port forwarding).

## What Audience Sees
Thousands of real devices left open to the internet — and the realisation their
own router/camera could be one.

## Presenter Script
"People think 'who'd find my home camera?' Shodan would — it catalogues anything
answering on the internet. The fix isn't fear; it's closing the door: change
defaults, update firmware, don't expose devices."

## Security Lesson
If a device is reachable from the internet with weak/default settings, it's
discoverable and attackable. Reduce exposure.

## Prevention
- Change **default** router/camera/IoT passwords immediately.
- Keep firmware updated.
- Don't port-forward or expose admin panels; use a VPN for remote access.
- Disable UPnP if not needed; segment IoT on a guest network.
- Check your own exposure on Shodan periodically.

## Questions to Ask
- "Who has a CCTV/router they can view from their phone? How is it secured?"
- "Did you ever change the default admin password?"

## Safety Warning
**Look, don't touch.** Never access, log into, or test a device that isn't yours
or explicitly authorised — that's illegal. Use Shodan for awareness statistics
and your own assets only. **AUTHORISED DEMONSTRATION ONLY.**
