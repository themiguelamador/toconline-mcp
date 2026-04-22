from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_ACCOUNTS_PATH = "/api/bank_accounts"
_TX_PATH = "/api/bank_transactions"


def register(mcp: FastMCP, client: TocClient) -> None:
    # ---------- Bank accounts ----------

    @mcp.tool()
    async def list_bank_accounts(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        sort: Annotated[str | None, Field(description="JSON:API sort, e.g. `name`.")] = None,
        fields: Annotated[
            str | None, Field(description="Comma-separated subset of fields to return.")
        ] = None,
    ) -> dict[str, Any]:
        """List company bank accounts (with iban, swift, name, type)."""
        return await client.request(
            "GET",
            _ACCOUNTS_PATH,
            params=build_list_params(
                page_size=page_size, page_number=page_number, sort=sort,
                fields={"bank_accounts": fields} if fields else None,
            ),
        )

    @mcp.tool()
    async def get_bank_account(
        id: Annotated[str, Field(description="Bank account id.")],
    ) -> dict[str, Any]:
        """Fetch a single bank account by id."""
        return await client.request("GET", f"{_ACCOUNTS_PATH}/{require_id(id, 'id')}")

    # ---------- Bank transactions ----------

    @mcp.tool()
    async def list_bank_transactions(
        page_size: Annotated[int, Field(description="Items per page (1-500).", ge=1, le=500)] = 25,
        page_number: Annotated[int, Field(description="1-based page number.", ge=1)] = 1,
        bank_account_id: Annotated[
            str | None,
            Field(description="Filter to a specific bank account id (from list_bank_accounts)."),
        ] = None,
        transaction_date: Annotated[
            str | None,
            Field(description="Exact transaction date (YYYY-MM-DD). TOCOnline does not support ranges."),
        ] = None,
        posted_date: Annotated[
            str | None, Field(description="Exact posted date (YYYY-MM-DD).")
        ] = None,
        sort: Annotated[
            str,
            Field(
                description=(
                    "JSON:API sort. Default `-transaction_date,-id` (newest first, stable). "
                    "Other useful: `-value` (largest debits/credits first), `transaction_date`."
                )
            ),
        ] = "-transaction_date,-id",
        fields: Annotated[
            str | None,
            Field(
                description=(
                    "Comma-separated subset of fields. Available: id, bank_account_id, "
                    "transaction_date, posted_date, description, payer_iban, value, "
                    "imported_balance, annotation, other_info, track_id, seqord."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """List bank transactions (movements) imported into TOCOnline.

        All filters are exact match. To get a date range, make one call per
        day or page through without a date filter. `value` is signed
        (negative for debits, positive for credits).
        """
        filters: dict[str, Any] = {}
        if bank_account_id:
            filters["bank_account_id"] = require_id(bank_account_id, "bank_account_id")
        if transaction_date:
            filters["transaction_date"] = require_iso_date(transaction_date, "transaction_date")
        if posted_date:
            filters["posted_date"] = require_iso_date(posted_date, "posted_date")
        return await client.request(
            "GET",
            _TX_PATH,
            params=build_list_params(
                page_size=page_size, page_number=page_number,
                filters=filters, sort=sort,
                fields={"bank_transactions": fields} if fields else None,
            ),
        )

    @mcp.tool()
    async def get_bank_transaction(
        id: Annotated[str, Field(description="Bank transaction id.")],
    ) -> dict[str, Any]:
        """Fetch a single bank transaction by id."""
        return await client.request("GET", f"{_TX_PATH}/{require_id(id, 'id')}")
