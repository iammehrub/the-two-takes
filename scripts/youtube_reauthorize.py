#!/usr/bin/env python3
"""Create a fresh Google OAuth refresh token for the Two Takes YouTube uploader.

This script is intended to be run locally, not in GitHub Actions.
It opens Google's consent screen and prints ONLY the new refresh token.
Never paste the token into chat or commit it to the repository.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DEFAULT_CLIENT_FILE = Path("client_secret.json")


def load_client_config(client_file: Path) -> dict:
    try:
        data = json.loads(client_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"OAuth client file not found: {client_file}\n"
            "Download your Google OAuth client JSON and save it locally."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"OAuth client file is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit("OAuth client JSON must contain an object.")

    # Google client JSON normally uses either "installed" or "web".
    if "installed" in data and isinstance(data["installed"], dict):
        return {"installed": data["installed"]}
    if "web" in data and isinstance(data["web"], dict):
        return {"web": data["web"]}

    # Also support a normalized config supplied by environment variables.
    return {"installed": data}


def config_from_env() -> dict | None:
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize the Two Takes YouTube uploader and print a new refresh token."
    )
    parser.add_argument(
        "--client-file",
        default=str(DEFAULT_CLIENT_FILE),
        help="Path to the Google OAuth client JSON (default: client_secret.json).",
    )
    args = parser.parse_args()

    env_config = config_from_env()
    if env_config is not None:
        client_config = env_config
        print("Using YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET from local environment.")
    else:
        client_path = Path(args.client_file).expanduser().resolve()
        client_config = load_client_config(client_path)
        print(f"Using OAuth client file: {client_path}")

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print()
    print("Google will open a browser for authorization.")
    print("Grant access to the YouTube channel that Two Takes should publish to.")
    print("Required scope: https://www.googleapis.com/auth/youtube.upload")
    print()

    try:
        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
            open_browser=True,
        )
    except Exception as exc:
        print(f"OAuth authorization failed: {exc}", file=sys.stderr)
        return 1

    refresh_token = (credentials.refresh_token or "").strip()
    if not refresh_token:
        print(
            "Google did not return a refresh token. Re-run and make sure "
            "offline access/consent is granted.",
            file=sys.stderr,
        )
        return 2

    print()
    print("=== NEW YOUTUBE_REFRESH_TOKEN ===")
    print(refresh_token)
    print("=== END TOKEN ===")
    print()
    print(
        "Replace the GitHub Actions secret named YOUTUBE_REFRESH_TOKEN with this value."
    )
    print(
        "Do not commit the token or paste it into chat."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
