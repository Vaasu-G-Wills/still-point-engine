"""
yt_uploader.py — YouTube Data API v3 Upload Module

Handles OAuth 2.0 authentication and video upload.
- First run: opens a browser tab for Google consent → saves token.json
- Subsequent runs: token.json is refreshed automatically (no browser needed)
- Thumbnail is auto-resized to fit YouTube's 2MB limit
"""
import os
import io
import json
import time
import google.oauth2.credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

CLIENT_SECRET_FILE = "client_secret.json"
# TOKEN_FILE is now dynamic based on channel name

# youtube.upload alone is sufficient for uploads; youtube scope adds management
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# YouTube's hard limits
YT_TITLE_MAX_CHARS       = 100
YT_DESCRIPTION_MAX_CHARS = 5000
YT_TAG_TOTAL_MAX_CHARS   = 500   # total characters across ALL tags combined
YT_THUMBNAIL_MAX_BYTES   = 2 * 1024 * 1024  # 2MB


# ─── Auth ─────────────────────────────────────────────────────────────────────

def get_authenticated_service(channel="channel_1"):
    """
    Returns an authenticated YouTube API service object.
    On first run, opens a local browser tab for Google OAuth consent.
    On subsequent runs, refreshes the saved token automatically.
    """
    creds = None
    token_file = f"token_{channel}.json"

    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            token_data = json.load(f)
        creds = google.oauth2.credentials.Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes'),
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.exceptions import RefreshError
            try:
                creds.refresh(Request())
            except RefreshError:
                print("[yt_uploader] Refresh token expired/revoked. Re-authenticating...")
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES
                )
                creds = flow.run_local_server(
                    port=0,
                    open_browser=True,
                    access_type='offline',
                    prompt='consent',
                )
        else:
            # access_type='offline' is REQUIRED to get a refresh_token in testing mode
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(
                port=0,
                open_browser=True,
                access_type='offline',
                prompt='consent',  # always show consent to force refresh_token issuance
            )

        # Persist updated token
        token_data = {
            'token':         creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri':     creds.token_uri,
            'client_id':     creds.client_id,
            'client_secret': creds.client_secret,
            'scopes':        list(creds.scopes),
        }
        with open(token_file, 'w') as f:
            json.dump(token_data, f, indent=2)

    return build("youtube", "v3", credentials=creds)


# ─── Tag sanitiser ────────────────────────────────────────────────────────────

def sanitise_tags(tags: list[str]) -> list[str]:
    """
    Trims the tag list so the TOTAL character count stays under YouTube's
    500-character limit (not 500 items — 500 *characters* combined).
    """
    result  = []
    running = 0
    for tag in tags:
        tag = tag.strip()[:30]  # individual tag max: 30 chars (undocumented but real)
        if not tag:
            continue
        # +1 for the comma separator YouTube counts internally
        if running + len(tag) + 1 > YT_TAG_TOTAL_MAX_CHARS:
            break
        result.append(tag)
        running += len(tag) + 1
    return result


# ─── Upload ───────────────────────────────────────────────────────────────────

