from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id

_RESOURCE = "contacts"
_PATH = "/api/contacts"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_contacts(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        customer_id: Annotated[
            str | None, Field(description="Filter to a specific customer's contacts.")
        ] = None,
        supplier_id: Annotated[
            str | None, Field(description="Filter to a specific supplier's contacts.")
        ] = None,
    ) -> dict[str, Any]:
        """List contacts. Normally scope to a customer_id or supplier_id."""
        filters = {}
        if customer_id:
            filters["customer_id"] = require_id(customer_id, "customer_id")
        if supplier_id:
            filters["supplier_id"] = require_id(supplier_id, "supplier_id")
        return await client.request(
            "GET", _PATH, params=build_list_params(page_size=page_size, filters=filters)
        )

    @mcp.tool()
    async def get_contact(
        id: Annotated[str, Field(description="Contact id.")],
    ) -> dict[str, Any]:
        """Fetch a single contact by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")

    @mcp.tool()
    async def create_contact(
        name: Annotated[str, Field(description="Contact name.")],
        email: Annotated[str | None, Field(description="Email address.")] = None,
        phone_number: Annotated[str | None, Field(description="Landline / main phone.")] = None,
        mobile_number: Annotated[str | None, Field(description="Mobile phone.")] = None,
        position: Annotated[str | None, Field(description="Job title / role.")] = None,
        customer_id: Annotated[
            str | None, Field(description="Attach to a customer. Provide one of customer_id or supplier_id.")
        ] = None,
        supplier_id: Annotated[
            str | None, Field(description="Attach to a supplier. Provide one of customer_id or supplier_id.")
        ] = None,
        is_primary: Annotated[
            bool, Field(description="Whether this is the primary contact.")
        ] = False,
    ) -> dict[str, Any]:
        """Create a contact attached to a customer or supplier."""
        if bool(customer_id) == bool(supplier_id):
            raise ValueError("provide exactly one of customer_id or supplier_id")
        attributes = {
            "name": name,
            "email": email,
            "phone_number": phone_number,
            "mobile_number": mobile_number,
            "position": position,
            "is_primary": is_primary,
        }
        relationships: dict[str, Any] = {}
        if customer_id:
            relationships["customer"] = ("customers", require_id(customer_id, "customer_id"))
        if supplier_id:
            relationships["supplier"] = ("suppliers", require_id(supplier_id, "supplier_id"))
        envelope = build_resource_envelope(_RESOURCE, attributes, relationships=relationships)
        return await client.request("POST", _PATH, json=envelope)

    @mcp.tool()
    async def update_contact(
        id: Annotated[str, Field(description="Contact id.")],
        name: Annotated[str | None, Field(description="Contact name.")] = None,
        email: Annotated[str | None, Field(description="Email address.")] = None,
        phone_number: Annotated[str | None, Field(description="Landline / main phone.")] = None,
        mobile_number: Annotated[str | None, Field(description="Mobile phone.")] = None,
        position: Annotated[str | None, Field(description="Job title / role.")] = None,
        is_primary: Annotated[
            bool | None, Field(description="Whether this is the primary contact.")
        ] = None,
    ) -> dict[str, Any]:
        """Update a contact. Only non-null fields are sent."""
        safe_id = require_id(id, "id")
        attributes = {
            "name": name,
            "email": email,
            "phone_number": phone_number,
            "mobile_number": mobile_number,
            "position": position,
            "is_primary": is_primary,
        }
        envelope = build_resource_envelope(_RESOURCE, attributes)
        envelope["data"]["id"] = safe_id
        return await client.request("PATCH", f"{_PATH}/{safe_id}", json=envelope)

    @mcp.tool()
    async def delete_contact(
        id: Annotated[str, Field(description="Contact id.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Safety gate against accidental deletes.")
        ] = False,
    ) -> dict[str, Any]:
        """Delete a contact. Requires `confirm=true`."""
        if not confirm:
            raise ValueError("delete_contact requires confirm=true")
        safe_id = require_id(id, "id")
        await client.request("DELETE", f"{_PATH}/{safe_id}")
        return {"status": "deleted", "id": safe_id}
