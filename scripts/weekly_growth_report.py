#!/usr/bin/env python3
"""Build a free weekly growth report from YouTube Studio video-level CSV exports.

Usage:
  python scripts/weekly_growth_report.py path/to/video_analytics.csv
Optional:
  --output weekly-growth-report.md

The script never uploads, edits, or publishes anything. CTR and first-30-second
retention are reported only when those columns exist in the export.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

ALIASES = {
    "title": ("video title", "title", "content"),
    "views": ("views",),
    "impressions": ("impressions",),
    "ctr": ("impressions click-through rate", "impressions ctr", "ctr"),
    "avg_duration": ("average view duration", "avg view duration"),
    "watch_time": ("watch time (hours)", "watch time"),
    "subs": ("subscribers", "subscribers gained", "subscribers added"),
    "retention30": ("30-second retention", "intro retention", "retention at 0:30", "0:30 retention"),
}

CATEGORIES = {
    "Real-life English": ("ordering food", "restaurant", "shopping", "job interview", "phone call",
                          "doctor", "travel", "airport", "hotel", "daily conversation", "small talk"),
    "Speaking Confidence": ("forget a word", "speak alone", "confidence", "fluency", "nervous",
                            "start a conversation", "keep speaking", "pronunciation"),
    "Vocabulary in Context": ("phrases", "vocabulary", "expressions", "common mistakes",
                              "instead of", "meaning", "words", "grammar"),
}


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def find_column(headers, aliases):
    normalized = {norm(h): h for h in headers}
    for alias in aliases:
        if norm(alias) in normalized:
            return normalized[norm(alias)]
    return None


def number(value):
    """Parse a numeric Studio field without turning missing data into zero."""
    if value is None:
        return None
    raw = str(value).strip().replace(",", "").replace("%", "")
    if not raw or raw.upper() in {"—", "-", "N/A", "NA"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def duration_seconds(value):
    """Parse Studio's H:MM:SS or M:SS average-view-duration values."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.upper() in {"—", "-", "N/A", "NA"}:
        return None
    if ":" not in raw:
        return number(raw)
    parts = raw.split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        parts = [int(part) for part in parts]
    except ValueError:
        return None
    if any(part < 0 for part in parts):
        return None
    if len(parts) == 2:
        minutes, seconds = parts
        if seconds >= 60:
            return None
        return float(minutes * 60 + seconds)
    hours, minutes, seconds = parts
    if minutes >= 60 or seconds >= 60:
        return None
    return float(hours * 3600 + minutes * 60 + seconds)


def category_for(title):
    text = norm(title)
    for category, terms in CATEGORIES.items():
        if any(term in text for term in terms):
            return category
    return "Other / Unclassified"


def load_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")
        columns = {key: find_column(reader.fieldnames, aliases) for key, aliases in ALIASES.items()}
        if not columns["title"]:
            raise ValueError("Could not find a video title column.")
        return list(reader), columns


def weighted_average(items, metric_key, weight_key):
    """Use the metric's denominator when available; fall back to a plain mean."""
    pairs = [
        (item[metric_key], item[weight_key])
        for item in items
        if item.get(metric_key) is not None
    ]
    if not pairs:
        return None
    weighted = [(value, weight) for value, weight in pairs if weight is not None and weight > 0]
    if weighted:
        denominator = sum(weight for _, weight in weighted)
        return sum(value * weight for value, weight in weighted) / denominator
    return sum(value for value, _ in pairs) / len(pairs)


def analyze(path):
    rows, columns = load_rows(path)
    videos = []
    grouped = defaultdict(list)
    for row in rows:
        title = row.get(columns["title"], "").strip()
        if not title:
            continue
        item = {"title": title, "category": category_for(title)}
        for key in ("views", "impressions", "ctr", "watch_time", "subs", "retention30"):
            col = columns[key]
            item[key] = number(row.get(col)) if col else None
        duration_col = columns["avg_duration"]
        item["avg_duration"] = duration_seconds(row.get(duration_col)) if duration_col else None
        videos.append(item)
        grouped[item["category"]].append(item)

    category_stats = []
    for name, items in grouped.items():
        category_stats.append({
            "name": name,
            "count": len(items),
            "views": sum(v["views"] or 0 for v in items),
            "impressions": sum(v["impressions"] or 0 for v in items),
            "watch_time": sum(v["watch_time"] or 0 for v in items),
            "avg_duration": weighted_average(items, "avg_duration", "views"),
            "avg_ctr": weighted_average(items, "ctr", "impressions"),
            "avg_retention30": weighted_average(items, "retention30", "views"),
            "subs": sum(v["subs"] or 0 for v in items),
        })
    category_stats.sort(key=lambda x: (x["subs"], x["views"]), reverse=True)
    return videos, category_stats, columns


