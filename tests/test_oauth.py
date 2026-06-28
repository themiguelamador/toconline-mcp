from __future__ import annotations

import httpx
import pytest
import respx

from toconline_mcp.auth.oauth import exchange_code, refresh_token_async
from toconline_mcp.util.errors import AuthError

TOKEN_URL = "https://oauth.example.com/token"


@respx.mock
def test_exchange_code_sends_basic_auth_and_form():
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "a", "refresh_token": "r", "expires_in": 3600},
        )
    )
    tokens = exchange_code(TOKEN_URL, "cid", "csec", "CODE", "http://127.0.0.1:53682/callback")
    assert tokens.access_token == "a"
    assert tokens.refresh_token == "r"
    assert tokens.expires_at - tokens.obtained_at == 3600
    req = route.calls[0].request
    assert req.headers["authorization"].startswith("Basic ")
    assert req.headers["content-type"] == "application/x-www-form-urlencoded"
    body = dict(pair.split("=", 1) for pair in req.content.decode().split("&"))
    assert body["grant_type"] == "authorization_code"
    assert body["code"] == "CODE"


@respx.mock
def test_exchange_code_raises_on_error():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(AuthError):
        exchange_code(TOKEN_URL, "cid", "csec", "CODE", "http://127.0.0.1:53682/callback")


@respx.mock
async def test_refresh_token_returns_new_pair():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "a2", "refresh_token": "r2", "expires_in": 60},
        )
    )
    tokens = await refresh_token_async(TOKEN_URL, "cid", "csec", "OLD")
    assert tokens.access_token == "a2"
    assert tokens.refresh_token == "r2"


@respx.mock
async def test_refresh_token_reuses_old_token_when_response_omits_it():
    # TKT-9: TOCOnline's refresh response can omit refresh_token (and expires_in);
    # we must reuse the previous refresh token instead of erroring.
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a2"})
    )
    tokens = await refresh_token_async(TOKEN_URL, "cid", "csec", "OLD")
    assert tokens.access_token == "a2"
    assert tokens.refresh_token == "OLD"  # reused
    assert tokens.expires_at > 0


@respx.mock
async def test_refresh_token_raises_auth_error_on_invalid_grant():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(AuthError) as exc_info:
        await refresh_token_async(TOKEN_URL, "cid", "csec", "OLD")
    assert "setup" in str(exc_info.value).lower()
