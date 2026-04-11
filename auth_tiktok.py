"""
One-time TikTok OAuth setup.
Run this once to authorize your TikTok account.
Saves a token to tiktok_token.json for the publisher to reuse.

Usage:
    python auth_tiktok.py
"""

import os
import json
import hashlib
import base64
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from dotenv import load_dotenv

import requests

load_dotenv()

TOKEN_FILE = "tiktok_token.json"
REDIRECT_URI = "http://localhost:8080/callback/"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


class CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    state_received = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback/":
            params = parse_qs(parsed.query)
            CallbackHandler.auth_code = params.get("code", [None])[0]
            CallbackHandler.state_received = params.get("state", [None])[0]

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style='font-family:sans-serif;text-align:center;padding:60px'>
                <h2>Authorized.</h2>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
            """)

    def log_message(self, format, *args):
        pass  # Suppress server logs


def main():
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()

    if not client_key or not client_secret:
        print("ERROR: TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set in .env")
        return

    # PKCE S256 — canonical format: base64url(random bytes) as verifier
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    state = base64.urlsafe_b64encode(os.urandom(8)).rstrip(b"=").decode("ascii")

    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": "video.publish,video.upload",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"{AUTH_URL}?{urlencode(params)}"
    print(f"Opening browser for TikTok authorization...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Start local server to catch the redirect
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    print("Waiting for authorization (listening on http://localhost:8080/callback/)...")
    while CallbackHandler.auth_code is None:
        server.handle_request()
    server.server_close()

    if CallbackHandler.state_received != state:
        print("ERROR: State mismatch. Possible CSRF attack. Aborting.")
        return

    auth_code = CallbackHandler.auth_code
    print(f"Authorization code received. Exchanging for token...")
    print(f"  code_verifier ({len(code_verifier)} chars): {code_verifier}")
    print(f"  code_challenge: {code_challenge}")
    print(f"  auth_code: {auth_code[:20]}...")

    resp = requests.post(TOKEN_URL, data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    print(f"  Response {resp.status_code}: {resp.text}")

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed ({resp.status_code}): {resp.text}")
        return

    token_data = resp.json()
    if "error" in token_data:
        print(f"ERROR: {token_data.get('error')}: {token_data.get('error_description')}")
        return

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"Done. Token saved to {TOKEN_FILE}")
    print(f"Open ID: {token_data.get('open_id')}")
    print("You can now run: python publish.py --job <JOB_ID>")


if __name__ == "__main__":
    main()
