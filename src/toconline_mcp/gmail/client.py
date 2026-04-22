from __future__ import annotations

import asyncio
import base64
import re
import time
from pathlib import Path
from typing import Any

import httpx

from toconline_mcp.gmail.oauth import refresh_token_async
from toconline_mcp.gmail.store import (
    GmailCredentials,
    load_gmail_credentials,
    save_gmail_credentials,
)
from toconline_mcp.util.errors import ApiError, AuthError
from toconline_mcp.util.logger import get_logger

_log = get_logger(__name__)
_API_BASE = "https://gmail.googleapis.com/gmail/v1"
_REFRESH_MARGIN_SECONDS = 120

# Filename sanitization: allow letters, digits, spaces, dots, dashes, underscores.
# Replace everything else with `_`. Also strip any leading `.` / path traversal.
_SAFE_CHAR = re.compile(r"[^A-Za-z0-9 ._\-()]")


def _sanitize_filename(name: str, fallback: str = "attachment.bin") -> str:
    if not name:
        return fallback
    name = name.replace("/", "_").replace("\\", "_")
    name = _SAFE_CHAR.sub("_", name).strip(". ")
    return name or fallback


def _b64url_decode(s: str) -> bytes:
    """Gmail returns attachment data as base64-URL (with - and _ instead of + and /)."""
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _index_headers(headers: list[dict[str, str]] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {h["name"].lower(): h["value"] for h in headers if "name" in h and "value" in h}


class GmailClient:
    """Async Gmail API client with lazy token refresh.

    Loads credentials on first use. Refreshes access_token proactively before
    each call (if within margin) and reactively on 401. Token changes are
    persisted back to disk.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._creds: GmailCredentials | None = None
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def invalidate(self) -> None:
        async with self._lock:
            self._creds = None
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _ensure_ready(self) -> None:
        if self._creds is None:
            self._creds = load_gmail_credentials()
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=_API_BASE, timeout=self._timeout)

    async def _refresh_if_needed(self, force: bool = False) -> None:
        assert self._creds is not None
        now = int(time.time())
        if not force and self._creds.expires_at - now > _REFRESH_MARGIN_SECONDS:
            return
        seen_token = self._creds.access_token
        async with self._lock:
            if self._creds.access_token != seen_token:
                return  # someone else refreshed while we waited
            now = int(time.time())
            if not force and self._creds.expires_at - now > _REFRESH_MARGIN_SECONDS:
                return
            _log.info("Refreshing Gmail access token")
            tokens = await refresh_token_async(
                client_id=self._creds.client_id,
                client_secret=self._creds.client_secret,
                refresh_token=self._creds.refresh_token,
            )
            assert tokens.refresh_token  # Google returns the previous one if omitted
            self._creds = self._creds.with_tokens(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expires_at=tokens.expires_at,
                obtained_at=tokens.obtained_at,
            )
            save_gmail_credentials(self._creds)

    def _headers(self) -> dict[str, str]:
        assert self._creds is not None
        return {
            "Authorization": f"Bearer {self._creds.access_token}",
            "Accept": "application/json",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        await self._ensure_ready()
        await self._refresh_if_needed()
        assert self._client is not None

        response = await self._send(method, path, params=params, json=json)
        if response.status_code == 401:
            _log.info("Gmail 401; forcing refresh and retrying once")
            await self._refresh_if_needed(force=True)
            response = await self._send(method, path, params=params, json=json)
        return self._handle_response(response)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> httpx.Response:
        assert self._client is not None
        return await self._client.request(
            method.upper(),
            path if path.startswith("/") else f"/{path}",
            params=params,
            json=json,
            headers=self._headers(),
        )

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if response.status_code == 204:
            return None
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        if response.status_code >= 400:
            message = "unknown error"
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict):
                    message = err.get("message") or str(err)
                elif isinstance(err, str):
                    message = err
            if response.status_code == 401:
                raise AuthError(f"Gmail 401: {message}. Run `toconline-mcp gmail-setup`.")
            raise ApiError(response.status_code, message, body)
        return body

    # ---------- High-level Gmail operations ----------

    async def list_messages(
        self, query: str | None = None, max_results: int = 20,
        page_token: str | None = None, label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"maxResults": max(1, min(int(max_results), 500))}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token
        if label_ids:
            params["labelIds"] = label_ids
        return await self.request("GET", "/users/me/messages", params=params)

    async def get_message(self, message_id: str, *, fmt: str = "full") -> dict[str, Any]:
        return await self.request(
            "GET", f"/users/me/messages/{message_id}", params={"format": fmt}
        )

    async def get_attachment_bytes(self, message_id: str, attachment_id: str) -> bytes:
        payload = await self.request(
            "GET", f"/users/me/messages/{message_id}/attachments/{attachment_id}"
        )
        if not isinstance(payload, dict) or "data" not in payload:
            raise ApiError(500, "attachment response missing data field", payload)
        return _b64url_decode(payload["data"])

    async def modify_message_labels(
        self, message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids
        if not body:
            raise ValueError("provide at least one of add_label_ids or remove_label_ids")
        return await self.request(
            "POST", f"/users/me/messages/{message_id}/modify", json=body
        )

    async def list_labels(self) -> dict[str, Any]:
        return await self.request("GET", "/users/me/labels")

    async def create_label(
        self, name: str,
        label_list_visibility: str = "labelShow",
        message_list_visibility: str = "show",
    ) -> dict[str, Any]:
        return await self.request(
            "POST", "/users/me/labels",
            json={
                "name": name,
                "labelListVisibility": label_list_visibility,
                "messageListVisibility": message_list_visibility,
            },
        )

    # ---------- Helpers used by tools ----------

    @staticmethod
    def extract_message_metadata(msg: dict[str, Any]) -> dict[str, Any]:
        """Flatten a Gmail message payload to a compact dict for tool output."""
        headers = _index_headers((msg.get("payload") or {}).get("headers"))
        return {
            "id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "snippet": msg.get("snippet"),
            "internal_date": msg.get("internalDate"),
            "size_estimate": msg.get("sizeEstimate"),
            "label_ids": msg.get("labelIds") or [],
            "from": headers.get("from"),
            "to": headers.get("to"),
            "subject": headers.get("subject"),
            "date": headers.get("date"),
        }

    @staticmethod
    def iter_attachment_parts(payload: dict[str, Any] | None):
        """Yield (filename, mime_type, attachment_id, size) for each attachment part.

        Recurses into multipart structures. Ignores parts without an
        attachmentId (inline text/html body parts).
        """
        if not isinstance(payload, dict):
            return
        body = payload.get("body") or {}
        att_id = body.get("attachmentId")
        filename = payload.get("filename") or ""
        if att_id and filename:
            yield (filename, payload.get("mimeType") or "application/octet-stream",
                   att_id, body.get("size") or 0)
        for child in payload.get("parts") or []:
            yield from GmailClient.iter_attachment_parts(child)

    @staticmethod
    def unique_save_path(directory: Path, filename: str) -> Path:
        """Return a non-existing path inside `directory` for `filename`.

        If `directory/filename` exists, appends ` (2)`, ` (3)`, ... before the
        extension until an unused name is found. Caller is responsible for
        ensuring `directory` is already created.
        """
        safe = _sanitize_filename(filename)
        candidate = directory / safe
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        for i in range(2, 10000):
            candidate = directory / f"{stem} ({i}){suffix}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"could not find a free filename in {directory}")
