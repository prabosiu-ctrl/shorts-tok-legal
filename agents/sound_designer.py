"""
Sound Designer

Generates per-shot ambient sound effects using ElevenLabs text_to_sound_effects.
Produces one SFX file per shot, then mixes them into a single stereo bed track
that plays under the narration at reduced volume.
"""

import os
import time
import subprocess
from pathlib import Path
from elevenlabs import ElevenLabs


def generate_sfx_track(shots: list[dict], work_dir: Path) -> Path:
    """
    Generates one SFX clip per shot, concatenates them, and returns
    a single ambient audio file matching the total video duration.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ElevenLabs_API_Key")
    client = ElevenLabs(api_key=api_key)

    sfx_paths = []

    for i, shot in enumerate(shots):
        sound_cue = shot.get("sound_cue", "soft ambient room tone")
        duration = float(shot.get("duration", 8))

        print(f"  SFX {i+1}/{len(shots)}: {sound_cue[:60]}")

        audio_bytes = b""
        for attempt in range(3):
            try:
                for chunk in client.text_to_sound_effects.convert(
                    text=sound_cue,
                    duration_seconds=duration,
                    prompt_influence=0.4,
                    output_format="mp3_44100_128",
                ):
                    if chunk:
                        audio_bytes += chunk
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  SFX retry {attempt+1} ({e})")
                    time.sleep(5)
                else:
                    raise

        sfx_path = work_dir / f"sfx_{i:03d}.mp3"
        sfx_path.write_bytes(audio_bytes)
        sfx_paths.append(sfx_path)

    return _concat_sfx(sfx_paths, work_dir)


def _concat_sfx(sfx_paths: list[Path], work_dir: Path) -> Path:
    """Concatenates all SFX clips into one continuous ambient track."""
    concat_file = work_dir / "sfx_concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in sfx_paths),
        encoding="utf-8"
    )

    sfx_track = work_dir / "sfx_track.mp3"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file.resolve().as_posix(),
        "-c", "copy",
        sfx_track.resolve().as_posix()
    ], check=True, capture_output=True)

    return sfx_track


def mix_audio(narration_path: Path, sfx_track: Path, work_dir: Path) -> Path:
    """
    Mixes narration (full volume) with SFX bed (-14dB under narration).
    Returns the mixed audio file.
    """
    mixed_path = work_dir / "audio_mixed.m4a"

    # Upmix narration to stereo, mix with SFX bed at -15dB
    subprocess.run([
        "ffmpeg", "-y",
        "-i", narration_path.resolve().as_posix(),
        "-i", sfx_track.resolve().as_posix(),
        "-filter_complex",
        "[0:a]volume=1.0,aformat=channel_layouts=stereo[narr];"
        "[1:a]volume=0.18,aformat=channel_layouts=stereo[sfx];"
        "[narr][sfx]amix=inputs=2:duration=first:dropout_transition=0[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        mixed_path.resolve().as_posix()
    ], check=True, capture_output=True)

    return mixed_path
