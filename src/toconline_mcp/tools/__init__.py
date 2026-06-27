from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from toconline_mcp.gmail.store import gmail_credentials_path
from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import (
    addresses,
    auth,
    bank,
    company,
    contacts,
    customers,
    document_actions,
    generic,
    gmail_tools,
    products,
    purchases,
    reference,
    sales_documents,
    sales_receipts,
    services,
    suppliers,
)


def register_all(mcp: FastMCP, client: TocClient) -> None:
    auth.register(mcp, client)
    company.register(mcp, client)
    customers.register(mcp, client)
    suppliers.register(mcp, client)
    products.register(mcp, client)
    services.register(mcp, client)
    reference.register(mcp, client)
    sales_documents.register(mcp, client)
    sales_receipts.register(mcp, client)
    purchases.register(mcp, client)
    addresses.register(mcp, client)
    contacts.register(mcp, client)
    bank.register(mcp, client)
    document_actions.register(mcp, client)
    generic.register(mcp, client)
    # Gmail is an optional companion (invoice-PDF archiving). Only expose its
    # tools once credentials exist — first-time login is the CLI `gmail-setup`.
    # ponytail: gate on creds file; set TOCONLINE_GMAIL=1 to force-enable.
    if os.environ.get("TOCONLINE_GMAIL") == "1" or gmail_credentials_path().exists():
        gmail_tools.register(mcp)
