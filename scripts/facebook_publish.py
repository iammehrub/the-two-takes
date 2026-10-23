#!/usr/bin/env python3
"""Publish the existing Two Takes episode and matching Short to a Facebook Page.

This script reuses work/the_two_takes.mp4 and the first item in
work/shorts/shorts_manifest.json, which is the same Short selected by YouTube.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
REPORT_PATH = WORK / "facebook_publish.json"
DEFAULT_API_VERSION = "v26.0"
REQUEST_TIMEOUT = (60, 900)


class FacebookPublishError(RuntimeError):
    """A Facebook Graph API or media-upload request failed."""


def _json_response(response, action):
    try:
        data = response.json()
    except ValueError as exc:
        raise FacebookPublishError(
            f"{action} returned HTTP {response.status_code} with a non-JSON response."
        ) from exc

    if response.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        error = data.get("error", {}) if isinstance(data, dict) else {}
        if isinstance(error, dict):
            message = str(error.get("message", "Unknown Graph API error"))
            code = error.get("code")
            suffix = f" (code {code})" if code is not None else ""
        else:
            message, suffix = str(error), ""
        raise FacebookPublishError(
            f"{action} failed with HTTP {response.status_code}: {message}{suffix}"
        )

    if not isinstance(data, dict):
        raise FacebookPublishError(f"{action} returned an unexpected response.")
    return data


def _graph_url(api_version, edge):
    return f"https://graph.facebook.com/{api_version}/{edge.lstrip('/')}"


def build_full_description(info, growth_pack=None):
    growth_pack = growth_pack if isinstance(growth_pack, dict) else {}
    hook = str(growth_pack.get("hook") or "").strip()
    topic = str(info.get("topic") or "English conversation practice").strip()
    parts = [
        hook,
        "Practise natural English with Himel and Niha through a friendly conversation, useful everyday phrases, and speaking practice.",
        f"Episode topic: {topic}",
        "Question for you: Which phrase will you practise today? Share one example in the comments.",
        "#TwoTakesPodcast #LearnEnglish #EnglishLearning #EnglishConversation",
    ]
    return "\n\n".join(part for part in parts if part)[:5000]


def build_reel_description(topic, facebook_episode_url):
    topic = str(topic or "everyday English").strip()
    parts = [f"Practise one useful English idea with Himel and Niha: {topic}."]
    if facebook_episode_url:
        parts.append(f"🎧 Watch the full podcast on this Facebook Page: {facebook_episode_url}")
    else:
        parts.append("🎧 Visit this Facebook Page to watch the full podcast episode.")
    parts.append("#TwoTakesPodcast #LearnEnglish #EnglishLearning #EnglishReels")
    return "\n\n".join(parts)[:2000]


def select_matching_short(manifest_path):
    """Select the same first Short that the YouTube uploader publishes."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FacebookPublishError(f"Cannot read Shorts manifest: {exc}") from exc

    if not isinstance(manifest, list) or not manifest:
        raise FacebookPublishError("No Shorts were rendered; the Facebook Reel was skipped.")

    item = manifest[0]
    if not isinstance(item, dict) or not item.get("file"):
        raise FacebookPublishError("The first Shorts manifest entry is invalid.")

    file_path = Path(manifest_path).parent / str(item["file"])
    if not file_path.is_file():
        raise FacebookPublishError(f"The matching Short file is missing: {file_path.name}")

    try:
        duration = float(item.get("duration_seconds", 0))
    except (TypeError, ValueError):
        duration = 0
    if not 18 <= duration <= 35:
        raise FacebookPublishError(
            f"The selected Short is {duration:.1f}s; expected 18–35s to match YouTube."
        )

    return file_path, item


def publish_full_video(video_path, page_id, page_token, api_version, title, description):
    url = _graph_url(api_version, f"{page_id}/videos")
    print(f"Publishing full podcast to Facebook Page from {Path(video_path).name}...")
    with Path(video_path).open("rb") as video_file:
        response = requests.post(
            url,
            data={
                "access_token": page_token,
                "title": title[:255],
                "description": description,
                "published": "true",
            },
            files={"source": (Path(video_path).name, video_file, "video/mp4")},
            timeout=REQUEST_TIMEOUT,
        )
    data = _json_response(response, "Facebook full-video upload")
    video_id = str(data.get("id") or "").strip()
    if not video_id:
        raise FacebookPublishError("Facebook full-video upload returned no video ID.")

    permalink = ""
    try:
        check = requests.get(
            _graph_url(api_version, video_id),
            params={"fields": "permalink_url", "access_token": page_token},
            timeout=(15, 45),
        )
        check_data = _json_response(check, "Facebook full-video permalink lookup")
        permalink = str(check_data.get("permalink_url") or "").strip()
    except Exception as exc:
        # A permalink lookup failure should not erase a successful upload.
        print(f"Could not read Facebook permalink automatically: {exc}")
    if not permalink:
        permalink = f"https://www.facebook.com/{page_id}/videos/{video_id}/"

    return {
        "status": "submitted",
        "video_id": video_id,
        "permalink": permalink,
        "title": title[:255],
        "file": Path(video_path).name,
    }


