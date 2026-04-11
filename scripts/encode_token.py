"""
Helper to base64-encode youtube_token.pickle for use as a GitHub Actions Secret.

Usage:
    python scripts/encode_token.py

Copy the printed value into GitHub → Settings → Secrets → YOUTUBE_TOKEN_B64.
The workflow will decode it back to youtube_token.pickle at runtime.
"""

import base64
from pathlib import Path

TOKEN_FILE = Path("youtube_token.pickle")

if not TOKEN_FILE.exists():
    print("youtube_token.pickle not found. Run auth_youtube.py first.")
else:
    encoded = base64.b64encode(TOKEN_FILE.read_bytes()).decode("utf-8")
    print("Copy this value into GitHub Secret YOUTUBE_TOKEN_B64:\n")
    print(encoded)
