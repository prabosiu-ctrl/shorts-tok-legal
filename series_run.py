"""
Series pipeline — generates a 5-part story series.

Usage:
    python series_run.py
    python series_run.py --theme "a nurse who finds her biological mother as a patient"
    python series_run.py --theme "..." --ending bittersweet --no-publish

Output:
    output/SERIES_ID/
        series.json          — full series data (scripts, shots, metadata)
        part_1/              — individual part job folders
            script.txt
            audio.mp3
            captions.srt
            shots.json
            image_*.jpg
            clip_*.mp4
            part.mp4         — Short with title card + end card
        part_2/ ... part_5/
        longform.mp4         — all 5 parts concatenated for YouTube long-form
"""

import json
import argparse
import subprocess
import sys
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agents.series_scriptwriter import generate_series
from agents.narrator import generate_narration
from agents.transcriber import generate_captions
from agents.scene_director import direct_scenes
from agents.video_generator import generate_clips_veo, process_images_to_clips, assemble_video
from agents.quality_gate import check_arc, extract_entities, get_shot_sentiments


def _make_text_frame(text: str, work_dir: Path, filename: str) -> Path:
    """Create a black image with white centred text using Pillow."""
    from PIL import Image as PilImage, ImageDraw, ImageFont
    img = PilImage.new("RGB", (576, 1024), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Try to load a system font, fall back to default
    font_size = 42
    font = None
    for font_path in [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    # Word-wrap
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > 500 and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    # Draw centred
    total_h = len(lines) * (font_size + 10)
    y = (1024 - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (576 - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, fill=(255, 255, 255), font=font)
        y += font_size + 10

    out_path = work_dir / filename
    img.save(str(out_path), format="JPEG", quality=95)
    return out_path


def _image_to_clip(img_path: Path, duration: int, out_path: Path):
    """Convert a static image to a video clip."""
    result = subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(img_path.resolve()),
        "-t", str(duration),
        "-vf", f"scale=576:1024",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_path.resolve()),
    ], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Image to clip failed: {result.stderr.decode()[-300:]}")


def add_title_card(part_video: Path, series_title: str, part_num: int, total_parts: int, work_dir: Path) -> Path:
    """Prepend a title card and append an end card using Pillow + FFmpeg concat."""
    out_path = work_dir / "part_titled.mp4"

    clips_to_concat = []

    # Title card (3s)
    title_text = f"{series_title}\nPart {part_num} of {total_parts}"
    title_img = _make_text_frame(title_text, work_dir, "title_card.jpg")
    title_clip = work_dir / "title_clip.mp4"
    _image_to_clip(title_img, 3, title_clip)
    clips_to_concat.append(title_clip)

    # Main video (needs silent audio track to match title/end clips)
    clips_to_concat.append(part_video)

    # End card (3s) — only for parts 1-4
    if part_num < total_parts:
        end_text = f"Watch Part {part_num + 1}"
        end_img = _make_text_frame(end_text, work_dir, "end_card.jpg")
        end_clip = work_dir / "end_clip.mp4"
        _image_to_clip(end_img, 3, end_clip)
        clips_to_concat.append(end_clip)

    # Add silent audio to title/end clips, then concat everything
    # Step 1: add silence to title clip
    title_with_audio = work_dir / "title_clip_audio.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(title_clip.resolve()),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(title_with_audio.resolve()),
    ], capture_output=True)

    final_clips = [title_with_audio, part_video]

    if part_num < total_parts:
        end_clip = work_dir / "end_clip.mp4"
        end_with_audio = work_dir / "end_clip_audio.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(end_clip.resolve()),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(end_with_audio.resolve()),
        ], capture_output=True)
        final_clips.append(end_with_audio)

    # Step 2: concat all clips
    concat_file = work_dir / "titled_concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in final_clips),
        encoding="utf-8"
    )
    result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file.resolve().as_posix(),
        "-c", "copy",
        str(out_path.resolve()),
    ], capture_output=True)

    if result.returncode != 0:
        print(f"  Warning: title card concat failed, using plain video.")
        shutil.copy(part_video, out_path)

    return out_path


