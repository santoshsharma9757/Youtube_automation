from __future__ import annotations

import logging
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import AppConfig
from seo_generator import SeoPackage


LOGGER = logging.getLogger(__name__)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube"
]


class YouTubeUploader:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def sanitize_tags(self, tags: list[str]) -> list[str]:
        import re
        sanitized = []
        total_len = 0
        for tag in tags:
            # Keep only standard English letters, numbers, and space to prevent any API crashes
            clean_tag = re.sub(r'[^a-zA-Z0-9 ]', '', tag).strip()
            if not clean_tag:
                continue
            clean_tag = re.sub(r'\s+', ' ', clean_tag)[:40].strip()
            # Separators are commas in API, so add 1 for the comma (except the first tag)
            tag_len = len(clean_tag) + (1 if sanitized else 0)
            if len(sanitized) >= 15 or total_len + tag_len > 350:
                break
            sanitized.append(clean_tag)
            total_len += tag_len
        return sanitized

    def upload_short(self, video_path: Path, seo: SeoPackage, publish_at: str | None = None) -> dict:
        client_secrets = Path(self.config.youtube_client_secrets_file)
        if not client_secrets.exists():
            raise FileNotFoundError(
                f"YouTube client secrets file was not found: {client_secrets.resolve()}"
            )
        LOGGER.info("Uploading short to YouTube: %s (Scheduled for: %s)", video_path, publish_at or "Immediate")
        youtube = build("youtube", "v3", credentials=self._load_credentials())
        
        # CRITICAL FIX: COPPA ("Made for Kids") completely disables the viral Shorts Feed
        # because the feed algorithm requires personalized tracking. Shorts must be
        # targeted at "Family/Parents" (Not Made for Kids) to get views.
        status_body = {
            "privacyStatus": self.config.default_privacy_status if not publish_at else "private",
            "selfDeclaredMadeForKids": False,  # Forced false for Shorts feed algorithm
            "containsSyntheticMedia": True,
        }
        if publish_at:
            status_body["publishAt"] = publish_at

        body = {
            "snippet": {
                "title": seo.title,
                "description": seo.description,
                "tags": self.sanitize_tags(seo.tags),
                "categoryId": "1",   # 1 = Film & Animation — Wonder Stories TV
                "defaultLanguage": seo.language_code,
                "defaultAudioLanguage": seo.audio_language_code,
            },
            "status": status_body,
        }
        print("SANITIZED TAGS TO YOUTUBE API:", body["snippet"]["tags"])

        if self.config.youtube_enable_monetization:
            # Only request monetization for partner-enabled channels.
            request = youtube.videos().insert(
                part="snippet,status,monetizationDetails",
                body={**body, "monetizationDetails": {"access": {"monetization": "true"}}},
                media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
            )
            try:
                response = None
                while response is None:
                    _, response = request.next_chunk()
            except Exception as e:
                if "forbidden" in str(e).lower() or "403" in str(e):
                    LOGGER.warning("Monetization access denied. Disabling monetization for this upload and falling back to standard insert.")
                    request = youtube.videos().insert(
                        part="snippet,status",
                        body=body,
                        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
                    )
                    response = None
                    while response is None:
                        _, response = request.next_chunk()
                else:
                    raise e
        else:
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
            )
            response = None
            while response is None:
                _, response = request.next_chunk()

        LOGGER.info("Upload complete with video id %s", response["id"])
        return response

    def _load_credentials(self) -> Credentials:
        token_path = Path(self.config.youtube_token_file)
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                LOGGER.warning("Token expired or revoked. Forcing re-authentication.")
                creds = None
                if token_path.exists():
                    token_path.unlink()

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(self.config.youtube_client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds
