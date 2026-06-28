from __future__ import annotations

import asyncio
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from toconline_mcp.http.client import TocClient
from toconline_mcp.http.jsonapi import build_resource_envelope
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date
from toconline_mcp.util.errors import ApiError
from toconline_mcp.util.logger import get_logger

_log = get_logger(__name__)

_DOCS_PATH = "/api/commercial_sales_documents"
_DOCS_V1_PATH = "/api/v1/commercial_sales_documents"
_LINES_PATH = "/api/commercial_sales_document_lines"
_DOC_TYPE = "commercial_sales_documents"
_LINES_TYPE = "commercial_sales_document_lines"
_V1_HEADERS = {"Content-Type": "application/json"}


class SalesDocumentLine(BaseModel):
    """One line on a sales document.

    Either `item_id` (with `item_type`) or a free-text `description` must be
    present — TOCOnline rejects a line with neither. The v1 endpoint accepts
    both shapes.
    """

    model_config = ConfigDict(populate_by_name=True)

    item_type: str | None = Field(
        None, description="Item type when referencing the catalog: `Product` or `Service`. Required with item_id."
    )
    item_id: str | None = Field(
        None,
        description=(
            "Catalog product/service id (from list_products / list_services). When set with "
            "item_type, the line inherits the item's code, unit, and (if not overridden) price/VAT — "
            "`item_code` is filled automatically. Omit for a free-text line and set `description`."
        ),
    )
    description: str | None = Field(
        None,
        validation_alias=AliasChoices("description", "item_description"),
        description="Line description (required unless item_id is set). Accepts `item_description` as an alias.",
    )
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    unit_of_measure_id: str | None = Field(None, description="Unit of measure id from /api/units_of_measure.")
    tax_code: str | None = Field(
        None, description="VAT rate code — `NOR`, `INT`, `RED`, `ISE`. Simpler than tax_id; the line resolves the rate."
    )
    tax_id: str | None = Field(None, description="Tax id from /api/taxes. Prefer `tax_code` unless you need a specific tax row.")
    settlement_expression: str | None = Field(None, description="Line-level discount expression, e.g. '3'.")

    @model_validator(mode="after")
    def _require_description_or_item(self) -> "SalesDocumentLine":
        if not self.description and not self.item_id:
            raise ValueError(
                "each sales document line needs `description` (free text) or `item_id` — "
                "TOCOnline rejects lines with neither"
            )
        return self


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
        # Nested route — the flat /commercial_sales_document_lines?filter[document_id]
        # query raises JA011, so fetch lines via /{id}/lines instead.
        lines_task = client.request("GET", f"{_DOCS_PATH}/{safe_id}/lines")
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
        date: Annotated[
            str,
            Field(
                description=(
                    "ISO date, e.g. 2025-01-15. On a certified series the date cannot "
                    "precede the last issued document's date — TOCOnline rejects back-dating "
                    "before the most recent document in the series."
                )
            ),
        ],
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
        series_id: Annotated[
            str | None,
            Field(
                description=(
                    "Document series id (from /api/commercial_document_series) to issue into. "
                    "A document_type can have several series, each with its own numbering. "
                    "Omit to use the type's default series."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a sales document with line items.

        Two code paths depending on `finalize`:

          * `finalize=True` — uses the v1 endpoint
            (`POST /api/v1/commercial_sales_documents`), which takes a flat
            body, embeds lines inline, and **issues the document immediately**
            (fiscally binding, irreversible). Customer identity fields are
            denormalized by fetching `/api/customers/{customer_id}` first.
          * `finalize=False` (default) — uses the legacy JSON:API endpoint
            multi-step: POST the header to `/api/commercial_sales_documents`,
            then POST each line to `/api/commercial_sales_document_lines`
            with `document_id` linking. The document stays as a **draft**
            (status 0) — editable, not yet fiscally valid. To issue later,
            call `finalize_sales_document(id)`.

        v1 ignores `finalize=0` (the documented field), so the legacy path is
        the only way to actually leave a doc in draft state via this API.

        Customer identity (name, tax number, address) is denormalized onto the
        header by TOCOnline server-side, on both paths — but only from the
        customer's **main address**. If the header comes back with an empty
        `customer_address_detail`, the customer has no `main_address_id` set;
        fix the customer's address rather than passing address fields here.

        Date: on a certified series the date cannot precede that series' last
        issued document. The API enforces this per series; we deliberately
        don't pre-check it client-side — a document_type can map to several
        series (e.g. FT uses both `FT 2026/…` and `FT 2026P/…`) and we don't
        know which the API will assign, so any client-side guess would risk
        blocking a legitimately back-dated document in another series.

        Series: omit `series_id` to use the type's default series. The draft
        path honours `series_id` (verified). On the `finalize=True` v1 path the
        series field is best-effort and unverified (verifying it needs an
        irreversible emission) — it falls back to the default if unsupported.
        Discover ids with `list_document_series`.
        """
        require_iso_date(date, "date")
        safe_customer_id = require_id(customer_id, "customer_id")
        if due_date:
            require_iso_date(due_date, "due_date")

        if finalize:
            return await _create_finalized_v1(
                client,
                document_type=document_type,
                customer_id=safe_customer_id,
                date=date,
                lines=lines,
                due_date=due_date,
                notes=notes,
                external_reference=external_reference,
                payment_mechanism=payment_mechanism,
                parent_document_id=parent_document_id,
                series_id=series_id,
            )
        return await _create_draft_legacy(
            client,
            document_type=document_type,
            customer_id=safe_customer_id,
            date=date,
            lines=lines,
            due_date=due_date,
            notes=notes,
            external_reference=external_reference,
            payment_mechanism=payment_mechanism,
            parent_document_id=parent_document_id,
            series_id=series_id,
        )

    @mcp.tool()
    async def delete_sales_document(
        id: Annotated[str, Field(description="Sales document id to delete.")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Only drafts can be deleted; finalized documents must be voided instead."),
        ] = False,
    ) -> dict[str, Any]:
        """Delete a draft sales document.

        Use this for cleaning up unfinalised drafts (e.g. orphans left behind
        by a failed `create_sales_document` call, or experimental drafts you
        no longer want). Will fail if the document has been finalised
        (status != 0) — finalised documents must be voided via a credit note,
        not deleted.
        """
        if not confirm:
            raise ValueError("delete_sales_document requires confirm=true")
        safe_id = require_id(id, "id")
        await client.request("DELETE", f"{_DOCS_PATH}/{safe_id}")
        return {"status": "deleted", "id": safe_id}


async def _create_finalized_v1(
    client: TocClient,
    *,
    document_type: str,
    customer_id: str,
    date: str,
    lines: list["SalesDocumentLine"],
    due_date: str | None,
    notes: str | None,
    external_reference: str | None,
    payment_mechanism: str | None,
    parent_document_id: str | None,
    series_id: str | None = None,
) -> dict[str, Any]:
    customer = await client.request("GET", f"/api/customers/{customer_id}")
    body: dict[str, Any] = {
        "document_type": document_type,
        "date": date,
        "finalize": 1,
        "customer_tax_registration_number": customer.get("tax_registration_number"),
        "customer_business_name": customer.get("business_name"),
        "customer_country": customer.get("country_iso_alpha_2"),
        "due_date": due_date,
        "notes": notes,
        "external_reference": external_reference,
        "payment_mechanism": payment_mechanism,
        # Flat-body series field for the v1 endpoint. Unverified live (would need an
        # irreversible emission); when omitted the API uses the type's default series.
        "commercial_document_series_id": require_id(series_id, "series_id") if series_id else None,
        "lines": [line.model_dump(exclude_none=True) for line in lines],
    }
    if parent_document_id:
        body["parent_documents_ids"] = [require_id(parent_document_id, "parent_document_id")]
    body = {k: v for k, v in body.items() if v is not None}
    return await client.request("POST", _DOCS_V1_PATH, json=body, headers=_V1_HEADERS)


async def _create_draft_legacy(
    client: TocClient,
    *,
    document_type: str,
    customer_id: str,
    date: str,
    lines: list["SalesDocumentLine"],
    due_date: str | None,
    notes: str | None,
    external_reference: str | None,
    payment_mechanism: str | None,
    parent_document_id: str | None,
    series_id: str | None = None,
) -> dict[str, Any]:
    """Multi-step draft creation: POST header, POST each line, refetch with lines merged."""
    header_attrs: dict[str, Any] = {
        "document_type": document_type,
        "date": date,
        "customer_id": customer_id,
        "due_date": due_date,
        "notes": notes,
        "external_reference": external_reference,
        "payment_mechanism": payment_mechanism,
    }
    envelope = build_resource_envelope(_DOC_TYPE, header_attrs)
    if parent_document_id:
        # JSON:API to-many relationship for rectificative-document parents.
        safe_parent = require_id(parent_document_id, "parent_document_id")
        envelope["data"].setdefault("relationships", {})
        envelope["data"]["relationships"]["parent_documents"] = {
            "data": [{"type": _DOC_TYPE, "id": safe_parent}]
        }
    if series_id:
        # Series is set via a relationship, not an attribute (an attribute raises
        # JA000). Verified live: the draft lands in the requested series.
        envelope["data"].setdefault("relationships", {})
        envelope["data"]["relationships"]["commercial_document_series"] = {
            "data": {"type": "commercial_document_series", "id": require_id(series_id, "series_id")}
        }

    header = await client.request("POST", _DOCS_PATH, json=envelope)
    new_id = header.get("id") if isinstance(header, dict) else None
    if not new_id:
        raise ApiError(500, "draft document created but id missing from response", header)
    new_id = str(new_id)

    # Lines reference the header by document_id (attribute, not relationship).
    line_envelopes = [
        build_resource_envelope(
            _LINES_TYPE,
            {**line.model_dump(exclude_none=True), "document_id": new_id},
        )
        for line in lines
    ]
    # Post lines in parallel for speed. If any fails, roll back the orphan
    # header so the caller doesn't accumulate empty/partial drafts on retry.
    try:
        await asyncio.gather(
            *[client.request("POST", _LINES_PATH, json=env) for env in line_envelopes]
        )
    except Exception as line_err:
        rollback_note = ""
        try:
            await client.request("DELETE", f"{_DOCS_PATH}/{new_id}")
            _log.info(f"Rolled back orphan draft sales document id={new_id} after line POST failure")
            rollback_note = f" (orphan header id={new_id} was deleted)"
        except Exception as rb_err:
            _log.warning(
                f"Failed to roll back orphan draft sales document id={new_id}: {rb_err}"
            )
            rollback_note = (
                f" (WARNING: orphan draft id={new_id} could not be auto-deleted: "
                f"{rb_err}; delete it with delete_sales_document or via the UI)"
            )
        # Re-raise as ApiError so the failure surfaces clearly with the rollback note.
        status = getattr(line_err, "status", 500)
        raise ApiError(status, f"line creation failed: {line_err}{rollback_note}", None) from line_err

    # Lenient refetch: if it fails, the document IS created — don't make the
    # caller think the whole call failed (which leads to retry storms that
    # accumulate duplicate drafts).
    try:
        doc, lines_resp = await asyncio.gather(
            client.request("GET", f"{_DOCS_PATH}/{new_id}"),
            client.request("GET", f"{_DOCS_PATH}/{new_id}/lines"),
        )
        if isinstance(doc, dict):
            doc["lines"] = lines_resp.get("items") if isinstance(lines_resp, dict) else lines_resp
        return doc
    except Exception as refetch_err:
        _log.warning(f"create_sales_document: refetch failed for id={new_id}: {refetch_err}")
        result = dict(header) if isinstance(header, dict) else {"id": new_id}
        result["_warning"] = (
            f"document created successfully (id={new_id}) but refetch failed: "
            f"{refetch_err}. Use get_sales_document(id={new_id}) to see the final state."
        )
        return result
