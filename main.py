import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agents.scriptwriter import generate_script
from agents.narrator import generate_narration
from agents.transcriber import generate_captions


def run_pipeline(theme: str = None, ending: str = None) -> str:
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Job {job_id} ===")

    # 1. Script
    print("[1/3] Generating script...")
    script, scenes = generate_script(theme=theme, ending=ending)
    (job_dir / "script.txt").write_text(script, encoding="utf-8")
    (job_dir / "scene_prompts.json").write_text(json.dumps(scenes, indent=2), encoding="utf-8")
    print(f"      {len(script.split())} words | {len(scenes)} scenes")
    print(f"\n--- SCRIPT PREVIEW ---\n{script[:200]}...\n")

    # 2. Narration
    print("[2/3] Generating narration (ElevenLabs)...")
    audio_path = job_dir / "audio.mp3"
    generate_narration(script, output_path=str(audio_path))
    print(f"      Saved: {audio_path}")

    # 3. Captions
    print("[3/3] Transcribing audio -> captions (Whisper)...")
    srt_path = job_dir / "captions.srt"
    generate_captions(str(audio_path), output_path=str(srt_path))
    print(f"      Saved: {srt_path}")

    print(f"\nDone. Output -> {job_dir}")
    print("\nNext: Upload the job folder to Google Drive for Colab video generation.")
    print(f"  Folder contents: script.txt, audio.mp3, captions.srt, scene_prompts.json")

    return str(job_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shorts Tok Swarm — Story Pipeline")
    parser.add_argument("--theme", type=str, help="Story theme, e.g. 'a soldier coming home'")
    parser.add_argument(
        "--ending",
        type=str,
        choices=["happy", "sad", "bittersweet"],
        help="Ending type (default: random)",
    )
    args = parser.parse_args()
    run_pipeline(theme=args.theme, ending=args.ending)
