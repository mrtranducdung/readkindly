#!/usr/bin/env python3
"""
One-time TikTok OAuth flow to get an access token.

Usage:
    python tiktok_auth.py

Reads TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET from .env
Saves TIKTOK_ACCESS_TOKEN back to .env
"""

import os
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = "https://localhost"

if not CLIENT_KEY or not CLIENT_SECRET:
    print("✗ TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set in .env")
    raise SystemExit(1)

# Step 1 — Build auth URL
params = {
    "client_key": CLIENT_KEY,
    "scope": "video.upload,video.publish",
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "state": "readkindly",
}
auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)

print("Opening TikTok login in your browser...")
print(f"\n{auth_url}\n")
webbrowser.open(auth_url)

print("After authorizing, your browser will redirect to https://localhost?code=XXXX")
print("The page won't load — that's fine. Copy the full URL from the address bar.\n")
redirect = input("Paste the full redirect URL here: ").strip()

# Step 2 — Extract code
parsed = urllib.parse.urlparse(redirect)
code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
if not code:
    print("✗ Could not find 'code' in the URL.")
    raise SystemExit(1)

# Step 3 — Exchange code for token
r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    },
)
r.raise_for_status()
data = r.json()

access_token = data.get("access_token")
refresh_token = data.get("refresh_token", "")

if not access_token:
    print(f"✗ Token exchange failed: {data}")
    raise SystemExit(1)

print(f"\n✅ Got access token: {access_token[:20]}...")

# Step 4 — Save to .env
env_path = Path(".env")
env_text = env_path.read_text()

for key, value in [("TIKTOK_ACCESS_TOKEN", access_token), ("TIKTOK_REFRESH_TOKEN", refresh_token)]:
    if f"{key}=" in env_text:
        lines = env_text.splitlines()
        env_text = "\n".join(
            f"{key}={value}" if line.startswith(f"{key}=") else line
            for line in lines
        )
    else:
        env_text += f"\n{key}={value}"

env_path.write_text(env_text)
print(f"✅ Saved TIKTOK_ACCESS_TOKEN to .env")
print("\nYou can now run the pipeline and it will auto-upload to TikTok.")
