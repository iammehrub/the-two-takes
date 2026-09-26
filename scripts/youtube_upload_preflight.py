#!/usr/bin/env python3
"""Fail fast when the YouTube refresh token cannot upload videos."""

from __future__ import annotations

import os
import sys

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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
        if "invalid_scope" in message.lower():
            print(
                "YouTube OAuth check failed: YOUTUBE_REFRESH_TOKEN is not "
                "authorized for the YouTube upload scope."
            )
            print(
                "Re-authorize the same Google OAuth client with "
                "https://www.googleapis.com/auth/youtube.upload and replace "
                "the GitHub secret YOUTUBE_REFRESH_TOKEN."
            )
            return 3

        print("YouTube OAuth refresh failed: " + message[:800])
        return 4

    try:
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        response = youtube.channels().list(part="id,snippet", mine=True).execute()
    except Exception as exc:
        print("YouTube API access check failed: " + str(exc)[:800])
        return 5

    channels = response.get("items", [])
    if not channels:
        print("YouTube OAuth refreshed, but no authenticated channel was returned.")
        return 6

    channel = channels[0]
    title = str(channel.get("snippet", {}).get("title", "Unknown channel"))
    channel_id = str(channel.get("id", "unknown"))

    print("YouTube upload OAuth check passed.")
    print(f"Authenticated channel: {title} ({channel_id})")
    print(f"Required scope: {UPLOAD_SCOPE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