def assemble_longform(part_videos: list[Path], series_dir: Path) -> Path:
    """Concatenate all 5 part videos into one long-form video."""
    concat_file = series_dir / "longform_concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in part_videos),
        encoding="utf-8"
    )

    out_path = series_dir / "longform.mp4"
    result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file.resolve().as_posix(),
        "-c", "copy",
        out_path.resolve().as_posix(),
    ], capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(f"Long-form concat failed:\n{result.stderr.decode()[-400:]}")

    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        out_path.resolve().as_posix()
    ], capture_output=True, text=True)
    duration = float(probe.stdout.strip() or "0")
    print(f"  Long-form duration: {duration:.1f}s ({duration/60:.1f} min)")

    return out_path


def run_part(part_data: dict, part_dir: Path, series_title: str, part_num: int, total_parts: int, character_anchor: str = "", ending: str = "", use_veo: bool = False) -> Path:
    """Run the full pipeline for a single part. Returns path to titled Short."""
    script = part_data["script"]
    print(f"\n  --- Part {part_num}: {part_data['title']} ---")

    # Script
    (part_dir / "script.txt").write_text(script, encoding="utf-8")

    # Narration
    audio_path = part_dir / "audio.mp3"
    if not audio_path.exists():
        generate_narration(script, output_path=str(audio_path))
    print(f"  Audio saved.")

    # Captions
    srt_path = part_dir / "captions.srt"
    if not srt_path.exists():
        audio_duration = generate_captions(str(audio_path), output_path=str(srt_path))
    else:
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path.resolve())
        ], capture_output=True, text=True)
        audio_duration = float(probe.stdout.strip() or "55")
    print(f"  Captions saved. ({audio_duration:.1f}s)")

    # Scene direction
    shots_path = part_dir / "shots.json"
    if not shots_path.exists():
        mode = "video" if use_veo else "images"
        entities = extract_entities(script)
        if entities:
            print(f"  Key entities: {', '.join(entities[:6])}")
        shots = direct_scenes(script, audio_duration, character_anchor=character_anchor, mode=mode,
                              context_entities=entities)

        # Attach per-shot sentiment scores for dynamic colour grading
        sentiments = get_shot_sentiments(shots)
        if any(s != 0.0 for s in sentiments):
            for shot, score in zip(shots, sentiments):
                shot["sentiment"] = score
            print(f"  Shot sentiments: {[f'{s:+.2f}' for s in sentiments]}")

        shots_path.write_text(json.dumps(shots, indent=2), encoding="utf-8")
    else:
        shots = json.loads(shots_path.read_text(encoding="utf-8"))
    print(f"  {len(shots)} shots directed.")

    if use_veo:
        # Veo clips
        clip_paths = sorted(part_dir.glob("clip_0*.mp4"))
        if len(clip_paths) != len(shots):
            print(f"  Generating {len(shots)} Veo clips...")
            clip_paths = generate_clips_veo(shots, part_dir)
        else:
            print(f"  Clips already exist, skipping.")
    else:
        # FLUX images + Ken Burns (free)
        from agents.image_generator import generate_images
        image_paths = sorted(part_dir.glob("image_*.jpg"))
        if len(image_paths) != len(shots):
            print(f"  Generating {len(shots)} images (free)...")
            image_paths = generate_images(shots, part_dir)
        else:
            print(f"  Images already exist, skipping.")

        clip_paths = sorted(part_dir.glob("clip_0*.mp4"))
        if len(clip_paths) != len(shots):
            print(f"  Applying Ken Burns motion...")
            clip_paths = process_images_to_clips(shots, image_paths, part_dir)
        else:
            print(f"  Clips already exist, skipping.")

    # Assemble part video
    part_video = part_dir / "final.mp4"
    if not part_video.exists():
        print(f"  Assembling part video...")
        shot_sentiments = [s.get("sentiment", 0.0) for s in shots] if any("sentiment" in s for s in shots) else None
        part_video = assemble_video(clip_paths, audio_path, srt_path, part_dir, script=script, ending=ending,
                                    shot_sentiments=shot_sentiments)

    # Add title card + end card
    print(f"  Adding title card...")
    titled_video = add_title_card(part_video, series_title, part_num, total_parts, part_dir)

    return titled_video