def fmt(value, suffix=""):
    return "not available in this export" if value is None else f"{value:.2f}{suffix}"


def fmt_duration(seconds):
    if seconds is None:
        return "not available in this export"
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def build_report(videos, stats, columns):
    lines = [
        "# Two Takes Podcast — Weekly Growth Review", "",
        f"- Videos analyzed: **{len(videos)}**",
        "- Source: user-supplied YouTube Studio video-level CSV export",
        "- CTR is weighted by impressions; average view duration and 0:30 retention are weighted by views when denominators are available.",
        "- This report is descriptive; small samples do not prove causation.", "",
        "## Category performance", "",
        "| Category | Videos | Views | Impressions | Avg. CTR | Avg. view duration | 0:30 retention | Subscribers gained |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(
            f"| {s['name']} | {s['count']} | {s['views']:.0f} | {s['impressions']:.0f} | "
            f"{fmt(s['avg_ctr'], '%')} | {fmt_duration(s['avg_duration'])} | "
            f"{fmt(s['avg_retention30'], '%')} | {s['subs']:.0f} |"
        )
    lines += ["", "## What to inspect", ""]
    if not columns["ctr"]:
        lines.append("- **CTR unavailable:** export the video-level Impressions click-through rate column from Studio.")
    if not columns["retention30"]:
        lines.append("- **First-30-second retention unavailable:** export intro/0:30 retention data from Studio or add it manually.")
    if not columns["avg_duration"]:
        lines.append("- **Average view duration unavailable:** include that metric in the Studio export.")
    if stats:
        lines += ["", "## Provisional next-week topic directions", ""]
        for s in stats[:3]:
            if s["name"] == "Real-life English":
                idea = "A realistic conversation for a specific everyday situation"
            elif s["name"] == "Speaking Confidence":
                idea = "What to say when a learner gets stuck while speaking"
            elif s["name"] == "Vocabulary in Context":
                idea = "Useful phrases taught through a natural Himel–Niha dialogue"
            else:
                idea = "Retest this category with a clearer, more searchable learner promise"
            lines.append(f"- **{s['name']}** ({s['count']} sampled videos): {idea}.")
    lines += [
        "", "## Decision rules", "",
        "- Low CTR with reasonable impressions: test a clearer title/thumbnail promise.",
        "- Weak 0:30 retention: rewrite the cold open; show the learner problem and payoff immediately.",
        "- Good retention but low views: investigate impressions and topic demand before changing the format.",
        "- Subscriber gains: prioritize categories that repeatedly convert viewers, not one-off view spikes.",
        "- Do not compare Shorts and long-form in the same performance ranking.",
        "- Treat missing fields as unknown, never as zero.", "",
        "## Production guardrails", "",
        "- Keep the English-learning niche; do not copy another creator's scripts or branding.",
        "- Publish 5–7 long-form episodes only while quality remains stable; otherwise publish five.",
        "- Aim for 1 Short per day and 1 weekly compilation when enough coherent material exists.",
        "- These are operating targets, not growth guarantees.",
        "", "## Highest-performing sampled videos", "",
    ]
    for item in sorted(videos, key=lambda x: (x["subs"] or 0, x["views"] or 0), reverse=True)[:10]:
        views = item["views"] if item["views"] is not None else "views unknown"
        subs = item["subs"] if item["subs"] is not None else "subscriber data unavailable"
        lines.append(f"- {item['title']} — {views} views; {subs} subscribers gained.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("weekly-growth-report.md"))
    args = parser.parse_args()
    videos, stats, columns = analyze(args.csv_file)
    report = build_report(videos, stats, columns)
    args.output.write_text(report, encoding="utf-8")
    print(f"Analyzed {len(videos)} videos. Report saved to {args.output}")


if __name__ == "__main__":
    main()
