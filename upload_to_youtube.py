#!/usr/bin/env python3
"""
Upload a story video to YouTube.

Usage:
    python upload_to_youtube.py                         # upload latest out/ run
    python upload_to_youtube.py out/2026-04-07_08-26-56 # upload specific run
"""

import argparse
import json
import os
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from youtube_auth import get_credentials


def find_latest_out() -> Path:
    runs = sorted(Path("out").glob("????-??-??_??-??-??"), reverse=True)
    if not runs:
        raise FileNotFoundError("No runs found in out/")
    return runs[0]


def upload_video(workdir: Path) -> dict:
    config_path = workdir / "story_config.json"
    video_path = workdir / "video" / "story_video.mp4"
    thumb_path = workdir / "video" / "thumb.jpg"

    if not config_path.exists():
        raise FileNotFoundError(f"story_config.json not found in {workdir}")
    if not video_path.exists():
        raise FileNotFoundError(f"story_video.mp4 not found in {workdir}")

    config = json.loads(config_path.read_text())
    title = config.get("title", "Kids Story")
    moral = config.get("moral", "")
    hook = config.get("hook", "")
    story_hashtags = config.get("hashtags", ["#kidsstories", "#storytime"])

    # SEO-optimised title
    yt_title = f"{title} | Kids Moral Story | Bedtime Story for Children"

    # Viral hashtags shown above title (YouTube picks first 3 from description)
    viral_tags = [
        "#KidsStories", "#BedtimeStory", "#MoralStory",
        "#KidsAnimation", "#StorytimeForKids", "#ChildrensStories",
        "#AnimatedStory", "#KidsLearning", "#GoodHabits", "#FamilyFriendly",
    ]
    story_specific = " ".join(story_hashtags)
    viral_block = " ".join(viral_tags)

    description = (
        f"{hook}\n\n"
        f"{title} — {moral}\n\n"
        f"Watch more fun and heartwarming kids stories on our channel! "
        f"Every story teaches a positive lesson for children aged 3-10.\n\n"
        f"{story_specific} {viral_block}"
    )

    # Tags: story-specific + broad searchable terms
    base_tags = [
        "kids stories", "bedtime story", "moral story for kids",
        "animated story", "children story", "kids animation",
        "storytime", "good habits", "family friendly", "kids learning",
        "moral tales", "short stories for kids", "kids cartoon story",
    ]
    story_tags = [t.lstrip("#") for t in story_hashtags]
    all_tags = story_tags + base_tags

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    print(f"Uploading \"{yt_title}\" to YouTube...")
    body = {
        "snippet": {
            "title": yt_title,
            "description": description,
            "tags": all_tags,
            "categoryId": "1",  # Film & Animation
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Uploading... {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"✅ Uploaded: https://www.youtube.com/watch?v={video_id} — \"{yt_title}\"")

    # Upload thumbnail if available (requires verified channel)
    if thumb_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg")
            ).execute()
            print("✅ Thumbnail uploaded")
        except Exception as e:
            print(f"⚠️  Thumbnail skipped (channel not verified): {e}")

    return {"video_id": video_id, "title": title, "url": f"https://www.youtube.com/watch?v={video_id}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir", nargs="?", help="Path to run dir. Defaults to latest out/ run.")
    args = parser.parse_args()

    workdir = Path(args.workdir) if args.workdir else find_latest_out()
    print(f"Uploading from: {workdir}")
    result = upload_video(workdir)
    print(f"\nLive at: {result['url']}")


if __name__ == "__main__":
    main()
