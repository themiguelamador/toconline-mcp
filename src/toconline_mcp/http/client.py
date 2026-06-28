from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from toconline_mcp.auth.oauth import refresh_token_async
from toconline_mcp.auth.store import Credentials, load_credentials, save_credentials
from toconline_mcp.http.jsonapi import flatten_response
from toconline_mcp.util.errors import ApiError, AuthError
from toconline_mcp.util.logger import get_logger

_log = get_logger(__name__)
_JSONAPI_MEDIA_TYPE = "application/vnd.api+json"
_REFRESH_MARGIN_SECONDS = 120


class TocClient:
    """Async HTTP client for the TOCOnline JSON:API.

    Loads credentials lazily, refreshes access tokens proactively, and retries
    a single 401 by forcing a refresh. Flattens JSON:API responses on the way
    out.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._creds: Credentials | None = None
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "TocClient":
        await self._ensure_ready()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def invalidate(self) -> None:
        """Drop in-memory credentials and httpx client.

        Call after `login` or `logout` so the next request re-reads credentials
        from disk (or raises AuthError if they're gone). The httpx client is
        closed because a new login may point at a different `api_base`.
        """
        async with self._lock:
            self._creds = None
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _ensure_ready(self) -> None:
        if self._creds is None:
            self._creds = load_credentials()
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._creds.api_base.rstrip("/"),
                timeout=self._timeout,
            )

    @staticmethod
    def _load_creds_quietly() -> Credentials | None:
        try:
            return load_credentials()
        except Exception:  # noqa: BLE001 — best-effort pickup; absence is handled by caller
            return None

    async def _adopt_creds(self, creds: Credentials) -> None:
        """Switch to credentials re-created out-of-band, rebuilding the client if
        the api_base changed (a fresh setup may point at a different tenant)."""
        rebuild = self._client is not None and creds.api_base != self._creds.api_base
        self._creds = creds
        if rebuild and self._client is not None:
            await self._client.aclose()
            self._client = None
            await self._ensure_ready()

    async def _do_refresh(self) -> None:
        assert self._creds is not None
        tokens = await refresh_token_async(
            token_url=self._creds.token_url,
            client_id=self._creds.client_id,
            client_secret=self._creds.client_secret,
            refresh_token=self._creds.refresh_token,
        )
        self._creds = self._creds.with_tokens(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_at=tokens.expires_at,
            obtained_at=tokens.obtained_at,
        )
        save_credentials(self._creds)

    async def _refresh_if_needed(self, force: bool = False) -> None:
        assert self._creds is not None
        now = int(time.time())
        if not force and self._creds.expires_at - now > _REFRESH_MARGIN_SECONDS:
            return
        seen_token = self._creds.access_token
        async with self._lock:
            # Another task may have refreshed while we waited for the lock.
            if self._creds.access_token != seen_token:
                return
            # Pick up credentials re-created out-of-band (e.g. a manual `setup`)
            # without a process restart.
            disk = self._load_creds_quietly()
            if disk is not None and disk.obtained_at > self._creds.obtained_at:
                await self._adopt_creds(disk)
            now = int(time.time())
            if not force and self._creds.expires_at - now > _REFRESH_MARGIN_SECONDS:
                return
            _log.info("Refreshing TOCOnline access token")
            try:
                await self._do_refresh()
            except AuthError:
                # The refresh token may have been rotated by an out-of-band
                # re-setup; reload from disk and retry once with the fresh token.
                disk = self._load_creds_quietly()
                if disk is not None and disk.refresh_token != self._creds.refresh_token:
                    _log.info("Refresh failed; adopting newer credentials from disk and retrying")
                    await self._adopt_creds(disk)
                    await self._do_refresh()
                else:
                    raise

    def _headers(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        assert self._creds is not None
        headers = {
            "Authorization": f"Bearer {self._creds.access_token}",
            "Accept": _JSONAPI_MEDIA_TYPE,
            "Content-Type": _JSONAPI_MEDIA_TYPE,
        }
        if overrides:
            headers.update(overrides)
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        flatten: bool = True,
    ) -> Any:
        """Make an authenticated API call.

        `headers` is merged over the default Authorization/Accept/Content-Type
        — pass `{"Content-Type": "application/json"}` when calling v1
        endpoints that take flat (non-JSON:API) bodies.
        """
        await self._ensure_ready()
        await self._refresh_if_needed()
        assert self._client is not None

        response = await self._send(method, path, params=params, json=json, headers=headers)
        if response.status_code == 401:
            _log.info("Got 401, forcing token refresh and retrying once")
            await self._refresh_if_needed(force=True)
            response = await self._send(method, path, params=params, json=json, headers=headers)
        return self._handle_response(response, flatten=flatten)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        assert self._client is not None
        return await self._client.request(
            method.upper(),
            path if path.startswith("/") else f"/{path}",
            params=params,
            json=json,
            headers=self._headers(headers),
        )

    def _handle_response(self, response: httpx.Response, *, flatten: bool) -> Any:
        if response.status_code == 204:
            return None
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        if response.status_code >= 400:
            message = self._extract_error_message(body, response.text)
            if response.status_code == 401:
                raise AuthError(
                    f"TOCOnline rejected the request (401): {message}. "
                    "Run `toconline-mcp setup` if this persists."
                )
            message = self._augment_message(message)
            raise ApiError(response.status_code, message, body)
        if body is None:
            return None
        return flatten_response(body) if flatten else body

    @staticmethod
    def _augment_message(message: str) -> str:
        """Attach actionable guidance to opaque API errors so a model driving the
        MCP can self-correct instead of treating them as dead ends.

        `JA011` is the API's generic "invalid request" — it is not a server fault
        and usually means an unsupported query shape, not a bug to report.
        """
        if "JA011" in message:
            return (
                f"{message}\n\nHint: JA011 means the query shape is unsupported (not a "
                "server bug). Common causes and fixes:\n"
                "- Filtering a child collection flat (e.g. "
                "`filter[document_id]`, `filter[customer_id]`) is not supported — use the "
                "nested route instead: `/api/commercial_sales_documents/{id}/lines`, "
                "`/api/customers/{id}/addresses`. The typed tools "
                "(`get_sales_document(include_lines=true)`, `list_addresses(customer_id=…)`) "
                "already do this.\n"
                "- Putting relationship fields (names ending in `_id`/`_ids`, e.g. "
                "`main_address_id`) in `fields[...]` — sparse fieldsets accept scalar "
                "attributes only. Drop them or fetch the full record."
            )
        return message

    @staticmethod
    def _extract_error_message(body: Any, fallback: str) -> str:
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    parts = [first.get("title"), first.get("detail")]
                    joined = " — ".join(p for p in parts if p)
                    if joined:
                        return joined
            if body.get("message"):
                return str(body["message"])
        return fallback[:500] if fallback else "unknown error"
