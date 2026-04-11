"""
Publishes a finished job to social platforms.

Usage:
    python publish.py                       # publishes latest job
    python publish.py --job 20260404_131120 # publishes specific job
    python publish.py --job 20260404_131120 --platforms youtube tiktok

Before first run:
    YouTube:  python auth_youtube.py
    TikTok:   python auth_tiktok.py
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agents.youtube_publisher import upload_to_youtube
from agents.tiktok_publisher import upload_to_tiktok


def get_latest_job() -> Path:
    output_dir = Path("output")
    jobs = sorted([j for j in output_dir.iterdir() if j.is_dir()], reverse=True)
    if not jobs:
        print("No jobs found in output/")
        sys.exit(1)
    return jobs[0]


def main():
    parser = argparse.ArgumentParser(description="Publish finished video to platforms")
    parser.add_argument("--job", type=str, help="Job ID (folder name under output/)")
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["youtube", "tiktok"],
        default=["youtube", "tiktok"],
        help="Platforms to publish to (default: all)",
    )
    args = parser.parse_args()

    job_dir = Path("output") / args.job if args.job else get_latest_job()
    if not job_dir.exists():
        print(f"Job folder not found: {job_dir}")
        sys.exit(1)

    job_id = job_dir.name
    print(f"\n=== Publishing job: {job_id} ===\n")

    if "youtube" in args.platforms:
        print("[YouTube]")
        try:
            url = upload_to_youtube(str(job_dir))
            print(f"  Done: {url}\n")
        except FileNotFoundError as e:
            print(f"  Skipped: {e}\n")
        except Exception as e:
            print(f"  Failed: {e}\n")

    if "tiktok" in args.platforms:
        print("[TikTok]")
        try:
            url = upload_to_tiktok(str(job_dir))
            print(f"  Done: {url}\n")
        except FileNotFoundError as e:
            print(f"  Skipped: {e}\n")
        except Exception as e:
            print(f"  Failed: {e}\n")


if __name__ == "__main__":
    main()
