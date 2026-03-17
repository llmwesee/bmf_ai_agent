from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from functools import lru_cache
from typing import Any

from bfm_agent.config import Settings, get_settings


READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


@dataclass(frozen=True)
class GmailStatus:
    configured: bool
    detail: str


@dataclass(frozen=True)
class SendResult:
    status: str
    thread_id: str | None
    message_id: str | None
    detail: str


@dataclass(frozen=True)
class GmailReply:
    thread_id: str
    message_id: str | None
    sender_email: str | None
    subject: str
    body: str
    received_at: datetime | None


def _import_google_clients():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception as exc:  # pragma: no cover - exercised indirectly via status checks
        return None, None, None, str(exc)
    return Request, Credentials, build, None


def _required_settings(settings: Settings) -> list[tuple[str, str | None]]:
    return [
        ("GMAIL_CLIENT_ID", settings.gmail_client_id),
        ("GMAIL_CLIENT_SECRET", settings.gmail_client_secret),
        ("GMAIL_REFRESH_TOKEN", settings.gmail_refresh_token),
        ("GMAIL_USER_EMAIL", settings.gmail_user_email),
    ]


def gmail_status(settings: Settings | None = None) -> GmailStatus:
    settings = settings or get_settings()
    missing = [name for name, value in _required_settings(settings) if not value]
    if missing:
        return GmailStatus(False, f"Set {', '.join(missing)} to enable Gmail send and sync.")
    _, _, _, import_issue = _import_google_clients()
    if import_issue:
        return GmailStatus(False, f"Gmail libraries are unavailable: {import_issue}")
    return GmailStatus(True, "Configured for Gmail API send and reply sync.")


class GmailService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def status(self) -> GmailStatus:
        return gmail_status(self.settings)

    @lru_cache
    def _service(self):
        status = self.status()
        if not status.configured:
            raise RuntimeError(status.detail)

        Request, Credentials, build, import_issue = _import_google_clients()
        if import_issue:
            raise RuntimeError(import_issue)

        credentials = Credentials(
            token=None,
            refresh_token=self.settings.gmail_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.gmail_client_id,
            client_secret=self.settings.gmail_client_secret,
            scopes=[READ_SCOPE, SEND_SCOPE],
        )
        credentials.refresh(Request())
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def send_message(self, recipient_email: str, subject: str, body: str, thread_id: str | None = None) -> SendResult:
        try:
            service = self._service()
        except Exception as exc:
            return SendResult(status="Not Configured", thread_id=None, message_id=None, detail=str(exc))

        message = MIMEText(body)
        message["to"] = recipient_email
        message["from"] = self.settings.gmail_user_email or ""
        message["subject"] = subject
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        payload: dict[str, Any] = {"raw": encoded_message}
        if thread_id:
            payload["threadId"] = thread_id

        try:
            result = service.users().messages().send(userId="me", body=payload).execute()
        except Exception as exc:  # pragma: no cover - depends on remote API behavior
            return SendResult(status="Failed", thread_id=None, message_id=None, detail=str(exc))

        return SendResult(
            status="Sent",
            thread_id=result.get("threadId"),
            message_id=result.get("id"),
            detail="Message sent through Gmail API.",
        )

    def sync_threads(self, thread_ids: list[str]) -> list[GmailReply]:
        unique_ids = [thread_id for thread_id in dict.fromkeys(thread_ids) if thread_id]
        if not unique_ids:
            return []

        service = self._service()
        replies: list[GmailReply] = []
        sender_email = (self.settings.gmail_user_email or "").lower()
        for thread_id in unique_ids:
            try:
                thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
            except Exception:
                continue
            messages = thread.get("messages", [])
            if not messages:
                continue
            latest_reply = None
            for message in reversed(messages):
                headers = {
                    header.get("name", "").lower(): header.get("value", "")
                    for header in message.get("payload", {}).get("headers", [])
                }
                from_header = headers.get("from", "")
                if sender_email and sender_email in from_header.lower():
                    continue
                subject = headers.get("subject", "")
                body = _extract_text(message.get("payload", {}))
                if not body and not from_header:
                    continue
                timestamp = message.get("internalDate")
                received_at = None
                if timestamp:
                    received_at = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
                latest_reply = GmailReply(
                    thread_id=thread_id,
                    message_id=message.get("id"),
                    sender_email=from_header,
                    subject=subject,
                    body=body,
                    received_at=received_at,
                )
                break
            if latest_reply:
                replies.append(latest_reply)
        return replies


def _extract_text(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType")
    body_data = payload.get("body", {}).get("data")
    if body_data and mime_type == "text/plain":
        try:
            return base64.urlsafe_b64decode(body_data).decode("utf-8")
        except Exception:
            return ""
    for part in payload.get("parts", []) or []:
        text = _extract_text(part)
        if text:
            return text
    if body_data:
        try:
            return base64.urlsafe_b64decode(body_data).decode("utf-8")
        except Exception:
            return ""
    return ""
