import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

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



def simplify_stories(items):
    """Rewrite selected news for English learners at approximately CEFR A2-B1."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to the Bangladesh news workflow so "
            "the Discord post can use simple A2-B1 English."
        )

    input_items = [
        {
            "id": i,
            "headline": item["title"],
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
        }
        for i, item in enumerate(items, 1)
    ]
    prompt = (
        "Rewrite these factual Bangladesh news stories for English learners at "
        "CEFR A2-B1 level. Return ONLY a valid JSON array, with exactly one object "
        "for each input id. Each object must have: id (integer), title (string), "
        "summary (string). Write a clear, short headline of 5-12 common words. "
        "Write exactly two short sentences for each summary; aim for 8-15 words "
        "per sentence. Use common everyday words, simple grammar, and active voice. "
        "Explain or replace difficult terms with common words. Keep names, places, "
        "numbers, and the main facts accurate. Do not add facts, opinions, or advice. "
        "Do not copy source labels into titles. Avoid idioms, unexplained technical "
        "terms, and long sentences. Do not omit an important fact just to make it simple.\n\n"
        "NEWS INPUT JSON:\n" + json.dumps(input_items, ensure_ascii=False)
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )
    last_error = "No response"
    for attempt in range(1, 4):
        try:
            response = requests.post(
                url,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 2200,
                        "responseMimeType": "application/json",
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
                timeout=(15, 60),
            )
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                last_error = f"Gemini HTTP {response.status_code}: {response.text[:300]}"
                print(f"Easy-English rewrite retry {attempt}/3 after temporary API error.")
                continue
            if not response.ok:
                raise RuntimeError(
                    f"Gemini easy-English rewrite failed: HTTP {response.status_code}: "
                    f"{response.text[:600]}"
                )
            data = response.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            text = "\n".join(
                part.get("text", "") for part in parts if part.get("text")
            ).strip()
            text = re.sub(r"^\s*json\s*\n", "", text, flags=re.I)
            text = re.sub(r"\s*\x60{3}\s*$", "", text).strip()
            try:
                output = json.loads(text)
            except json.JSONDecodeError:
                left, right = text.find("["), text.rfind("]")
                if left < 0 or right <= left:
                    raise RuntimeError("Gemini did not return a JSON array.")
                output = json.loads(text[left:right + 1])
            if isinstance(output, dict):
                output = output.get("stories", [])
            if not isinstance(output, list):
                raise RuntimeError("Gemini response did not contain a list of stories.")

            by_id = {
                int(row["id"]): row for row in output
                if isinstance(row, dict) and str(row.get("id", "")).isdigit()
            }
            if len(by_id) != len(items):
                raise RuntimeError(
                    f"Gemini returned {len(by_id)} of {len(items)} required story rewrites."
                )

            rewritten = []
            for i, original in enumerate(items, 1):
                row = by_id.get(i, {})
                title = clean(str(row.get("title", "")))
                summary = clean(str(row.get("summary", "")))
                if not title or not summary:
                    raise RuntimeError(f"Gemini returned an empty rewrite for story {i}.")
                copied = dict(original)
                copied["easy_title"] = title[:180]
                copied["easy_summary"] = summary[:650]
                rewritten.append(copied)
            print("Rewrote the five Bangladesh stories in simple A2-B1 English.")
            return rewritten
        except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < 3:
                print(f"Easy-English rewrite attempt {attempt}/3 failed: {last_error[:300]}")
                continue
            break

    raise RuntimeError(
        "Could not create easy-English versions of the selected news: " + last_error
    )


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

    selected = simplify_stories(selected)
    generated_at = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Dhaka")).strftime("%Y-%m-%d %H:%M BST")
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
