#!/usr/bin/env python3
"""Find potentially useful public remote automation/AI jobs and keep a local queue.

This is an opportunity finder, not an application bot. Every listing keeps its
original source URL and attribution so the user can review eligibility and apply
manually.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "opportunity_queue.json"

FEEDS = [
    ("Remotive", "https://remotive.com/feed"),
    ("We Work Remotely", "https://weworkremotely.com/remote-jobs.rss"),
]

KEYWORDS = {
    "automation": 7,
    "python": 6,
    "github actions": 6,
    "api": 5,
    "ai": 5,
    "integration": 5,
    "workflow": 5,
    "backend": 4,
    "developer": 3,
    "devops": 4,
    "data": 2,
    "content": 2,
    "social media": 3,
    "no-code": 3,
    "zapier": 4,
    "make.com": 4,
}

BEGINNER_TERMS = {
    "intern": 5,
    "internship": 5,
    "junior": 5,
    "entry level": 5,
    "entry-level": 5,
    "trainee": 4,
    "freelance": 4,
    "part-time": 3,
    "contract": 2,
}

def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Two-Takes-Opportunity-Watcher/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

def text(node, *names: str) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return re.sub(r"\s+", " ", child.text).strip()
    return ""

def parse_feed(source: str, xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    rows = []
    for item in root.findall(".//item"):
        title = text(item, "title")
        link = text(item, "link")
        description = text(item, "description", "summary")
        guid = text(item, "guid") or link or title
        if not title or not link:
            continue

        blob = f"{title} {description}".lower()
        score = sum(weight for term, weight in KEYWORDS.items() if term in blob)
        beginner_score = sum(weight for term, weight in BEGINNER_TERMS.items() if term in blob)

        # Prefer roles that look relevant to automation and don't require
        # advanced specialization, while keeping the actual listing untouched.
        total = score + beginner_score
        if score < 3:
            continue

        rows.append({
            "id": guid[:300],
            "source": source,
            "title": title[:220],
            "link": link,
            "description": re.sub(r"\s+", " ", description)[:700],
            "relevance_score": total,
            "skill_matches": [
                term for term in KEYWORDS
                if term in blob
            ][:10],
            "beginner_signal": beginner_score,
            "found_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows

def load_state() -> dict:
    if not STATE.exists():
        return {"seen": [], "items": []}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"seen": [], "items": []}
    except Exception:
        return {"seen": [], "items": []}

def save_state(data: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def notify_discord(items: list[dict]) -> None:
    webhook = __import__("os").environ.get("DISCORD_ALERTS_WEBHOOK", "").strip()
    if not webhook or not items:
        return
    lines = ["**New automation/AI opportunity matches**"]
    for item in items[:6]:
        beginner = " · possible junior/intern/freelance signal" if item["beginner_signal"] else ""
        lines.append(
            f"• **{item['title']}**{beginner}\n"
            f"  {item['source']} · {', '.join(item['skill_matches'][:5])}\n"
            f"  {item['link']}"
        )
    payload = json.dumps({"content": "\n".join(lines)[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Two-Takes-Opportunity-Watcher/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            response.read()
    except Exception as exc:
        print(f"Discord notification skipped: {exc}")

def main() -> None:
    state = load_state()
    seen = set(str(x) for x in state.get("seen", []))
    all_items = []
    for source, url in FEEDS:
        try:
            all_items.extend(parse_feed(source, fetch(url)))
        except Exception as exc:
            print(f"{source} feed skipped: {exc}")

    unique = {}
    for item in all_items:
        unique.setdefault(item["id"], item)

    items = sorted(
        unique.values(),
        key=lambda x: (x["relevance_score"], x["beginner_signal"]),
        reverse=True,
    )
    new_items = [item for item in items if item["id"] not in seen][:25]

    history = state.get("items", [])
    history = (new_items + history)[:250]
    state["items"] = history
    state["seen"] = list((seen | {x["id"] for x in items}))[-500:]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    if new_items:
        print(f"Found {len(new_items)} new opportunity matches.")
        notify_discord(new_items)
    else:
        print("No new opportunity matches.")

if __name__ == "__main__":
    main()
