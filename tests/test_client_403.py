from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
import respx

from toconline_mcp.auth.store import Credentials, save_credentials
from toconline_mcp.http.client import TocClient
from toconline_mcp.util.errors import ApiError, AuthError

API_BASE = "https://api.example.com"
TOKEN_URL = "https://oauth.example.com/token"


def _write_creds(path: Path) -> None:
    now = int(time.time())
    save_credentials(
        Credentials(
            profile="default",
            api_base=API_BASE,
            client_id="cid",
            client_secret="csec",
            token_url=TOKEN_URL,
            access_token="tok",
            refresh_token="ref",
            expires_at=now + 3600,
            obtained_at=now,
        ),
        path=path,
    )


@respx.mock
async def test_403_raises_api_error_not_auth_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    _write_creds(path)
    respx.get(f"{API_BASE}/api/customers").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"title": "Forbidden", "detail": "scope missing"}]}
        )
    )
    async with TocClient() as client:
        with pytest.raises(ApiError) as exc:
            await client.request("GET", "/api/customers")
    assert exc.value.status == 403
    assert "setup" not in str(exc.value).lower(), (
        "403 is a scope/permissions issue, should not tell user to re-run setup"
    )


@respx.mock
async def test_401_still_raises_auth_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    _write_creds(path)
    # Both initial and retry return 401 → refresh succeeds but API still 401s.
    respx.get(f"{API_BASE}/api/customers").mock(
        return_value=httpx.Response(401, json={"errors": [{"title": "unauthorized"}]})
    )
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "fresh", "refresh_token": "r2", "expires_in": 3600}
        )
    )
    async with TocClient() as client:
        with pytest.raises(AuthError) as exc:
            await client.request("GET", "/api/customers")
    assert "setup" in str(exc.value).lower()
