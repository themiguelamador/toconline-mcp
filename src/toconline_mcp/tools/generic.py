from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient

# Each segment: starts and ends with alnum/underscore; dash permitted in the middle only.
# Path is `/api` + one or more such segments, optional trailing slash.
# Rejects `//`, leading/trailing dashes in segments, query strings, fragments, `..`.
_SEGMENT = r"[A-Za-z0-9_](?:[A-Za-z0-9_\-]*[A-Za-z0-9_])?"
_PATH_RE = re.compile(rf"^/api(?:/{_SEGMENT})+/?$")
_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    if not _PATH_RE.match(path):
        raise ValueError(
            f"path {path!r} must match `/api/<resource>[/<sub>...]` — letters, "
            "digits, underscore, or dash only; no query string, fragment, or `..` segments"
        )


def register(mcp: FastMCP, client: TocClient) -> None:
    @mcp.tool()
    async def api_request(
        method: Annotated[
            Literal["GET", "POST", "PATCH", "PUT", "DELETE"],
            Field(description="HTTP method."),
        ],
        path: Annotated[
            str,
            Field(description="API path starting with /api/, e.g. /api/commercial_purchases_documents."),
        ],
        query: Annotated[
            dict[str, Any] | None,
            Field(description="Query parameters as a flat object."),
        ] = None,
        body: Annotated[
            dict[str, Any] | None,
            Field(description="Raw JSON:API envelope for writes, shape `{data: {type, attributes, ...}}`."),
        ] = None,
        flatten: Annotated[
            bool,
            Field(description="Flatten JSON:API response. Set false to see the raw envelope."),
        ] = True,
        confirm: Annotated[
            bool,
            Field(description="Must be true for POST/PATCH/PUT/DELETE. Safety gate against unintended writes."),
        ] = False,
    ) -> Any:
        """Escape hatch for endpoints not covered by typed tools.

        Path must match `/api/<resource>[/<sub>...]`. Destructive methods require
        `confirm=true`. Prefer the typed tools (list_customers, create_sales_document,
        etc.) when they fit.

        Known API constraints (these are API limitations, not bugs — a `JA011`
        "pedido inválido" is the symptom, don't treat it as a server fault):
        - To list a document's lines or an entity's addresses, use the NESTED
          route, not a flat filter: `GET /api/commercial_sales_documents/{id}/lines`
          and `GET /api/customers/{id}/addresses`. The flat
          `?filter[document_id]=…` / `?filter[customer_id]=…` forms return JA011.
        - Sparse fieldsets (`fields[<type>]=…`) accept scalar attributes only;
          relationship names (`*_id`, `*_ids`) cause JA011 — omit them.
        - Link an address to a customer/supplier via the `addressable_type` +
          `addressable_id` attributes (a `customer` relationship is ignored).
        """
        _validate_path(path)
        upper = method.upper()
        if upper in _WRITE_METHODS and not confirm:
            raise ValueError(
                f"{upper} requires confirm=true. "
                "Set confirm=true only when you intend to write/delete."
            )
        return await client.request(upper, path, params=query, json=body, flatten=flatten)