def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    category_id: str = "27",
    privacy: str = "private",
    language: str = "en",
    playlist_id: str = None,
    progress_callback = None,
    channel: str = "channel_1"
) -> dict:
    """
    Uploads a video to YouTube with the given metadata.
    Returns a dict with 'video_id' and 'url'.
    """
    if not os.path.exists(CLIENT_SECRET_FILE):
        raise FileNotFoundError(
            f"'{CLIENT_SECRET_FILE}' not found. "
            "Download OAuth credentials from Google Cloud Console (Desktop App type)."
        )

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    youtube    = get_authenticated_service(channel)
    clean_tags = sanitise_tags(tags)

    body = {
        "snippet": {
            "title":                title[:YT_TITLE_MAX_CHARS],
            "description":          description[:YT_DESCRIPTION_MAX_CHARS],
            "tags":                 clean_tags,
            "categoryId":           category_id,
            "defaultLanguage":      language,       # content language
            "defaultAudioLanguage": language,       # audio track language
        },
        "status": {
            "privacyStatus":           privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 2,   # 2MB chunks — more reliable on slow uplinks
    )

    request = youtube.videos().insert(
        part="snippet,status",   # explicit — don't rely on body.keys()
        body=body,
        media_body=media,
    )

    response    = None
    retry_count = 0
    max_retries = 6
    # Transient server errors we retry; client errors we raise immediately
    RETRIABLE_STATUS = {500, 502, 503, 504}

    while response is None:
        try:
            status, response = request.next_chunk()
            if status and progress_callback:
                progress_callback(status.resumable_progress, status.total_size or 1)

        except HttpError as e:
            status_code = e.resp.status
            error_body  = e.content.decode("utf-8", errors="replace")

            # Give actionable messages for the most common testing-mode errors
            if status_code == 403:
                if "quotaExceeded" in error_body or "dailyLimitExceeded" in error_body:
                    raise RuntimeError(
                        "YouTube API daily quota exceeded (10,000 units/day). "
                        "Each upload costs 1,600 units. Wait until midnight PST or "
                        "request a quota increase in Google Cloud Console → "
                        "APIs & Services → YouTube Data API v3 → Quotas."
                    ) from e
                if "forbidden" in error_body.lower():
                    raise RuntimeError(
                        "YouTube API returned 403 Forbidden. "
                        "Make sure your Google account is added as a Test User in "
                        "Google Cloud Console → OAuth consent screen → Test Users."
                    ) from e

            if status_code == 400:
                raise RuntimeError(
                    f"YouTube API rejected the request (400 Bad Request).\n"
                    f"Detail: {error_body}\n"
                    "Common cause: invalid tags, title too long, or bad category ID."
                ) from e

            if status_code in RETRIABLE_STATUS and retry_count < max_retries:
                retry_count += 1
                wait = 2 ** retry_count
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"YouTube API error {status_code}:\n{error_body}"
                ) from e

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"Upload completed but no video ID returned. Response: {response}")

    # ── Add to playlist if specified ──────────────────────────────────────────
    if playlist_id and video_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
        except HttpError:
            pass  # Non-fatal

    return {
        "video_id": video_id,
        "url":      f"https://www.youtube.com/watch?v={video_id}",
        "privacy":  privacy,
    }


# ─── Thumbnail ────────────────────────────────────────────────────────────────

def prepare_thumbnail(thumbnail_path: str) -> tuple[bytes, str]:
    """
    Loads a thumbnail image, auto-resizes it to 1280×720 if needed,
    and compresses it to fit within YouTube's 2MB hard limit.
    Returns (image_bytes, mimetype).
    """
    from PIL import Image

    img = Image.open(thumbnail_path).convert("RGB")

    # Resize to 1280×720 if larger
    if img.width > 1280 or img.height > 720:
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.ANTIALIAS
        img = img.resize((1280, 720), resample)

    # Compress until under 2MB
    quality = 92
    buf = io.BytesIO()
    while quality >= 40:
        buf.seek(0)
        buf.truncate(0)
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= YT_THUMBNAIL_MAX_BYTES:
            break
        quality -= 8

    return buf.getvalue(), "image/jpeg"


def upload_thumbnail(video_id: str, thumbnail_path: str, channel: str = "channel_1") -> bool:
    """
    Sets the custom thumbnail for an already-uploaded video.
    Auto-resizes/compresses to meet YouTube's 2MB limit.
    """
    if not os.path.exists(thumbnail_path):
        return False

    youtube = get_authenticated_service(channel)

    try:
        img_bytes, mimetype = prepare_thumbnail(thumbnail_path)
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaIoBaseUpload(
                io.BytesIO(img_bytes),
                mimetype=mimetype,
                resumable=False,
            ),
        ).execute()
        return True
    except HttpError as e:
        print(f"[yt_uploader] Thumbnail upload failed: {e.resp.status} {e.content}")
        return False


# ─── Post-Upload Archive ──────────────────────────────────────────────────────

def move_to_archive(topic_dir: str, archive_base: str) -> str:
    """
    Moves a completed topic folder to the HDD archive directory.
    Creates `archive_base/Stillpoint Uploaded Videos/` if it doesn't exist.
    Returns the new path.
    """
    import shutil

    archive_root = os.path.join(archive_base, "Stillpoint Uploaded Videos")
    os.makedirs(archive_root, exist_ok=True)

    folder_name = os.path.basename(topic_dir.rstrip("/"))
    dest        = os.path.join(archive_root, folder_name)

    # Avoid collision if the same topic was uploaded twice
    if os.path.exists(dest):
        dest = dest + "_archived"

    shutil.move(topic_dir, dest)
    return dest
