from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id
from toconline_mcp.util.errors import ApiError

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
        """List addresses. Normally scope to a customer_id or supplier_id.

        Scoping uses the nested route (`/api/customers/{id}/addresses`); the
        flat `/api/addresses?filter[customer_id]=` query raises JA011.
        """
        if customer_id and supplier_id:
            raise ValueError("provide at most one of customer_id or supplier_id")
        params = build_list_params(
            page_size=page_size, page_number=page_number, sort=sort,
            fields={_RESOURCE: fields} if fields else None,
        )
        if customer_id:
            path = f"/api/customers/{require_id(customer_id, 'customer_id')}/addresses"
        elif supplier_id:
            path = f"/api/suppliers/{require_id(supplier_id, 'supplier_id')}/addresses"
        else:
            path = _PATH
        return await client.request("GET", path, params=params)

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

        Returns the created (or, on a duplicate, the existing) address re-fetched
        by id, so the parent link and all fields are populated — the raw POST
        echo omits them, which makes the address look empty/unlinked.

        TOCOnline enforces a uniqueness constraint on address_detail + postcode
        per parent and raises `[400] já existe na tabela` on a duplicate; this
        tool catches that and returns the existing address (idempotent).
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
        parent = "customers" if customer_id else "suppliers"
        parent_path = f"/api/{parent}/{addressable_id}/addresses"

        def _match(listing: Any) -> dict[str, Any] | None:
            for addr in (listing.get("items") if isinstance(listing, dict) else []) or []:
                if addr.get("address_detail") == address_detail and addr.get("postcode") == postcode:
                    return addr
            return None

        # Idempotent: TOCOnline happily creates duplicate (detail+postcode) rows,
        # so check the parent's existing addresses first and return a match.
        existing = _match(await client.request("GET", parent_path))
        if existing:
            return existing
        try:
            created = await client.request("POST", _PATH, json=envelope)
        except ApiError as e:
            # Some tenants instead reject the duplicate with "já existe na tabela";
            # fall back to returning the existing row.
            if e.status == 400 and "já existe" in str(e).lower():
                if match := _match(await client.request("GET", parent_path)):
                    return match
            raise
        # The POST echo omits resolved relationships (customer/supplier come back
        # null), making the address look unlinked. Re-fetch for a truthful record.
        new_id = created.get("id") if isinstance(created, dict) else None
        return await client.request("GET", f"{_PATH}/{new_id}") if new_id else created

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
