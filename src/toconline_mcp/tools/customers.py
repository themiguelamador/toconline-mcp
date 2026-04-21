from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id

_RESOURCE = "customers"
_PATH = "/api/customers"


def _customer_attributes(
    *,
    business_name: str | None,
    tax_registration_number: str | None,
    contact_name: str | None,
    email: str | None,
    phone_number: str | None,
    mobile_number: str | None,
    website: str | None,
    country_iso_alpha_2: str | None,
    tax_country_region: str | None,
    observations: str | None,
    internal_observations: str | None,
    not_final_customer: bool | None,
    cashed_vat: bool | None,
    is_tax_exempt: bool | None,
) -> dict[str, Any]:
    return {
        "business_name": business_name,
        "tax_registration_number": tax_registration_number,
        "contact_name": contact_name,
        "email": email,
        "phone_number": phone_number,
        "mobile_number": mobile_number,
        "website": website,
        "country_iso_alpha_2": country_iso_alpha_2,
        "tax_country_region": tax_country_region,
        "observations": observations,
        "internal_observations": internal_observations,
        "not_final_customer": not_final_customer,
        "cashed_vat": cashed_vat,
        "is_tax_exempt": is_tax_exempt,
    }


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
        sort: Annotated[
            str | None,
            Field(description="JSON:API sort, e.g. `business_name`, `-created_at`. Default: server order."),
        ] = None,
    ) -> dict[str, Any]:
        """List customers. All filters are exact match."""
        filters = {
            "business_name": business_name,
            "tax_registration_number": tax_registration_number,
            "email": email,
        }
        return await client.request(
            "GET",
            _PATH,
            params=build_list_params(page_size=page_size, filters=filters, sort=sort),
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
            str | None, Field(description="VAT / NIF.")
        ] = None,
        contact_name: Annotated[str | None, Field(description="Primary contact person.")] = None,
        email: Annotated[str | None, Field(description="Primary email.")] = None,
        phone_number: Annotated[str | None, Field(description="Landline / main phone.")] = None,
        mobile_number: Annotated[str | None, Field(description="Mobile phone.")] = None,
        website: Annotated[str | None, Field(description="Website URL.")] = None,
        country_iso_alpha_2: Annotated[
            str | None,
            Field(description="ISO 3166-1 alpha-2 country code, e.g. PT, US, DE."),
        ] = None,
        tax_country_region: Annotated[
            str | None,
            Field(description="Tax region — `PT` (Portugal), `UE` (EU member state), `NON-UE` (non-EU)."),
        ] = None,
        observations: Annotated[
            str | None, Field(description="Visible notes about the customer.")
        ] = None,
        internal_observations: Annotated[
            str | None, Field(description="Internal-only notes (not shown to customer).")
        ] = None,
        not_final_customer: Annotated[
            bool | None,
            Field(description="True if the customer is a reseller (not a final consumer)."),
        ] = None,
        cashed_vat: Annotated[
            bool | None, Field(description="Cashed-VAT regime (regime de IVA de caixa).")
        ] = None,
        is_tax_exempt: Annotated[
            bool | None, Field(description="True if the customer is VAT-exempt.")
        ] = None,
    ) -> dict[str, Any]:
        """Create a customer. Returns the created record."""
        attrs = _customer_attributes(
            business_name=business_name,
            tax_registration_number=tax_registration_number,
            contact_name=contact_name,
            email=email,
            phone_number=phone_number,
            mobile_number=mobile_number,
            website=website,
            country_iso_alpha_2=country_iso_alpha_2,
            tax_country_region=tax_country_region,
            observations=observations,
            internal_observations=internal_observations,
            not_final_customer=not_final_customer,
            cashed_vat=cashed_vat,
            is_tax_exempt=is_tax_exempt,
        )
        envelope = build_resource_envelope(_RESOURCE, attrs)
        return await client.request("POST", _PATH, json=envelope)

    @mcp.tool()
    async def update_customer(
        id: Annotated[str, Field(description="Customer id.")],
        business_name: Annotated[str | None, Field(description="Legal/trading name.")] = None,
        tax_registration_number: Annotated[str | None, Field(description="VAT / NIF.")] = None,
        contact_name: Annotated[str | None, Field(description="Primary contact person.")] = None,
        email: Annotated[str | None, Field(description="Primary email.")] = None,
        phone_number: Annotated[str | None, Field(description="Landline / main phone.")] = None,
        mobile_number: Annotated[str | None, Field(description="Mobile phone.")] = None,
        website: Annotated[str | None, Field(description="Website URL.")] = None,
        country_iso_alpha_2: Annotated[
            str | None, Field(description="ISO 3166-1 alpha-2 country code.")
        ] = None,
        tax_country_region: Annotated[
            str | None, Field(description="`PT`, `UE`, or `NON-UE`.")
        ] = None,
        observations: Annotated[str | None, Field(description="Visible notes.")] = None,
        internal_observations: Annotated[str | None, Field(description="Internal notes.")] = None,
        not_final_customer: Annotated[bool | None, Field(description="Reseller flag.")] = None,
        cashed_vat: Annotated[bool | None, Field(description="Cashed-VAT regime.")] = None,
        is_tax_exempt: Annotated[bool | None, Field(description="VAT-exempt flag.")] = None,
    ) -> dict[str, Any]:
        """Update a customer. Only non-null fields are sent."""
        safe_id = require_id(id, "id")
        attrs = _customer_attributes(
            business_name=business_name,
            tax_registration_number=tax_registration_number,
            contact_name=contact_name,
            email=email,
            phone_number=phone_number,
            mobile_number=mobile_number,
            website=website,
            country_iso_alpha_2=country_iso_alpha_2,
            tax_country_region=tax_country_region,
            observations=observations,
            internal_observations=internal_observations,
            not_final_customer=not_final_customer,
            cashed_vat=cashed_vat,
            is_tax_exempt=is_tax_exempt,
        )
        envelope = build_resource_envelope(_RESOURCE, attrs)
        envelope["data"]["id"] = safe_id
        return await client.request("PATCH", f"{_PATH}/{safe_id}", json=envelope)
