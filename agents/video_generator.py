"""
Video generator — two pipelines:

  Default (free):  FLUX images + Ken Burns zoompan via FFmpeg
  --veo flag:      Veo video clips (~$0.05/s at 720p via Gemini API)

Override Veo model: VEO_MODEL in .env
  veo-3.1-lite-generate-preview  — $0.05/s 720p, $0.08/s 1080p (default when --veo used)
  veo-2.0-generate-001           — $0.35/s (legacy)
"""

import os
import time
import shutil
import subprocess
import requests
from pathlib import Path


# --- Veo settings -----------------------------------------------------------

VEO_MODEL = os.environ.get("VEO_MODEL", "veo-3.1-lite-generate-preview")

# Colour grade presets per ending type (FFmpeg colorbalance)
COLOR_GRADES = {
    "sad":         "colorbalance=rs=-0.2:gs=-0.05:bs=0.15:rm=-0.1:gm=0:bm=0.08",
    "happy":       "colorbalance=rs=0.12:gs=0.08:bs=-0.08:rm=0.08:gm=0.05:bm=-0.05",
    "bittersweet": "colorbalance=rs=-0.08:gs=0:bs=0.1:rh=0.1:gh=0.05:bh=-0.08",
}


# --- Veo clip generation ----------------------------------------------------

