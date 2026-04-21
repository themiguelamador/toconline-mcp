from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import register_all
from toconline_mcp.util.logger import get_logger

_log = get_logger(__name__)


def _pin_all_loggers_to_stderr() -> None:
    """Force every logger — root, httpx, mcp — to stderr.

    Stdout is reserved for MCP stdio framing. Any library that logs to root
    at import time (httpx, httpcore, mcp.*) must never touch stdout.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    for name in ("httpx", "httpcore", "mcp", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def build_server() -> FastMCP:
    mcp = FastMCP(
        name="toconline",
        instructions=(
            "Tools for the TOCOnline (Portuguese accounting/invoicing) API. "
            "Use list_* to search, get_* to fetch by id, and create_*/update_* for writes. "
            "Prefer typed tools over api_request. Responses are flattened from JSON:API."
        ),
    )
    client = TocClient()
    register_all(mcp, client)
    return mcp


def run() -> None:
    _pin_all_loggers_to_stderr()
    mcp = build_server()
    _log.info("Starting TOCOnline MCP server on stdio")
    mcp.run(transport="stdio")
