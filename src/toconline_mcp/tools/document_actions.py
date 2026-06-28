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

# v1 action endpoints take flat (non-JSON:API) bodies; the client defaults to
# application/vnd.api+json, so override per the TocClient.request contract.
_V1_JSON = {"Content-Type": "application/json"}


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
            Field(description="`Document` (sales doc), `Receipt` (sales receipt), or `PurchasesDocument` (purchase doc)."),
        ] = "Document",
    ) -> dict[str, Any]:
        """Get a signed, shareable, short-lived URL to a PDF render of a document or receipt. Only finalized documents have a PDF; finalize a draft first."""
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
        """Send a sales document or receipt to a recipient via TOCOnline's built-in email delivery."""
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
        """Finalize (issue) a draft sales document. Becomes fiscally valid and immutable; irreversible, requires confirm=true."""
        if not confirm:
            raise ValueError(
                "finalize_sales_document requires confirm=true. "
                "Finalizing is irreversible and makes the document fiscally valid."
            )
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_sales_documents/{safe_id}/finalize",
            json={}, headers=_V1_JSON,
        )

    @mcp.tool()
    async def finalize_purchase_document(
        id: Annotated[str, Field(description="Purchase document id.")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Finalization is binding."),
        ] = False,
    ) -> dict[str, Any]:
        """Finalize a draft purchase document. Binding; requires confirm=true."""
        if not confirm:
            raise ValueError("finalize_purchase_document requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_purchases_documents/{safe_id}/finalize",
            json={}, headers=_V1_JSON,
        )

    @mcp.tool()
    async def communicate_sales_document_at(
        id: Annotated[str, Field(description="Sales document id (must be finalized first).")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Communicating to the AT is a binding fiscal action."),
        ] = False,
    ) -> dict[str, Any]:
        """Communicate a finalized sales document to the AT (Portuguese tax authority). Document must be finalized first; binding fiscal submission, requires confirm=true."""
        if not confirm:
            raise ValueError("communicate_sales_document_at requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH",
            f"/api/v1/commercial_sales_documents/{safe_id}/send_document_at_webservice",
            json={}, headers=_V1_JSON,
        )

    @mcp.tool()
    async def communicate_purchase_document_at(
        id: Annotated[str, Field(description="Purchase document id (must be finalized first).")],
        confirm: Annotated[
            bool,
            Field(description="Must be true. Communicating to the AT is a binding fiscal action."),
        ] = False,
    ) -> dict[str, Any]:
        """Communicate a finalized purchase document to the AT (Portuguese tax authority). Binding fiscal submission, requires confirm=true."""
        if not confirm:
            raise ValueError("communicate_purchase_document_at requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH",
            f"/api/v1/commercial_purchases_documents/{safe_id}/send_document_at_webservice",
            json={}, headers=_V1_JSON,
        )

    @mcp.tool()
    async def void_sales_receipt(
        id: Annotated[str, Field(description="Sales receipt id to void.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Voiding cannot be reversed.")
        ] = False,
    ) -> dict[str, Any]:
        """Void (anular) a sales receipt. Irreversible; requires confirm=true."""
        if not confirm:
            raise ValueError("void_sales_receipt requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_sales_receipts/{safe_id}/void",
            json={}, headers=_V1_JSON,
        )

    @mcp.tool()
    async def void_purchase_document(
        id: Annotated[str, Field(description="Purchase document id to void.")],
        confirm: Annotated[
            bool, Field(description="Must be true. Voiding cannot be reversed.")
        ] = False,
    ) -> dict[str, Any]:
        """Void (anular) a purchase document. Irreversible; requires confirm=true."""
        if not confirm:
            raise ValueError("void_purchase_document requires confirm=true")
        safe_id = require_id(id, "id")
        return await client.request(
            "PATCH", f"/api/v1/commercial_purchases_documents/{safe_id}/void",
            json={}, headers=_V1_JSON,
        )
