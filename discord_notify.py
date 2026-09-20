import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests

USER_AGENT = "TwoTakesAutomation/1.0 (+GitHub Actions)"


def bd_time(value=None) -> str:
    """Return a readable Bangladesh timestamp."""
    if value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(ZoneInfo("Asia/Dhaka"))
    return dt.strftime("%d %b %Y • %I:%M %p BST")


def send_webhook(env_name: str, title: str, description: str, *, fields=None, url: str = "", footer: str = "Two Takes Automation", mention_role_id: str = "") -> bool:
    webhook = os.environ.get(env_name, "").strip()
    if not webhook:
        print(f"Discord webhook {env_name} is not configured; skipping.")
        return False
    embed = {
        "title": str(title)[:256],
        "description": str(description)[:4096],
        "fields": [
            {"name": str(name)[:256], "value": str(value)[:1024], "inline": bool(inline)}
            for name, value, inline in (fields or [])
        ],
        "footer": {"text": str(footer)[:2048]},
    }
    if url:
        embed["url"] = url
    payload = {
        "username": "Two Takes Automation",
        "content": f"<@&{mention_role_id}>" if mention_role_id else "",
        "embeds": [embed],
        "allowed_mentions": (
            {"parse": [], "roles": [mention_role_id]}
            if mention_role_id
            else {"parse": []}
        ),
    }
    try:
        response = requests.post(webhook, json=payload, headers={"User-Agent": USER_AGENT}, timeout=(10, 20))
    except requests.RequestException as exc:
        print(f"Discord request failed: {exc}")
        return False
    if response.status_code not in (200, 204):
        print(f"Discord webhook failed: HTTP {response.status_code}: {response.text[:500]}")
        return False
    return True


def notify_bangladesh_news(items: list[dict], generated_at: str) -> bool:
    fields = []
    for i, item in enumerate(items[:5], 1):
        fields.append((
            f"{i}. {item['title']}",
            f"{item.get('summary','No summary available.')}\nSource: {item.get('source','Unknown')}\n{item.get('link','')}",
            False,
        ))
    return send_webhook(
        "DISCORD_BD_NEWS_WEBHOOK",
        "🇧🇩 Bangladesh Top 5 News",
        f"Fresh stories selected from multiple Bangladesh news sources. Updated {generated_at}.",
        fields=fields,
        footer="Synapse Feed • Bangladesh",
    )


def notify_youtube(video: dict, kind: str, webhook_env: str) -> bool:
    published_bd = bd_time(video.get("published"))
    mention_role_id = os.environ.get("DISCORD_YOUTUBE_MENTION_ROLE_ID", "").strip()
    return send_webhook(
        webhook_env,
        f"🎬 YouTube {kind} Published",
        f"A new {kind.lower()} video was detected.",
        fields=[
            ("Title", video.get("title", "Untitled"), False),
            ("Published", published_bd, True),
            ("Channel", video.get("channel", "Unknown"), True),
        ],
        url=video.get("link", ""),
        footer=f"YouTube • {kind} • Bangladesh time",
        mention_role_id=mention_role_id,
    )


def notify_error(message: str, component: str) -> bool:
    return send_webhook(
        "DISCORD_ALERTS_WEBHOOK",
        "🚨 Automation Error",
        str(message)[:3500],
        fields=[("Component", component, True)],
        footer="System Alerts",
    )



def notify_youtube_analytics(analysis: dict) -> bool:
    analyzed_bd = bd_time(analysis.get("analyzed_at"))
    mention_role_id = os.environ.get("DISCORD_YOUTUBE_MENTION_ROLE_ID", "").strip()
    return send_webhook(
        "DISCORD_YOUTUBE_ANALYTICS_WEBHOOK",
        "📊 12-Hour YouTube Analysis",
        analysis.get("summary", "YouTube analytics snapshot completed."),
        fields=[
            ("Video", analysis.get("title", "Untitled"), False),
            ("Type", analysis.get("kind", "YouTube"), True),
            ("Views", str(analysis.get("views", 0)), True),
            ("Likes", str(analysis.get("likes", 0)), True),
            ("Comments", str(analysis.get("comments", 0)), True),
            ("Like rate", f"{analysis.get('like_rate', 0):.2f}%", True),
            ("Analyzed", analyzed_bd, True),
        ],
        url=analysis.get("link", ""),
        footer="YouTube • 12-Hour Analytics • Bangladesh time",
        mention_role_id=mention_role_id,
    )



def notify_youtube_audience(audience: dict, analyzed_at: str) -> bool:
    mention_role_id = os.environ.get("DISCORD_YOUTUBE_MENTION_ROLE_ID", "").strip()
    countries = audience.get("countries", [])
    traffic = audience.get("traffic_sources", [])
    age_gender = audience.get("age_gender", [])

    country_text = ", ".join(
        f"{x['country']} ({x['views']:,})" for x in countries[:5]
    ) or "Not enough processed data yet"
    traffic_text = ", ".join(
        f"{x['source']} ({x['views']:,})" for x in traffic[:5]
    ) or "Not enough processed data yet"
    age_text = ", ".join(
        f"{x['age_group']} {x['gender']} ({x['viewer_percentage']:.1f}%)"
        for x in age_gender[:5]
    ) or "Not enough data"

    return send_webhook(
        "DISCORD_YOUTUBE_ANALYTICS_WEBHOOK",
        "🎯 YouTube Audience Intelligence",
        "Processed audience data for the latest available analytics window. Use this to improve topic selection, packaging, and audience fit.",
        fields=[
            ("Top countries", country_text, False),
            ("Traffic sources", traffic_text, False),
            ("Age / gender", age_text, False),
            ("Analytics window", audience.get("window", "Unknown"), True),
            ("Analyzed", bd_time(analyzed_at), True),
        ],
        footer="YouTube • Audience Intelligence • Bangladesh time",
        mention_role_id=mention_role_id,
    )
