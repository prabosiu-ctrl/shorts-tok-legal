"""
Image generator — two modes:

  Default:  FLUX.1-schnell via Replicate ($0.003/image) or HuggingFace (free)
  Series:   fofr/consistent-character via Replicate — generates a character
            reference on the first shot and reuses it for every subsequent
            character shot, keeping faces/clothing visually consistent.

Set CONSISTENT_CHARACTER=0 in .env to disable the consistent-character model
and fall back to FLUX.1-schnell for all shots.
"""

import os
import io
import time
import base64
import requests
from pathlib import Path
from PIL import Image

IMAGE_WIDTH  = 576
IMAGE_HEIGHT = 1024
MAX_PROMPT_CHARS = 220

REPLICATE_FLUX_URL  = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
REPLICATE_CC_URL    = "https://api.replicate.com/v1/models/fofr/consistent-character/predictions"


# ── Replicate helpers ─────────────────────────────────────────────────────────

def _replicate_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ.get('REPLICATE_API_TOKEN', '').strip()}",
        "Content-Type": "application/json",
    }


def _replicate_poll(get_url: str, headers: dict, interval: int = 3, max_attempts: int = 40) -> dict:
    for _ in range(max_attempts):
        time.sleep(interval)
        r = requests.get(get_url, headers=headers, timeout=30)
        data = r.json()
        if data.get("status") == "succeeded":
            return data
        if data.get("status") == "failed":
            raise RuntimeError(f"Replicate failed: {data.get('error')}")
    raise RuntimeError("Replicate timed out")


def _save_output(data: dict, img_path: Path, headers: dict):
    output = data.get("output")
    if not output:
        raise RuntimeError(f"Replicate returned no output: {data}")
    img_url = output[0] if isinstance(output, list) else output
    img_resp = requests.get(img_url, headers=headers, timeout=60)
    img_resp.raise_for_status()
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    img = img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)
    img.save(str(img_path), format="JPEG", quality=90)


# ── FLUX.1-schnell (fast, generic) ────────────────────────────────────────────

def _generate_flux(prompt: str, img_path: Path) -> bool:
    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        return False

    headers = _replicate_headers()
    resp = requests.post(REPLICATE_FLUX_URL, headers=headers, json={
        "input": {
            "prompt": prompt,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "num_outputs": 1,
            "output_format": "jpg",
            "output_quality": 90,
        }
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") not in ("succeeded", None):
        data = _replicate_poll(data["urls"]["get"], headers)

    _save_output(data, img_path, headers)
    return True


# ── fofr/consistent-character (character-locked shots) ───────────────────────

def _generate_consistent_character(
    prompt: str,
    img_path: Path,
    reference_path: Path = None,
) -> bool:
    """
    Generate a shot using fofr/consistent-character.

    First call (no reference_path): generates a character reference image.
    Subsequent calls: pass reference_path to lock the character's appearance.
    """
    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        return False

    headers = _replicate_headers()
    payload: dict = {
        "prompt": prompt,
        "output_format": "jpg",
        "output_quality": 90,
        "number_of_outputs": 1,
        "number_of_images_per_pose": 1,
        "randomise_poses": False,
        "disable_safety_checker": True,
    }

    if reference_path and reference_path.exists():
        b64 = base64.b64encode(reference_path.read_bytes()).decode()
        payload["subject"] = f"data:image/jpeg;base64,{b64}"

    resp = requests.post(REPLICATE_CC_URL, headers=headers,
                         json={"input": payload}, timeout=30)
    if resp.status_code == 404:
        return False  # model unavailable — caller falls back to FLUX
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") not in ("succeeded",):
        data = _replicate_poll(data["urls"]["get"], headers, interval=4, max_attempts=50)

    _save_output(data, img_path, headers)
    return True


# ── HuggingFace fallback ──────────────────────────────────────────────────────

def _generate_huggingface(prompt: str, img_path: Path) -> bool:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return False

    from huggingface_hub import InferenceClient
    client = InferenceClient(api_key=token)
    img = client.text_to_image(
        prompt,
        model="black-forest-labs/FLUX.1-schnell",
        width=IMAGE_WIDTH,
        height=IMAGE_HEIGHT,
    )
    img = img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)
    img.save(str(img_path), format="JPEG", quality=90)
    return True


# ── Main entry ────────────────────────────────────────────────────────────────

def generate_images(
    shots: list[dict],
    work_dir: Path,
    character_ref: Path = None,
    character_anchor: str = "",
) -> list[Path]:
    """
    Generate one image per shot.

    Args:
        shots:           Shot list from scene_director.
        work_dir:        Output directory for image files.
        character_ref:   Path to reference character image (series_dir/character_ref.jpg).
                         If None and consistent-character mode is on, the first character
                         shot generates the reference automatically.
        character_anchor: Character description string — used to detect character shots.
    """
    use_consistent = os.environ.get("CONSISTENT_CHARACTER", "1").strip() != "0"
    image_paths    = []

    for i, shot in enumerate(shots):
        raw    = shot.get("prompt_core") or shot["prompt"]
        prompt = raw.encode("ascii", "ignore").decode()[:MAX_PROMPT_CHARS]

        img_path = work_dir / f"image_{i:03d}.jpg"
        if img_path.exists():
            print(f"  Image {i+1}/{len(shots)}: already exists, skipping.")
            image_paths.append(img_path)
            continue

        print(f"  Image {i+1}/{len(shots)}: {prompt[:75]}...")

        # Determine if this shot contains the protagonist
        has_character = bool(
            character_anchor and character_anchor[:25].lower() in prompt.lower()
        ) or "character" in prompt.lower()

        for attempt in range(4):
            try:
                generated = False

                if use_consistent and has_character:
                    # Use consistent-character for protagonist shots
                    if _generate_consistent_character(prompt, img_path, character_ref):
                        # Promote first generated image to reference for the series
                        if character_ref is None:
                            character_ref = img_path
                            print(f"    Character reference set: image_{i:03d}.jpg")
                        generated = True

                if not generated:
                    # FLUX.1-schnell or HuggingFace for non-character / fallback
                    if not _generate_flux(prompt, img_path):
                        _generate_huggingface(prompt, img_path)

                break

            except Exception as e:
                if attempt < 3:
                    wait = (attempt + 1) * 8
                    print(f"  Retry {attempt + 1} in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Failed image {i + 1} after 4 attempts: {e}")

        image_paths.append(img_path)
        print(f"  Saved: image_{i:03d}.jpg ({img_path.stat().st_size // 1024}KB)")
        time.sleep(1)

    return image_paths
