#!/usr/bin/env python3
"""Generate a no-API, approval-first sample content pack for a small business."""

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = Path(__file__).with_name("client_profile.example.json")
DEFAULT_OUTPUT = ROOT / "work" / "business_service_demo"

IDEAS = [
    ("Meet the business", "Introduce what the business offers and who it serves."),
    ("Behind the scenes", "Show a real, approved glimpse of preparation or daily work."),
    ("Product spotlight", "Feature one confirmed product or service without inventing price or availability."),
    ("Helpful tip", "Share a useful tip related to the business's niche."),
    ("Frequently asked question", "Answer one question the business has verified."),
    ("Community moment", "Invite the audience to share a preference or answer a simple question."),
    ("Weekly reminder", "Remind people how to find the business or ask about current details."),
]


def slugify(value):
    value = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return value or "business"


def safe(value, fallback="Not provided"):
    text = str(value or "").strip()
    return text if text else fallback


def load_profile(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Profile must be a JSON object.")
    required = ["business_name", "industry", "audience", "primary_offer"]
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        raise ValueError("Missing required profile fields: " + ", ".join(missing))
    return data


def build_items(profile, start_date):
    name = safe(profile.get("business_name"))
    industry = safe(profile.get("industry"), "local business")
    audience = safe(profile.get("audience"), "your community")
    offer = safe(profile.get("primary_offer"), "your services")
    channel = safe(profile.get("primary_channel"), "social media")
    cta = safe(profile.get("call_to_action"), "Contact the business for confirmed details")
    tone = safe(profile.get("tone"), "clear and helpful")
    items = []

    for offset, (theme, brief) in enumerate(IDEAS):
        publish_date = start_date + timedelta(days=offset)
        caption = (
            f"{name}: a quick {industry} update for {audience}. "
            f"Today’s idea is to highlight {offer}. "
            f"{brief} {cta}."
        )
        items.append({
            "date": publish_date.isoformat(),
            "day": publish_date.strftime("%A"),
            "theme": theme,
            "channel": channel,
            "caption_draft": caption,
            "visual_direction": (
                "Use an original photo/video supplied or approved by the business; "
                "do not imply that a stock image shows the real premises or product."
            ),
            "tone": tone,
            "review_checklist": [
                "Confirm every product/service detail with the business.",
                "Check spelling, tone, and local relevance.",
                "Confirm image/video usage rights and any people shown have consented.",
                "Confirm CTA, availability, prices, and opening hours before adding them.",
            ],
            "status": "DRAFT — HUMAN APPROVAL REQUIRED",
        })
    return items


def render_markdown(profile, items, start_date):
    lines = [
        f"# 7-Day Content Draft Pack — {safe(profile.get('business_name'))}",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Planned start: {start_date.isoformat()}",
        f"- Industry: {safe(profile.get('industry'))}",
        f"- Audience: {safe(profile.get('audience'))}",
        f"- Primary channel: {safe(profile.get('primary_channel'), 'Social media')}",
        "- Status: INTERNAL DEMO — NO POSTS HAVE BEEN PUBLISHED",
        "",
        "> Review all claims, facts, visuals, and calls to action before sharing or publishing.",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines += [
            f"## Day {index} — {item['date']} — {item['theme']}",
            "",
            f"**Channel:** {item['channel']}",
            "",
            f"**Caption draft:** {item['caption_draft']}",
            "",
            f"**Visual direction:** {item['visual_direction']}",
            "",
            "**Approval checklist:**",
        ]
        lines += [f"- [ ] {check}" for check in item["review_checklist"]]
        lines += ["", f"**Status:** {item['status']}", "", "---", ""]
    lines += [
        "## Client feedback",
        "- Preferred topics:",
        "- Topics to avoid:",
        "- Approved brand phrases:",
        "- Required disclaimer or policy:",
        "- Approval owner:",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE), help="Path to a business profile JSON file")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Directory for generated draft files")
    parser.add_argument("--start-date", default=date.today().isoformat(), help="Plan start date in YYYY-MM-DD format")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    profile = load_profile(args.profile)
    items = build_items(profile, start_date)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pack = {
        "business": profile,
        "generated_on": date.today().isoformat(),
        "planned_start": start_date.isoformat(),
        "published": False,
        "approval_required": True,
        "items": items,
    }
    (out / "content_pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "content_pack.md").write_text(
        render_markdown(profile, items, start_date) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(items)} draft items for {profile['business_name']}")
    print(f"Markdown: {out / 'content_pack.md'}")
    print(f"JSON: {out / 'content_pack.json'}")
    print("Safety: nothing was published or sent to any customer.")


if __name__ == "__main__":
    main()
