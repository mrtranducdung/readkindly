#!/usr/bin/env python3
"""
One-time YouTube OAuth flow to get credentials.

Usage:
    python youtube_auth.py

Reads youtube_client_secret.json from project root.
Saves credentials to youtube_token.json for reuse.
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "youtube_client_secret.json"
TOKEN_FILE = "youtube_token.json"


def get_credentials():
    creds = None

    # On Render: token stored as env var JSON string
    token_env = os.environ.get("YOUTUBE_TOKEN_JSON", "")
    if token_env and not Path(TOKEN_FILE).exists():
        Path(TOKEN_FILE).write_text(token_env)

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            Path(TOKEN_FILE).write_text(creds.to_json())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            Path(TOKEN_FILE).write_text(creds.to_json())
        print(f"✅ Credentials saved to {TOKEN_FILE}")

    return creds


if __name__ == "__main__":
    if not Path(CLIENT_SECRET_FILE).exists():
        print(f"✗ {CLIENT_SECRET_FILE} not found. Download it from Google Cloud Console.")
        raise SystemExit(1)
    get_credentials()
    print("✅ YouTube authentication complete. Ready to upload.")
