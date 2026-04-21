from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import build_list_params, require_id

_PATH = "/api/suppliers"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_suppliers(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        business_name: Annotated[
            str | None,
            Field(description="Exact match on business_name."),
        ] = None,
        tax_registration_number: Annotated[
            str | None, Field(description="Exact VAT/NIF match.")
        ] = None,
        sort: Annotated[
            str | None,
            Field(description="JSON:API sort, e.g. `business_name`, `-created_at`."),
        ] = None,
    ) -> dict[str, Any]:
        """List suppliers. All filters are exact match."""
        filters = {
            "business_name": business_name,
            "tax_registration_number": tax_registration_number,
        }
        return await client.request(
            "GET",
            _PATH,
            params=build_list_params(page_size=page_size, filters=filters, sort=sort),
        )

    @mcp.tool()
    async def get_supplier(
        id: Annotated[str, Field(description="Supplier id.")],
    ) -> dict[str, Any]:
        """Fetch a single supplier by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")
