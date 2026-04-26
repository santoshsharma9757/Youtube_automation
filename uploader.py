from __future__ import annotations

import logging
from pathlib import Path

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

    def upload_short(self, video_path: Path, seo: SeoPackage, publish_at: str | None = None) -> dict:
        client_secrets = Path(self.config.youtube_client_secrets_file)
        if not client_secrets.exists():
            raise FileNotFoundError(
                f"YouTube client secrets file was not found: {client_secrets.resolve()}"
            )
        LOGGER.info("Uploading short to YouTube: %s (Scheduled for: %s)", video_path, publish_at or "Immediate")
        youtube = build("youtube", "v3", credentials=self._load_credentials())
        
        status_body = {
            "privacyStatus": self.config.default_privacy_status if not publish_at else "private",
            "selfDeclaredMadeForKids": False,
        }
        if publish_at:
            status_body["publishAt"] = publish_at

        body = {
            "snippet": {
                "title": seo.title,
                "description": seo.description,
                "tags": seo.tags,
                "categoryId": self.config.youtube_category_id,
                "defaultLanguage": seo.language_code,
                "defaultAudioLanguage": seo.audio_language_code,
            },
            "status": status_body,
        }

        # Attempt to enable monetization if the user is a partner
        # We try this first; if it fails with 403, we fall back to a standard upload
        try:
            request = youtube.videos().insert(
                part="snippet,status,monetizationDetails",
                body={**body, "monetizationDetails": {"access": {"monetization": "true"}}},
                media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
            )
            response = None
            while response is None:
                _, response = request.next_chunk()
        except Exception as e:
            if "forbidden" in str(e).lower() or "403" in str(e):
                LOGGER.warning("Monetization access denied (channel might not be a Partner). Falling back to standard upload.")
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

        LOGGER.info("Upload complete with video id %s", response["id"])
        return response

    def _load_credentials(self) -> Credentials:
        token_path = Path(self.config.youtube_token_file)
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(self.config.youtube_client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds
