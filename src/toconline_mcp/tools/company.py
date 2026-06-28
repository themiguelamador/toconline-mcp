from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient

_PATH = "/api/current_company"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def get_current_company() -> dict[str, Any]:
        """Return the authenticated company's own profile (NIPC/tax number, business name, address, currency). Use for the reporting entity's identity in tax reports."""
        return await client.request("GET", _PATH)
