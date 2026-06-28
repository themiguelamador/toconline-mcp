from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, item_attributes, require_id

_RESOURCE = "services"
_PATH = "/api/services"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_services(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        item_description: Annotated[
            str | None, Field(description="Exact match on item_description.")
        ] = None,
        item_code: Annotated[
            str | None, Field(description="Exact match on item_code.")
        ] = None,
        sort: Annotated[
            str | None, Field(description="JSON:API sort, e.g. `item_description`, `-created_at`.")
        ] = None,
        fields: Annotated[
            str | None, Field(description="Comma-separated subset of fields to return.")
        ] = None,
    ) -> dict[str, Any]:
        """List services. All filters are exact match. Services are separate from products; document lines distinguish them via item_type (`Service` vs `Product`)."""
        filters = {
            "item_description": item_description,
            "item_code": item_code,
        }
        return await client.request(
            "GET",
            _PATH,
            params=build_list_params(
                page_size=page_size, page_number=page_number,
                filters=filters, sort=sort,
                fields={_RESOURCE: fields} if fields else None,
            ),
        )

    @mcp.tool()
    async def get_service(
        id: Annotated[str, Field(description="Service id.")],
    ) -> dict[str, Any]:
        """Fetch a single service by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")

    @mcp.tool()
    async def create_service(
        item_code: Annotated[str, Field(description="Unique service code.")],
        item_description: Annotated[str, Field(description="Service name/description.")],
        sales_price: Annotated[
            float | None, Field(description="Unit sales price.")
        ] = None,
        sales_price_includes_vat: Annotated[
            bool | None, Field(description="True if sales_price already includes VAT.")
        ] = None,
        tax_code: Annotated[
            str | None,
            Field(description="VAT rate code — `NOR` (normal), `INT` (intermediate), `RED` (reduced), `ISE` (exempt)."),
        ] = None,
        item_family_id: Annotated[
            str | None, Field(description="Item family id to associate.")
        ] = None,
    ) -> dict[str, Any]:
        """Create a service. Returns the created record."""
        attrs = item_attributes(
            item_type="Service",
            item_code=item_code,
            item_description=item_description,
            sales_price=sales_price,
            sales_price_includes_vat=sales_price_includes_vat,
            tax_code=tax_code,
        )
        attrs["item_family_id"] = item_family_id
        envelope = build_resource_envelope(_RESOURCE, attrs)
        return await client.request("POST", _PATH, json=envelope)

    @mcp.tool()
    async def update_service(
        id: Annotated[str, Field(description="Service id.")],
        item_code: Annotated[str | None, Field(description="Unique service code.")] = None,
        item_description: Annotated[str | None, Field(description="Service name/description.")] = None,
        sales_price: Annotated[float | None, Field(description="Unit sales price.")] = None,
        sales_price_includes_vat: Annotated[
            bool | None, Field(description="True if sales_price already includes VAT.")
        ] = None,
        tax_code: Annotated[
            str | None, Field(description="VAT rate code — `NOR`, `INT`, `RED`, `ISE`.")
        ] = None,
        item_family_id: Annotated[
            str | None, Field(description="Item family id to associate.")
        ] = None,
    ) -> dict[str, Any]:
        """Update a service. Only non-null fields are sent."""
        safe_id = require_id(id, "id")
        attrs = item_attributes(
            item_code=item_code,
            item_description=item_description,
            sales_price=sales_price,
            sales_price_includes_vat=sales_price_includes_vat,
            tax_code=tax_code,
        )
        attrs["item_family_id"] = item_family_id
        envelope = build_resource_envelope(_RESOURCE, attrs)
        envelope["data"]["id"] = safe_id
        return await client.request("PATCH", f"{_PATH}/{safe_id}", json=envelope)

    @mcp.tool()
    async def delete_service(
        id: Annotated[str, Field(description="Service id.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Safety gate against accidental deletes.")
        ] = False,
    ) -> dict[str, Any]:
        """Delete a service. Requires `confirm=true`."""
        if not confirm:
            raise ValueError("delete_service requires confirm=true")
        safe_id = require_id(id, "id")
        await client.request("DELETE", f"{_PATH}/{safe_id}")
        return {"status": "deleted", "id": safe_id}
