#!/usr/bin/env python3
"""Update the existing Notion AI Command Center with recent GitHub Actions runs.

Required environment variables:
  NOTION_TOKEN
  GITHUB_TOKEN
  GITHUB_REPOSITORY (provided by GitHub Actions)
Optional:
  NOTION_PAGE_ID (defaults to the existing AI Command Center page)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NOTION_PAGE_ID = os.getenv(
    "NOTION_PAGE_ID", "4026d90fa42981199432cc6e5e693bcf"
)
NOTION_VERSION = "2022-06-28"
LOCAL_TZ = ZoneInfo("Asia/Dhaka")
MONITOR_WORKFLOW_PATH = ".github/workflows/notion-command-center-monitor.yml"


def request_json(url: str, *, method: str = "GET", headers: dict[str, str], payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc.reason}") from exc


def local_time(value: str | None) -> str:
    if not value:
        return "time unavailable"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value


def github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Two-Takes-Notion-Command-Center-Monitor",
    }


def notion_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "Two-Takes-Notion-Command-Center-Monitor",
    }


def recent_runs(repo: str, token: str) -> list[dict]:
    """Fetch the latest 100 workflow runs while excluding this monitor's own runs."""
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100"
    data = request_json(url, headers=github_headers(token))
    runs = data.get("workflow_runs", [])
    # Do not let the monitor create noisy self-referential entries in its own dashboard.
    return [run for run in runs if run.get("path") != MONITOR_WORKFLOW_PATH]


def run_timestamp(run: dict) -> datetime:
    """Parse a run timestamp for comparisons; missing timestamps sort to the epoch."""
    value = run.get("run_started_at") or run.get("created_at") or run.get("updated_at")
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.fromtimestamp(0, timezone.utc)


def latest_runs_by_workflow(runs: list[dict]) -> list[dict]:
    """Return one newest run per workflow file, ordered newest first."""
    latest: dict[str, dict] = {}
    for run in runs:
        key = str(
            run.get("path")
            or run.get("workflow_id")
            or run.get("name")
            or run.get("display_title")
            or "unknown-workflow"
        )
        if key not in latest or run_timestamp(run) > run_timestamp(latest[key]):
            latest[key] = run
    return sorted(latest.values(), key=run_timestamp, reverse=True)


