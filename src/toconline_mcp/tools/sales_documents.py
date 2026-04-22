from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_DOCS_PATH = "/api/commercial_sales_documents"
_DOCS_V1_PATH = "/api/v1/commercial_sales_documents"
_LINES_PATH = "/api/commercial_sales_document_lines"
_DOC_TYPE = "commercial_sales_documents"
_V1_HEADERS = {"Content-Type": "application/json"}


class SalesDocumentLine(BaseModel):
    """One line on a sales document.

    Either `item_id` (with `item_type`) or a free-text `description` must be
    present. The v1 endpoint accepts both shapes.
    """

    item_type: str | None = Field(
        None, description="TOCOnline item type, usually `Product` or `Service`. Required when item_id is set."
    )
    item_id: str | None = Field(None, description="TOCOnline product or service id.")
    description: str | None = Field(None, description="Free-text description when no item_id.")
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    unit_of_measure_id: str | None = Field(None, description="Unit of measure id from /api/units_of_measure.")
    tax_id: str | None = Field(None, description="Tax id from /api/taxes.")
    settlement_expression: str | None = Field(None, description="Line-level discount expression, e.g. '3'.")


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_sales_documents(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[
            int, Field(description="1-based page number for paging past the first page.", ge=1)
        ] = 1,
        document_type: Annotated[
            str | None,
            Field(description="Exact document type code, e.g. FT (invoice), FR (receipt), NC (credit note)."),
        ] = None,
        customer_id: Annotated[
            str | None, Field(description="Filter by customer id (exact match).")
        ] = None,
        date: Annotated[
            str | None,
            Field(description="Exact date match (YYYY-MM-DD). TOCOnline does not support ranges."),
        ] = None,
        sort: Annotated[
            str,
            Field(
                description=(
                    "JSON:API sort expression. Prefix with `-` for descending. "
                    "Defaults to `-date`. Examples: `-date`, `date,document_no`, `-id`, `-gross_total`."
                )
            ),
        ] = "-date,-id",
        fields: Annotated[
            str | None,
            Field(
                description=(
                    "Comma-separated subset of fields to return. Hugely reduces response size — "
                    "sales docs have 117 fields. Common subset: `document_no,date,gross_total,status,customer_id`."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """List commercial sales documents, newest first by default.

        Use `page_number` + `page_size` to paginate, and `fields` to limit
        the response to just the columns you need.
        """
        filters: dict[str, Any] = {}
        if document_type:
            filters["document_type"] = document_type
        if customer_id:
            filters["customer_id"] = require_id(customer_id, "customer_id")
        if date:
            filters["date"] = require_iso_date(date, "date")
        return await client.request(
            "GET",
            _DOCS_PATH,
            params=build_list_params(
                page_size=page_size, page_number=page_number,
                filters=filters, sort=sort,
                fields={_DOC_TYPE: fields} if fields else None,
            ),
        )

    @mcp.tool()
    async def get_sales_document(
        id: Annotated[str, Field(description="Sales document id.")],
        include_lines: Annotated[
            bool,
            Field(description="If true, fetch line items separately and attach under `lines`."),
        ] = True,
    ) -> dict[str, Any]:
        """Fetch a sales document, optionally with its line items merged."""
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
    async def create_sales_document(
        document_type: Annotated[
            str,
            Field(
                description=(
                    "Document type code. Common: FT (invoice), FR (invoice-receipt), "
                    "NC (credit note / rectificative), ND (debit note / rectificative), "
                    "FT-FA (simplified invoice)."
                )
            ),
        ],
        customer_id: Annotated[str, Field(description="TOCOnline customer id.")],
        date: Annotated[str, Field(description="ISO date, e.g. 2025-01-15.")],
        lines: Annotated[
            list[SalesDocumentLine], Field(description="At least one line item.", min_length=1)
        ],
        due_date: Annotated[str | None, Field(description="Payment due date (YYYY-MM-DD).")] = None,
        notes: Annotated[str | None, Field(description="Customer-visible notes on the document.")] = None,
        external_reference: Annotated[
            str | None, Field(description="External reference id (e.g. PO number).")
        ] = None,
        payment_mechanism: Annotated[
            str | None,
            Field(description="TOCOnline payment mechanism code (e.g. MO, NUM, TRA, CC)."),
        ] = None,
        finalize: Annotated[
            bool,
            Field(description="If true, the document is issued immediately (fiscally binding). If false, it stays as a draft."),
        ] = False,
        parent_document_id: Annotated[
            str | None,
            Field(
                description=(
                    "For rectificative documents (NC / ND): id of the original sales document this rectifies. "
                    "Included via the `parent_documents_ids` attribute."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a sales document with line items in a single call.

        Uses the v1 endpoint (`POST /api/v1/commercial_sales_documents`) which
        takes a flat body and embeds lines inline — no separate line calls.
        Customer details (tax number, name, address) are denormalized onto the
        document by fetching `/api/customers/{customer_id}` first, matching
        how TOCOnline's own UI issues documents.
        """
        require_iso_date(date, "date")
        safe_customer_id = require_id(customer_id, "customer_id")
        if due_date:
            require_iso_date(due_date, "due_date")

        # Fetch the customer to denormalize the identity fields v1 expects.
        customer = await client.request("GET", f"/api/customers/{safe_customer_id}")
        body: dict[str, Any] = {
            "document_type": document_type,
            "date": date,
            "finalize": 1 if finalize else 0,
            "customer_tax_registration_number": customer.get("tax_registration_number"),
            "customer_business_name": customer.get("business_name"),
            "customer_country": customer.get("country_iso_alpha_2"),
            "due_date": due_date,
            "notes": notes,
            "external_reference": external_reference,
            "payment_mechanism": payment_mechanism,
            "lines": [line.model_dump(exclude_none=True) for line in lines],
        }
        if parent_document_id:
            body["parent_documents_ids"] = [require_id(parent_document_id, "parent_document_id")]
        body = {k: v for k, v in body.items() if v is not None}

        return await client.request(
            "POST", _DOCS_V1_PATH, json=body, headers=_V1_HEADERS
        )
