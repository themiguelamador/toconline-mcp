"""Read-only auxiliary/reference tables.

Small lookup resources used when building documents and items: countries,
item families, units of measure, tax descriptors (VAT rates), and cash
accounts. All are GET-only lists.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import build_list_params

# (tool_name, resource_type, path, docstring)
_TABLES = [
    ("list_countries", "countries", "/api/countries", "List countries (ISO codes, names)."),
    ("list_item_families", "item_families", "/api/item_families",
     "List item families — used to categorize products/services (`item_family_id`)."),
    ("list_units_of_measure", "units_of_measure", "/api/units_of_measure",
     "List units of measure (unidades) for document lines."),
    ("list_tax_descriptors", "tax_descriptors", "/api/tax_descriptors",
     "List tax descriptors — VAT rates and their codes (`NOR`, `INT`, `RED`, `ISE`)."),
    ("list_cash_accounts", "cash_accounts", "/api/cash_accounts",
     "List cash accounts (caixas) used for receipts/payments."),
]


def register(mcp: FastMCP, client: TocClient) -> None:
    for tool_name, resource, path, doc in _TABLES:
        _make_list_tool(mcp, client, tool_name, resource, path, doc)


def _make_list_tool(
    mcp: FastMCP, client: TocClient, tool_name: str, resource: str, path: str, doc: str
) -> None:
    # path/resource captured by closure — this function's own scope per table row.
    async def _list(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 100,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        sort: Annotated[str | None, Field(description="JSON:API sort, e.g. `-created_at`.")] = None,
        fields: Annotated[
            str | None, Field(description="Comma-separated subset of fields to return.")
        ] = None,
    ) -> dict[str, Any]:
        return await client.request(
            "GET",
            path,
            params=build_list_params(
                page_size=page_size, page_number=page_number,
                filters=None, sort=sort,
                fields={resource: fields} if fields else None,
            ),
        )

    _list.__name__ = tool_name
    _list.__doc__ = doc
    mcp.tool(name=tool_name)(_list)