def seven_day_run_stats(
    runs: list[dict], *, now: datetime | None = None
) -> dict[str, int]:
    """Count run outcomes in the latest seven-day window among the runs fetched."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = current - timedelta(days=7)
    stats = {"succeeded": 0, "failed": 0, "active": 0, "cancelled": 0, "other": 0}
    failure_conclusions = {"failure", "timed_out", "action_required", "startup_failure", "stale"}
    for run in runs:
        if run_timestamp(run) < cutoff:
            continue
        status = str(run.get("status") or "unknown")
        conclusion = str(run.get("conclusion") or "")
        if status != "completed":
            stats["active"] += 1
        elif conclusion == "success":
            stats["succeeded"] += 1
        elif conclusion in failure_conclusions:
            stats["failed"] += 1
        elif conclusion == "cancelled":
            stats["cancelled"] += 1
        else:
            stats["other"] += 1
    return stats


def fetch_repo_json_file(repo: str, token: str, path: str) -> object:
    """Read a committed JSON state/report file through the repository Contents API."""
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    data = request_json(
        f"https://api.github.com/repos/{repo}/contents/{encoded_path}?ref=main",
        headers=github_headers(token),
    )
    encoded = data.get("content")
    if not isinstance(encoded, str):
        raise RuntimeError(f"JSON file has no readable content: {path}")
    raw = base64.b64decode("".join(encoded.split())).decode("utf-8")
    return json.loads(raw)


def load_youtube_snapshot(repo: str, token: str) -> tuple[dict[str, object], list[str]]:
    """Read existing committed YouTube report and upload-history files; never needs OAuth scopes."""
    data: dict[str, object] = {}
    errors: list[str] = []
    for key, path in (
        ("deep", "data/youtube_deep_analytics.json"),
        ("audience", "data/youtube_audience_insights.json"),
        ("history", "data/content_history.json"),
    ):
        try:
            data[key] = fetch_repo_json_file(repo, token, path)
        except Exception:
            # Keep the command center alive if one optional saved report is missing.
            errors.append(path)
    return data, errors


def duration_label(value: object) -> str:
    """Format seconds as a compact minutes-and-seconds label."""
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError):
        return "unavailable"
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}m {remainder}s" if minutes else f"{remainder}s"


def youtube_snapshot_chunks(
    snapshot: dict[str, object], errors: list[str] | None = None
) -> list[dict]:
    """Create safe Notion rich-text chunks from saved YouTube and upload JSON."""
    chunks: list[dict] = []

    def add_text(content: str, *, bold: bool = False, url: str | None = None) -> None:
        item: dict = {"type": "text", "text": {"content": content[:1800]}}
        if url and url.startswith("https://"):
            item["text"]["link"] = {"url": url}
        if bold:
            item["annotations"] = {"bold": True}
        chunks.append(item)

    def add_line(content: str = "", *, bold: bool = False, url: str | None = None) -> None:
        add_text(content, bold=bold, url=url)
        add_text("\n")

    add_line("YOUTUBE SNAPSHOT — saved report, not real-time channel data:", bold=True)
    deep = snapshot.get("deep")
    if isinstance(deep, dict):
        window = str(deep.get("window") or "report window unavailable")
        metrics: list[str] = []
        for key, label in (
            ("views", "views"),
            ("estimated_minutes_watched", "minutes watched"),
            ("likes", "likes"),
            ("comments", "comments"),
            ("subscribers_gained", "subscribers gained"),
        ):
            value = deep.get(key)
            if value is not None:
                metrics.append(f"{label}: {value}")
        if deep.get("average_view_duration_seconds") is not None:
            metrics.append(
                "average view duration: "
                + duration_label(deep.get("average_view_duration_seconds"))
            )
        if deep.get("average_view_percentage") is not None:
            metrics.append(f"average viewed: {deep.get('average_view_percentage')}%")
        add_line(f"Reporting window {window}. " + "; ".join(metrics) + ".")
    else:
        add_line("No saved deep-analytics report was available.")

    audience = snapshot.get("audience")
    if isinstance(audience, dict):
        window = str(audience.get("window") or "saved window")
        countries = audience.get("countries") if isinstance(audience.get("countries"), list) else []
        traffic = audience.get("traffic_sources") if isinstance(audience.get("traffic_sources"), list) else []
        top_country = max(
            (item for item in countries if isinstance(item, dict)),
            key=lambda item: float(item.get("views") or 0),
            default=None,
        )
        top_source = max(
            (item for item in traffic if isinstance(item, dict)),
            key=lambda item: float(item.get("views") or 0),
            default=None,
        )
        parts = [f"Audience snapshot ({window})"]
        if top_country:
            country = str(top_country.get("country") or "unknown")
            country = "Bangladesh" if country == "BD" else country
            parts.append(f"top country: {country} ({top_country.get('views', 0)} views)")
        if top_source:
            parts.append(f"top traffic source: {top_source.get('source', 'unknown')} ({top_source.get('views', 0)} views)")
        if len(parts) > 1:
            add_line("; ".join(parts) + ".")
    else:
        add_line("Audience breakdown unavailable in the saved report.")

    history = snapshot.get("history")
    if isinstance(history, list):
        uploads = [item for item in history if isinstance(item, dict) and (item.get("video_id") or item.get("link"))]
        uploads.sort(key=lambda item: str(item.get("published") or ""), reverse=True)
        add_line("RECENT RECORDED UPLOADS:", bold=True)
        if not uploads:
            add_line("No published video records found in data/content_history.json.")
        for item in uploads[:3]:
            title = str(item.get("title") or item.get("topic") or "Untitled video")
            kind = str(item.get("kind") or "Video")
            published = str(item.get("published") or "date unavailable")[:10]
            link = item.get("link")
            video_id = str(item.get("video_id") or "")
            if not link and video_id and all(ch.isalnum() or ch in "_-" for ch in video_id):
                link = f"https://youtu.be/{video_id}"
            label = f"{kind}: {title[:95]} (published {published}) — "
            if link:
                add_text(label)
                add_text("Open video", url=str(link))
                add_text("\n")
            else:
                add_line(label + "link unavailable.")
    if errors:
        add_line("Some optional saved sources could not be read: " + ", ".join(errors[:3]) + ".")
    return chunks


def summarize_failed_jobs(jobs: list[dict]) -> list[str]:
    """Extract failed job and step names from GitHub's job metadata (not raw logs)."""
    failure_conclusions = {"failure", "timed_out", "action_required", "startup_failure", "stale"}
    summaries: list[str] = []
    for job in jobs:
        failed_steps = [
            str(step.get("name") or "Unnamed step")
            for step in (job.get("steps") or [])
            if str(step.get("conclusion") or "") in failure_conclusions
        ]
        job_conclusion = str(job.get("conclusion") or "")
        if not failed_steps and job_conclusion not in failure_conclusions:
            continue
        job_name = str(job.get("name") or "Unnamed job")
        if failed_steps:
            summaries.append(f"{job_name}: failed step(s): {', '.join(failed_steps[:3])}")
        else:
            summaries.append(f"{job_name}: job conclusion {job_conclusion}")
    return summaries


