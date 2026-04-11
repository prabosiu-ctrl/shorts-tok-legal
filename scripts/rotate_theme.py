"""
Returns the next story theme for series generation.

Priority:
  1. themes.txt — use next line, remove it (manual curation)
  2. Auto-generate — if themes.txt is empty, ask Gemini for 10 fresh themes,
     save them to themes.txt, and return the first.

Used by GitHub Actions (daily_series.yml) and can be run locally.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

THEMES_FILE = Path(__file__).parent.parent / "themes.txt"

EMOTIONAL_ANCHORS = [
    "grief and unexpected discovery",
    "betrayal by someone trusted",
    "reunion after long absence",
    "a long-kept secret finally surfacing",
    "sacrifice that goes unrecognised",
    "identity hidden from someone who loved them",
    "forgiveness that arrives too late",
    "a stranger who knows more than they should",
    "the moment a lie becomes impossible to maintain",
    "something returned that was thought lost forever",
]


def _generate_themes() -> list[str]:
    """Ask Gemini to generate 10 fresh emotionally resonant story premises."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return []

    client = genai.Client(api_key=api_key)
    anchors_str = "\n".join(f"- {a}" for a in EMOTIONAL_ANCHORS)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            f"Generate 10 original story premises for short-form vertical video (TikTok/Reels/Shorts).\n\n"
            f"Each premise must explore one of these emotional anchors:\n{anchors_str}\n\n"
            f"Rules:\n"
            f"- One sentence per premise. Specific and vivid — name the character type and the exact situation.\n"
            f"- Contemporary realism only. No sci-fi, no fantasy, no supernatural.\n"
            f"- Each premise must feel like the first sentence of a story someone cannot stop watching.\n"
            f"- No two premises should share the same emotional anchor.\n\n"
            f"Return a JSON array of 10 strings."
        ),
        config=types.GenerateContentConfig(
            temperature=0.95,
            response_mime_type="application/json",
        ),
    )

    try:
        data = json.loads(response.text)
        if isinstance(data, list):
            return [str(t) for t in data if t]
        if isinstance(data, dict):
            return [str(t) for t in (data.get("themes") or data.get("premises") or []) if t]
    except Exception:
        pass
    return []


def main():
    lines = THEMES_FILE.read_text(encoding="utf-8").splitlines() if THEMES_FILE.exists() else []
    candidates = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]

    # If themes.txt is exhausted, generate fresh ones
    if not candidates:
        print("themes.txt empty — generating fresh themes with Gemini...", flush=True)
        new_themes = _generate_themes()
        if new_themes:
            THEMES_FILE.write_text("\n".join(new_themes) + "\n", encoding="utf-8")
            candidates = new_themes
            print(f"  Generated {len(new_themes)} new themes.", flush=True)

    if not candidates:
        print("", end="")  # empty — scriptwriter will use its own fallback
        return

    # Pop and return the first theme
    theme = candidates[0]
    remaining = candidates[1:]
    THEMES_FILE.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    print(theme, end="")


if __name__ == "__main__":
    main()
