from __future__ import annotations

import json
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


@pytest.fixture
def creds_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    return path


def _write_creds(path: Path, *, expires_at: int | None = None, access: str = "tok1") -> Credentials:
    now = int(time.time())
    creds = Credentials(
        profile="default",
        api_base=API_BASE,
        client_id="cid",
        client_secret="csec",
        token_url=TOKEN_URL,
        access_token=access,
        refresh_token="ref1",
        expires_at=expires_at if expires_at is not None else now + 3600,
        obtained_at=now,
    )
    save_credentials(creds, path=path)
    return creds


@respx.mock
async def test_request_flattens_jsonapi_response(creds_path: Path):
    _write_creds(creds_path)
    route = respx.get(f"{API_BASE}/api/customers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "1", "type": "customers", "attributes": {"business_name": "A"}},
                ],
                "meta": {"total": 1},
            },
        )
    )
    async with TocClient() as client:
        result = await client.request("GET", "/api/customers")
    assert route.called
    assert result == {"items": [{"id": "1", "type": "customers", "business_name": "A"}], "meta": {"total": 1}}


@respx.mock
async def test_request_refreshes_on_401_and_retries(creds_path: Path):
    _write_creds(creds_path, access="stale")
    first_resp = httpx.Response(401, json={"errors": [{"title": "expired"}]})
    second_resp = httpx.Response(200, json={"data": {"id": "1", "type": "customers", "attributes": {"business_name": "A"}}})
    api_route = respx.get(f"{API_BASE}/api/customers/1").mock(side_effect=[first_resp, second_resp])
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fresh", "refresh_token": "ref2", "expires_in": 3600},
        )
    )
    async with TocClient() as client:
        result = await client.request("GET", "/api/customers/1")
    assert api_route.call_count == 2
    assert token_route.called
    assert result["business_name"] == "A"
    # second call should carry the refreshed token
    second_call_auth = api_route.calls[1].request.headers.get("authorization")
    assert second_call_auth == "Bearer fresh"
    # credentials file should now reflect the new token
    with open(creds_path) as fh:
        stored = json.load(fh)
    assert stored["access_token"] == "fresh"
    assert stored["refresh_token"] == "ref2"


@respx.mock
async def test_request_raises_auth_error_when_refresh_fails(creds_path: Path):
    _write_creds(creds_path, access="stale")
    respx.get(f"{API_BASE}/api/customers").mock(return_value=httpx.Response(401))
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    async with TocClient() as client:
        with pytest.raises(AuthError):
            await client.request("GET", "/api/customers")


@respx.mock
async def test_request_surfaces_api_error_with_message(creds_path: Path):
    _write_creds(creds_path)
    respx.get(f"{API_BASE}/api/customers/99").mock(
        return_value=httpx.Response(
            404,
            json={"errors": [{"title": "Not found", "detail": "customer 99"}]},
        )
    )
    async with TocClient() as client:
        with pytest.raises(ApiError) as exc_info:
            await client.request("GET", "/api/customers/99")
    assert exc_info.value.status == 404
    assert "Not found" in str(exc_info.value)


@respx.mock
async def test_request_refreshes_when_token_near_expiry(creds_path: Path):
    _write_creds(creds_path, expires_at=int(time.time()) + 30, access="about-to-expire")
    api_route = respx.get(f"{API_BASE}/api/products").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fresh", "refresh_token": "ref2", "expires_in": 3600},
        )
    )
    async with TocClient() as client:
        await client.request("GET", "/api/products")
    assert token_route.called, "proactive refresh should fire when token is near expiry"
    assert api_route.calls[0].request.headers["authorization"] == "Bearer fresh"
