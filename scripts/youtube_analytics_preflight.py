#!/usr/bin/env python3
"""Check that YouTube analytics token grants both required read scopes."""
from __future__ import annotations

import os
import sys

import requests

REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
}


def main() -> int:
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_ANALYTICS_REFRESH_TOKEN", "").strip()

    missing = [
        name for name, value in (
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_ANALYTICS_REFRESH_TOKEN", refresh_token),
        ) if not value
    ]
    if missing:
        print("Missing required GitHub Actions secrets: " + ", ".join(missing))
        print(
            "Create YOUTUBE_ANALYTICS_REFRESH_TOKEN with both "
            "youtube.readonly and yt-analytics.readonly permissions."
        )
        return 2

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=(10, 30),
        )
    except requests.RequestException as exc:
        print("Google OAuth request failed: " + str(exc)[:500])
        return 3

    if not response.ok:
        print(
            f"Analytics token refresh failed with HTTP {response.status_code}: "
            f"{response.text[:700]}"
        )
        print("Re-authorize the same Google OAuth client with both required analytics scopes.")
        return 3

    access_token = str(response.json().get("access_token", "")).strip()
    if not access_token:
        print("Google OAuth response did not include an access token.")
        return 3

    try:
        token_info = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token},
            timeout=(10, 20),
        )
        token_info.raise_for_status()
        granted = set(str(token_info.json().get("scope", "")).split())
    except (requests.RequestException, ValueError) as exc:
        print("Could not verify analytics token scopes: " + str(exc)[:500])
        return 4

    missing_scopes = sorted(REQUIRED_SCOPES - granted)
    if missing_scopes:
        print("Analytics token is valid but is missing required scope(s):")
        for scope in missing_scopes:
            print(" - " + scope)
        print(
            "Re-authorize with BOTH scopes above, then save the new refresh token "
            "as the GitHub secret YOUTUBE_ANALYTICS_REFRESH_TOKEN. This can be a "
            "separate token from YOUTUBE_REFRESH_TOKEN, which is used for uploads."
        )
        return 5

    print("YouTube analytics OAuth check passed.")
    for scope in sorted(REQUIRED_SCOPES):
        print("Google confirms scope: " + scope)
    return 0


if __name__ == "__main__":
    sys.exit(main())
