"""
Quality Gate — Google Cloud Natural Language API

Runs structured analysis on scripts before committing to expensive generation:
  1. check_arc()           — validates 5-part sentiment trajectory before narration
  2. extract_entities()    — top entities by salience (YouTube tags + shot context)
  3. get_shot_sentiments() — per-shot sentiment for dynamic clip-level color grading
  4. moderate_script()     — content safety check before YouTube upload

Setup:
  In .env, set GOOGLE_CLOUD_API_KEY to a Google Cloud API key with
  Cloud Natural Language API enabled. If not set, falls back to GOOGLE_API_KEY.
  To enable: console.cloud.google.com → APIs → Cloud Natural Language API → Enable.

Cost: ~$0.02 per series (NL API pricing: $1 per 1,000 units, 1 unit = 1,000 chars)
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

NL_V1 = "https://language.googleapis.com/v1"
NL_V2 = "https://language.googleapis.com/v2"

_API_KEY = os.environ.get("GOOGLE_NL_KEY") or os.environ.get("GOOGLE_CLOUD_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")


def _available() -> bool:
    return bool(_API_KEY)


def _post(base: str, endpoint: str, body: dict) -> dict:
    url = f"{base}/documents:{endpoint}?key={_API_KEY}"
    resp = requests.post(url, json=body, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _analyze_sentiment(text: str) -> dict:
    return _post(NL_V1, "analyzeSentiment", {
        "document": {"type": "PLAIN_TEXT", "content": text},
        "encodingType": "UTF8",
    })


def _analyze_entities(text: str) -> dict:
    return _post(NL_V1, "analyzeEntities", {
        "document": {"type": "PLAIN_TEXT", "content": text},
        "encodingType": "UTF8",
    })


def _moderate_text(text: str) -> dict:
    return _post(NL_V2, "moderateText", {
        "document": {"type": "PLAIN_TEXT", "content": text},
    })


# ---------------------------------------------------------------------------

def check_arc(part_scripts: list[str]) -> tuple[bool, str]:
    """
    Validates the emotional arc across all parts before committing to generation.

    Checks:
    - Dramatic range: scores must span at least 0.25 across the series
    - Conflict: at least one part must be negative (there must be tension)

    Returns (is_valid, reason). Always returns True if API key is unavailable.
    """
    if not _available():
        return True, "NL API key not configured — skipping arc check"

    scores = []
    for i, script in enumerate(part_scripts):
        try:
            result = _analyze_sentiment(script)
            score = result["documentSentiment"]["score"]
            magnitude = result["documentSentiment"]["magnitude"]
            scores.append((score, magnitude))
            print(f"    Part {i + 1}: sentiment={score:+.2f}, magnitude={magnitude:.2f}")
        except Exception as e:
            print(f"    Part {i + 1}: arc check skipped ({e})")
            return True, "Arc check skipped due to API error"

    score_vals = [s[0] for s in scores]
    score_range = max(score_vals) - min(score_vals)

    # Flat arc — no journey
    if score_range < 0.25:
        return False, (
            f"Flat arc — all parts score within {score_range:.2f} of each other "
            f"({[f'{s:+.2f}' for s in score_vals]}). No dramatic range."
        )

    # No conflict — all positive, nothing at stake
    if all(s > 0.05 for s in score_vals):
        return False, (
            f"No conflict — all parts positive ({[f'{s:+.2f}' for s in score_vals]}). "
            f"Story needs tension."
        )

    return True, f"Arc valid — range: {score_range:.2f} | scores: {[f'{s:+.2f}' for s in score_vals]}"


def extract_entities(text: str, top_n: int = 10) -> list[str]:
    """
    Returns top N entity names ranked by salience score.

    Use for:
    - Injecting high-salience story elements into shot prompts
    - Enriching YouTube tags beyond LLM-guessed keywords
    """
    if not _available():
        return []

    try:
        result = _analyze_entities(text)
        entities = sorted(
            result.get("entities", []),
            key=lambda e: e["salience"],
            reverse=True,
        )
        return [e["name"] for e in entities[:top_n]]
    except Exception as e:
        print(f"  Entity extraction failed: {e}")
        return []


def get_shot_sentiments(shots: list[dict]) -> list[float]:
    """
    Returns a sentiment score in [-1.0, 1.0] for each shot by analyzing
    its script_segment. Used for per-shot dynamic color grading.

    Negative = cold/blue tint. Positive = warm/amber tint. Near-zero = neutral.
    Returns all-zeros if API is unavailable (falls back to global ending grade).
    """
    if not _available():
        return [0.0] * len(shots)

    sentiments = []
    for shot in shots:
        segment = shot.get("script_segment", "").strip()
        if not segment:
            sentiments.append(0.0)
            continue
        try:
            result = _analyze_sentiment(segment)
            sentiments.append(result["documentSentiment"]["score"])
        except Exception:
            sentiments.append(0.0)

    return sentiments


def moderate_script(text: str) -> tuple[bool, list[str]]:
    """
    Checks script for content policy violations before YouTube upload.
    Returns (is_safe, flagged_categories).

    Falls back to (True, []) if API unavailable or NL v2 not enabled.
    Confidence threshold: 0.7 (70%).
    """
    if not _available():
        return True, []

    try:
        result = _moderate_text(text)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status in (403, 404):
            print(f"  Content moderation skipped (NL API v2 not enabled on this key: {status})")
        else:
            print(f"  Content moderation failed ({status}): {e}")
        return True, []
    except Exception as e:
        print(f"  Content moderation failed: {e}")
        return True, []

    flagged = [
        f"{cat['name']} ({cat['confidence']:.0%})"
        for cat in result.get("moderationCategories", [])
        if cat.get("confidence", 0) > 0.7
    ]
    return len(flagged) == 0, flagged
