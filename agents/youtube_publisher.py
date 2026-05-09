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
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if refresh_token:
        client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
        if not (client_id and client_secret) and os.path.exists("oauth_client.json"):
            with open("oauth_client.json") as f:
                data = json.load(f)
            installed = data.get("installed", data.get("web", {}))
            client_id = installed["client_id"]
            client_secret = installed["client_secret"]
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        creds.refresh(Request())
        return build("youtube", "v3", credentials=creds)

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


def generate_metadata(
    script: str,
    series_title: str = "",
    part_num: int = 0,
    total_parts: int = 5,
    is_short: bool = True,
) -> dict:
    """
    Generate CTR-optimised YouTube metadata using Gemini.

    Produces an emotionally charged title, scroll-stopping description,
    and 12-15 targeted tags mixing broad emotion, story-type, and format keywords.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    context = ""
    next_part_ref = ""
    if series_title and part_num:
        context = f"Series: '{series_title}' | This is Part {part_num} of {total_parts}\n\n"
        next_part = part_num + 1
        next_part_ref = (
            f"Follow for Part {next_part}." if part_num < total_parts
            else "Watch the full series in the playlist."
        )

    format_note = "YouTube Short (vertical, under 60 seconds)" if is_short else "YouTube long-form video"

    prompt = f"""{context}Script:
{script}

Generate highly optimised YouTube metadata for a {format_note}.
Think like a viral content creator AND an SEO expert.

Rules:
- Title: Lead with the emotional hook — what the viewer FEELS, not what happens. Under 60 chars. Title case. No ALL CAPS. No "Part X" prefix.
- Description: First sentence is a scroll-stopper (stakes or question). Second expands intrigue without spoiling. Third is a CTA: "{next_part_ref or 'Follow for more.'}" End with a line break then hashtags.
- Tags: 12-15 tags. Mix: 2-3 broad emotion tags (e.g. "grief", "betrayal"), 3-4 story-type tags (e.g. "short story", "drama"), 3-4 format tags (e.g. "youtube shorts story", "ai short film"), 2-3 niche tags specific to this story.

Return valid JSON only:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...]
}}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.75,
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
