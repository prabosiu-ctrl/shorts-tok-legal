"""
Full pipeline — one command to run everything.

Usage:
    python run.py
    python run.py --theme "a nurse who finds her late mother's patient file"
    python run.py --theme "..." --ending sad --no-publish

What it does:
    1. Generates script            (Gemini, free)
    2. Generates narration         (edge-tts, free)
    3. Generates captions          (Whisper, free)
    4. Generates images + video    (Pollinations.ai + FFmpeg, free)
    5. Publishes to YouTube        (optional)

Total cost per video: $0.00
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agents.scriptwriter import generate_script
from agents.narrator import generate_narration
from agents.transcriber import generate_captions
from agents.video_generator import generate_video
from agents.youtube_publisher import upload_to_youtube


def main():
    parser = argparse.ArgumentParser(description="Shorts Tok Swarm - Full Pipeline")
    parser.add_argument("--theme", type=str)
    parser.add_argument("--ending", choices=["happy", "sad", "bittersweet"])
    parser.add_argument("--no-publish", action="store_true", help="Skip upload to platforms")
    parser.add_argument("--veo", action="store_true", help="Use Veo AI video (~$3.20/video) instead of free FLUX images")
    args = parser.parse_args()

    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*50}")
    print(f" Job: {job_id}")
    print(f"{'='*50}\n")

    # Step 1: Script
    print("[1/4] Generating script...")
    script = generate_script(theme=args.theme, ending=args.ending)
    (job_dir / "script.txt").write_text(script, encoding="utf-8")
    print(f"      {len(script.split())} words")

    # Step 2: Narration
    print("[2/4] Generating narration...")
    audio_path = job_dir / "audio.mp3"
    generate_narration(script, output_path=str(audio_path))
    print(f"      Saved: {audio_path.name}")

    # Step 3: Captions (word-level, returns audio duration)
    print("[3/4] Generating captions...")
    srt_path = job_dir / "captions.srt"
    audio_duration = generate_captions(str(audio_path), output_path=str(srt_path))
    print(f"      Saved: {srt_path.name} ({audio_duration:.1f}s)")

    # Step 4: Veo 2 clips + assembly
    print("[4/4] Generating Veo 2 clips and assembling video...")
    final_path = generate_video(str(job_dir), ending=args.ending or "", use_veo=args.veo)
    print(f"      Final: {final_path}\n")

    # Publish
    if not args.no_publish:
        print("[YouTube] Uploading...")
        try:
            url = upload_to_youtube(str(job_dir))
            print(f"  Done: {url}")
        except Exception as e:
            print(f"  Failed: {e}")
            print(f"  Run manually: python publish.py --job {job_id}")
    else:
        print(f"Skipped publishing. Run when ready:")
        print(f"  python publish.py --job {job_id}")

    print(f"\n{'='*50}")
    print(f" Complete: output/{job_id}/")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