def recent_failed_run_details(
    repo: str, token: str, runs: list[dict], *, max_runs: int = 4
) -> list[dict]:
    """Read failure step metadata for a few workflows; missing details never block status updates."""
    failure_conclusions = {"failure", "timed_out", "action_required", "startup_failure", "stale"}
    candidates = [
        run for run in latest_runs_by_workflow(runs)
        if run.get("status") == "completed"
        and str(run.get("conclusion") or "") in failure_conclusions
        and run.get("id")
    ]
    results: list[dict] = []
    for run in candidates[:max_runs]:
        title = str(run.get("name") or run.get("path") or run.get("display_title") or "Workflow")
        url = run.get("html_url") if str(run.get("html_url") or "").startswith("https://github.com/") else None
        try:
            data = request_json(
                f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100",
                headers=github_headers(token),
            )
            details = summarize_failed_jobs(data.get("jobs", []))
            if not details:
                details = ["No failed job/step details were returned."]
        except Exception:
            details = ["Job/step details unavailable; open the run for details."]
        results.append({
            "number": run.get("run_number"),
            "title": title,
            "url": url,
            "details": details[:3],
        })
    return results

def notion_page_title(page: dict) -> str:
    """Return a Notion page's title across the supported title-property shapes."""
    properties = page.get("properties", {})
    for value in properties.values():
        if isinstance(value, dict) and value.get("type") == "title":
            return "".join(item.get("plain_text", "") for item in value.get("title", []))
    # Be tolerant of the standard title property name in API payloads.
    title_prop = properties.get("title", {}) if isinstance(properties, dict) else {}
    if isinstance(title_prop, dict):
        return "".join(item.get("plain_text", "") for item in title_prop.get("title", []))
    return ""


def notion_search_exact_page(token: str, title: str) -> list[dict]:
    data = request_json(
        "https://api.notion.com/v1/search",
        method="POST",
        headers=notion_headers(token),
        payload={"query": title, "page_size": 100},
    )
    return [
        item for item in data.get("results", [])
        if item.get("object") == "page" and notion_page_title(item).strip() == title
    ]


def notion_connection_identity(token: str) -> str:
    """Return safe identity metadata for diagnosing workspace/token mismatches."""
    try:
        data = request_json("https://api.notion.com/v1/users/me", headers=notion_headers(token))
        bot = data.get("bot", {}) if isinstance(data.get("bot"), dict) else {}
        name = data.get("name") or bot.get("name") or "unknown connection"
        workspace = bot.get("workspace_name") or "workspace name unavailable"
        workspace_id = bot.get("workspace_id") or "workspace ID unavailable"
        return f"connection={name!r}, workspace={workspace!r} ({workspace_id})"
    except Exception:
        return "connection identity unavailable from /v1/users/me"


def resolve_dashboard_page_id(requested_id: str, token: str) -> tuple[str, list[dict]]:
    """Verify the configured page is visible; recover only from a unique exact-title match."""
    try:
        return requested_id, get_page_blocks(requested_id, token)
    except RuntimeError as exc:
        original_error = str(exc)
        if "HTTP 404" not in original_error or "object_not_found" not in original_error:
            raise

    exact_matches = notion_search_exact_page(token, "AI Command Center")
    if len(exact_matches) == 1:
        found_id = exact_matches[0].get("id", "")
        if found_id and found_id != requested_id:
            print("Configured dashboard ID is not visible; found one exact-title dashboard visible to this token. Testing that page ID.")
            return found_id, get_page_blocks(found_id, token)
        if found_id == requested_id:
            raise RuntimeError(
                "Notion Search can see AI Command Center, but its child blocks returned 404. "
                "Check that this connection has Read content access for the page. Original error: " + original_error
            )

    if len(exact_matches) > 1:
        ids = ", ".join(str(item.get("id", "unknown")) for item in exact_matches[:5])
        raise RuntimeError(
            "The Notion token can see multiple pages titled 'AI Command Center' (IDs: " + ids + "). "
            "For safety, no page was modified. Set NOTION_PAGE_ID to the intended dashboard page ID."
        )

    setup_matches = notion_search_exact_page(token, "15-Minute Automation Setup")
    identity = notion_connection_identity(token)
    if setup_matches:
        extra = (
            " The token CAN see '15-Minute Automation Setup' but CANNOT see its parent dashboard. "
            "The connection was likely added only to the child page; add this same connection to the "
            "AI Command Center parent page itself."
        )
    else:
        extra = (
            " Search cannot see either the dashboard or its setup page. Verify that the repository secret "
            "was copied from the exact internal connection you added to the dashboard, and that this "
            "connection's Associated workspace matches the dashboard's workspace. A same-named connection "
            "in another workspace has a different token and will not grant access."
        )

    raise RuntimeError(
        "The NOTION_TOKEN is valid, but this integration cannot see the target 'AI Command Center' page. "
        "Notion returned 404 and Search did not return an accessible page with that exact title. "
        "This is a Notion connection identity/workspace/page-access mismatch, not a Python or GitHub secret problem."
        + extra + " API identity: " + identity + ". Original Notion error: " + original_error
    )


def get_page_blocks(page_id: str, token: str) -> list[dict]:
    headers = notion_headers(token)
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    all_blocks: list[dict] = []
    while url:
        page = request_json(url, headers=headers)
        all_blocks.extend(page.get("results", []))
        cursor = page.get("next_cursor")
        url = (
            f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100&start_cursor={cursor}"
            if page.get("has_more") and cursor else ""
        )
        if len(all_blocks) > 500:
            raise RuntimeError("Refusing to inspect more than 500 dashboard blocks.")
    return all_blocks


def rich_text_plain(block: dict) -> str:
    block_type = block.get("type")
    obj = block.get(block_type, {}) if block_type else {}
    return "".join(item.get("plain_text", "") for item in obj.get("rich_text", []))


