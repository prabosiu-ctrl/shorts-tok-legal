"""
Finds the next queued (private) part in the series and makes it public.

Reads queue.json to find the current series and which parts have been published.
Marks the next part public via YouTube API and updates queue.json.

Usage:
    python scripts/schedule_publish.py
"""

import json
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agents.youtube_publisher import get_youtube_service

QUEUE_FILE = Path("queue.json")


def main():
    if not QUEUE_FILE.exists():
        print("No queue.json found — nothing to publish.")
        sys.exit(0)

    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    series_id = queue.get("series_id")
    published = queue.get("published", [])   # list of video IDs already made public
    pending = queue.get("pending", [])        # list of {video_id, label} to publish

    if not pending:
        print("Queue is empty — all parts published.")
        sys.exit(0)

    next_item = pending.pop(0)
    video_id = next_item["video_id"]
    label = next_item.get("label", video_id)

    print(f"Publishing: {label} ({video_id})")

    youtube = get_youtube_service()
    youtube.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
    ).execute()

    published.append({"video_id": video_id, "label": label})
    queue["published"] = published
    queue["pending"] = pending
    QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    print(f"Published: https://www.youtube.com/watch?v={video_id}")
    print(f"Remaining in queue: {len(pending)}")


if __name__ == "__main__":
    main()
