"""
Image generator using Replicate FLUX.1-schnell.
Cost: ~$0.003/image. Requires REPLICATE_API_TOKEN in environment.
Falls back to HuggingFace if Replicate token not set.
"""

import os
import io
import time
import requests
from pathlib import Path
from PIL import Image

IMAGE_WIDTH = 576
IMAGE_HEIGHT = 1024
MAX_PROMPT_CHARS = 200

REPLICATE_URL = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"


def _generate_replicate(prompt: str, img_path: Path) -> bool:
    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    payload = {
        "input": {
            "prompt": prompt,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "num_outputs": 1,
            "output_format": "jpg",
            "output_quality": 90,
        }
    }

    resp = requests.post(REPLICATE_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # Poll if not completed immediately
    if data.get("status") not in ("succeeded", None):
        get_url = data.get("urls", {}).get("get", "")
        for _ in range(30):
            time.sleep(3)
            r = requests.get(get_url, headers=headers, timeout=30)
            data = r.json()
            if data.get("status") == "succeeded":
                break
            if data.get("status") == "failed":
                raise RuntimeError(f"Replicate prediction failed: {data.get('error')}")

    output = data.get("output")
    if not output:
        raise RuntimeError(f"Replicate returned no output: {data}")

    img_url = output[0] if isinstance(output, list) else output
    img_resp = requests.get(img_url, timeout=60)
    img_resp.raise_for_status()

    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    img.save(str(img_path), format="JPEG", quality=90)
    return True


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
    img.save(str(img_path), format="JPEG", quality=90)
    return True


def generate_images(shots: list[dict], work_dir: Path) -> list[Path]:
    image_paths = []

    for i, shot in enumerate(shots):
        raw = shot.get("prompt_core") or shot["prompt"]
        prompt = raw.encode("ascii", "ignore").decode()[:MAX_PROMPT_CHARS]
        print(f"  Image {i+1}/{len(shots)}: {prompt[:75]}...")

        img_path = work_dir / f"image_{i:03d}.jpg"

        for attempt in range(4):
            try:
                if not _generate_replicate(prompt, img_path):
                    _generate_huggingface(prompt, img_path)
                break
            except Exception as e:
                if attempt < 3:
                    wait = (attempt + 1) * 8
                    print(f"  Retry {attempt+1} in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Failed image {i+1} after 4 attempts: {e}")

        image_paths.append(img_path)
        print(f"  Saved: image_{i:03d}.jpg ({img_path.stat().st_size // 1024}KB)")
        time.sleep(1)

    return image_paths
