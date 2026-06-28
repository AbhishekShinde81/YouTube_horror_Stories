"""
youtube_uploader.py
--------------------
Uploads the final video to YOUR YouTube channel via the YouTube Data API v3.

This requires credentials that only YOU can create (Claude/Anthropic cannot
do this step for you — see README "YouTube setup"):
  1. A Google Cloud project with the YouTube Data API v3 enabled.
  2. An OAuth client (Desktop app type).
  3. A one-time local authorization that produces token.json (refresh token).
token.json is then stored as a GitHub Secret and reused headlessly by the
scheduled workflow — no browser/human needed after that one-time setup.

Defaults to uploading as UNLISTED ("review" mode in config.yaml) so you can
sanity-check each video before it goes public. This also meaningfully
reduces the risk of YouTube's inauthentic-content system flagging a channel
that has literally zero human review (see README "Monetization risk").
"""
import json
import sys
from pathlib import Path

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def get_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            "token.json not found. Run `python src/youtube_uploader.py --authorize` "
            "locally once (see README YouTube setup) to create it, then store its "
            "contents as the YOUTUBE_TOKEN_JSON GitHub secret."
        )
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_PATH.read_text()), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def authorize_interactively() -> None:
    """Run this once, locally, on a machine with a browser."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret_path = ROOT / "client_secret.json"
    if not client_secret_path.exists():
        raise RuntimeError(
            "Download your OAuth client's client_secret.json from Google Cloud Console "
            "and place it at the project root, then re-run this command."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Wrote {TOKEN_PATH}. Copy its contents into the YOUTUBE_TOKEN_JSON GitHub secret.")


def run(story_path: str, video_path: str) -> str:
    cfg = load_config()
    story = json.loads(Path(story_path).read_text())
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    privacy = "unlisted" if cfg["run"]["publish_mode"] == "review" else "public"

    body = {
        "snippet": {
            "title": story["youtube_title"],
            "description": story["description"] + "\n\n#horror #shorts #scarystory",
            "tags": cfg["youtube"]["default_tags"] + story.get("tags", []),
            "categoryId": cfg["youtube"]["category_id"],
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": cfg["youtube"]["made_for_kids"],
        },
    }
    if cfg["youtube"]["self_certify_synthetic"]:
        # "Altered or synthetic content" disclosure (YouTube Studio's required checkbox
        # for realistic AI-generated content). Field name per current Data API docs —
        # verify against the latest YouTube Data API reference before relying on this,
        # API surfaces for this disclosure have been changing.
        body["status"]["containsSyntheticMedia"] = True

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[youtube_uploader] upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"[youtube_uploader] uploaded as {privacy}: https://youtu.be/{video_id}")
    return video_id


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--authorize":
        authorize_interactively()
    elif len(sys.argv) == 3:
        run(sys.argv[1], sys.argv[2])
    else:
        print("usage:\n  python youtube_uploader.py --authorize\n"
              "  python youtube_uploader.py <story.json> <final_video.mp4>")
        sys.exit(1)
