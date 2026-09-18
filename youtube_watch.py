import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

from discord_notify import notify_error, notify_youtube

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "youtube_state.json"


def load_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_feed(channel_id):
    response = requests.get(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        headers={"User-Agent": "TwoTakesYouTubeWatcher/1.0"},
        timeout=(10, 20),
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ns = {"yt": "http://www.youtube.com/xml/schemas/2015", "atom": "http://www.w3.org/2005/Atom"}
    videos = []
    for entry in root.findall("atom:entry", ns):
        video_id = (entry.findtext("yt:videoId", "", ns) or "").strip()
        title = (entry.findtext("atom:title", "", ns) or "").strip()
        published = (entry.findtext("atom:published", "", ns) or "").strip()
        link_node = entry.find("atom:link", ns)
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        author = entry.find("atom:author/atom:name", ns)
        channel = author.text.strip() if author is not None and author.text else ""
        if video_id and title and link:
            videos.append({"video_id": video_id, "title": title, "published": published, "link": link, "channel": channel})
    return videos


def main():
    configs = [
        ("YOUTUBE_PODCAST_CHANNEL_ID", "DISCORD_YOUTUBE_PODCAST_WEBHOOK", "Podcast"),
        ("YOUTUBE_SHORTS_CHANNEL_ID", "DISCORD_YOUTUBE_SHORTS_WEBHOOK", "Shorts"),
    ]
    state = load_state()
    seen = {str(x) for x in state.get("seen_video_ids", [])}
    initialized = bool(state.get("initialized", False))
    configured = 0

    for channel_env, webhook_env, label in configs:
        channel_id = os.environ.get(channel_env, "").strip()
        if not channel_id:
            print(f"{channel_env} is not configured; skipping {label}.")
            continue
        configured += 1
        try:
            feed = fetch_feed(channel_id)
        except Exception as exc:
            notify_error(str(exc), f"YouTube {label} watcher")
            continue

        if not initialized:
            seen.update(v["video_id"] for v in feed)
            print(f"Seeded {label} with {len(feed)} existing uploads.")
            continue

        for video in reversed(feed):
            if video["video_id"] in seen:
                continue
            if notify_youtube(video, label, webhook_env):
                seen.add(video["video_id"])
                notified_videos.append({
                    "video_id": video["video_id"],
                    "title": video["title"],
                    "published": video.get("published", ""),
                    "link": video["link"],
                    "channel": video.get("channel", label),
                    "kind": label,
                    "notified_at": datetime.now(timezone.utc).isoformat(),
                })
                print(f"Discord notified: {label} — {video['title']}")

    if configured == 0:
        raise RuntimeError("Configure at least one YouTube channel ID in repository variables.")

    state["seen_video_ids"] = list(seen)[-300:]
    state["initialized"] = True
    state["checked_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        notify_error(str(exc), "YouTube watcher")
        raise
