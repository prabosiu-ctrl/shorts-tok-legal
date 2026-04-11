"""
Reassembles an existing job using already-generated clips.
Applies: word-level captions, sound design, fixed audio merge.
Does NOT call Replicate — free to run.

Usage:
    python reassemble.py --job 20260404_213322
"""

import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agents.transcriber import generate_captions
from agents.video_generator import process_clips, assemble_video
from agents.sound_designer import generate_sfx_track, mix_audio


# Map old scene_prompts to sound cues if shots.json doesn't exist
SCENE_TO_SOUND_CUE = [
    "distant birds outside, wooden porch creak underfoot",
    "interior silence, fingers touching cold metal, low hum of fluorescent light",
    "muffled street sounds through windows, a woman humming softly in a warm room",
    "heavy thud of bag on hardwood floor, sudden stillness after impact",
    "soft nursery ambience, barely audible breathing, gentle creak of a bassinet",
    "complete silence, then the faintest sound of a newborn stirring",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, help="Job ID under output/")
    args = parser.parse_args()

    job_dir = Path("output") / args.job
    if not job_dir.exists():
        print(f"Job not found: {job_dir}")
        return

    audio_path = job_dir / "audio.mp3"
    captions_path = job_dir / "captions.srt"

    # Step 1: Regenerate word-level captions
    print("[1/4] Regenerating word-level captions...")
    audio_duration = generate_captions(str(audio_path), output_path=str(captions_path))
    print(f"      Done ({audio_duration:.1f}s audio)")

    # Step 2: Build shots list for sound designer
    print("[2/4] Generating sound design...")
    shots_path = job_dir / "shots.json"
    if shots_path.exists():
        shots = json.loads(shots_path.read_text())
    else:
        # Derive from old scene_prompts.json
        scenes = json.loads((job_dir / "scene_prompts.json").read_text())
        shots = [
            {"duration": 10, "sound_cue": SCENE_TO_SOUND_CUE[i] if i < len(SCENE_TO_SOUND_CUE) else "soft ambient room tone"}
            for i, _ in enumerate(scenes)
        ]

    try:
        sfx_track = generate_sfx_track(shots, job_dir)
        mixed_audio = mix_audio(audio_path, sfx_track, job_dir)
        print("      Sound design mixed.")
    except Exception as e:
        print(f"      Sound design failed ({e}), using narration only.")
        mixed_audio = audio_path

    # Step 3: Re-process raw clips (consistent encode)
    print("[3/4] Re-processing clips...")
    raw_clips = sorted(job_dir.glob("clip_*_raw.mp4"))
    if not raw_clips:
        print("      No raw clips found. Cannot reassemble.")
        return
    processed = process_clips(raw_clips, job_dir)

    # Step 4: Reassemble
    print("[4/4] Assembling final video...")
    final_path = assemble_video(processed, mixed_audio, captions_path, job_dir)
    print(f"\nDone: {final_path}")
    print("Check the video, then publish with:")
    print(f"  python publish.py --job {args.job}")


if __name__ == "__main__":
    main()
