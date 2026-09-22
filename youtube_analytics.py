import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from discord_notify import notify_error, notify_youtube_analytics, notify_youtube_audience

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


def analytics_get(oauth_token: str, params: dict) -> dict:
    response = requests.get(
        "https://youtubeanalytics.googleapis.com/v2/reports",
        params={**params, "access_token": oauth_token},
        timeout=(10, 30),
    )
    if not response.ok:
        raise RuntimeError(
            f"YouTube Analytics API failed: HTTP {response.status_code}: "
            f"{response.text[:900]}"
        )
    return response.json()


def query_audience_insights(oauth_token: str) -> dict:
    """
    Build an audience profile from processed YouTube Analytics data.
    Analytics data is intentionally queried over a 28-day window because
    YouTube documents that Analytics reports can lag by roughly 48-72 hours.
    """
    from datetime import timedelta

    end = (datetime.now(timezone.utc) - timedelta(days=3)).date()
    start = end - timedelta(days=27)
    start_s = start.isoformat()
    end_s = end.isoformat()

    result = {
        "window": f"{start_s} to {end_s}",
        "countries": [],
        "age_gender": [],
        "traffic_sources": [],
        "top_videos": [],
    }

    # Country: where the audience is watching from.
    country = analytics_get(oauth_token, {
        "ids": "channel==MINE",
        "startDate": start_s,
        "endDate": end_s,
        "metrics": "views,estimatedMinutesWatched",
        "dimensions": "country",
        "sort": "-views",
        "maxResults": 10,
    })
    for row in country.get("rows", [])[:10]:
        result["countries"].append({
            "country": row[0],
            "views": int(row[1] or 0),
            "minutes": round(float(row[2] or 0), 1),
        })

    # Age/gender: broad audience composition. Some channels may have
    # insufficient data, in which case the API simply returns no rows.
    try:
        ag = analytics_get(oauth_token, {
            "ids": "channel==MINE",
            "startDate": start_s,
            "endDate": end_s,
            "metrics": "viewerPercentage",
            "dimensions": "ageGroup,gender",
            "sort": "-viewerPercentage",
            "maxResults": 20,
        })
        for row in ag.get("rows", [])[:20]:
            result["age_gender"].append({
                "age_group": row[0],
                "gender": row[1],
                "viewer_percentage": round(float(row[2] or 0), 2),
            })
    except Exception as exc:
        print(f"Age/gender report unavailable: {exc}")

    # Traffic source tells us whether discovery is coming from search,
    # recommendations, browse features, external sites, etc.
    try:
        traffic = analytics_get(oauth_token, {
            "ids": "channel==MINE",
            "startDate": start_s,
            "endDate": end_s,
            "metrics": "views,estimatedMinutesWatched",
            "dimensions": "insightTrafficSourceType",
            "sort": "-views",
            "maxResults": 10,
        })
        for row in traffic.get("rows", [])[:10]:
            result["traffic_sources"].append({
                "source": row[0],
                "views": int(row[1] or 0),
                "minutes": round(float(row[2] or 0), 1),
            })
    except Exception as exc:
        print(f"Traffic-source report unavailable: {exc}")

    # Save a compact, generator-friendly audience profile.
    return result


def query_channel_deep_analytics(oauth_token: str) -> dict:
    """Return deeper channel performance from the latest processed Analytics window."""
    from datetime import timedelta

    end = (datetime.now(timezone.utc) - timedelta(days=3)).date()
    start = end - timedelta(days=27)
    start_s, end_s = start.isoformat(), end.isoformat()

    # These are core Analytics metrics documented by Google. The fallback keeps
    # the workflow working if a newer/optional metric is unavailable.
    primary_metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,comments,subscribersGained"
    )
    report = analytics_get(oauth_token, {
        "ids": "channel==MINE",
        "startDate": start_s,
        "endDate": end_s,
        "metrics": primary_metrics,
    })

    headers = [x.get("name") for x in report.get("columnHeaders", [])]
    values = report.get("rows", [])
    row = values[0] if values else []

    data = {name: row[i] for i, name in enumerate(headers) if i < len(row)}
    result = {
        "window": f"{start_s} to {end_s}",
        "views": int(float(data.get("views", 0) or 0)),
        "estimated_minutes_watched": round(float(data.get("estimatedMinutesWatched", 0) or 0), 1),
        "average_view_duration_seconds": round(float(data.get("averageViewDuration", 0) or 0), 1),
        "average_view_percentage": round(float(data.get("averageViewPercentage", 0) or 0), 2),
        "likes": int(float(data.get("likes", 0) or 0)),
        "comments": int(float(data.get("comments", 0) or 0)),
        "subscribers_gained": int(float(data.get("subscribersGained", 0) or 0)),
    }

    # Impressions/CTR availability varies by report eligibility, so treat them
    # as optional rather than making the whole analytics workflow fail.
    try:
        optional = analytics_get(oauth_token, {
            "ids": "channel==MINE",
            "startDate": start_s,
            "endDate": end_s,
            "metrics": "views,impressions,impressionsCtr",
        })
        oh = [x.get("name") for x in optional.get("columnHeaders", [])]
        ov = optional.get("rows", [])
        if ov:
            od = {name: ov[0][i] for i, name in enumerate(oh) if i < len(ov[0])}
            result["impressions"] = int(float(od.get("impressions", 0) or 0))
            result["impressions_ctr"] = round(float(od.get("impressionsCtr", 0) or 0), 2)
    except Exception as exc:
        print(f"Impressions/CTR report unavailable: {exc}")

    return result


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

    audience = None
    audience_error = ""
    try:
        audience = query_audience_insights(oauth_token)
        save(ROOT / "data" / "youtube_audience_insights.json", audience)
        notify_youtube_audience(audience, now.isoformat())
    except Exception as exc:
        audience_error = str(exc)
        print(f"Audience intelligence unavailable: {exc}")

    try:
        deep = query_channel_deep_analytics(oauth_token)
        save(ROOT / "data" / "youtube_deep_analytics.json", deep)
        print("Deep channel analytics saved.")
    except Exception as exc:
        print(f"Deep channel analytics unavailable: {exc}")

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
                "audience_insights_available": bool(audience),
                "audience_error": audience_error,
            }

            analysis["summary"] = (
                f"At about {age_hours:.1f} hours, this video has "
                f"{analysis['views']} views, {analysis['likes']} likes, and "
                f"{analysis['comments']} comments. "
                f"Like rate: {analysis['like_rate']:.2f}%. "
                "This is the early YouTube Data API snapshot."
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
