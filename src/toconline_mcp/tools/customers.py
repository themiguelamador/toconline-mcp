from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id

_RESOURCE = "customers"
_PATH = "/api/customers"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_customers(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        business_name: Annotated[
            str | None,
            Field(description="Exact match on business_name (TOCOnline does not support substring search)."),
        ] = None,
        tax_registration_number: Annotated[
            str | None, Field(description="Exact VAT/NIF match.")
        ] = None,
        email: Annotated[str | None, Field(description="Exact email match.")] = None,
    ) -> dict[str, Any]:
        """List customers. All filters are exact match."""
        filters = {
            "business_name": business_name,
            "tax_registration_number": tax_registration_number,
            "email": email,
        }
        return await client.request(
            "GET", _PATH, params=build_list_params(page_size=page_size, filters=filters)
        )

    @mcp.tool()
    async def get_customer(
        id: Annotated[str, Field(description="Customer id.")],
    ) -> dict[str, Any]:
        """Fetch a single customer by id."""
        safe_id = require_id(id, "id")
        return await client.request("GET", f"{_PATH}/{safe_id}")

    @mcp.tool()
    async def create_customer(
        business_name: Annotated[str, Field(description="Legal/trading name.")],
        tax_registration_number: Annotated[
            str | None, Field(description="VAT/NIF.")
        ] = None,
        email: Annotated[str | None, Field(description="Primary email.")] = None,
        country_code: Annotated[
            str | None, Field(description="ISO 3166-1 alpha-2, e.g. PT.")
        ] = None,
        website: Annotated[str | None, Field(description="Website URL.")] = None,
    ) -> dict[str, Any]:
        """Create a customer. Returns the created record."""
        attributes = {
            "business_name": business_name,
            "tax_registration_number": tax_registration_number,
            "email": email,
            "country_code": country_code,
            "website": website,
        }
        envelope = build_resource_envelope(_RESOURCE, attributes)
        return await client.request("POST", _PATH, json=envelope)

    @mcp.tool()
    async def update_customer(
        id: Annotated[str, Field(description="Customer id.")],
        business_name: Annotated[str | None, Field(description="Legal/trading name.")] = None,
        tax_registration_number: Annotated[str | None, Field(description="VAT/NIF.")] = None,
        email: Annotated[str | None, Field(description="Primary email.")] = None,
        country_code: Annotated[str | None, Field(description="ISO 3166-1 alpha-2.")] = None,
        website: Annotated[str | None, Field(description="Website URL.")] = None,
    ) -> dict[str, Any]:
        """Update a customer. Only non-null fields are sent."""
        safe_id = require_id(id, "id")
        attributes = {
            "business_name": business_name,
            "tax_registration_number": tax_registration_number,
            "email": email,
            "country_code": country_code,
            "website": website,
        }
        envelope = build_resource_envelope(_RESOURCE, attributes)
        envelope["data"]["id"] = safe_id
        return await client.request("PATCH", f"{_PATH}/{safe_id}", json=envelope)
