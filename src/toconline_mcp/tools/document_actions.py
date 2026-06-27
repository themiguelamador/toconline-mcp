"""Cross-cutting actions on sales/purchase documents: PDF, email, finalize, void.

Discovered from the TOCOnline Postman collection — these endpoints are not in
the public docs but are documented in the collection users can download from
Empresa → Configurações → Dados API.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import require_id

_URL_FOR_PRINT = "/api/url_for_print"
_EMAIL = "/api/email/document"


def _assemble_url(url_obj: dict[str, Any]) -> str:
    """`url_for_print` returns `{scheme, host, port, path}`. Reassemble to a string."""
    scheme = url_obj.get("scheme", "https")
    host = url_obj.get("host", "")
    port = url_obj.get("port")
    path = url_obj.get("path", "")
    port_part = ""
    if port and not (
        (scheme == "https" and int(port) == 443) or (scheme == "http" and int(port) == 80)
    ):
        port_part = f":{port}"
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{host}{port_part}{path}"


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def get_document_pdf_url(
        id: Annotated[str, Field(description="Document id (sales doc, sales receipt, or purchase doc).")],
        document_kind: Annotated[
            Literal["Document", "Receipt", "PurchasesDocument"],
            Field(
                description=(
                    "`Document` for sales documents, `Receipt` for sales receipts, "
                    "`PurchasesDocument` for purchase documents."
                )
            ),
        ] = "Document",
    ) -> dict[str, Any]:
        """Get a signed, shareable URL to a PDF render of a document or receipt.

        Returns a short-lived URL on `app14.toconline.pt` (or equivalent for
        your tenant) that serves the rendered PDF. The URL is signed and does
        not require authentication to open — give it to a user and they can
        download the PDF in their browser. It typically expires after a few
        hours.
        """
        safe_id = require_id(id, "id")
        response = await client.request(
            "GET",
            f"{_URL_FOR_PRINT}/{safe_id}",
            params={"filter[type]": document_kind},
        )
        # Flattened shape: {id, type, url: {scheme, host, port, path}}
        url_obj = response.get("url") if isinstance(response, dict) else None
        if not isinstance(url_obj, dict):
            return {"url": None, "raw": response}
        return {"url": _assemble_url(url_obj), "expires": "short-lived (typically hours)"}

    @mcp.tool()
    async def send_document_email(
        id: Annotated[str, Field(description="Id of the sales document or receipt to send.")],
        to_email: Annotated[str, Field(description="Recipient email address.")],
        from_email: Annotated[str, Field(description="Sender email address (must be allowed by TOCOnline).")],
        from_name: Annotated[str, Field(description="Sender display name.")],
        subject: Annotated[str, Field(description="Email subject line.")],
        document_kind: Annotated[
            Literal["Document", "Receipt"],
            Field(description="`Document` for a sales document, `Receipt` for a sales receipt."),
        ] = "Document",
    ) -> dict[str, Any]:
        """Send a sales document or receipt to a recipient by email.

        Uses TOCOnline's built-in email delivery — the message arrives from
        TOCOnline's mail servers with your document attached / linked.
        """
        safe_id = require_id(id, "id")
        envelope = {
            "data": {
                "type": "email/document",
                "id": safe_id,
                "attributes": {
                    "type": document_kind,
                    "to_email": to_email,
                    "from_email": from_email,
                    "from_name": from_name,
                    "subject": subject,
                },
            }
        }
        return await client.request("PATCH", _EMAIL, json=envelope)

    @mcp.tool()
    async def finalize_sales_document(
        id: Annotated[str, Field(description="Sales document id (must currently be in draft status).")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Finalization is fiscally binding and cannot be undone."),
        ] = False,
    ) -> dict[str, Any]:
        """Finalize (issue) a draft sales document.

        Once finalized, the document becomes fiscally valid and immutable.
        Requires `confirm=true` because the operation cannot be reversed.
        """
        if not confirm:
            raise ValueError(
                "finalize_sales_document requires confirm=true. "
                "Finalizing is irreversible and makes the document fiscally valid."
            )
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_sales_documents/{safe_id}/finalize", json={}
        )

    @mcp.tool()
    async def finalize_purchase_document(
        id: Annotated[str, Field(description="Purchase document id.")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Finalization is binding."),
        ] = False,
    ) -> dict[str, Any]:
        """Finalize a draft purchase document."""
        if not confirm:
            raise ValueError("finalize_purchase_document requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_purchases_documents/{safe_id}/finalize", json={}
        )

    @mcp.tool()
    async def communicate_sales_document_at(
        id: Annotated[str, Field(description="Sales document id (must be finalized first).")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Communicating to the AT is a binding fiscal action."),
        ] = False,
    ) -> dict[str, Any]:
        """Communicate a finalized sales document to the AT (Portuguese tax authority).

        Triggers TOCOnline's `send_document_at_webservice` action. The document
        must already be finalized. Requires `confirm=true` because the report is
        a binding fiscal submission. The response carries the AT communication
        status/code returned by the webservice.
        """
        if not confirm:
            raise ValueError("communicate_sales_document_at requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH",
            f"/api/v1/commercial_sales_documents/{safe_id}/send_document_at_webservice",
            json={},
        )

    @mcp.tool()
    async def communicate_purchase_document_at(
        id: Annotated[str, Field(description="Purchase document id (must be finalized first).")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Communicating to the AT is a binding fiscal action."),
        ] = False,
    ) -> dict[str, Any]:
        """Communicate a finalized purchase document to the AT (Portuguese tax authority)."""
        if not confirm:
            raise ValueError("communicate_purchase_document_at requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH",
            f"/api/v1/commercial_purchases_documents/{safe_id}/send_document_at_webservice",
            json={},
        )

    @mcp.tool()
    async def void_sales_receipt(
        id: Annotated[str, Field(description="Sales receipt id to void.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Voiding cannot be reversed.")
        ] = False,
    ) -> dict[str, Any]:
        """Void (anular) a sales receipt."""
        if not confirm:
            raise ValueError("void_sales_receipt requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_sales_receipts/{safe_id}/void", json={}
        )

    @mcp.tool()
    async def void_purchase_document(
        id: Annotated[str, Field(description="Purchase document id to void.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Voiding cannot be reversed.")
        ] = False,
    ) -> dict[str, Any]:
        """Void (anular) a purchase document."""
        if not confirm:
            raise ValueError("void_purchase_document requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_purchases_documents/{safe_id}/void", json={}
        )
