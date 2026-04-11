"""
Encodes youtube_token.pickle as base64 for the YOUTUBE_TOKEN_B64 GitHub secret.

Usage:
    python scripts/encode_yt_token.py

Copy the printed string into:
    GitHub repo → Settings → Secrets → YOUTUBE_TOKEN_B64
"""

import base64
from pathlib import Path

token_file = Path("youtube_token.pickle")
if not token_file.exists():
    print("youtube_token.pickle not found. Run auth_youtube.py first.")
else:
    encoded = base64.b64encode(token_file.read_bytes()).decode()
    print(encoded)
