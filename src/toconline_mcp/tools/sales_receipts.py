from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_PATH = "/api/commercial_sales_receipts"
_TYPE = "commercial_sales_receipts"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_sales_receipts(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        customer_id: Annotated[
            str | None, Field(description="Filter by customer id (exact match).")
        ] = None,
        date: Annotated[
            str | None, Field(description="Exact date match (YYYY-MM-DD).")
        ] = None,
        sort: Annotated[
            str,
            Field(description="JSON:API sort. Defaults to `-date`."),
        ] = "-date",
    ) -> dict[str, Any]:
        """List sales receipts (customer payments), newest first by default."""
        filters: dict[str, Any] = {}
        if customer_id:
            filters["third_party_id"] = require_id(customer_id, "customer_id")
        if date:
            filters["date"] = require_iso_date(date, "date")
        return await client.request(
            "GET",
            _PATH,
            params=build_list_params(page_size=page_size, filters=filters, sort=sort),
        )

    @mcp.tool()
    async def get_sales_receipt(
        id: Annotated[str, Field(description="Sales receipt id.")],
    ) -> dict[str, Any]:
        """Fetch a single sales receipt by id."""
        return await client.request("GET", f"{_PATH}/{require_id(id, 'id')}")

    @mcp.tool()
    async def create_sales_receipt(
        customer_id: Annotated[str, Field(description="TOCOnline customer id.")],
        date: Annotated[str, Field(description="ISO receipt date (YYYY-MM-DD).")],
        gross_total: Annotated[float, Field(description="Total amount received.", gt=0)],
        payment_mechanism: Annotated[
            str | None,
            Field(description="TOCOnline payment mechanism code (e.g. NUM, TRA, CC)."),
        ] = None,
        bank_account_id: Annotated[
            str | None,
            Field(description="Bank account id from /api/bank_accounts, if received into a bank account."),
        ] = None,
        observations: Annotated[str | None, Field(description="Optional observations.")] = None,
    ) -> dict[str, Any]:
        """Create a sales receipt (customer payment) record.

        Note: this creates the receipt itself; linking it to specific sales
        documents (settlement) may require additional steps the MVP does not
        cover. Use `api_request` if you need to attach settlement lines.
        """
        require_iso_date(date, "date")
        safe_customer_id = require_id(customer_id, "customer_id")
        attributes = {
            "date": date,
            "gross_total": gross_total,
            "payment_mechanism": payment_mechanism,
            "observations": observations,
            "third_party_type": "customers",
        }
        relationships: dict[str, Any] = {"third_party": ("customers", safe_customer_id)}
        if bank_account_id:
            relationships["bank_accounts"] = (
                "bank_accounts",
                require_id(bank_account_id, "bank_account_id"),
            )
        envelope = build_resource_envelope(_TYPE, attributes, relationships=relationships)
        return await client.request("POST", _PATH, json=envelope)