def format_status(
    repo: str,
    runs: list[dict],
    checked_at: str,
    error: str | None = None,
    youtube_snapshot: dict[str, object] | None = None,
    youtube_errors: list[str] | None = None,
    failure_details: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    chunks: list[dict] = []
    header = f"AUTOMATION LIVE STATUS: Checked {checked_at} Bangladesh time. Repository: {repo}. "
    if error:
        header += f"MONITOR ERROR: {error[:400]}. Existing run data may be stale."
    else:
        stats = seven_day_run_stats(runs)
        header += (
            f" Window: latest {len(runs)} retrieved runs; last 7 days: "
            f"{stats['succeeded']} succeeded, {stats['failed']} failed, "
            f"{stats['active']} active, {stats['cancelled']} cancelled, "
            f"{stats['other']} skipped/other. Latest result per workflow:"
        )
    chunks.append({"type": "text", "text": {"content": header + "\n"}})

    if not error and runs:
        latest = latest_runs_by_workflow(runs)
        for run in latest[:18]:
            title = str(run.get("name") or run.get("path") or run.get("display_title") or "Workflow")
            status = str(run.get("status") or "unknown")
            conclusion = str(run.get("conclusion") or "pending")
            branch = str(run.get("head_branch") or "branch unknown")
            updated = local_time(run.get("updated_at") or run.get("created_at"))
            run_url = run.get("html_url")
            number = run.get("run_number")
            line = (
                f"#{number} {title[:95]} — status: {status}; conclusion: {conclusion}; "
                f"branch: {branch}; updated: {updated}. "
            )
            chunks.append({"type": "text", "text": {"content": line}})
            if run_url and run_url.startswith("https://github.com/"):
                chunks.append({
                    "type": "text",
                    "text": {"content": "Open run", "link": {"url": run_url}},
                })
            chunks.append({"type": "text", "text": {"content": "\n"}})
    elif not error:
        chunks.append({"type": "text", "text": {"content": "No recent workflow runs were returned by GitHub.\n"}})

    details = failure_details or []
    if details:
        chunks.append({"type": "text", "text": {"content": "FAILED JOB / STEP DETAILS (from GitHub metadata; not an AI diagnosis):\n"}, "annotations": {"bold": True}})
        for failure in details[:4]:
            detail_text = "; ".join(str(item) for item in failure.get("details", [])[:3])
            line = f"#{failure.get('number')} {str(failure.get('title') or 'Workflow')[:80]}: {detail_text[:700]} "
            chunks.append({"type": "text", "text": {"content": line[:900]}})
            url = failure.get("url")
            if url and str(url).startswith("https://github.com/"):
                chunks.append({"type": "text", "text": {"content": "Open failed run", "link": {"url": url}}})
            chunks.append({"type": "text", "text": {"content": "\n"}})

    chunks.extend(youtube_snapshot_chunks(youtube_snapshot or {}, youtube_errors))
    plain_preview = "".join(
        item["text"]["content"] for item in chunks if item["type"] == "text"
    )[:1900]
    return plain_preview, chunks

def update_existing_status(page_id: str, token: str, chunks: list[dict]) -> str:
    resolved_page_id, blocks = resolve_dashboard_page_id(page_id, token)
    heading_index = None
    for index, block in enumerate(blocks):
        if block.get("type") == "heading_2" and rich_text_plain(block).strip() == "AUTOMATION LIVE STATUS":
            heading_index = index
            break

    if heading_index is None:
        raise RuntimeError("Could not find the existing 'AUTOMATION LIVE STATUS' heading in the Notion page.")

    existing_statuses: list[dict] = []
    for block in blocks[heading_index + 1:]:
        # Stop once another section heading starts.
        if block.get("type") in {"heading_1", "heading_2"}:
            break
        if block.get("type") == "paragraph" and rich_text_plain(block).startswith("AUTOMATION LIVE STATUS:"):
            existing_statuses.append(block)

    if not existing_statuses:
        raise RuntimeError(
            "The status heading exists, but its status paragraph was not found. "
            "No new blocks were added to avoid altering the page structure."
        )

    api_base = "https://api.notion.com/v1"
    headers = notion_headers(token)
    status_block = existing_statuses[0]
    request_json(
        f"{api_base}/blocks/{status_block['id']}",
        method="PATCH",
        headers=headers,
        payload={"paragraph": {"rich_text": chunks}},
    )

    # Remove only duplicate monitor status lines after the canonical block was updated.
    for duplicate in existing_statuses[1:]:
        request_json(
            f"{api_base}/blocks/{duplicate['id']}",
            method="DELETE",
            headers=headers,
        )

    return resolved_page_id


def main() -> int:
    notion_token = os.getenv("NOTION_TOKEN", "").strip()
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()

    if not notion_token:
        print("NOTION_TOKEN is missing. The workflow should skip this step until configured.")
        return 2
    if not github_token or not repo:
        print("GITHUB_TOKEN or GITHUB_REPOSITORY is missing.")
        return 2

    checked_at = datetime.now(timezone.utc).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    runs: list[dict] = []
    error_text = None
    try:
        runs = recent_runs(repo, github_token)
    except Exception as exc:  # Preserve a visible monitor error if Notion is still reachable.
        error_text = str(exc)

    youtube_snapshot, youtube_errors = load_youtube_snapshot(repo, github_token)
    failure_details = recent_failed_run_details(repo, github_token, runs) if not error_text else []
    _, chunks = format_status(
        repo, runs, checked_at, error_text, youtube_snapshot, youtube_errors, failure_details
    )
    resolved_page_id = update_existing_status(NOTION_PAGE_ID, notion_token, chunks)
    if error_text:
        print(f"Updated Notion with monitor error: {error_text}")
        return 1

    print(f"Updated the existing Notion status block on page {resolved_page_id} with {len(runs)} recent GitHub Actions runs.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Notion Command Center Monitor failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
