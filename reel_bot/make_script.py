"""Turn news headlines into a 5-slide reel script (Claude, with template fallback)."""
import json
import os

from config import CLAUDE_MODEL

SCHEMA = {
    "type": "object",
    "properties": {
        "scam_name": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "screen_text": {"type": "string"},
                    "voiceover_hindi": {"type": "string"},
                },
                "required": ["screen_text", "voiceover_hindi"],
                "additionalProperties": False,
            },
        },
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scam_name", "slides", "caption", "hashtags"],
    "additionalProperties": False,
}

PROMPT = """You write daily Instagram/YouTube Shorts reels for the public-awareness page
"Cyber Safe Jhunjhunu" (Tech Guardians, RJ Nehra). Audience: common people of Rajasthan,
including elders. Goal: warn people about a real, current fraud and teach them how to stay safe.

From the news items below, pick the ONE most useful/relatable fraud for common people and
write exactly 5 slides:
1. HOOK - shocking one-liner that stops scrolling (max 8 words)
2. KYA HUA - what happened in the news (facts ONLY from the items, no invented numbers/names)
3. SCAM KAISE HOTA HAI - how the trick works, 3 short points separated by " | "
4. KAISE BACHEIN - 3 short safety tips separated by " | "
5. CTA - "Report on 1930 / cybercrime.gov.in, share with family, follow Cyber Safe Jhunjhunu"

Rules:
- screen_text: Hinglish in Latin script, short (max ~25 words), easy to read on a phone.
- voiceover_hindi: natural spoken Hindi in Devanagari script, 1-3 sentences, total reel 30-45 sec.
- No victim names, no fear-mongering beyond the facts, no instructions that help commit fraud.
- caption: 2-3 lines Hinglish with emoji + mention the news source name.
- hashtags: 8-10 tags without spaces, start with #.

News items:
{news}
"""


def _with_claude(news: list[dict]) -> dict | None:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic

    client = anthropic.Anthropic()
    news_txt = "\n".join(
        f"- {n['title']} ({n['source']}): {n['summary'][:300]}" for n in news)
    resp = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": PROMPT.format(news=news_txt)}],
    )
    if resp.stop_reason != "end_turn":
        print("Claude did not finish (stop_reason=%s), using template." % resp.stop_reason)
        return None
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    return data if len(data.get("slides", [])) >= 3 else None


def _template(news: list[dict]) -> dict:
    n = news[0] if news else {"title": "Naya online fraud saamne aaya", "source": ""}
    return {
        "scam_name": "Aaj ka Scam Alert",
        "slides": [
            {"screen_text": "🚨 AAJ KA SCAM ALERT 🚨\nEk galti aur account khaali!",
             "voiceover_hindi": "सावधान! आज का स्कैम अलर्ट ज़रूर देखें।"},
            {"screen_text": "KHABAR:\n" + n["title"],
             "voiceover_hindi": "आज की खबर में एक नया ऑनलाइन फ्रॉड सामने आया है। पूरी जानकारी कैप्शन में है।"},
            {"screen_text": "SCAMMER KYA KARTE HAIN:\nCall/SMS se darate hain | Link ya OTP maangte hain | Jaldi paise bhejne ko bolte hain",
             "voiceover_hindi": "ठग डराकर या लालच देकर लिंक, ओटीपी या पैसे मांगते हैं।"},
            {"screen_text": "KAISE BACHEIN:\nOTP/PIN kabhi share na karein | Anjaan link na kholein | Police kabhi video call par arrest nahi karti",
             "voiceover_hindi": "अपना ओटीपी या पिन किसी को न बताएं, अनजान लिंक न खोलें।"},
            {"screen_text": "Fraud ho to turant 1930 par call karo\nFamily ko SHARE karo 🙏",
             "voiceover_hindi": "फ्रॉड होने पर तुरंत 1930 पर कॉल करें। इस वीडियो को अपने परिवार के साथ ज़रूर शेयर करें।"},
        ],
        "caption": f"🚨 Aaj ka Scam Alert!\n{n['title']}\nSource: {n.get('source', '')}",
        "hashtags": ["#CyberSafeJhunjhunu", "#TechGuardians", "#ScamAlert", "#CyberFraud",
                     "#CyberSafety", "#DigitalArrest", "#Jhunjhunu", "#Rajasthan", "#1930"],
    }


def make_script(news: list[dict]) -> dict:
    try:
        data = _with_claude(news)
        if data:
            return data
    except Exception as e:  # never break the daily run because of the AI step
        print("Claude step failed, using template:", e)
    return _template(news)