def main():
    parser = argparse.ArgumentParser(description="Series pipeline — 5-part story")
    parser.add_argument("--theme", type=str)
    parser.add_argument("--ending", choices=["happy", "sad", "bittersweet"])
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--veo", action="store_true", help="Use Veo AI video (~$16/series) instead of free FLUX images")
    parser.add_argument("--series", type=str, help="Resume an existing series folder (e.g. series_20260409_234023)")
    args = parser.parse_args()

    if args.series:
        # Resume mode — load existing series.json, skip already-done work
        series_id = args.series
        series_dir = Path("output") / series_id
        if not series_dir.exists():
            print(f"Series folder not found: {series_dir}")
            sys.exit(1)
        series_data = json.loads((series_dir / "series.json").read_text(encoding="utf-8"))
        print(f"\n{'='*50}")
        print(f" Resuming: {series_id}")
        print(f"{'='*50}\n")
    else:
        series_id = datetime.now().strftime("series_%Y%m%d_%H%M%S")
        series_dir = Path("output") / series_id
        series_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*50}")
        print(f" Series: {series_id}")
        print(f"{'='*50}\n")

        print("[1/3] Generating 5-part series script...")
        series_data = generate_series(theme=args.theme, ending=args.ending)

        # Arc validation — regenerate up to 2 extra times if flat/conflict-free
        print("      Checking emotional arc...")
        for attempt in range(3):
            arc_ok, arc_msg = check_arc([p["script"] for p in series_data["parts"]])
            print(f"      {arc_msg}")
            if arc_ok:
                break
            if attempt < 2:
                print(f"      Regenerating series (attempt {attempt + 2}/3)...")
                series_data = generate_series(theme=args.theme, ending=args.ending)

        (series_dir / "series.json").write_text(json.dumps(series_data, indent=2), encoding="utf-8")

    series_title = series_data["series_title"]
    parts = series_data["parts"]
    total_parts = len(parts)

    if args.series:
        print(f"[1/3] Script loaded: {series_title} ({total_parts} parts)")

    # Run pipeline for each part
    print(f"\n[2/3] Generating {total_parts} parts...")
    titled_videos = []
    for part_data in parts:
        part_num = part_data["part"]
        part_dir = series_dir / f"part_{part_num}"
        part_dir.mkdir(exist_ok=True)
        titled_video = run_part(part_data, part_dir, series_title, part_num, total_parts,
                               character_anchor=series_data.get("character_anchor", ""),
                               ending=args.ending or "",
                               use_veo=args.veo)
        titled_videos.append(titled_video)

    # Assemble long-form
    print(f"\n[3/3] Assembling long-form video...")
    longform_path = assemble_longform(titled_videos, series_dir)
    print(f"  Long-form: {longform_path}")

    print(f"\n{'='*50}")
    print(f" Complete: output/{series_id}/")
    print(f" Shorts:   part_1/part_titled.mp4 ... part_5/part_titled.mp4")
    print(f" Long-form: longform.mp4")
    print(f"{'='*50}\n")

    if not args.no_publish:
        print("To publish, run:")
        for i in range(1, total_parts + 1):
            print(f"  python publish.py --job {series_id}/part_{i} --platforms youtube")
        print(f"  python series_publish.py --series {series_id}  # long-form")


if __name__ == "__main__":
    main()
