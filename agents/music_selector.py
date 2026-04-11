"""
Music Selector — picks a background music track from assets/music/.

Uses Gemini to match the script's emotional tone to an available track.
Falls back to random selection if Gemini fails or no script provided.
Returns None if no music files are present (pipeline continues without music).
"""

import os
import random
from pathlib import Path
from google import genai
from google.genai import types

MUSIC_DIR = Path(__file__).parent.parent / "assets" / "music"


def select_music(script: str = "") -> Path | None:
    """
    Select the best matching music file for the given script.

    Returns the Path to an MP3 file, or None if no music files exist.
    """
    tracks = sorted(MUSIC_DIR.glob("*.mp3"))
    if not tracks:
        return None

    if len(tracks) == 1 or not script:
        chosen = random.choice(tracks)
        print(f"  Music: {chosen.name} (random)")
        return chosen

    # Ask Gemini to pick the best track by filename
    track_names = "\n".join(f"- {t.name}" for t in tracks)

    try:
        api_key = os.environ.get("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=(
                f"Script:\n{script[:600]}\n\n"
                f"Available music tracks:\n{track_names}\n\n"
                "Reply with ONLY the exact filename of the best matching track. "
                "Choose based on emotional tone: sad/loss → melancholic piano/strings, "
                "happy → warm acoustic/upbeat, bittersweet → cinematic strings, "
                "tense/dark → dark orchestral. No explanation."
            ),
            config=types.GenerateContentConfig(temperature=0.2),
        )

        chosen_name = response.text.strip().strip('"').strip("'")
        match = next((t for t in tracks if t.name == chosen_name), None)

        if match:
            print(f"  Music: {match.name} (Gemini pick)")
            return match

    except Exception:
        pass

    # Fallback: random
    chosen = random.choice(tracks)
    print(f"  Music: {chosen.name} (random fallback)")
    return chosen
