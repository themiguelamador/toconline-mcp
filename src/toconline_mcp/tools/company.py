from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient

_PATH = "/api/current_company"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def get_current_company() -> dict[str, Any]:
        """Return the authenticated company's own profile.

        Includes `tax_registration_number` (NIPC for Portuguese companies),
        `business_name`, `tax_country_region`, contact fields, `currency_id`,
        `accountant_tax_registration_number`, and the linked `address_id`.

        Use this when you need the reporting entity's own identity — for
        example when producing tax-authority reports (Modelo 30, SAFT-PT),
        where you need the company's NIPC as the reporter, not the customer's.
        """
        return await client.request("GET", _PATH)
