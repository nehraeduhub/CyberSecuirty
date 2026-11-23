"""Daily pipeline: latest fraud news -> script -> voice + video -> output/ folder.

Upload to Google Drive is done by rclone (see README / GitHub workflow).
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

from fetch_news import fetch_latest  # noqa: E402
from make_script import make_script  # noqa: E402
from make_video import build_reel  # noqa: E402


def main():
    today = dt.date.today().isoformat()
    out_dir = os.getenv("REEL_OUT", "output")
    os.makedirs(out_dir, exist_ok=True)

    news = fetch_latest()
    print(f"{len(news)} news items found")
    script = make_script(news)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", script.get("scam_name", "Scam_Alert")).strip("_")[:40]
    base = os.path.join(out_dir, f"{today}_{slug or 'Scam_Alert'}")

    build_reel(script, base + ".mp4", os.path.join(out_dir, "_work"))
    with open(base + "_caption.txt", "w", encoding="utf-8") as fh:
        fh.write(script["caption"] + "\n\n" + " ".join(script["hashtags"]) + "\n\nSources:\n")
        fh.writelines(f"- {n['title']} ({n['source']}) {n['link']}\n" for n in news[:3])
    with open(base + "_script.json", "w", encoding="utf-8") as fh:
        json.dump(script, fh, ensure_ascii=False, indent=2)
    print("Reel ready:", base + ".mp4")


if __name__ == "__main__":
    main()