def publish_reel(video_path, page_id, page_token, api_version, title, description):
    video_path = Path(video_path)
    size = video_path.stat().st_size
    edge = f"{page_id}/video_reels"

    print(f"Starting Facebook Reel upload from {video_path.name}...")
    start_response = requests.post(
        _graph_url(api_version, edge),
        data={"access_token": page_token, "upload_phase": "start"},
        timeout=(15, 60),
    )
    start_data = _json_response(start_response, "Facebook Reel upload initialization")
    video_id = str(start_data.get("video_id") or "").strip()
    upload_url = str(start_data.get("upload_url") or "").strip()
    if not video_id or not upload_url:
        raise FacebookPublishError("Facebook Reel initialization returned no video ID/upload URL.")

    with video_path.open("rb") as video_file:
        upload_response = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {page_token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "application/octet-stream",
            },
            data=video_file,
            timeout=REQUEST_TIMEOUT,
        )
    _json_response(upload_response, "Facebook Reel binary upload")

    finish_response = requests.post(
        _graph_url(api_version, edge),
        data={
            "access_token": page_token,
            "video_id": video_id,
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "title": title[:255],
            "description": description,
        },
        timeout=(30, 180),
    )
    finish_data = _json_response(finish_response, "Facebook Reel publish request")
    if finish_data.get("success") is False:
        raise FacebookPublishError("Facebook Reel publish request was not accepted.")

    return {
        "status": "submitted_processing_may_continue",
        "video_id": video_id,
        "permalink": f"https://www.facebook.com/reel/{video_id}/",
        "title": title[:255],
        "file": video_path.name,
        "note": "Meta accepted the publish request; processing/availability may take additional time.",
    }


def write_report(report):
    WORK.mkdir(parents=True, exist_ok=True)
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\nFacebook publishing report:")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip()
    page_token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    api_version = os.environ.get("FACEBOOK_GRAPH_API_VERSION", DEFAULT_API_VERSION).strip()
    if not re.fullmatch(r"v\d+\.\d+", api_version):
        api_version = DEFAULT_API_VERSION

    missing = []
    if not page_id:
        missing.append("FACEBOOK_PAGE_ID")
    if not page_token:
        missing.append("FACEBOOK_PAGE_ACCESS_TOKEN")

    if missing:
        write_report({
            "overall_status": "skipped_not_configured",
            "reason": "Missing GitHub Actions secret(s): " + ", ".join(missing),
            "full_video": {"status": "skipped"},
            "reel": {"status": "skipped"},
        })
        print("::notice::Facebook publishing is not configured yet; add the listed repository secrets to enable it.")
        return 0

    if not re.fullmatch(r"\d+", page_id):
        write_report({
            "overall_status": "configuration_error",
            "reason": "FACEBOOK_PAGE_ID should be the numeric Facebook Page ID.",
            "full_video": {"status": "skipped"},
            "reel": {"status": "skipped"},
        })
        print("::warning::FACEBOOK_PAGE_ID does not look like a numeric Page ID.")
        return 0

    video_path = WORK / "the_two_takes.mp4"
    info_path = WORK / "youtube_upload.json"
    manifest_path = WORK / "shorts" / "shorts_manifest.json"
    if not video_path.is_file() or not info_path.is_file():
        write_report({
            "overall_status": "error",
            "reason": "The finished episode or YouTube upload metadata is missing.",
            "full_video": {"status": "failed"},
            "reel": {"status": "skipped"},
        })
        print("::warning::Facebook publisher is missing the finished episode or upload metadata.")
        return 0

    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        write_report({
            "overall_status": "error",
            "reason": f"Could not read YouTube upload metadata: {exc}",
            "full_video": {"status": "failed"},
            "reel": {"status": "skipped"},
        })
        print("::warning::Facebook publisher could not read YouTube upload metadata.")
        return 0

    title = str(info.get("title") or "Two Takes Podcast").strip()
    topic = str(info.get("topic") or "English conversation practice").strip()
    try:
        growth_pack = json.loads((WORK / "growth_pack.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        growth_pack = {}
    full_description = build_full_description(info, growth_pack)
    report = {
        "overall_status": "started",
        "page_id": page_id,
        "graph_api_version": api_version,
        "full_video": {"status": "pending"},
        "reel": {"status": "pending"},
        "note": "Both uploads reuse the same media files used by YouTube; no new media is generated.",
    }

    try:
        full_result = publish_full_video(
            video_path, page_id, page_token, api_version, title, full_description
        )
        report["full_video"] = full_result
    except Exception as exc:
        report["full_video"] = {"status": "failed", "error": str(exc)[:1000]}
        report["reel"] = {
            "status": "skipped",
            "reason": "The full Facebook episode did not publish, so the Reel cannot link to it.",
        }
        report["overall_status"] = "partial_failure"
        write_report(report)
        print(f"::warning::Facebook full episode upload failed: {str(exc)[:500]}")
        return 0

    try:
        short_path, short_item = select_matching_short(manifest_path)
        short_title = str(short_item.get("title") or f"One English idea: {topic}").strip()
        reel_description = build_reel_description(topic, full_result.get("permalink", ""))
        reel_result = publish_reel(
            short_path, page_id, page_token, api_version, short_title, reel_description
        )
        report["reel"] = reel_result
        report["overall_status"] = "submitted"
    except Exception as exc:
        report["reel"] = {"status": "failed", "error": str(exc)[:1000]}
        report["overall_status"] = "partial_failure"
        print(f"::warning::Facebook Reel publishing failed: {str(exc)[:500]}")

    write_report(report)
    if report["overall_status"] == "submitted":
        print("Facebook full episode and the matching Reel were submitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
