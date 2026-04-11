"""
Uploads a local job folder to Google Drive for Colab to pick up.

One-time setup:
  1. Go to: https://console.cloud.google.com/apis/credentials?project=758500091136
  2. Create Credentials -> OAuth 2.0 Client ID -> Desktop app -> Download JSON
  3. Save it as oauth_client.json in this folder
  4. Run this script — your browser will open to authorize (once only)

Usage:
  python upload_job.py                          # uploads latest job
  python upload_job.py --job 20260404_131120    # uploads specific job
"""

import os
import sys
import pickle
import argparse
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
OAUTH_CLIENT_FILE = "oauth_client.json"
TOKEN_FILE = "token.pickle"
DRIVE_ROOT_FOLDER_NAME = "ShortsTokSwarm"


def get_drive_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CLIENT_FILE):
                print(
                    f"ERROR: {OAUTH_CLIENT_FILE} not found.\n\n"
                    "One-time setup:\n"
                    "  1. Go to https://console.cloud.google.com/apis/credentials?project=758500091136\n"
                    "  2. Create Credentials -> OAuth 2.0 Client ID -> Desktop app\n"
                    "  3. Download JSON and save as oauth_client.json in this folder\n"
                    "  4. Re-run this script"
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("drive", "v3", credentials=creds)


def find_folder(service, name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def create_folder(service, name, parent_id=None):
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def get_or_create_folder(service, name, parent_id=None):
    folder_id = find_folder(service, name, parent_id)
    if not folder_id:
        folder_id = create_folder(service, name, parent_id)
        print(f"  Created folder: {name}")
    return folder_id


def upload_file(service, local_path: Path, parent_folder_id: str):
    mime_types = {
        ".mp3": "audio/mpeg",
        ".srt": "text/plain",
        ".txt": "text/plain",
        ".json": "application/json",
    }
    mime = mime_types.get(local_path.suffix, "application/octet-stream")

    existing = service.files().list(
        q=f"name='{local_path.name}' and '{parent_folder_id}' in parents and trashed=false",
        fields="files(id)"
    ).execute().get("files", [])
    for f in existing:
        service.files().delete(fileId=f["id"]).execute()

    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
    file_meta = {"name": local_path.name, "parents": [parent_folder_id]}
    service.files().create(body=file_meta, media_body=media, fields="id").execute()
    print(f"  Uploaded: {local_path.name}")


def get_latest_job() -> Path:
    output_dir = Path("output")
    jobs = sorted([j for j in output_dir.iterdir() if j.is_dir()], reverse=True)
    if not jobs:
        print("No jobs found in output/")
        sys.exit(1)
    return jobs[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=str, help="Job ID (folder name under output/)")
    args = parser.parse_args()

    job_dir = Path("output") / args.job if args.job else get_latest_job()
    if not job_dir.exists():
        print(f"Job folder not found: {job_dir}")
        sys.exit(1)

    job_id = job_dir.name
    print(f"Uploading job: {job_id}")

    service = get_drive_service()

    root_id = get_or_create_folder(service, DRIVE_ROOT_FOLDER_NAME)
    jobs_folder_id = get_or_create_folder(service, "jobs", root_id)
    job_folder_id = get_or_create_folder(service, job_id, jobs_folder_id)

    files_to_upload = ["script.txt", "audio.mp3", "captions.srt", "scene_prompts.json"]
    for filename in files_to_upload:
        local_file = job_dir / filename
        if local_file.exists():
            upload_file(service, local_file, job_folder_id)
        else:
            print(f"  Skipped (not found): {filename}")

    print(f"\nDone. Job '{job_id}' is ready in Drive.")
    print(f"Open Colab and set: JOB_ID = \"{job_id}\"")


if __name__ == "__main__":
    main()
