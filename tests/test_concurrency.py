from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from toconline_mcp.auth import oauth as oauth_module
from toconline_mcp.auth.oauth import TokenResponse
from toconline_mcp.auth.store import Credentials, save_credentials
from toconline_mcp.http.client import TocClient


def _write_stale_creds(path: Path) -> None:
    now = int(time.time())
    save_credentials(
        Credentials(
            profile="default",
            api_base="https://api.example.com",
            client_id="cid",
            client_secret="csec",
            token_url="https://oauth.example.com/token",
            access_token="stale",
            refresh_token="ref1",
            expires_at=now + 3600,
            obtained_at=now,
        ),
        path=path,
    )


async def test_concurrent_refresh_only_fires_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Exercise the lock + seen-token check by launching N concurrent forced refreshes.

    Each caller captures `seen_token` before acquiring the lock. The first one
    inside the lock refreshes; the rest must observe that `access_token` has
    changed and bail out without firing a second refresh.
    """
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    _write_stale_creds(path)

    call_count = 0

    async def fake_refresh(**_kwargs) -> TokenResponse:
        nonlocal call_count
        call_count += 1
        # Yield to the event loop so other waiters can pile up on the lock
        # before we return — this is the whole point of the test.
        await asyncio.sleep(0.01)
        now = int(time.time())
        return TokenResponse(
            access_token="fresh", refresh_token="ref2", expires_at=now + 3600, obtained_at=now
        )

    monkeypatch.setattr(oauth_module, "refresh_token_async", fake_refresh)
    # Also patch it where client.py imported it from.
    import toconline_mcp.http.client as client_module
    monkeypatch.setattr(client_module, "refresh_token_async", fake_refresh)

    client = TocClient()
    await client._ensure_ready()  # type: ignore[attr-defined]
    try:
        await asyncio.gather(
            client._refresh_if_needed(force=True),  # type: ignore[attr-defined]
            client._refresh_if_needed(force=True),  # type: ignore[attr-defined]
            client._refresh_if_needed(force=True),  # type: ignore[attr-defined]
            client._refresh_if_needed(force=True),  # type: ignore[attr-defined]
        )
    finally:
        await client.aclose()

    assert call_count == 1, f"expected exactly 1 refresh despite concurrent callers, got {call_count}"
    assert client._creds.access_token == "fresh"  # type: ignore[attr-defined]
