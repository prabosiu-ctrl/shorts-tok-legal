"""
Gemini Scene Director

Two modes:
  mode="images"  — directs still photographs for FLUX + Ken Burns (free, default)
  mode="video"   — directs 8s video clips for Veo (paid, use --veo flag)
"""

import os
import json
from google import genai
from google.genai import types


IMAGE_SYSTEM_PROMPT = """You are a stills photographer and photo editor creating a cinematic photo slideshow for a short story narration.

Each "shot" is a single photograph — not a video. You are directing still images, not motion.

## Core Rules
- 7 to 9 images total. Each image covers a specific beat in the narration.
- Image durations: 6, 8, or 10 seconds only. Total must sum within 2 seconds of audio duration.
- 6s = punchy/fast beat. 8s = steady beat. 10s = the emotional peak (once, on the final image).
- Map each image to the exact narration words it plays over.

## Prompt Construction
1. ONE subject per image. One thing in focus. Everything else is background.
2. Describe what IS in frame — not what is happening. It's a photograph, frozen in time.
3. NO action verbs. Say "a green canvas bag resting on worn floorboards" not "a bag dropping".
4. NO wide shots in 9:16 vertical. Use: extreme close-up, close-up, medium close-up, medium shot, full body, over-shoulder, low angle, high angle POV.
5. Character anchor: define the character once (age, build, hair, clothing) and use the EXACT same description in every shot they appear.
6. Motivated lighting: every image must have a clear, specific light source. No generic "soft lighting".
7. Colour grade direction: one phrase. "Deep shadows, amber midtones." "Crushed blacks, warm highlights."

## Ken Burns Motion (per image)
- "slow_zoom_in" — slow push toward subject (intimacy, tension)
- "slow_zoom_out" — slow pull back (isolation, reveal)
- "slow_pan_left" / "slow_pan_right" — slow drift
- "static" — no motion (stillness, weight)

Use "slow_zoom_in" on the emotional peak. Use "static" sparingly.

RESPONSE FORMAT — valid JSON only, no markdown fences:
{
  "character_anchor": "Exact physical description reused in every shot with the character",
  "shots": [
    {
      "duration": 8,
      "script_segment": "Exact narration words this image plays over",
      "prompt": "Single subject, frozen state, camera angle, motivated lighting, colour grade — NO style prefix",
      "motion": "slow_zoom_in"
    }
  ]
}"""


VIDEO_SYSTEM_PROMPT = """You are a cinematographer directing 8-second video clips for Google Veo, an AI video generation model.

Each clip is EXACTLY 8 seconds of motion video. You are not directing stills.

## Core Rules
- 7 to 9 shots total. Each shot covers one beat in the narration.
- Every shot is exactly 8 seconds — do NOT vary duration.
- Map each shot to the exact narration words it plays over.

## Prompt Construction
Structure each prompt as a single dense paragraph:
  [SHOT TYPE]. [SUBJECT — full physical description + what they are doing over 8 seconds]. [LOCATION with one specific detail]. [LIGHT SOURCE — named, directional, quality]. [CAMERA MOVEMENT]. [CINEMATIC STYLE — one sentence].

Rules:
1. ONE subject per shot.
2. Describe the CHARACTER FULLY every shot they appear. Age, build, hair, specific clothing. NEVER use pronouns. Copy verbatim each time.
3. Describe MOTION that unfolds over 8 seconds. What does the subject do? How does the camera move?
4. Shot types: extreme close-up, close-up, medium close-up, medium shot, over-the-shoulder, low angle, high angle.
5. Motivated lighting: name the specific source. "Warm amber from a single lamp to the left." "Hard overhead fluorescent."
6. Camera: "Camera slowly pushes in toward her face." "Static camera, subject walks toward lens." "Slow tilt up."
7. Style: reference a real cinematographer or film stock. "Shot on ARRI Alexa, shallow depth of field, warm skin tones."

## Character Anchor
Define the character once as "character_anchor". Use EXACT description in every shot containing that character.

## No Music or Sound Cues
Sound design is handled separately.

RESPONSE FORMAT — valid JSON only, no markdown fences:
{
  "character_anchor": "Exact physical description used verbatim in every character shot",
  "shots": [
    {
      "script_segment": "Exact narration words this clip plays over",
      "prompt": "Medium close-up. A 38-year-old woman, slight build, dark brown hair in a loose bun, wearing a faded olive-green hospital scrub top, stands frozen in a corridor holding a patient file. Cold fluorescent light from overhead. Camera slowly pushes in. Shot on ARRI Alexa, desaturated greens and greys."
    }
  ]
}"""


def direct_scenes(script: str, audio_duration: float, character_anchor: str = "", mode: str = "images", context_entities: list = None) -> list[dict]:
    """
    Generate shot briefs from a narration script.

    Args:
        script: The narration text.
        audio_duration: Audio length in seconds.
        character_anchor: Pre-defined character description (overrides Gemini's if provided).
        mode: "images" for FLUX stills + Ken Burns (default/free), "video" for Veo clips (paid).
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    system_prompt = VIDEO_SYSTEM_PROMPT if mode == "video" else IMAGE_SYSTEM_PROMPT
    n_shots = max(7, min(9, round(audio_duration / 8)))

    entity_hint = ""
    if context_entities:
        entity_hint = f"\nKey story elements to ground visually: {', '.join(context_entities[:6])}\n"

    prompt = (
        f"Audio duration: {audio_duration:.1f} seconds\n"
        f"Target shots: {n_shots}\n"
        f"{entity_hint}\n"
        f"Script:\n{script}\n\n"
        "Create the shot list now."
    )

    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.6,
            response_mime_type="application/json",
        ),
    )

    data = json.loads(response.text)
    shots = data.get("shots", [])
    anchor = character_anchor or data.get("character_anchor", "")

    if not shots:
        raise ValueError("Scene director returned no shots.")

    if mode == "images":
        valid_durations = {6, 8, 10}
        valid_motions = {"slow_zoom_in", "slow_zoom_out", "slow_pan_left", "slow_pan_right", "static"}
        for shot in shots:
            if shot.get("duration") not in valid_durations:
                shot["duration"] = 8
            if shot.get("motion") not in valid_motions:
                shot["motion"] = "slow_zoom_in"

        # Inject style prefix and character anchor for image generation
        style_prefix = os.environ.get("STYLE_PREFIX", "").strip()
        for shot in shots:
            core = shot.get("prompt", "")
            shot["prompt_core"] = core  # kept clean for image API
            base = core
            if anchor:
                base = f"{base} Character appearance: {anchor}."
            shot["prompt"] = f"{style_prefix}, {base}" if style_prefix else base

        total = sum(s["duration"] for s in shots)
        print(f"      {len(shots)} shots | {total}s video | {audio_duration:.1f}s audio | mode: images (free)")

    else:  # video
        for shot in shots:
            if anchor and anchor[:30] not in shot.get("prompt", ""):
                shot["prompt"] = shot["prompt"].rstrip(".") + f". Character: {anchor}."

        total_estimated = len(shots) * 8
        print(f"      {len(shots)} shots | ~{total_estimated}s video | {audio_duration:.1f}s audio | mode: Veo (${len(shots) * 8 * 0.05:.2f} est.)")

    if anchor:
        print(f"      Anchor: {anchor[:80]}")

    return shots
