from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import (
    addresses,
    auth,
    contacts,
    customers,
    generic,
    products,
    purchases,
    sales_documents,
    sales_receipts,
    suppliers,
)


def register_all(mcp: FastMCP, client: TocClient) -> None:
    auth.register(mcp, client)
    customers.register(mcp, client)
    suppliers.register(mcp, client)
    products.register(mcp, client)
    sales_documents.register(mcp, client)
    sales_receipts.register(mcp, client)
    purchases.register(mcp, client)
    addresses.register(mcp, client)
    contacts.register(mcp, client)
    generic.register(mcp, client)
