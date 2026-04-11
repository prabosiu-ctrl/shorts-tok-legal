import os
import pickle
import json
from pathlib import Path

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from google.genai import types

TOKEN_FILE = "youtube_token.pickle"


def get_youtube_service():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            f"{TOKEN_FILE} not found. Run: python auth_youtube.py"
        )
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def generate_metadata(script: str) -> dict:
    """Use Gemini to generate a title, description, and tags from the script."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    prompt = f"""Given this short story narration script, generate YouTube metadata.

Script:
{script}

Return valid JSON only:
{{
  "title": "A punchy, emotional title under 60 characters. No clickbait, no ALL CAPS.",
  "description": "2-3 sentence summary that hints at the story without spoiling it. End with relevant hashtags: #Shorts #AIStory #ShortFilm",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""

    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )

    return json.loads(response.text)


def upload_to_youtube(job_dir: str) -> str:
    job_path = Path(job_dir)
    video_path = job_path / "final.mp4"
    script_path = job_path / "script.txt"

    if not video_path.exists():
        raise FileNotFoundError(
            f"final.mp4 not found in {job_dir}\n"
            "Download it from Google Drive into the job folder first."
        )

    script = script_path.read_text(encoding="utf-8") if script_path.exists() else ""

    print("  Generating title and description...")
    metadata = generate_metadata(script)
    title = metadata.get("title", "An AI Short Story")
    description = metadata.get("description", "")
    tags = metadata.get("tags", ["Shorts", "AIStory"])

    print(f"  Title: {title}")
    print(f"  Tags:  {', '.join(tags)}")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # Required disclosure for AI content
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,  # 5MB chunks
    )

    print("  Uploading to YouTube...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload progress: {pct}%", end="\r")

    video_id = response["id"]
    url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"\n  Published (public): {url}")
    return url
