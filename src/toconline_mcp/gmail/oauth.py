"""Google OAuth 2.0 — code exchange and refresh.

Differs from TOCOnline's OAuth: Google uses `client_id` + `client_secret` in
the token-endpoint request body (not HTTP Basic), and requires
`access_type=offline` + `prompt=consent` at the auth step to get a
refresh_token.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from toconline_mcp.util.errors import AuthError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# gmail.modify covers read + label changes + mark-read/unread + move-to-trash.
# Narrower than full-access (mail.google.com) which also allows permanent delete.
# Narrower scopes like gmail.readonly/gmail.labels cannot label messages.
GMAIL_DEFAULT_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None  # only returned on initial code exchange
    expires_at: int
    obtained_at: int


def _parse_token_payload(payload: dict, previous_refresh: str | None = None) -> TokenResponse:
    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not access_token or expires_in is None:
        raise AuthError("Google token endpoint response missing access_token or expires_in.")
    refresh_token = payload.get("refresh_token") or previous_refresh
    now = int(time.time())
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=now + int(expires_in),
        obtained_at=now,
    )


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    timeout: float = 15.0,
) -> TokenResponse:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(TOKEN_URL, data=form, headers={"Accept": "application/json"})
    if response.status_code >= 400:
        raise AuthError(
            f"Google token endpoint returned {response.status_code}: {response.text[:500]}"
        )
    tokens = _parse_token_payload(response.json())
    if not tokens.refresh_token:
        raise AuthError(
            "Google did not return a refresh_token. Make sure your auth URL included "
            "`access_type=offline&prompt=consent`, and that you revoked any prior "
            "consent at https://myaccount.google.com/permissions before retrying."
        )
    return tokens


async def refresh_token_async(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: float = 15.0,
) -> TokenResponse:
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            TOKEN_URL, data=form, headers={"Accept": "application/json"}
        )
    if response.status_code >= 400:
        raise AuthError(
            f"Google token refresh returned {response.status_code}: {response.text[:500]}. "
            "Run `toconline-mcp gmail-setup` to re-authenticate."
        )
    return _parse_token_payload(response.json(), previous_refresh=refresh_token)
