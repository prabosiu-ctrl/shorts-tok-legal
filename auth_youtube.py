"""
One-time YouTube OAuth setup.
Run this once to authorize your YouTube channel.
Saves a token to youtube_token.pickle for the publisher to reuse.

Usage:
    python auth_youtube.py
"""

import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube",          # read + update metadata, manage playlists
    "https://www.googleapis.com/auth/youtube.upload",   # upload videos
]
OAUTH_CLIENT_FILE = "oauth_client.json"
TOKEN_FILE = "youtube_token.pickle"


def main():
    if not os.path.exists(OAUTH_CLIENT_FILE):
        print(
            f"ERROR: {OAUTH_CLIENT_FILE} not found.\n"
            "Get it from: https://console.cloud.google.com/apis/credentials?project=758500091136\n"
            "Create Credentials -> OAuth 2.0 Client ID -> Desktop app -> Download JSON"
        )
        return

    print("Opening browser for YouTube authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)

    print(f"Done. Token saved to {TOKEN_FILE}")
    print("You can now run: python publish.py --job <JOB_ID>")


if __name__ == "__main__":
    main()
