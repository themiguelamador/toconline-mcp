from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import build_list_params, require_id

_PATH = "/api/products"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_products(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        item_description: Annotated[
            str | None,
            Field(description="Exact match on item_description."),
        ] = None,
        item_code: Annotated[
            str | None, Field(description="Exact match on item_code.")
        ] = None,
    ) -> dict[str, Any]:
        """List products. All filters are exact match."""
        filters = {
            "item_description": item_description,
            "item_code": item_code,
        }
        return await client.request(
            "GET", _PATH, params=build_list_params(page_size=page_size, filters=filters)
        )

    @mcp.tool()
    async def get_product(
        id: Annotated[str, Field(description="Product id.")],
    ) -> dict[str, Any]:
        """Fetch a single product by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")
