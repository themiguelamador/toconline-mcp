from __future__ import annotations

import re
from typing import Any

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def require_id(value: str, field: str) -> str:
    """Reject ids that aren't alnum/underscore/dash. Used for URL path segments
    and filter values — prevents traversal and keeps us aligned with
    JSON:API id conventions."""
    if not _ID_RE.match(str(value)):
        raise ValueError(f"{field} must contain only letters, digits, `_`, or `-`")
    return str(value)


def require_iso_date(value: str, field: str) -> str:
    """Require YYYY-MM-DD. TOCOnline filter[date]=... expects this format."""
    if not _ISO_DATE_RE.match(str(value)):
        raise ValueError(f"{field} must be an ISO date in YYYY-MM-DD format")
    return str(value)


def item_attributes(
    *,
    item_type: str | None = None,
    item_code: str | None,
    item_description: str | None,
    sales_price: float | None,
    sales_price_includes_vat: bool | None,
    tax_code: str | None,
) -> dict[str, Any]:
    """Writable attributes shared by products and services (same item schema).

    The API requires the item-type attribute `type` ("Product"/"Service") on
    create and rejects items without it. Note this is the attribute named
    `type`, distinct from the JSON:API resource `data.type` ("products")."""
    return {
        "type": item_type,
        "item_code": item_code,
        "item_description": item_description,
        "sales_price": sales_price,
        "sales_price_includes_vat": sales_price_includes_vat,
        "tax_code": tax_code,
    }


def build_list_params(
    page_size: int | None = None,
    page_number: int | None = None,
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build query params for a TOCOnline list endpoint.

    Supports the JSON:API standard quartet:
      - `page[size]` / `page[number]` — pagination (page_size capped at 500).
      - `filter[field]=value` — equality filters only; TOCOnline rejects
        comparison operators with JA011.
      - `sort` — comma-separated fields, prefix with `-` for descending.
      - `fields[<type>]=f1,f2,...` — sparse fieldsets (huge token savings on
        records with many attributes, e.g. sales docs with 117 fields).
    """
    params: dict[str, Any] = {}
    if page_size is not None:
        params["page[size]"] = max(1, min(int(page_size), 500))
    if page_number is not None:
        params["page[number]"] = max(1, int(page_number))
    if filters:
        for field, value in filters.items():
            if value is None or value == "":
                continue
            params[f"filter[{field}]"] = str(value)
    if sort:
        params["sort"] = sort
    if fields:
        for resource_type, field_list in fields.items():
            if field_list:
                params[f"fields[{resource_type}]"] = field_list
    return params
