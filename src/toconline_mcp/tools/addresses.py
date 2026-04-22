from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id

_RESOURCE = "addresses"
_PATH = "/api/addresses"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_addresses(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        customer_id: Annotated[
            str | None, Field(description="Filter to a specific customer's addresses.")
        ] = None,
        supplier_id: Annotated[
            str | None, Field(description="Filter to a specific supplier's addresses.")
        ] = None,
        sort: Annotated[str | None, Field(description="JSON:API sort.")] = None,
        fields: Annotated[
            str | None, Field(description="Comma-separated subset of fields to return.")
        ] = None,
    ) -> dict[str, Any]:
        """List addresses. Normally scope to a customer_id or supplier_id."""
        filters = {}
        if customer_id:
            filters["customer_id"] = require_id(customer_id, "customer_id")
        if supplier_id:
            filters["supplier_id"] = require_id(supplier_id, "supplier_id")
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
    async def get_address(
        id: Annotated[str, Field(description="Address id.")],
    ) -> dict[str, Any]:
        """Fetch a single address by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")

    @mcp.tool()
    async def create_address(
        address_detail: Annotated[str, Field(description="Street / address line.")],
        city: Annotated[str, Field(description="City.")],
        postcode: Annotated[str | None, Field(description="Postcode / ZIP.")] = None,
        region: Annotated[str | None, Field(description="Region / state.")] = None,
        customer_id: Annotated[
            str | None,
            Field(description="Attach to a customer. Provide exactly one of customer_id or supplier_id."),
        ] = None,
        supplier_id: Annotated[
            str | None,
            Field(description="Attach to a supplier. Provide exactly one of customer_id or supplier_id."),
        ] = None,
        is_primary: Annotated[
            bool, Field(description="Whether this is the entity's primary address.")
        ] = False,
    ) -> dict[str, Any]:
        """Create an address attached to a customer or supplier.

        TOCOnline uses a polymorphic association — the parent is identified
        via the `addressable_type` ("Customer" | "Supplier") and
        `addressable_id` attributes, not a JSON:API relationship.
        """
        if bool(customer_id) == bool(supplier_id):
            raise ValueError("provide exactly one of customer_id or supplier_id")
        if customer_id:
            addressable_type = "Customer"
            addressable_id = require_id(customer_id, "customer_id")
        else:
            addressable_type = "Supplier"
            addressable_id = require_id(supplier_id, "supplier_id")
        attributes = {
            "address_detail": address_detail,
            "city": city,
            "postcode": postcode,
            "region": region,
            "is_primary": is_primary,
            "addressable_type": addressable_type,
            "addressable_id": addressable_id,
        }
        envelope = build_resource_envelope(_RESOURCE, attributes)
        return await client.request("POST", _PATH, json=envelope)

    @mcp.tool()
    async def update_address(
        id: Annotated[str, Field(description="Address id.")],
        address_detail: Annotated[str | None, Field(description="Street / address line.")] = None,
        city: Annotated[str | None, Field(description="City.")] = None,
        postcode: Annotated[str | None, Field(description="Postcode / ZIP.")] = None,
        region: Annotated[str | None, Field(description="Region / state.")] = None,
        is_primary: Annotated[
            bool | None, Field(description="Whether this is the primary address.")
        ] = None,
    ) -> dict[str, Any]:
        """Update an address. Only non-null fields are sent."""
        safe_id = require_id(id, "id")
        attributes = {
            "address_detail": address_detail,
            "city": city,
            "postcode": postcode,
            "region": region,
            "is_primary": is_primary,
        }
        envelope = build_resource_envelope(_RESOURCE, attributes)
        envelope["data"]["id"] = safe_id
        return await client.request("PATCH", f"{_PATH}/{safe_id}", json=envelope)

    @mcp.tool()
    async def delete_address(
        id: Annotated[str, Field(description="Address id.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Safety gate against accidental deletes.")
        ] = False,
    ) -> dict[str, Any]:
        """Delete an address. Requires `confirm=true`."""
        if not confirm:
            raise ValueError("delete_address requires confirm=true")
        safe_id = require_id(id, "id")
        await client.request("DELETE", f"{_PATH}/{safe_id}")
        return {"status": "deleted", "id": safe_id}
