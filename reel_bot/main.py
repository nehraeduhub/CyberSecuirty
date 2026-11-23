"""Make one branded cyber-fraud reel and save it in the reels/ folder.

  python reel_bot/main.py                      # auto: latest news -> Claude script
  python reel_bot/main.py --script my.json     # use a ready script (no news/AI step)

Pushing the reels/ folder to GitHub triggers the "Upload reels to Google Drive" workflow.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_video import build_reel  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="JSON file with scam_name, slides, caption, hashtags")
    ap.add_argument("--out", default=os.getenv("REEL_OUT", "reels"))
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    news = []
    if args.script:
        with open(args.script, encoding="utf-8") as fh:
            script = json.load(fh)
    else:
        from fetch_news import fetch_latest
        from make_script import make_script
        news = fetch_latest()
        print(f"{len(news)} news items found")
        script = make_script(news)

    os.makedirs(args.out, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", script.get("scam_name", "Scam_Alert")).strip("_")[:40]
    base = os.path.join(args.out, f"{args.date}_{slug or 'Scam_Alert'}")

    with tempfile.TemporaryDirectory() as work:
        build_reel(script, base + ".mp4", work)

    sources = script.get("sources") or [
        f"{n['title']} ({n['source']}) {n['link']}" for n in news[:3]]
    with open(base + "_caption.txt", "w", encoding="utf-8") as fh:
        fh.write(script["caption"] + "\n\n" + " ".join(script["hashtags"]) + "\n")
        if sources:
            fh.write("\nSources:\n" + "".join(f"- {s}\n" for s in sources))
    with open(base + "_script.json", "w", encoding="utf-8") as fh:
        json.dump(script, fh, ensure_ascii=False, indent=2)
    print("Reel ready:", base + ".mp4")


if __name__ == "__main__":
    main()
