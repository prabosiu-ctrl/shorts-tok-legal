"""
Publishes a completed series to YouTube.

- Long-form video: uploaded PUBLIC immediately
- Individual parts: uploaded PRIVATE (publish manually or via schedule)

Usage:
    python series_publish.py --series series_20260406_121055

Before first run:
    python auth_youtube.py
"""

import json
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agents.youtube_publisher import generate_metadata, get_youtube_service
from agents.quality_gate import moderate_script, extract_entities
from googleapiclient.http import MediaFileUpload


def create_playlist(youtube, title: str, description: str = "") -> str:
    """Create a YouTube playlist and return its ID."""
    response = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
            },
            "status": {
                "privacyStatus": "public",
            },
        },
    ).execute()
    playlist_id = response["id"]
    print(f"  Playlist created: https://www.youtube.com/playlist?list={playlist_id}")
    return playlist_id


def add_to_playlist(youtube, playlist_id: str, video_id: str, position: int = None):
    """Add a video to a playlist at a given position."""
    snippet = {
        "playlistId": playlist_id,
        "resourceId": {
            "kind": "youtube#video",
            "videoId": video_id,
        },
    }
    if position is not None:
        snippet["position"] = position
    youtube.playlistItems().insert(
        part="snippet",
        body={"snippet": snippet},
    ).execute()


def upload_video(youtube, video_path: Path, title: str, description: str, tags: list,
                 privacy: str, is_short: bool = False) -> str:

    category_id = "24"  # Entertainment

    # #Shorts must appear at the very start of the description for reliable classification
    if is_short and not description.startswith("#Shorts"):
        description = "#Shorts\n\n" + description

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,
    )

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
            print(f"    Upload: {pct}%", end="\r")

    video_id = response["id"]
    if is_short:
        url = f"https://www.youtube.com/shorts/{video_id}"
    else:
        url = f"https://www.youtube.com/watch?v={video_id}"

    return url


