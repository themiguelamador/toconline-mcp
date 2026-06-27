from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_PATH = "/api/commercial_sales_receipts"
_TYPE = "commercial_sales_receipts"
_LINE_PATH = "/api/commercial_sales_receipt_lines"
_LINE_TYPE = "commercial_sales_receipt_lines"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_sales_receipts(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        customer_id: Annotated[
            str | None, Field(description="Filter by customer id (exact match).")
        ] = None,
        date: Annotated[
            str | None, Field(description="Exact date match (YYYY-MM-DD).")
        ] = None,
        sort: Annotated[
            str, Field(description="JSON:API sort. Defaults to `-date`.")
        ] = "-date,-id",
        fields: Annotated[
            str | None, Field(description="Comma-separated subset of fields to return.")
        ] = None,
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
            params=build_list_params(
                page_size=page_size, page_number=page_number,
                filters=filters, sort=sort,
                fields={_TYPE: fields} if fields else None,
            ),
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

        Note: this creates the receipt itself. To settle specific sales
        documents against it, add `create_sales_receipt_line` calls referencing
        this receipt's id.
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

    @mcp.tool()
    async def create_sales_receipt_line(
        receipt_id: Annotated[str, Field(description="Parent sales receipt id (from create_sales_receipt).")],
        receivable_id: Annotated[
            str, Field(description="Id of the receivable being settled — the sales document id.")
        ],
        received_value: Annotated[
            float, Field(description="Amount of this receipt applied to the receivable.", gt=0)
        ],
        receivable_type: Annotated[
            str, Field(description="Receivable kind. `Document` for a sales document.")
        ] = "Document",
        gross_total: Annotated[float | None, Field(description="Gross total of the receivable line.")] = None,
        net_total: Annotated[float | None, Field(description="Net total of the receivable line.")] = None,
        retention_total: Annotated[float | None, Field(description="Withholding/retention amount.")] = None,
        settlement_amount: Annotated[float | None, Field(description="Early-settlement discount amount.")] = None,
        settlement_percentage: Annotated[float | None, Field(description="Early-settlement discount percentage.")] = None,
        cashed_vat_amount: Annotated[float | None, Field(description="Cashed-VAT amount, if applicable.")] = None,
    ) -> dict[str, Any]:
        """Settle a sales document against a receipt (settlement line).

        Links an existing receipt to a receivable so the document is marked
        paid. Field values (how much settles what) are the caller's
        responsibility — this tool only builds the documented payload.
        """
        attributes = {
            "receipt_id": require_id(receipt_id, "receipt_id"),
            "receivable_id": require_id(receivable_id, "receivable_id"),
            "receivable_type": receivable_type,
            "received_value": received_value,
            "gross_total": gross_total,
            "net_total": net_total,
            "retention_total": retention_total,
            "settlement_amount": settlement_amount,
            "settlement_percentage": settlement_percentage,
            "cashed_vat_amount": cashed_vat_amount,
        }
        envelope = build_resource_envelope(_LINE_TYPE, attributes)
        return await client.request("POST", _LINE_PATH, json=envelope)
