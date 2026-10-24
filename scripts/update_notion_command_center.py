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

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
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
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=12"
    data = request_json(url, headers=github_headers(token))
    runs = data.get("workflow_runs", [])
    # Avoid showing this monitor as the most recent business workflow every 15 minutes.
    runs = [run for run in runs if run.get("path") != MONITOR_WORKFLOW_PATH]
    return runs[:4]


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


def format_status(repo: str, runs: list[dict], checked_at: str, error: str | None = None) -> tuple[str, list[dict]]:
    chunks: list[dict] = []
    header = f"AUTOMATION LIVE STATUS: Checked {checked_at} Bangladesh time. Repository: {repo}. "
    if error:
        header += f"MONITOR ERROR: {error[:500]}. Existing run data may be stale."
        chunks.append({"type": "text", "text": {"content": header[:1800]}})
        return header, chunks

    if not runs:
        header += "No recent workflow runs were returned by GitHub."
        chunks.append({"type": "text", "text": {"content": header}})
        return header, chunks

    header += "Recent GitHub Actions runs (monitor workflow excluded):"
    chunks.append({"type": "text", "text": {"content": header + "\n"}})
    for run in runs:
        title = str(run.get("display_title") or run.get("name") or run.get("path") or "Workflow")
        status = run.get("status") or "unknown"
        conclusion = run.get("conclusion") or "pending"
        branch = run.get("head_branch") or "branch unknown"
        updated = local_time(run.get("updated_at") or run.get("created_at"))
        run_url = run.get("html_url")
        number = run.get("run_number")
        line = (
            f"#{number} {title[:100]} — status: {status}; conclusion: {conclusion}; "
            f"branch: {branch}; updated: {updated}. "
        )
        chunks.append({"type": "text", "text": {"content": line}})
        if run_url and run_url.startswith("https://github.com/"):
            chunks.append({
                "type": "text",
                "text": {"content": "Open run", "link": {"url": run_url}},
            })
        chunks.append({"type": "text", "text": {"content": "\n"}})

    # Notion's rich-text content limit is per text item; keep the total compact as well.
    return "".join(
        item["text"]["content"] for item in chunks if item["type"] == "text"
    )[:1900], chunks


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

    _, chunks = format_status(repo, runs, checked_at, error_text)
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
