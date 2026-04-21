from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import (
    auth,
    customers,
    generic,
    products,
    sales_documents,
    suppliers,
)


def register_all(mcp: FastMCP, client: TocClient) -> None:
    auth.register(mcp, client)
    customers.register(mcp, client)
    suppliers.register(mcp, client)
    products.register(mcp, client)
    sales_documents.register(mcp, client)
    generic.register(mcp, client)
