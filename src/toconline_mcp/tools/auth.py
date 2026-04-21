from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.auth.setup import run_setup
from toconline_mcp.auth.store import load_credentials
from toconline_mcp.config import (
    DEFAULT_API_BASE,
    DEFAULT_REDIRECT_PORT,
    DEFAULT_SCOPE,
    SetupInputs,
    credentials_path,
)
from toconline_mcp.http.client import TocClient
from toconline_mcp.util.errors import TocError

_LOGIN_TIMEOUT_SECONDS = 180.0


def register(mcp: FastMCP, client: TocClient) -> None:
    _login_lock = asyncio.Lock()

    @mcp.tool()
    async def auth_status() -> dict[str, Any]:
        """Report whether TOCOnline credentials are configured and their expiry.

        Fast, no side effects. Call this to decide whether to prompt the user
        through `login` before attempting other tools.
        """
        path = credentials_path()
        try:
            creds = load_credentials(path)
        except TocError as exc:
            return {
                "authenticated": False,
                "credentials_path": str(path),
                "reason": str(exc),
            }
        now = int(time.time())
        return {
            "authenticated": True,
            "profile": creds.profile,
            "api_base": creds.api_base,
            "client_id": creds.client_id,
            "credentials_path": str(path),
            "token_expires_in_seconds": creds.expires_at - now,
            "token_obtained_at": creds.obtained_at,
        }

    @mcp.tool()
    async def login(
        client_id: Annotated[str, Field(description="TOCOnline OAuth client id.")],
        client_secret: Annotated[str, Field(description="TOCOnline OAuth client secret.")],
        auth_url: Annotated[
            str,
            Field(description="OAuth authorization URL (TOCOnline provides OAUTH_URL/auth)."),
        ],
        token_url: Annotated[
            str,
            Field(description="OAuth token URL (TOCOnline provides OAUTH_URL/token)."),
        ],
        api_base: Annotated[
            str, Field(description="TOCOnline API base URL.")
        ] = DEFAULT_API_BASE,
        scope: Annotated[str, Field(description="OAuth scope.")] = DEFAULT_SCOPE,
        redirect_port: Annotated[
            int,
            Field(description="Local port for the OAuth callback listener.", ge=1024, le=65535),
        ] = DEFAULT_REDIRECT_PORT,
    ) -> dict[str, Any]:
        """Open a browser and complete OAuth login against TOCOnline.

        The user must have registered `http://127.0.0.1:<redirect_port>/callback`
        as a redirect URI in their TOCOnline integration. Credentials are stored
        at `~/.config/toconline-mcp/credentials.json` (mode 0600) and picked up
        by subsequent tool calls without restarting the server.

        This tool blocks for up to 3 minutes while waiting for the browser
        callback; ask the user to complete the consent promptly.
        """
        async with _login_lock:
            inputs = SetupInputs(
                client_id=client_id,
                client_secret=client_secret,
                auth_url=auth_url,
                token_url=token_url,
                api_base=api_base,
                scope=scope,
                redirect_port=redirect_port,
            )
            # run_setup is sync (stdlib HTTP server on a thread + webbrowser);
            # offload so we don't block the MCP event loop.
            await asyncio.to_thread(run_setup, inputs, True, _LOGIN_TIMEOUT_SECONDS)
            await client.invalidate()
        return {
            "status": "ok",
            "credentials_path": str(credentials_path()),
            "message": "Logged in. Credentials stored; subsequent tool calls will use them.",
        }

    @mcp.tool()
    async def logout() -> dict[str, Any]:
        """Delete the stored TOCOnline credentials and drop in-memory tokens."""
        path = credentials_path()
        existed = path.exists()
        if existed:
            path.unlink()
        await client.invalidate()
        return {
            "status": "ok" if existed else "no-op",
            "message": "Credentials deleted." if existed else "No credentials were stored.",
            "credentials_path": str(path),
        }