def generate_clips_veo(shots: list[dict], work_dir: Path) -> list[Path]:
    """Generate 8s video clips using Veo for each shot brief."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    clip_paths = []

    for i, shot in enumerate(shots):
        out_path = work_dir / f"clip_{i:03d}.mp4"

        if out_path.exists():
            print(f"  Clip {i+1}/{len(shots)}: already exists, skipping.")
            clip_paths.append(out_path)
            continue

        prompt = shot.get("prompt", "")
        print(f"  Clip {i+1}/{len(shots)}: {prompt[:80]}...")

        for attempt in range(3):
            try:
                operation = client.models.generate_videos(
                    model=VEO_MODEL,
                    prompt=prompt,
                    config=types.GenerateVideosConfig(
                        aspect_ratio="9:16",
                        duration_seconds=8,
                        number_of_videos=1,
                    ),
                )

                elapsed = 0
                while not operation.done:
                    time.sleep(5)
                    elapsed += 5
                    operation = client.operations.get(operation)
                    if elapsed % 20 == 0:
                        print(f"    Waiting... {elapsed}s", end="\r")

                video_uri = operation.result.generated_videos[0].video.uri
                resp = requests.get(
                    video_uri,
                    headers={"X-Goog-Api-Key": api_key},
                    timeout=120,
                )
                resp.raise_for_status()
                out_path.write_bytes(resp.content)
                print(f"  Saved: clip_{i:03d}.mp4 ({out_path.stat().st_size // 1024}KB)")
                break

            except Exception as e:
                if attempt < 2:
                    wait = (attempt + 1) * 20
                    print(f"  Retry {attempt + 1} in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Veo failed for clip {i + 1} after 3 attempts: {e}")

        clip_paths.append(out_path)
        if i < len(shots) - 1:
            time.sleep(8)  # brief pause between requests to avoid 429

    return clip_paths


# --- Ken Burns (free) -------------------------------------------------------

WIDTH, HEIGHT = 576, 1024
ZOOM_SCALE = 1.08


def _ken_burns_filter(motion: str, duration: int) -> str:
    fps = 24
    total_frames = duration * fps
    z_start, z_end = 1.0, ZOOM_SCALE

    if motion == "slow_zoom_in":
        return (
            f"scale={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z='min(zoom+{(z_end-z_start)/total_frames:.6f},1.08)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={WIDTH}x{HEIGHT}:fps={fps}"
        )
    elif motion == "slow_zoom_out":
        return (
            f"scale={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z='if(eq(on,1),1.08,max(zoom-{(z_end-z_start)/total_frames:.6f},1.0))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={WIDTH}x{HEIGHT}:fps={fps}"
        )
    elif motion == "slow_pan_right":
        return (
            f"scale={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z=1.0:"
            f"x='if(eq(on,1),0,x+{WIDTH*0.5/total_frames:.4f})':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={WIDTH}x{HEIGHT}:fps={fps}"
        )
    elif motion == "slow_pan_left":
        return (
            f"scale={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z=1.0:"
            f"x='if(eq(on,1),{WIDTH*0.5:.0f},x-{WIDTH*0.5/total_frames:.4f})':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={WIDTH}x{HEIGHT}:fps={fps}"
        )
    else:  # static
        return (
            f"scale={WIDTH*2}:{HEIGHT*2},"
            f"zoompan=z=1.0:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={WIDTH}x{HEIGHT}:fps={fps}"
        )


def process_images_to_clips(shots: list[dict], image_paths: list[Path], work_dir: Path) -> list[Path]:
    """Apply Ken Burns motion to each image and output as a video clip."""
    clip_paths = []

    for i, (shot, img_path) in enumerate(zip(shots, image_paths)):
        duration = shot.get("duration", 8)
        motion = shot.get("motion", "slow_zoom_in")
        out_path = work_dir / f"clip_{i:03d}.mp4"

        vf = _ken_burns_filter(motion, duration)

        result = subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", img_path.resolve().as_posix(),
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            out_path.resolve().as_posix()
        ], capture_output=True)

        if result.returncode != 0:
            raise RuntimeError(f"Ken Burns failed on image {i}:\n{result.stderr.decode()[-400:]}")

        clip_paths.append(out_path)
        print(f"  Clip {i+1}/{len(shots)} ({motion}, {duration}s)")

    return clip_paths


# --- Concat with cross-dissolve ---------------------------------------------

def _concat_with_dissolve(clip_paths: list[Path], work_dir: Path, dissolve: float = 0.4) -> Path:
    """Concatenate clips with 0.4s cross-dissolve. Falls back to plain concat."""
    out_path = work_dir / "concat.mp4"

    if len(clip_paths) == 1:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", clip_paths[0].resolve().as_posix(),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-an", out_path.resolve().as_posix(),
        ], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Encode failed:\n{result.stderr.decode()[-300:]}")
        return out_path

    # Probe first clip duration (handles both 8s Veo and variable Ken Burns durations)
    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        clip_paths[0].resolve().as_posix()
    ], capture_output=True, text=True)
    clip_duration = float(probe.stdout.strip() or "8.0")

    inputs = []
    for clip in clip_paths:
        inputs += ["-i", clip.resolve().as_posix()]

    step = clip_duration - dissolve
    filters = []
    prev = "[0:v]"
    for i in range(1, len(clip_paths)):
        out_label = f"[v{i}]" if i < len(clip_paths) - 1 else "[out]"
        offset = round(i * step, 3)
        filters.append(
            f"{prev}[{i}:v]xfade=transition=dissolve:duration={dissolve}:offset={offset}{out_label}"
        )
        prev = out_label

    result = subprocess.run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an",
        out_path.resolve().as_posix(),
    ], capture_output=True)

    if result.returncode != 0:
        print("  Warning: xfade failed, using plain concat.")
        concat_file = work_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in clip_paths),
            encoding="utf-8"
        )
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file.resolve().as_posix(),
            "-c", "copy",
            out_path.resolve().as_posix()
        ], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Concat fallback failed:\n{result.stderr.decode()[-400:]}")

    return out_path


# --- Per-shot colour grading (driven by quality_gate sentiment scores) -------

def _sentiment_to_colorbalance(score: float) -> str:
    """Map a sentiment score to an FFmpeg colorbalance filter string."""
    if score <= -0.4:   # dark/tense — cool blue shadows
        return "colorbalance=rs=-0.2:gs=-0.05:bs=0.15:rm=-0.1:gm=0:bm=0.08"
    elif score <= -0.1:  # slightly cold
        return "colorbalance=rs=-0.08:gs=0:bs=0.08:rm=-0.04:gm=0:bm=0.04"
    elif score >= 0.4:   # warm/hopeful — amber highlights
        return "colorbalance=rs=0.1:gs=0.06:bs=-0.06:rm=0.06:gm=0.04:bm=-0.04"
    elif score >= 0.1:   # slightly warm
        return "colorbalance=rs=0.05:gs=0.03:bs=-0.03"
    return ""  # neutral — no grade


def _grade_clips_by_sentiment(
    clip_paths: list[Path],
    sentiments: list[float],
    work_dir: Path,
) -> list[Path]:
    """Apply per-clip colour grade based on NL sentiment scores. Returns graded clip paths."""
    graded = []
    n_graded = 0
    for i, (clip, score) in enumerate(zip(clip_paths, sentiments)):
        grade = _sentiment_to_colorbalance(score)
        out = work_dir / f"graded_{i:03d}.mp4"
        if grade and not out.exists():
            result = subprocess.run([
                "ffmpeg", "-y",
                "-i", clip.resolve().as_posix(),
                "-vf", grade,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                out.resolve().as_posix(),
            ], capture_output=True)
            if result.returncode == 0:
                graded.append(out)
                n_graded += 1
                continue
        graded.append(clip)  # neutral or grade failed — use original
    if n_graded:
        print(f"  Per-shot grade applied to {n_graded}/{len(clip_paths)} clips.")
    return graded


# --- Assembly (shared by both pipelines) ------------------------------------

def assemble_video(
    clip_paths: list[Path],
    audio_path: Path,
    captions_path: Path,
    work_dir: Path,
    script: str = "",
    ending: str = "",
    shot_sentiments: list[float] = None,
) -> Path:
    # Step 1a: Per-shot colour grade (from NL API sentiment), overrides global ending grade
    if shot_sentiments and len(shot_sentiments) == len(clip_paths):
        clip_paths = _grade_clips_by_sentiment(clip_paths, shot_sentiments, work_dir)
        ending = ""  # per-shot grading supersedes the global ending grade

    # Step 1b: Concat with cross-dissolve
    concat_video = _concat_with_dissolve(clip_paths, work_dir)
    print("  Clips concatenated.")

    # Step 2: Merge audio (+ optional background music at 12% volume)
    from agents.music_selector import select_music
    music_path = select_music(script)

    merged_path = work_dir / "merged.mp4"

    if music_path:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", concat_video.resolve().as_posix(),
            "-i", audio_path.resolve().as_posix(),
            "-stream_loop", "-1",
            "-i", music_path.resolve().as_posix(),
            "-filter_complex",
            "[1:a]aformat=channel_layouts=stereo[narr];"
            "[2:a]volume=0.12,aformat=channel_layouts=stereo[music];"
            "[narr][music]amix=inputs=2:duration=first:dropout_transition=2[out]",
            "-map", "0:v:0", "-map", "[out]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            merged_path.resolve().as_posix()
        ], capture_output=True)
        if result.returncode != 0:
            print("  Warning: music mix failed, using narration only.")
            music_path = None

    if not music_path:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", concat_video.resolve().as_posix(),
            "-i", audio_path.resolve().as_posix(),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            merged_path.resolve().as_posix()
        ], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Audio merge failed:\n{result.stderr.decode()[-400:]}")

    print("  Audio merged.")

    # Step 3: Burn captions (ASS karaoke preferred, SRT fallback) + colour grade
    ass_source = Path(str(captions_path).replace(".srt", ".ass"))
    if ass_source.exists():
        shutil.copy(ass_source, work_dir / "subs.ass")
        sub_filter = "subtitles=subs.ass"
    else:
        shutil.copy(captions_path, work_dir / "subs.srt")
        caption_style = (
            "FontName=Arial,FontSize=30,PrimaryColour=&H00ffffff,"
            "OutlineColour=&H00000000,Outline=3,Shadow=1,Bold=1,"
            "Alignment=2,MarginV=80"
        )
        sub_filter = f"subtitles=subs.srt:force_style='{caption_style}'"

    grade = COLOR_GRADES.get(ending, "")
    vf = f"{sub_filter},{grade}" if grade else sub_filter

    final_path = work_dir / "final.mp4"
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", merged_path.resolve().as_posix(),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        final_path.resolve().as_posix()
    ], capture_output=True, cwd=str(work_dir.resolve()))

    if result.returncode != 0:
        print("  Warning: captions/grade failed, outputting without.")
        shutil.copy(merged_path, final_path)
    else:
        mode = "ASS karaoke" if ass_source.exists() else "SRT"
        grade_note = f" + {ending} grade" if grade else ""
        print(f"  Captions burned ({mode}{grade_note}).")
        merged_path.unlink(missing_ok=True)

    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        final_path.resolve().as_posix()
    ], capture_output=True, text=True)
    duration = float(probe.stdout.strip() or "0")
    print(f"  Duration: {duration:.1f}s")

    return final_path


# --- Entry point for run.py -------------------------------------------------

def generate_video(job_dir: str, ending: str = "", use_veo: bool = False) -> str:
    """Full pipeline for a single video. Free by default; pass use_veo=True for Veo clips."""
    import json
    from agents.scene_director import direct_scenes

    job_path = Path(job_dir)
    script = (job_path / "script.txt").read_text(encoding="utf-8")
    audio_path = job_path / "audio.mp3"
    captions_path = job_path / "captions.srt"

    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path.resolve().as_posix()
    ], capture_output=True, text=True)
    audio_duration = float(probe.stdout.strip() or "55")
    print(f"  Audio: {audio_duration:.1f}s")

    shots_path = job_path / "shots.json"
    if not shots_path.exists():
        mode = "video" if use_veo else "images"
        print(f"  Directing scenes ({mode})...")
        shots = direct_scenes(script, audio_duration, mode=mode)
        shots_path.write_text(json.dumps(shots, indent=2), encoding="utf-8")
    else:
        shots = json.loads(shots_path.read_text(encoding="utf-8"))
        print(f"  {len(shots)} shots loaded from cache.")

    if use_veo:
        clip_paths = sorted(job_path.glob("clip_0*.mp4"))
        if len(clip_paths) == len(shots):
            print(f"  All {len(shots)} clips already exist, skipping.")
        else:
            print(f"  Generating {len(shots)} Veo clips (est. ${len(shots)*8*0.05:.2f})...")
            clip_paths = generate_clips_veo(shots, job_path)
    else:
        from agents.image_generator import generate_images
        image_paths = sorted(job_path.glob("image_*.jpg"))
        if len(image_paths) != len(shots):
            print(f"  Generating {len(shots)} images (free)...")
            image_paths = generate_images(shots, job_path)
        else:
            print(f"  Images already exist, skipping.")

        clip_paths = sorted(job_path.glob("clip_0*.mp4"))
        if len(clip_paths) != len(shots):
            print(f"  Applying Ken Burns motion...")
            clip_paths = process_images_to_clips(shots, image_paths, job_path)
        else:
            print(f"  Clips already exist, skipping.")

    print("  Assembling final video...")
    return str(assemble_video(clip_paths, audio_path, captions_path, job_path,
                              script=script, ending=ending))
