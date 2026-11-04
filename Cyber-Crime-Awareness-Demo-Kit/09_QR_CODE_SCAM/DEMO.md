<!-- TG-BRAND -->
![Tech Guardians](../assets/tech-guardians-logo-small.png)

**Tech Guardians · Cyber Crime Awareness Live Demo Kit**  
*Rj Nehra — Master in Cyber Security · “Think Like a Hacker — Protect Like a Defender.”*

---

# 09 · QR Code Scam — "Receive money" vs "Authorise payment"
**Tech Guardians · AUTHORISED DEMONSTRATION ONLY**

**Objective:** Destroy the dangerous myth that "scanning a QR to RECEIVE money"
is safe. Show that a QR can trigger a *payment* or open a malicious link.

**Time Required:** 5–7 minutes
**Difficulty:** Beginner
**Internet:** Not required. **No real transaction is ever performed.**

## What You Need
- The sample QR images / messages in `SAMPLE_QR/` and `SAMPLE_MESSAGES/`.
- (Optional) make your own harmless demo QR with `SAMPLE_QR/make_qr.sh`.

## The core truth
> To **RECEIVE** money, you give someone your UPI ID / show YOUR QR.
> You **NEVER** scan a QR or enter a PIN to *receive* money.
> Scanning + entering a UPI PIN = **you are PAYING**, not receiving.

## Step-by-Step
1. Show the scam message: "I'll send you ₹5,000 — just scan this QR to receive it."
2. Ask the audience: "Receive or pay?" (Many say receive — that's the trap.)
3. Explain what the QR actually encodes: a **collect/pay** request.
4. Show the two mock flows side by side (`SAMPLE_MESSAGES/flows.md`).
5. Reveal: the victim who scans + enters PIN has *authorised a debit*.

## What Audience Sees
A "receive money" QR that is really a "pay money" request — the exact trick used
on sellers (OLX/Marketplace), donors and refund victims.

## Presenter Script
"Someone wants to buy your old phone online. They say 'I've sent the money, scan
this QR to confirm receipt.' You scan, your app asks for your UPI PIN, you enter
it — and ₹5,000 leaves YOUR account. You never type a PIN to RECEIVE."

## Security Lesson
A UPI PIN only ever **authorises money leaving your account**. Any QR/link that
asks for your PIN "to get money" is a scam.

## Prevention
- To receive money, only share your UPI ID / your own QR. Never scan to receive.
- Read what the app says before entering the PIN — it shows **debit** vs credit.
- Be suspicious of QR codes in emails, posters, parking meters and "refund" chats.
- Verify payment in your own bank app, not from the other person's "screenshot".

## Questions to Ask
- "When you RECEIVE a payment, does your app ask for your PIN?" (No.)
- "Who has been asked to 'scan to receive'?"

## Safety Warning
Never perform a real transaction in the demo. Use the sample/mock material only.
