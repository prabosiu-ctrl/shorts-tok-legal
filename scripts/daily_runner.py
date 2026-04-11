"""
Daily Series Runner — GitHub Actions orchestrator

Runs once per day. State persists in state.json (committed to repo).

Timeline per series (7 clips/part, Veo 10 RPD limit):
  Day 0: Generate scripts + arc check — no Veo used
  Day 1: Generate & assemble Part 1 → upload PRIVATE
  Day 2: Generate & assemble Part 2 → upload PRIVATE
  ...
  Day 5: Generate & assemble Part 5 → upload PRIVATE
  Day 6: Assemble longform → upload PUBLIC + create playlist
  Day 7: New series starts (back to Day 0)

Parts drip-feed to PUBLIC via schedule_publish.py (publish_part.yml).

Usage:
    python scripts/daily_runner.py [--veo] [--dry-run] [--theme "..."] [--ending bittersweet]
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from series_run import run_part, assemble_longform
from series_publish import upload_video, create_playlist, add_to_playlist
from agents.series_scriptwriter import generate_series
from agents.quality_gate import check_arc, moderate_script
from agents.youtube_publisher import get_youtube_service, generate_metadata

STATE_FILE = ROOT / "state.json"
QUEUE_FILE  = ROOT / "queue.json"


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"active_series": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_queue() -> dict:
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    return {"pending": [], "published": []}


def save_queue(queue: dict):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")


# ── Series generation ─────────────────────────────────────────────────────────

def generate_new_series(theme=None, ending=None) -> dict:
    """Generate scripts with arc validation (up to 3 attempts)."""
    print("[Scripts] Generating 5-part series...")
    series_data = generate_series(theme=theme, ending=ending)

    print("  Checking emotional arc...")
    for attempt in range(3):
        arc_ok, arc_msg = check_arc([p["script"] for p in series_data["parts"]])
        print(f"  {arc_msg}")
        if arc_ok:
            break
        if attempt < 2:
            print(f"  Regenerating (attempt {attempt + 2}/3)...")
            series_data = generate_series(theme=theme, ending=ending)

    return series_data


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Daily series runner for GitHub Actions")
    parser.add_argument("--veo", action="store_true", help="Use Veo for clip generation")
    parser.add_argument("--dry-run", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--theme", type=str)
    parser.add_argument("--ending", choices=["happy", "sad", "bittersweet"])
    args = parser.parse_args()

    state  = load_state()
    active = state.get("active_series")

    print(f"\n{'='*52}")
    print(f"  Daily Series Runner — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*52}\n")

    # ── No active series OR previous series fully complete ────────────────────
    if not active or active.get("complete"):
        series_data = generate_new_series(theme=args.theme, ending=args.ending)

        series_id  = datetime.utcnow().strftime("series_%Y%m%d_%H%M%S")
        series_dir = ROOT / "output" / series_id
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "series.json").write_text(json.dumps(series_data, indent=2), encoding="utf-8")

        active = {
            "series_id":        series_id,
            "series_title":     series_data["series_title"],
            "total_parts":      len(series_data["parts"]),
            "character_anchor": series_data.get("character_anchor", ""),
            "ending":           args.ending or "",
            "parts_generated":  [],
            "part_video_ids":   [],   # list of [video_id, label]
            "longform_done":    False,
            "playlist_id":      None,
            "complete":         False,
        }
        state["active_series"] = active
        save_state(state)

        print(f"New series: '{series_data['series_title']}' ({series_id})")
        print(f"Scripts saved. Part 1 generates on the next daily run.")
        return

    # ── Active series — load data ─────────────────────────────────────────────
    series_id      = active["series_id"]
    series_dir     = ROOT / "output" / series_id
    series_data    = json.loads((series_dir / "series.json").read_text(encoding="utf-8"))
    parts          = series_data["parts"]
    total_parts    = active["total_parts"]
    parts_generated = active["parts_generated"]

    print(f"Series:     {active['series_title']}")
    print(f"Progress:   {len(parts_generated)}/{total_parts} parts generated\n")

    # ── All parts generated — assemble longform + finalise ────────────────────
    if len(parts_generated) == total_parts and not active["longform_done"]:
        print("[Longform] Assembling all parts...")

        titled_videos = []
        for i in range(1, total_parts + 1):
            v = series_dir / f"part_{i}" / "part_titled.mp4"
            if not v.exists():
                v = series_dir / f"part_{i}" / "final.mp4"
            if not v.exists():
                print(f"  WARNING: part_{i} video not found — longform skipped.")
                return
            titled_videos.append(v)

        longform_path = assemble_longform(titled_videos, series_dir)
        print(f"  Longform: {longform_path}")

        if not args.dry_run:
            youtube = get_youtube_service()

            # Build chapter description
            chapters = "Chapters:\n"
            ts = 0
            for p in parts:
                mins, secs = divmod(int(ts), 60)
                chapters += f"{mins:02d}:{secs:02d} Part {p['part']} — {p['title']}\n"
                ts += 72

            description = (
                f"The complete story of '{active['series_title']}' — all {total_parts} parts in one video.\n\n"
                f"{chapters}\n#Story #ShortFilm #AIStory"
            )
            lf_url = upload_video(
                youtube, longform_path,
                title=f"{active['series_title']} | Full Story",
                description=description,
                tags=[active["series_title"], "short film", "AI story", "drama", "series"],
                privacy="public",
                is_short=False,
            )
            lf_id = lf_url.split("=")[-1]
            print(f"  Longform live: {lf_url}")

            # Create playlist — longform first, then individual parts
            playlist_id = create_playlist(
                youtube,
                active["series_title"],
                description=f"All {total_parts} episodes of '{active['series_title']}'.\n#Story #AIStory #Shorts",
            )
            add_to_playlist(youtube, playlist_id, lf_id, position=0)
            for pos, (vid, lbl) in enumerate(active["part_video_ids"], start=1):
                add_to_playlist(youtube, playlist_id, vid, position=pos)
                print(f"  Playlist: added {lbl}")

            active["playlist_id"] = playlist_id

            # Persist playlist_id in queue.json
            queue = load_queue()
            queue["playlist_id"] = playlist_id
            save_queue(queue)

        active["longform_done"] = True
        active["complete"]      = True
        state["active_series"]  = active
        save_state(state)

        print(f"\nSeries complete! New series starts on the next daily run.")
        return

    # ── Generate next part ────────────────────────────────────────────────────
    next_part_num = next(p["part"] for p in parts if p["part"] not in parts_generated)
    part_data     = next(p for p in parts if p["part"] == next_part_num)
    part_dir      = series_dir / f"part_{next_part_num}"
    part_dir.mkdir(exist_ok=True)

    print(f"[Part {next_part_num}/{total_parts}] {part_data['title']}")

    titled_video = run_part(
        part_data, part_dir,
        series_title=active["series_title"],
        part_num=next_part_num,
        total_parts=total_parts,
        character_anchor=active.get("character_anchor", ""),
        ending=active.get("ending", ""),
        use_veo=args.veo,
    )

    # ── Upload to YouTube as PRIVATE ──────────────────────────────────────────
    if not args.dry_run:
        # Content moderation gate
        script_text = (part_dir / "script.txt").read_text(encoding="utf-8") if (part_dir / "script.txt").exists() else ""
        if script_text:
            is_safe, flagged = moderate_script(script_text)
            if not is_safe:
                print(f"  Content flagged: {', '.join(flagged)} — skipping upload.")
                sys.exit(1)

        youtube  = get_youtube_service()
        metadata = generate_metadata(script_text)

        title       = f"{active['series_title']} - Part {next_part_num} of {total_parts}: {part_data['title']}"
        description = metadata.get("description", "") + f"\n\n#Shorts #Story #AIStory #{active['series_title'].replace(' ', '')}"
        tags        = metadata.get("tags", []) + [active["series_title"], f"Part {next_part_num}"]

        url      = upload_video(youtube, titled_video, title=title, description=description,
                                tags=tags, privacy="private", is_short=True)
        video_id = url.split("/")[-1].split("=")[-1]
        print(f"\n  Uploaded (private): {url}")

        # Add to daily publish queue
        queue = load_queue()
        queue.setdefault("series_id",    series_id)
        queue.setdefault("series_title", active["series_title"])
        queue.setdefault("pending",      [])
        queue.setdefault("published",    [])
        queue["pending"].append({"video_id": video_id, "label": f"Part {next_part_num}: {part_data['title'][:40]}"})
        save_queue(queue)

        active["part_video_ids"].append([video_id, f"Part {next_part_num}: {part_data['title'][:40]}"])

    # ── Update state ──────────────────────────────────────────────────────────
    parts_generated.append(next_part_num)
    active["parts_generated"] = parts_generated
    state["active_series"]    = active
    save_state(state)

    remaining = total_parts - len(parts_generated)
    print(f"\nPart {next_part_num} complete. {remaining} part(s) remaining.")
    if remaining > 0:
        print(f"Part {next_part_num + 1} generates on the next daily run.")
    else:
        print(f"All parts done. Longform assembles on the next daily run.")


if __name__ == "__main__":
    main()
