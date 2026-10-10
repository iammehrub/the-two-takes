#!/usr/bin/env python3
"""Validate that the configured Google refresh token includes upload permission."""
from __future__ import annotations

import os
import sys

import requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def main() -> int:
    required = {
        "YOUTUBE_CLIENT_ID": os.environ.get("YOUTUBE_CLIENT_ID", "").strip(),
        "YOUTUBE_CLIENT_SECRET": os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip(),
        "YOUTUBE_REFRESH_TOKEN": os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        print("Missing GitHub Actions secrets: " + ", ".join(missing))
        return 2

    creds = Credentials(
        token=None,
        refresh_token=required["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=required["YOUTUBE_CLIENT_ID"],
        client_secret=required["YOUTUBE_CLIENT_SECRET"],
        scopes=[UPLOAD_SCOPE],
    )

    try:
        creds.refresh(Request())
    except RefreshError as exc:
        message = str(exc)
        lowered = message.lower()
        if "invalid_grant" in lowered:
            print("YouTube OAuth failed: refresh token is expired or revoked.")
            print("Re-authorize the same OAuth client with the upload scope and update YOUTUBE_REFRESH_TOKEN.")
            print("If the OAuth consent screen is in Testing, Google may expire refresh tokens after 7 days.")
            return 4
        if "invalid_scope" in lowered:
            print(f"YouTube OAuth failed: token is not authorized for {UPLOAD_SCOPE}.")
            print("Re-authorize the same OAuth client with this scope and update YOUTUBE_REFRESH_TOKEN.")
            return 3
        print("YouTube OAuth refresh failed: " + message[:800])
        return 4

    # Do NOT call channels.list(mine=true) here: that endpoint requires
    # youtube.readonly and falsely rejects a valid upload-only token.
    try:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": creds.token},
            timeout=(10, 20),
        )
    except requests.RequestException as exc:
        print("Could not verify the access-token scopes: " + str(exc)[:500])
        return 5

    if not response.ok:
        print(f"Google tokeninfo request failed with HTTP {response.status_code}: {response.text[:500]}")
        return 5

    try:
        info = response.json()
    except ValueError:
        print("Google tokeninfo returned invalid JSON.")
        return 5

    granted = set(str(info.get("scope", "")).split())
    if UPLOAD_SCOPE not in granted:
        print("YouTube OAuth refreshed, but the access token lacks the upload scope.")
        print("Granted scopes reported by Google:")
        print("\n".join(sorted(granted)) or "(none returned)")
        print(f"Required scope: {UPLOAD_SCOPE}")
        print("Re-authorize the same OAuth client with youtube.upload and update YOUTUBE_REFRESH_TOKEN.")
        return 3

    print("YouTube upload OAuth check passed.")
    print(f"Google confirms required scope: {UPLOAD_SCOPE}")
    extra = sorted(granted - {UPLOAD_SCOPE})
    if extra:
        print("Additional granted scopes: " + ", ".join(extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
