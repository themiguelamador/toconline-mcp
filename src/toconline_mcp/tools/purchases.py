from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_DOCS_PATH = "/api/commercial_purchases_documents"
_DOCS_V1_PATH = "/api/v1/commercial_purchases_documents"
_LINES_PATH = "/api/commercial_purchases_document_lines"
_PAYMENTS_PATH = "/api/commercial_purchases_payments"
_PAY_TYPE = "commercial_purchases_payments"
_V1_HEADERS = {"Content-Type": "application/json"}


class PurchaseDocumentLine(BaseModel):
    item_type: str | None = Field(
        None,
        description="TOCOnline item type: `Product`, `Service`, or `Purchases::ExpenseCategory`.",
    )
    item_id: str | None = Field(None, description="Id matching `item_type` (product/service/expense_category).")
    description: str | None = Field(None, description="Free-text description when no item_id.")
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    unit_of_measure_id: str | None = Field(None, description="Unit of measure id.")
    tax_id: str | None = Field(None, description="Tax id.")


def register(mcp: FastMCP, client: TocClient) -> None:
    # ---------- Purchase documents ----------

    @mcp.tool()
    async def list_purchase_documents(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        document_type: Annotated[
            str | None,
            Field(description="Exact document type code (supplier-invoice codes vary)."),
        ] = None,
        supplier_id: Annotated[
            str | None, Field(description="Filter by supplier id (exact match).")
        ] = None,
        date: Annotated[
            str | None,
            Field(description="Exact date match (YYYY-MM-DD). TOCOnline does not support ranges."),
        ] = None,
        sort: Annotated[
            str,
            Field(description="JSON:API sort. Defaults to `-date` (newest first). Prefix with `-` for descending."),
        ] = "-date",
    ) -> dict[str, Any]:
        """List commercial purchase documents, newest first by default."""
        filters: dict[str, Any] = {}
        if document_type:
            filters["document_type"] = document_type
        if supplier_id:
            filters["supplier_id"] = require_id(supplier_id, "supplier_id")
        if date:
            filters["date"] = require_iso_date(date, "date")
        return await client.request(
            "GET",
            _DOCS_PATH,
            params=build_list_params(page_size=page_size, filters=filters, sort=sort),
        )

    @mcp.tool()
    async def get_purchase_document(
        id: Annotated[str, Field(description="Purchase document id.")],
        include_lines: Annotated[
            bool,
            Field(description="If true, fetch line items separately and attach under `lines`."),
        ] = True,
    ) -> dict[str, Any]:
        """Fetch a purchase document, optionally with its line items merged."""
        safe_id = require_id(id, "id")
        doc_task = client.request("GET", f"{_DOCS_PATH}/{safe_id}")
        if not include_lines:
            return await doc_task
        lines_task = client.request(
            "GET",
            _LINES_PATH,
            params=build_list_params(page_size=100, filters={"document_id": safe_id}),
        )
        doc, lines = await asyncio.gather(doc_task, lines_task)
        if isinstance(doc, dict):
            doc["lines"] = lines.get("items") if isinstance(lines, dict) else lines
        return doc

    @mcp.tool()
    async def create_purchase_document(
        document_type: Annotated[str, Field(description="Purchase document type code (e.g. FC).")],
        supplier_id: Annotated[str, Field(description="TOCOnline supplier id.")],
        date: Annotated[str, Field(description="ISO date (YYYY-MM-DD).")],
        lines: Annotated[
            list[PurchaseDocumentLine],
            Field(description="At least one line item.", min_length=1),
        ],
        due_date: Annotated[str | None, Field(description="Payment due date (YYYY-MM-DD).")] = None,
        notes: Annotated[str | None, Field(description="Document notes.")] = None,
        external_reference: Annotated[
            str | None, Field(description="External reference (e.g. supplier invoice number).")
        ] = None,
        document_series_id: Annotated[
            str | None, Field(description="Document series id from /api/commercial_document_series.")
        ] = None,
    ) -> dict[str, Any]:
        """Create a purchase document with lines in a single v1 call.

        Supplier identity fields (tax number, business name) are denormalized
        from the supplier record.
        """
        require_iso_date(date, "date")
        safe_supplier_id = require_id(supplier_id, "supplier_id")
        if due_date:
            require_iso_date(due_date, "due_date")

        supplier = await client.request("GET", f"/api/suppliers/{safe_supplier_id}")
        body: dict[str, Any] = {
            "document_type": document_type,
            "date": date,
            "supplier_id": safe_supplier_id,
            "supplier_tax_registration_number": supplier.get("tax_registration_number"),
            "supplier_business_name": supplier.get("business_name"),
            "supplier_country": supplier.get("country_iso_alpha_2"),
            "due_date": due_date,
            "notes": notes,
            "external_reference": external_reference,
            "document_series_id": document_series_id,
            "lines": [line.model_dump(exclude_none=True) for line in lines],
        }
        body = {k: v for k, v in body.items() if v is not None}

        return await client.request(
            "POST", _DOCS_V1_PATH, json=body, headers=_V1_HEADERS
        )

    # ---------- Purchase payments ----------

    @mcp.tool()
    async def list_purchase_payments(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
        supplier_id: Annotated[
            str | None, Field(description="Filter by supplier id (exact match).")
        ] = None,
        date: Annotated[
            str | None, Field(description="Exact date match (YYYY-MM-DD).")
        ] = None,
        sort: Annotated[
            str,
            Field(description="JSON:API sort. Defaults to `-date`."),
        ] = "-date",
    ) -> dict[str, Any]:
        """List purchase payments, newest first by default."""
        filters: dict[str, Any] = {}
        if supplier_id:
            filters["third_party_id"] = require_id(supplier_id, "supplier_id")
        if date:
            filters["date"] = require_iso_date(date, "date")
        return await client.request(
            "GET",
            _PAYMENTS_PATH,
            params=build_list_params(page_size=page_size, filters=filters, sort=sort),
        )

    @mcp.tool()
    async def get_purchase_payment(
        id: Annotated[str, Field(description="Purchase payment id.")],
    ) -> dict[str, Any]:
        """Fetch a single purchase payment by id."""
        return await client.request("GET", f"{_PAYMENTS_PATH}/{require_id(id, 'id')}")

    @mcp.tool()
    async def create_purchase_payment(
        supplier_id: Annotated[str, Field(description="TOCOnline supplier id.")],
        date: Annotated[str, Field(description="ISO payment date (YYYY-MM-DD).")],
        gross_total: Annotated[float, Field(description="Total amount paid.", gt=0)],
        payment_mechanism: Annotated[
            str | None,
            Field(description="TOCOnline payment mechanism code (e.g. NUM, TRA, CC)."),
        ] = None,
        bank_account_id: Annotated[
            str | None,
            Field(description="Bank account id from /api/bank_accounts, if paid from a bank account."),
        ] = None,
        observations: Annotated[str | None, Field(description="Optional observations.")] = None,
    ) -> dict[str, Any]:
        """Create a purchase payment record.

        Note: this creates the payment itself; linking it to specific purchase
        documents (settlement) requires `commercial_purchases_payment_lines`,
        which is not wrapped by a typed tool yet — use `api_request` for that.
        """
        require_iso_date(date, "date")
        safe_supplier_id = require_id(supplier_id, "supplier_id")
        attributes = {
            "date": date,
            "gross_total": gross_total,
            "payment_mechanism": payment_mechanism,
            "observations": observations,
            "third_party_type": "suppliers",
        }
        relationships: dict[str, Any] = {"third_party": ("suppliers", safe_supplier_id)}
        if bank_account_id:
            relationships["bank_accounts"] = ("bank_accounts", require_id(bank_account_id, "bank_account_id"))
        envelope = build_resource_envelope(_PAY_TYPE, attributes, relationships=relationships)
        return await client.request("POST", _PAYMENTS_PATH, json=envelope)
