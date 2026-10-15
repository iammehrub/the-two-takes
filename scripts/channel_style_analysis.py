#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    Credentials = None
    Request = None
    build = None


def iso_to_seconds(value: str) -> int:
    if not value:
        return 0
    total = 0
    match = re.search(r"(\d+)H", value)
    if match:
        total += int(match.group(1)) * 3600
    match = re.search(r"(\d+)M", value)
    if match:
        total += int(match.group(1)) * 60
    match = re.search(r"(\d+)S", value)
    if match:
        total += int(match.group(1))
    return total


def find_channel_id(query: str) -> str:
    if query.startswith("http://") or query.startswith("https://"):
        parsed = urlparse(query)
        if "youtube.com" not in parsed.netloc:
            raise ValueError("Only YouTube URLs are supported")
        if "/@" in parsed.path:
            return parsed.path.split("/@", 1)[1]
        if "/channel/" in parsed.path:
            return parsed.path.split("/channel/", 1)[1].split("/", 1)[0]
        if parsed.query:
            qs = parse_qs(parsed.query)
            if "channel_id" in qs:
                return qs["channel_id"][0]
            if "id" in qs:
                return qs["id"][0]
        raise ValueError(f"Could not parse channel id from URL: {query}")
    return query.strip().lstrip("@")


def get_public_channel_info(channel_input: str):
    if not os.environ.get("YOUTUBE_CLIENT_ID") or not os.environ.get("YOUTUBE_CLIENT_SECRET"):
        raise RuntimeError(
            "YouTube client secrets are required to inspect the channel via the API. "
            "Add YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET to the environment or repo secrets."
        )

    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip() or os.environ.get("YOUTUBE_ANALYTICS_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        raise RuntimeError(
            "A YouTube refresh token is required for channel inspection. "
            "Add YOUTUBE_REFRESH_TOKEN or YOUTUBE_ANALYTICS_REFRESH_TOKEN to the environment or repo secrets."
        )

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    )
    creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    channel_ref = channel_input.strip()
    channel_query = channel_ref
    if not channel_ref.startswith("@") and not channel_ref.startswith("UC"):
        channel_query = f"{channel_ref}"

    search = yt.search().list(
        part="snippet",
        q=channel_query,
        type="channel",
        maxResults=1,
    ).execute()
    items = search.get("items", [])
    if not items:
        raise RuntimeError(f"No channel results found for query: {channel_query}")

    channel = items[0]
    channel_id = channel["id"]["channelId"]
    channel_snippet = channel.get("snippet", {})
    channel_name = channel_snippet.get("title") or channel_ref

    channel_detail = yt.channels().list(
        part="snippet,brandingSettings,statistics",
        id=channel_id,
    ).execute()
    detail = channel_detail.get("items", [{}])[0]
    stats = detail.get("statistics", {})
    snippet = detail.get("snippet", {})
    branding = detail.get("brandingSettings", {}).get("channel", {})

    videos = yt.search().list(
        part="snippet",
        channelId=channel_id,
        type="video",
        order="date",
        maxResults=10,
    ).execute()
    video_ids = [item["id"]["videoId"] for item in videos.get("items", []) if item.get("id", {}).get("videoId")]
    video_details = {}
    if video_ids:
        info = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(video_ids)).execute()
        for item in info.get("items", []):
            vid = item.get("id")
            video_details[vid] = {
                "title": item.get("snippet", {}).get("title", ""),
                "published_at": item.get("snippet", {}).get("publishedAt", ""),
                "views": int((item.get("statistics", {}) or {}).get("viewCount", 0) or 0),
                "duration_seconds": iso_to_seconds((item.get("contentDetails", {}) or {}).get("duration", "")),
            }

    titles = [video_details.get(vid, {}).get("title", "") for vid in video_ids if video_details.get(vid, {}).get("title")]
    durations = [v.get("duration_seconds", 0) for v in video_details.values()]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    def phrase_score(text: str):
        text_l = text.lower()
        return sum(1 for p in ["english", "speaking", "conversation", "daily", "practice", "learn", "fluency", "phrases", "story", "confidence"] if p in text_l)

    top_titles = sorted(titles, key=phrase_score, reverse=True)[:5]

    return {
        "channel_id": channel_id,
        "channel_name": snippet.get("title") or channel_name,
        "description": snippet.get("description", ""),
        "custom_url": snippet.get("customUrl") or "",
        "published_at": snippet.get("publishedAt") or "",
        "view_count": int((stats.get("viewCount") or 0) or 0),
        "subscriber_count": int((stats.get("subscriberCount") or 0) or 0),
        "video_count": int((stats.get("videoCount") or 0) or 0),
        "branding": branding,
        "sample_titles": top_titles,
        "average_duration_seconds": avg_duration,
        "videos": [{"video_id": vid, **meta} for vid, meta in video_details.items()],
    }


def summarize_channel(style: dict):
    titles = [title for title in style.get("sample_titles", []) if title][:5]
    avg_seconds = float(style.get("average_duration_seconds") or 0)
    avg_minutes = round(avg_seconds / 60, 1) if avg_seconds else 0
    focus = "conversation-driven English learning with practical speaking patterns"
    if titles:
        focus = "conversation-based English learning with friendly teaching, phrases, natural dialogue, and easy practical examples"

    recommended = {
        "hook_style": "Start with a relatable problem in the first 10–15 seconds and promise a practical speaking win.",
        "format": "Friendly two-host English conversation, natural examples, phrase breakdowns, speaking practice, and a warm recap.",
        "title_model": "[main problem or phrase] + English conversation practice | natural speaking",
        "thumbnail_style": "Few words, high-contrast, one clear idea, large friendly text, clean background.",
        "length_target_minutes": avg_minutes if avg_minutes else 12,
        "content_focus": focus,
    }
    return recommended


def read_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Analyze a YouTube channel’s style signal and output a practical growth brief.")
    parser.add_argument("--channel", default="@English-leappodcast", help="Channel URL, custom URL, or channel id")
    parser.add_argument("--output", default="work/channel_style_analysis.json", help="Path for output JSON")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        info = get_public_channel_info(args.channel)
    except Exception as exc:
        print(f"Channel analysis failed: {exc}")
        output.write_text(json.dumps({"error": str(exc), "channel": args.channel, "generated_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel": args.channel,
        "style": info,
        "recommendation": summarize_channel(info),
    }
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"channel": info.get("channel_name"), "average_duration_minutes": round((info.get("average_duration_seconds") or 0) / 60, 1), "recommendation": summary["recommendation"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
