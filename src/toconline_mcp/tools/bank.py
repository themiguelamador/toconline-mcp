from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools._helpers import build_list_params, require_id, require_iso_date

_ACCOUNTS_PATH = "/api/bank_accounts"
_TX_PATH = "/api/bank_transactions"


def _derive_bank_identifiers(account: dict[str, Any]) -> None:
    """Annotate a bank account record with `id_banco` and `pais_conta` in place.

    These are commonly required for Portuguese tax-authority reports
    (Modelo 30 for foreign payments, SAFT-PT, IES bank annexes).

    Rules:
      - `pais_conta` — 2-letter ISO country code from the IBAN's first two
        characters. `PT`, `GB`, `LU`, `BE`, etc.
      - `id_banco` — bank-identifier code:
          * Portuguese accounts (pais_conta=`PT`): first 4 digits of the NIB,
            matching the Banco de Portugal / AT Tabelas_apoio list
            (e.g. `0007` = Novo Banco, `0035` = Caixa Geral de Depósitos).
          * Foreign accounts: SWIFT/BIC when populated; otherwise IBAN[4:8].
            (IBAN layout: 2 country chars + 2 check digits + variable-length
            bank code — positions 4..8 are the first 4 chars and cover PT,
            GB, LU, BE, NL, IE, ES, FR, DE, IT, and most other European
            formats' leading bank identifier.)
      - Both are `None` when the source fields are empty — in that case the
        bank account record itself is incomplete in TOCOnline and needs to
        be filled in the UI (Empresa → Contas bancárias) or via PATCH on
        `/api/bank_accounts`.
    """
    if not isinstance(account, dict):
        return
    iban = (account.get("iban") or "").strip()
    nib = (account.get("nib") or "").strip()
    swift = (account.get("swift") or "").strip()

    pais_conta = iban[:2].upper() if len(iban) >= 2 and iban[:2].isalpha() else None

    id_banco = None
    if pais_conta == "PT" and len(nib) >= 4:
        id_banco = nib[:4]
    elif swift:
        id_banco = swift
    elif len(iban) >= 8:
        id_banco = iban[4:8]

    account["id_banco"] = id_banco
    account["pais_conta"] = pais_conta


def _enrich_accounts_response(response: Any) -> Any:
    if isinstance(response, dict):
        if isinstance(response.get("items"), list):
            for acc in response["items"]:
                _derive_bank_identifiers(acc)
        else:
            _derive_bank_identifiers(response)
    return response


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
        """List company bank accounts (name, IBAN, SWIFT, type). Each item adds derived `pais_conta` (ISO country) and `id_banco` (bank identifier) fields used by Portuguese tax reports."""
        r = await client.request(
            "GET",
            _ACCOUNTS_PATH,
            params=build_list_params(
                page_size=page_size, page_number=page_number, sort=sort,
                fields={"bank_accounts": fields} if fields else None,
            ),
        )
        return _enrich_accounts_response(r)

    @mcp.tool()
    async def get_bank_account(
        id: Annotated[str, Field(description="Bank account id.")],
    ) -> dict[str, Any]:
        """Fetch a single bank account by id, with derived `id_banco` and `pais_conta` fields."""
        r = await client.request("GET", f"{_ACCOUNTS_PATH}/{require_id(id, 'id')}")
        return _enrich_accounts_response(r)

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
            Field(description="JSON:API sort. Default newest first."),
        ] = "-transaction_date,-id",
        fields: Annotated[
            str | None,
            Field(description="Comma-separated subset of fields to return."),
        ] = None,
    ) -> dict[str, Any]:
        """List bank transactions imported into TOCOnline. Filters are exact match (no date ranges). `value` is signed (negative=debit, positive=credit)."""
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