def main():
    parser = argparse.ArgumentParser(description="Publish a 5-part series to YouTube")
    parser.add_argument("--series", required=True, help="Series folder name under output/")
    parser.add_argument("--part", type=int, help="Upload only this specific part number")
    parser.add_argument("--skip-longform", action="store_true", help="Skip long-form upload")
    args = parser.parse_args()

    series_dir = Path("output") / args.series
    if not series_dir.exists():
        print(f"Series folder not found: {series_dir}")
        sys.exit(1)

    series_json = series_dir / "series.json"
    if not series_json.exists():
        print(f"series.json not found in {series_dir}")
        sys.exit(1)

    series_data = json.loads(series_json.read_text(encoding="utf-8"))
    series_title = series_data["series_title"]
    parts = series_data["parts"]

    print(f"\n=== Publishing series: {series_title} ===\n")

    # --- Content moderation gate ---
    all_scripts = []
    for part in parts:
        script_file = series_dir / f"part_{part['part']}" / "script.txt"
        if script_file.exists():
            all_scripts.append(script_file.read_text(encoding="utf-8"))
    if all_scripts:
        print("[Moderation] Checking content policy...")
        is_safe, flagged = moderate_script("\n\n".join(all_scripts))
        if not is_safe:
            print(f"  Flagged categories: {', '.join(flagged)}")
            print("  Upload aborted. Review scripts before publishing.")
            sys.exit(1)
        print(f"  Content check passed.")

    youtube = get_youtube_service()

    # --- Long-form (PUBLIC) ---
    longform_video_id = None
    longform_path = series_dir / "longform.mp4"
    if longform_path.exists() and not args.skip_longform and not args.part:
        print("[Long-form] Uploading as PUBLIC...")

        # Build chapter description
        chapters = "Chapters:\n"
        timestamp = 0
        for part in parts:
            mins, secs = divmod(int(timestamp), 60)
            chapters += f"{mins:02d}:{secs:02d} Part {part['part']} - {part['title']}\n"
            timestamp += 72

        description = (
            f"The complete story of '{series_title}' — watch all 5 parts in one video.\n\n"
            f"{chapters}\n"
            f"#Story #ShortFilm #AIStory"
        )

        url = upload_video(
            youtube,
            longform_path,
            title=f"{series_title} | Full Story",
            description=description,
            tags=[series_title, "short film", "AI story", "drama", "series"],
            privacy="public",
            is_short=False,
        )
        print(f"\n  Published (public): {url}")
        longform_video_id = url.split("=")[-1]
    else:
        print("[Long-form] longform.mp4 not found, skipping.")

    # --- Individual parts (PRIVATE) ---
    parts_to_upload = [p for p in parts if not args.part or p["part"] == args.part]
    print(f"\n[Parts] Uploading {len(parts_to_upload)} part(s) as PRIVATE...")
    part_video_ids = []  # list of (video_id, label) for queue.json
    for part in parts_to_upload:
        part_num = part["part"]
        part_dir = series_dir / f"part_{part_num}"
        video_path = part_dir / "part_titled.mp4"
        if not video_path.exists():
            video_path = part_dir / "final.mp4"
        if not video_path.exists():
            print(f"  Part {part_num}: video not found, skipping.")
            continue

        script = (part_dir / "script.txt").read_text(encoding="utf-8") if (part_dir / "script.txt").exists() else ""
        metadata = generate_metadata(script)
        entity_tags = extract_entities(script, top_n=5) if script else []

        title = f"{series_title} - Part {part_num} of {len(parts)}: {part['title']}"
        description = metadata.get("description", "") + f"\n\n#Shorts #Story #AIStory #{series_title.replace(' ', '')}"
        tags = metadata.get("tags", []) + [series_title, f"Part {part_num}"] + entity_tags

        print(f"  Part {part_num}: {title[:60]}...")
        url = upload_video(
            youtube,
            video_path,
            title=title,
            description=description,
            tags=tags,
            privacy="private",
            is_short=True,
        )
        print(f"\n  Uploaded (private): {url}")

        # Extract video ID from URL for queue.json
        video_id = url.split("/")[-1].split("=")[-1]
        part_video_ids.append((video_id, f"Part {part_num}: {part['title'][:40]}"))

    # Write queue.json so GitHub Actions can publish one part per day
    queue_file = Path("queue.json")
    existing_queue = json.loads(queue_file.read_text(encoding="utf-8")) if queue_file.exists() else {}
    existing_pending = existing_queue.get("pending", [])

    new_pending = [
        {"video_id": vid, "label": lbl}
        for vid, lbl in part_video_ids
    ]

    queue = {
        "series_id": args.series,
        "series_title": series_title,
        "pending": existing_pending + new_pending,
        "published": existing_queue.get("published", []),
    }
    queue_file.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    print(f"\n  queue.json updated — {len(new_pending)} part(s) queued for daily publish.")

    # --- Create YouTube playlist ---
    all_video_ids = []
    if longform_video_id:
        all_video_ids.append((longform_video_id, "Full Story"))
    all_video_ids += [(vid, lbl) for vid, lbl in part_video_ids]

    if all_video_ids and not args.part:
        print(f"\n[Playlist] Creating '{series_title}'...")
        playlist_description = (
            f"All episodes of '{series_title}' — a 5-part AI-generated short story series.\n"
            f"#Story #AIStory #Shorts"
        )
        playlist_id = create_playlist(youtube, series_title, description=playlist_description)

        for position, (video_id, label) in enumerate(all_video_ids):
            add_to_playlist(youtube, playlist_id, video_id, position=position)
            print(f"  Added: {label}")

        # Save playlist ID to queue.json
        queue["playlist_id"] = playlist_id
        queue_file.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    print(f"\n=== Done ===")
    print(f"Long-form is live. Parts are private, queued in queue.json.")
    print(f"Run scripts/schedule_publish.py (or GitHub Actions) to publish one per day.")


if __name__ == "__main__":
    main()
