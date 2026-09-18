import os
import requests

USER_AGENT = "TwoTakesAutomation/1.0 (+GitHub Actions)"


def send_webhook(env_name: str, title: str, description: str, *, fields=None, url: str = "", footer: str = "Two Takes Automation") -> bool:
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
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
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
    return send_webhook(
        webhook_env,
        f"🎬 YouTube {kind} Published",
        f"A new {kind.lower()} video was detected.",
        fields=[
            ("Title", video.get("title", "Untitled"), False),
            ("Published", video.get("published", "Unknown"), True),
            ("Channel", video.get("channel", "Unknown"), True),
        ],
        url=video.get("link", ""),
        footer=f"YouTube • {kind}",
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
        ],
        url=analysis.get("link", ""),
        footer="YouTube • 12-Hour Analytics",
    )
