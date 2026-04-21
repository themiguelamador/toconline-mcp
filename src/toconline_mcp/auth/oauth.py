from __future__ import annotations

import base64
import time
from dataclasses import dataclass

import httpx

from toconline_mcp.util.errors import AuthError


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str
    expires_at: int
    obtained_at: int


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _parse_token_payload(payload: dict) -> TokenResponse:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not access_token or not refresh_token or expires_in is None:
        raise AuthError(
            "Token endpoint response missing access_token, refresh_token, or expires_in."
        )
    now = int(time.time())
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=now + int(expires_in),
        obtained_at=now,
    )


def _post_token(
    client: httpx.Client,
    token_url: str,
    client_id: str,
    client_secret: str,
    form: dict[str, str],
) -> TokenResponse:
    headers = {
        "Authorization": _basic_auth_header(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    response = client.post(token_url, headers=headers, data=form)
    if response.status_code >= 400:
        raise AuthError(
            f"Token endpoint returned {response.status_code}: {response.text[:500]}"
        )
    return _parse_token_payload(response.json())


def exchange_code(
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> TokenResponse:
    with httpx.Client(timeout=timeout) as client:
        return _post_token(
            client,
            token_url,
            client_id,
            client_secret,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )


async def refresh_token_async(
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: float = 15.0,
) -> TokenResponse:
    headers = {
        "Authorization": _basic_auth_header(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(token_url, headers=headers, data=form)
    if response.status_code >= 400:
        raise AuthError(
            f"Token refresh returned {response.status_code}: {response.text[:500]}. "
            "Run `toconline-mcp setup` to re-authenticate."
        )
    return _parse_token_payload(response.json())
