import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests

from discord_notify import notify_bangladesh_news, notify_error

STATE_PATH = Path(__file__).resolve().parent / "data" / "bangladesh_news_state.json"
SOURCES = (
    ("The Daily Star", "site:thedailystar.net Bangladesh when:1d"),
    ("Dhaka Tribune", "site:dhakatribune.com Bangladesh when:1d"),
    ("The Business Standard", "site:tbsnews.net Bangladesh when:1d"),
    ("UNB", "site:unb.com.bd Bangladesh when:1d"),
    ("BSS", "site:bssnews.net Bangladesh when:1d"),
)


def load_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def parse_dt(value):
    try:
        dt = parsedate_to_datetime(value)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def norm(title):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", title.lower())).strip()


def similarity(a, b):
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def fetch(query):
    url = "https://news.google.com/rss/search?" + f"q={quote_plus(query)}&hl=en-US&gl=BD&ceid=BD:en"
    response = requests.get(url, headers={"User-Agent": "TwoTakesBangladeshNews/1.0"}, timeout=(10, 20))
    response.raise_for_status()
    root = ET.fromstring(response.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=30)
    result = []
    for node in root.findall("./channel/item")[:20]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        desc = clean(node.findtext("description") or "")
        pub = (node.findtext("pubDate") or "").strip()
        source_node = node.find("source")
        source = source_node.text.strip() if source_node is not None and source_node.text else ""
        dt = parse_dt(pub)
        if title and link and dt and dt >= cutoff:
            result.append({"title": title, "link": link, "summary": desc[:420], "source": source, "published_dt": dt})
    return result


def choose(items, previous):
    candidates = []
    for item in items:
        if item["link"] in previous:
            continue
        k = norm(item["title"])
        if len(k.split()) < 4:
            continue
        if any(similarity(k, norm(x["title"])) >= 0.72 for x in candidates):
            continue
        age = max(0.0, (datetime.now(timezone.utc) - item["published_dt"]).total_seconds() / 3600)
        bonus = {"the daily star": 35, "dhaka tribune": 30, "the business standard": 30, "unb": 25, "bss": 25}.get(item["source"].lower(), 10)
        item["score"] = bonus - min(24, age)
        candidates.append(item)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:5]


def main():
    state = load_state()
    previous = set(state.get("posted_links", []))
    collected = []
    seen = set()
    for source_name, query in SOURCES:
        try:
            for item in fetch(query):
                if item["link"] in seen:
                    continue
                if not item["source"]:
                    item["source"] = source_name
                seen.add(item["link"])
                collected.append(item)
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"News source failed: {source_name}: {exc}")

    selected = choose(collected, previous)
    if len(selected) < 5:
        raise RuntimeError(f"Only {len(selected)} fresh stories passed filtering; refusing to send a fake Top 5.")

    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if not notify_bangladesh_news(selected, generated_at):
        raise RuntimeError("Bangladesh news Discord webhook is not configured or failed.")

    state["posted_links"] = list(previous | {x["link"] for x in selected})[-250:]
    state["last_sent_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        notify_error(str(exc), "Bangladesh news")
        raise
