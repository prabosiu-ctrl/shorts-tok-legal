"""
TikTok publisher using Content Posting API v2.
Uploads video as a direct post to the authorized TikTok account.
Requires tiktok_token.json (run auth_tiktok.py first).
"""

import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = "tiktok_token.json"
UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _load_token() -> dict:
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            f"{TOKEN_FILE} not found. Run: python auth_tiktok.py"
        )
    with open(TOKEN_FILE) as f:
        return json.load(f)


def _refresh_token_if_needed(token_data: dict) -> dict:
    """Refresh access token if expired."""
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return token_data

    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.status_code == 200 and "access_token" in resp.json():
        token_data = resp.json()
        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

    return token_data


def upload_to_tiktok(job_dir: str) -> str:
    job_path = Path(job_dir)
    video_path = job_path / "final.mp4"
    script_path = job_path / "script.txt"

    if not video_path.exists():
        raise FileNotFoundError(f"final.mp4 not found in {job_dir}")

    token_data = _load_token()
    token_data = _refresh_token_if_needed(token_data)
    access_token = token_data.get("access_token")
    open_id = token_data.get("open_id")

    if not access_token or not open_id:
        raise ValueError("Invalid token data. Run auth_tiktok.py again.")

    script = script_path.read_text(encoding="utf-8") if script_path.exists() else ""

    # Build caption from first sentence of script (150 char TikTok limit)
    first_sentence = script.split(".")[0].strip() + "."
    caption = first_sentence[:150] + " #Shorts #Story #AIStory"

    video_size = video_path.stat().st_size
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # Step 1: Initialize upload
    print("  Initializing TikTok upload...")
    init_body = {
        "post_info": {
            "title": caption,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    resp = requests.post(UPLOAD_URL, headers=headers, json=init_body)
    if resp.status_code != 200:
        raise RuntimeError(f"TikTok init failed ({resp.status_code}): {resp.text}")

    data = resp.json().get("data", {})
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")

    if not publish_id or not upload_url:
        raise RuntimeError(f"TikTok init returned no upload URL: {resp.text}")

    print(f"  Upload URL received. Uploading video ({video_size // 1024}KB)...")

    # Step 2: Upload video bytes
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_headers = {
        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        "Content-Type": "video/mp4",
        "Content-Length": str(video_size),
    }
    upload_resp = requests.put(upload_url, headers=upload_headers, data=video_bytes)
    if upload_resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"TikTok upload failed ({upload_resp.status_code}): {upload_resp.text}")

    print("  Video uploaded. Waiting for processing...")

    # Step 3: Poll publish status
    for attempt in range(12):
        time.sleep(5)
        status_resp = requests.post(
            STATUS_URL,
            headers=headers,
            json={"publish_id": publish_id},
        )

        if status_resp.status_code != 200:
            print(f"  Status check failed: {status_resp.text}")
            continue

        status_data = status_resp.json().get("data", {})
        status = status_data.get("status")
        print(f"  Status: {status}")

        if status == "PUBLISH_COMPLETE":
            tiktok_id = status_data.get("publicaly_available_post_id", [None])[0]
            url = f"https://www.tiktok.com/@me/video/{tiktok_id}" if tiktok_id else "https://www.tiktok.com/profile"
            print(f"  Published: {url}")
            return url

        if status in ("FAILED", "PUBLISH_FAILED"):
            error = status_data.get("fail_reason", "Unknown error")
            raise RuntimeError(f"TikTok publish failed: {error}")

    raise RuntimeError("TikTok publish timed out after 60 seconds.")
