"""Fetch the latest cyber-crime / fraud news from Google News RSS."""
import html
import re
import urllib.parse

import feedparser

from config import NEWS_QUERIES


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_latest(limit: int = 8) -> list[dict]:
    items, seen = [], set()
    for q in NEWS_QUERIES:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "&hl=en-IN&gl=IN&ceid=IN:en")
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = _clean(e.get("title"))
            if not title or title in seen:
                continue
            seen.add(title)
            items.append({
                "title": title,
                "summary": _clean(e.get("summary")),
                "link": e.get("link", ""),
                "source": _clean(e.get("source", {}).get("title", "")),
                "published": e.get("published", ""),
            })
    return items[:limit]


if __name__ == "__main__":
    for n in fetch_latest():
        print("-", n["title"], "|", n["source"])
