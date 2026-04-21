from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_DOCS_PATH = "/api/commercial_sales_documents"
_LINES_PATH = "/api/commercial_sales_document_lines"
_DOC_TYPE = "commercial_sales_documents"


class SalesDocumentLine(BaseModel):
    product_id: str | None = Field(None, description="TOCOnline product id (optional if description provided).")
    description: str | None = Field(None, description="Free-text description when no product_id.")
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    tax_code: str | None = Field(None, description="TOCOnline tax code, e.g. NOR, ISE.")


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def list_sales_documents(
        page_size: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
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
    ) -> dict[str, Any]:
        """List commercial sales documents with pagination.

        All filters are **exact match** — TOCOnline does not expose range or
        substring operators. For a date range, make one call per day, or use
        `api_request` with whatever filter keys the endpoint supports.
        """
        filters: dict[str, Any] = {}
        if document_type:
            filters["document_type"] = document_type
        if customer_id:
            filters["customer_id"] = require_id(customer_id, "customer_id")
        if date:
            filters["date"] = require_iso_date(date, "date")
        return await client.request(
            "GET", _DOCS_PATH, params=build_list_params(page_size=page_size, filters=filters)
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
        notes: Annotated[str | None, Field(description="Optional document notes.")] = None,
        parent_document_id: Annotated[
            str | None,
            Field(
                description=(
                    "For rectificative documents (NC credit note, ND debit note): id of "
                    "the original sales document this one rectifies. Creates a "
                    "`parent_documents` relationship."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a draft sales document with line items.

        The document is created as a draft; finalizing/issuing is a separate
        TOCOnline operation not covered by the MVP. For credit/debit notes
        (rectificative documents), set `document_type='NC'` or `'ND'` and
        point `parent_document_id` at the original document.
        """
        if not lines:
            raise ValueError("at least one line item is required")
        require_iso_date(date, "date")
        safe_customer_id = require_id(customer_id, "customer_id")
        attributes = {
            "document_type": document_type,
            "date": date,
            "notes": notes,
            "lines": [line.model_dump(exclude_none=True) for line in lines],
        }
        relationships: dict[str, Any] = {"customer": ("customers", safe_customer_id)}
        if parent_document_id:
            safe_parent = require_id(parent_document_id, "parent_document_id")
            relationships["parent_documents"] = [(_DOC_TYPE, safe_parent)]
        envelope = build_resource_envelope(_DOC_TYPE, attributes, relationships=relationships)
        return await client.request("POST", _DOCS_PATH, json=envelope)
