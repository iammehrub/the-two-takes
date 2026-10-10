#!/usr/bin/env python3
"""Generate seven approval-only social-content drafts without an AI API."""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = Path(__file__).with_name("client_profile.example.json")
DEFAULT_OUTPUT = ROOT / "work" / "business_service_demo"
IDEAS = [
    ("Meet the business", "Introduce the business and its core offer."),
    ("Behind the scenes", "Show a real, approved glimpse of the process."),
    ("Offer spotlight", "Invite questions about the core offer."),
    ("Helpful checklist", "Share a useful way to compare or prepare."),
    ("Questions to ask", "Help customers know what to confirm before choosing."),
    ("Community question", "Invite a simple, relevant audience response."),
    ("Weekly reminder", "Remind the audience how to find out more."),
]
STATUS = "DRAFT — HUMAN APPROVAL REQUIRED"


def safe(value, fallback=""):
    return str(value).strip() if value is not None and str(value).strip() else fallback


def profile_list(data, key):
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array when provided.")
    return [str(v).strip() for v in value if str(v).strip()]


def load_profile(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Profile file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Profile is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Profile must be a JSON object.")
    required = ["business_name", "industry", "audience", "primary_offer"]
    missing = [key for key in required if not safe(data.get(key))]
    if missing:
        raise ValueError("Missing required profile fields: " + ", ".join(missing))
    profile_list(data, "brand_facts")
    profile_list(data, "avoid_claims")
    return data


def build_items(profile, start_date):
    name = safe(profile.get("business_name"))
    industry = safe(profile.get("industry"), "local business")
    location = safe(profile.get("location"))
    audience = safe(profile.get("audience"), "your community")
    offer = safe(profile.get("primary_offer"))
    channel = safe(profile.get("primary_channel"), "Social media")
    cta = safe(profile.get("call_to_action"), "Contact the business for confirmed details")
    location_phrase = f" in {location}" if location else ""
    captions = [
        f"Meet {name}{location_phrase}. We focus on {offer} for {audience}. If you are exploring {industry} options, tell us what matters most to you. {cta}.",
        f"A behind-the-scenes idea from {name}: show one real part of how we prepare or deliver {offer}. Use only a photo or video the business has approved, and explain what viewers are seeing. {cta}.",
        f"Thinking about {offer}? At {name}, we want it to be easy to ask questions before deciding. Tell us which details you would like confirmed. {cta}.",
        f"A helpful {industry} checklist: identify what you need, compare the details that matter to you, and confirm current terms before deciding. If you are part of {audience}, save this reminder. {cta}.",
        f"Before choosing a {industry} service, ask what is included, which details need confirming, and what to prepare in advance. Ask {name} about the current details of {offer}. {cta}.",
        f"Community question from {name}: when looking for {industry} options, what matters most to you—convenience, clear information, or having choices? Share your preference below. {cta}.",
        f"Planning your next {industry} visit or enquiry? Keep {name} in mind for {offer}. Check directly with the business for current availability and details before making plans. {cta}.",
    ]
    facts, avoid = profile_list(profile, "brand_facts"), profile_list(profile, "avoid_claims")
    items = []
    for i, ((theme, brief), caption) in enumerate(zip(IDEAS, captions)):
        day = start_date + timedelta(days=i)
        items.append({
            "date": day.isoformat(), "day": day.strftime("%A"), "theme": theme,
            "brief": brief, "channel": channel, "caption_draft": caption,
            "visual_direction": "Use original imagery supplied or approved by the business. Do not imply stock imagery depicts the real premises, staff, or product.",
            "tone": safe(profile.get("tone"), "clear and helpful"),
            "brand_facts_for_manual_check": facts, "claims_to_avoid": avoid,
            "review_checklist": [
                "Verify business, product, and service details with the client.",
                "Edit for the client's brand voice and chosen language.",
                "Confirm image/video rights and consent for identifiable people.",
                "Confirm calls to action, availability, prices, offers, dates, and hours.",
                "Remove unsupported claims, fake reviews, guarantees, and unapproved offers.",
            ],
            "status": STATUS,
        })
    return items


def render_markdown(profile, items, start_date):
    lines = [
        f"# 7-Day Content Draft Pack — {safe(profile.get('business_name'))}", "",
        f"- Generated: {date.today().isoformat()}",
        f"- Planned start: {start_date.isoformat()}",
        f"- Industry: {safe(profile.get('industry'))}",
        f"- Location: {safe(profile.get('location'), 'Not specified')}",
        f"- Audience: {safe(profile.get('audience'))}",
        f"- Primary offer: {safe(profile.get('primary_offer'))}",
        f"- Channel: {safe(profile.get('primary_channel'), 'Social media')}",
        "- Status: INTERNAL DRAFT PACK — NO POSTS HAVE BEEN PUBLISHED", "",
        "> Template-assisted copy, not AI research. Verify facts and edit every caption before sharing.", "",
    ]
    for i, item in enumerate(items, 1):
        lines += [
            f"## Day {i} — {item['date']} — {item['theme']}", "",
            f"**Purpose:** {item['brief']}", "",
            f"**Channel:** {item['channel']}", "",
            "**Caption draft:**", "", item["caption_draft"], "",
            f"**Visual direction:** {item['visual_direction']}", "",
            "**Client facts to check:**",
        ]
        lines += [f"- {x}" for x in item["brand_facts_for_manual_check"]] or ["- No verified facts provided; ask the client to confirm details."]
        lines += ["", "**Claims/topics to avoid:**"]
        lines += [f"- {x}" for x in item["claims_to_avoid"]] or ["- Avoid unsupported claims, invented testimonials, and guarantees."]
        lines += ["", "**Approval checklist:**"] + [f"- [ ] {x}" for x in item["review_checklist"]]
        lines += ["", f"**Status:** {item['status']}", "", "---", ""]
    lines += ["## Client feedback", "- Preferred topics:", "- Topics to avoid:", "- Approved brand phrases:", "- Required disclaimers:", "- Approval owner:", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--start-date", default=date.today().isoformat())
    args = parser.parse_args()
    try:
        start = date.fromisoformat(args.start_date)
    except ValueError as exc:
        parser.error(f"--start-date must be YYYY-MM-DD: {exc}")
    profile = load_profile(args.profile)
    items = build_items(profile, start)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pack = {
        "business": profile, "generator_mode": "template-assisted-no-api",
        "generated_on": date.today().isoformat(), "planned_start": start.isoformat(),
        "published": False, "approval_required": True, "items": items,
    }
    (out / "content_pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "content_pack.md").write_text(render_markdown(profile, items, start) + "\n", encoding="utf-8")
    print(f"Generated {len(items)} draft items for {profile['business_name']}")
    print(f"Markdown: {out / 'content_pack.md'}")
    print(f"JSON: {out / 'content_pack.json'}")
    print("Mode: template-assisted; no AI API used.")
    print("Safety: nothing was published or sent to any customer.")


if __name__ == "__main__":
    main()
