from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id

_RESOURCE = "suppliers"
_PATH = "/api/suppliers"


def _supplier_attributes(
    *,
    business_name: str | None,
    tax_registration_number: str | None,
    website: str | None,
    country_iso_alpha_2: str | None,
    tax_country_region: str | None,
    internal_observations: str | None,
    is_taxable: bool | None,
    is_tax_exempt: bool | None,
    self_billing: bool | None,
    is_independent_worker: bool | None,
    tax_exemption_reason_id: str | None,
    document_series_id: str | None,
    accounting_number: str | None,
) -> dict[str, Any]:
    return {
        "business_name": business_name,
        "tax_registration_number": tax_registration_number,
        "website": website,
        "country_iso_alpha_2": country_iso_alpha_2,
        "tax_country_region": tax_country_region,
        "internal_observations": internal_observations,
        "is_taxable": is_taxable,
        "is_tax_exempt": is_tax_exempt,
        "self_billing": self_billing,
        "is_independent_worker": is_independent_worker,
        "tax_exemption_reason_id": tax_exemption_reason_id,
        "document_series_id": document_series_id,
        "accounting_number": accounting_number,
    }


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_suppliers(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        business_name: Annotated[
            str | None, Field(description="Exact match on business_name.")
        ] = None,
        tax_registration_number: Annotated[
            str | None, Field(description="Exact VAT/NIF match.")
        ] = None,
        sort: Annotated[
            str | None, Field(description="JSON:API sort, e.g. `business_name`, `-created_at`.")
        ] = None,
        fields: Annotated[
            str | None, Field(description="Comma-separated subset of fields to return.")
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
            params=build_list_params(
                page_size=page_size, page_number=page_number,
                filters=filters, sort=sort,
                fields={_RESOURCE: fields} if fields else None,
            ),
        )

    @mcp.tool()
    async def get_supplier(
        id: Annotated[str, Field(description="Supplier id.")],
    ) -> dict[str, Any]:
        """Fetch a single supplier by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")

    @mcp.tool()
    async def create_supplier(
        business_name: Annotated[str, Field(description="Legal/trading name.")],
        tax_registration_number: Annotated[str, Field(description="VAT / NIF.")],
        website: Annotated[str | None, Field(description="Website URL.")] = None,
        country_iso_alpha_2: Annotated[
            str | None,
            Field(description="ISO 3166-1 alpha-2 country code, e.g. PT, US, DE."),
        ] = None,
        tax_country_region: Annotated[
            str | None,
            Field(description="Tax region — `PT` (Portugal), `UE` (EU member state), `NON-UE` (non-EU)."),
        ] = None,
        internal_observations: Annotated[
            str | None, Field(description="Internal-only notes.")
        ] = None,
        is_taxable: Annotated[bool | None, Field(description="Subject to VAT.")] = None,
        is_tax_exempt: Annotated[bool | None, Field(description="VAT-exempt.")] = None,
        self_billing: Annotated[
            bool | None, Field(description="Self-billing regime (autofaturação).")
        ] = None,
        is_independent_worker: Annotated[
            bool | None, Field(description="Independent worker / sole trader (trabalhador independente).")
        ] = None,
        tax_exemption_reason_id: Annotated[
            str | None, Field(description="Tax-exemption reason id (required when is_tax_exempt).")
        ] = None,
        document_series_id: Annotated[
            str | None, Field(description="Default document series id for this supplier.")
        ] = None,
        accounting_number: Annotated[
            str | None, Field(description="Accounting ledger number (conta).")
        ] = None,
    ) -> dict[str, Any]:
        """Create a supplier. Returns the created record.

        Contacts (email/phone) and addresses are separate resources — use
        `create_contact` / `create_address` with this supplier's id afterwards.
        """
        attrs = _supplier_attributes(
            business_name=business_name,
            tax_registration_number=tax_registration_number,
            website=website,
            country_iso_alpha_2=country_iso_alpha_2,
            tax_country_region=tax_country_region,
            internal_observations=internal_observations,
            is_taxable=is_taxable,
            is_tax_exempt=is_tax_exempt,
            self_billing=self_billing,
            is_independent_worker=is_independent_worker,
            tax_exemption_reason_id=tax_exemption_reason_id,
            document_series_id=document_series_id,
            accounting_number=accounting_number,
        )
        envelope = build_resource_envelope(_RESOURCE, attrs)
        return await client.request("POST", _PATH, json=envelope)

    @mcp.tool()
    async def update_supplier(
        id: Annotated[str, Field(description="Supplier id.")],
        business_name: Annotated[str | None, Field(description="Legal/trading name.")] = None,
        tax_registration_number: Annotated[str | None, Field(description="VAT / NIF.")] = None,
        website: Annotated[str | None, Field(description="Website URL.")] = None,
        country_iso_alpha_2: Annotated[
            str | None, Field(description="ISO 3166-1 alpha-2 country code.")
        ] = None,
        tax_country_region: Annotated[
            str | None, Field(description="`PT`, `UE`, or `NON-UE`.")
        ] = None,
        internal_observations: Annotated[str | None, Field(description="Internal notes.")] = None,
        is_taxable: Annotated[bool | None, Field(description="Subject to VAT.")] = None,
        is_tax_exempt: Annotated[bool | None, Field(description="VAT-exempt.")] = None,
        self_billing: Annotated[bool | None, Field(description="Self-billing regime.")] = None,
        is_independent_worker: Annotated[
            bool | None, Field(description="Independent worker / sole trader.")
        ] = None,
        tax_exemption_reason_id: Annotated[
            str | None, Field(description="Tax-exemption reason id.")
        ] = None,
        document_series_id: Annotated[
            str | None, Field(description="Default document series id.")
        ] = None,
        accounting_number: Annotated[str | None, Field(description="Accounting ledger number.")] = None,
    ) -> dict[str, Any]:
        """Update a supplier. Only non-null fields are sent."""
        safe_id = require_id(id, "id")
        attrs = _supplier_attributes(
            business_name=business_name,
            tax_registration_number=tax_registration_number,
            website=website,
            country_iso_alpha_2=country_iso_alpha_2,
            tax_country_region=tax_country_region,
            internal_observations=internal_observations,
            is_taxable=is_taxable,
            is_tax_exempt=is_tax_exempt,
            self_billing=self_billing,
            is_independent_worker=is_independent_worker,
            tax_exemption_reason_id=tax_exemption_reason_id,
            document_series_id=document_series_id,
            accounting_number=accounting_number,
        )
        envelope = build_resource_envelope(_RESOURCE, attrs)
        envelope["data"]["id"] = safe_id
        return await client.request("PATCH", f"{_PATH}/{safe_id}", json=envelope)

    @mcp.tool()
    async def delete_supplier(
        id: Annotated[str, Field(description="Supplier id.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Safety gate against accidental deletes.")
        ] = False,
    ) -> dict[str, Any]:
        """Delete a supplier. Requires `confirm=true`."""
        if not confirm:
            raise ValueError("delete_supplier requires confirm=true")
        safe_id = require_id(id, "id")
        await client.request("DELETE", f"{_PATH}/{safe_id}")
        return {"status": "deleted", "id": safe_id}
