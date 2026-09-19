import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from discord_notify import notify_error, notify_youtube_analytics

ROOT = Path(__file__).resolve().parent
WATCHER_STATE = ROOT / "data" / "youtube_state.json"
ANALYTICS_STATE = ROOT / "data" / "youtube_analytics_state.json"


def load(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def refresh_access_token() -> str:
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not client_id or not client_secret or not refresh_token:
        raise RuntimeError(
            "Missing YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, or YOUTUBE_REFRESH_TOKEN."
        )

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=(10, 30),
    )
    if not response.ok:
        raise RuntimeError(
            f"YouTube OAuth refresh failed: HTTP {response.status_code}: "
            f"{response.text[:700]}"
        )

    token = response.json().get("access_token", "")
    if not token:
        raise RuntimeError("YouTube OAuth response did not include an access token.")
    return token


def fetch_video(video_id: str, oauth_token: str) -> dict:
    params = {
        "part": "snippet,statistics",
        "id": video_id,
        "access_token": oauth_token,
    }

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params=params,
        timeout=(10, 30),
    )

    if not response.ok:
        body = response.text[:700]
        raise RuntimeError(
            f"YouTube Data API failed for {video_id}: "
            f"HTTP {response.status_code}: {body}"
        )

    items = response.json().get("items", [])
    if not items:
        raise RuntimeError(f"YouTube video {video_id} was not returned by the Data API.")

    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})

    views = int(stats.get("viewCount", 0) or 0)
    likes = int(stats.get("likeCount", 0) or 0)
    comments = int(stats.get("commentCount", 0) or 0)
    like_rate = (likes / views * 100) if views else 0.0

    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "like_rate": like_rate,
        "title": snippet.get("title") or video_id,
    }


def parse_dt(value: str):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def main() -> None:
    watcher = load(WATCHER_STATE, {})
    upload_records = {}
    upload_dir = ROOT / "data" / "youtube_uploads"
    if upload_dir.exists():
        for record_path in upload_dir.glob("*.json"):
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(record, dict) and record.get("video_id"):
                upload_records[str(record["video_id"]).strip()] = record

    # Keep legacy watcher history as a backwards-compatible source.
    for record in watcher.get("notified_videos", []):
        if isinstance(record, dict) and record.get("video_id"):
            upload_records.setdefault(str(record["video_id"]).strip(), record)
    state = load(ANALYTICS_STATE, {"processed": [], "history": []})
    processed = set(str(x) for x in state.get("processed", []))
    history = list(state.get("history", []))

    # Use the same YouTube OAuth refresh token as both upload workflows.
    # The token must have the broad YouTube account scope.
    oauth_token = refresh_access_token()

    now = datetime.now(timezone.utc)
    ready = []

    for video in upload_records.values():
        video_id = str(video.get("video_id", "")).strip()
        published = parse_dt(video.get("published", ""))
        if not video_id or not published or video_id in processed:
            continue

        age_hours = (now - published).total_seconds() / 3600
        if age_hours >= 12:
            ready.append((published, video, age_hours))

    if not ready:
        print("No YouTube uploads are ready for 12-hour analytics.")
        return

    for published, video, age_hours in sorted(ready, key=lambda x: x[0]):
        video_id = video["video_id"]

        try:
            metrics = fetch_video(video_id, oauth_token)

            analysis = {
                "analyzed_at": now.isoformat(),
                "age_hours": round(age_hours, 2),
                "video_id": video_id,
                "title": metrics["title"],
                "kind": video.get("kind", "YouTube"),
                "views": metrics["views"],
                "likes": metrics["likes"],
                "comments": metrics["comments"],
                "like_rate": metrics["like_rate"],
                "link": video.get(
                    "link",
                    f"https://www.youtube.com/watch?v={video_id}",
                ),
            }

            analysis["summary"] = (
                f"At about {age_hours:.1f} hours, this video has "
                f"{analysis['views']} views, {analysis['likes']} likes, and "
                f"{analysis['comments']} comments. "
                f"Like rate: {analysis['like_rate']:.2f}%. "
                "This is a YouTube API snapshot; it does not include "
                "watch time or retention."
            )

            if notify_youtube_analytics(analysis):
                processed.add(video_id)
                history.append(analysis)
                print(f"YouTube 12-hour analysis sent for {video_id}.")
            else:
                print(
                    f"Discord analytics notification failed for {video_id}; "
                    "will retry."
                )

        except Exception as exc:
            notify_error(str(exc), "YouTube 12-hour analytics")

    state["processed"] = list(processed)[-500:]
    state["history"] = history[-200:]
    save(ANALYTICS_STATE, state)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        notify_error(str(exc), "YouTube 12-hour analytics")
        raise
