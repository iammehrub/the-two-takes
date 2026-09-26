#!/usr/bin/env python3
"""Build a lightweight performance intelligence snapshot from saved channel data."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load(name, default):
    path = DATA / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default

def main():
    history = load("youtube_analytics_state.json", {}).get("history", [])
    if not isinstance(history, list):
        history = []

    rows = [x for x in history if isinstance(x, dict)]
    def num(x, key):
        try:
            return float(x.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    views = [num(x, "views") for x in rows]
    likes = [num(x, "likes") for x in rows]
    comments = [num(x, "comments") for x in rows]

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(rows),
        "total_recorded_views": int(sum(views)),
        "average_views": round(statistics.mean(views), 1) if views else 0,
        "median_views": round(statistics.median(views), 1) if views else 0,
        "average_likes": round(statistics.mean(likes), 1) if likes else 0,
        "average_comments": round(statistics.mean(comments), 1) if comments else 0,
        "top_videos_by_views": sorted(
            [
                {
                    "video_id": x.get("video_id"),
                    "title": x.get("title"),
                    "views": int(num(x, "views")),
                    "likes": int(num(x, "likes")),
                    "comments": int(num(x, "comments")),
                }
                for x in rows
            ],
            key=lambda x: x["views"],
            reverse=True,
        )[:10],
        "note": (
            "Descriptive performance history only. Small samples can be noisy; "
            "this snapshot is intended to guide future experiments, not guarantee results."
        ),
    }

    out = DATA / "performance_intelligence.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
