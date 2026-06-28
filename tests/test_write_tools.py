from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import (
    addresses,
    document_actions,
    products,
    purchases,
    reference,
    sales_documents,
    sales_receipts,
    services,
    suppliers,
)
from toconline_mcp.tools._helpers import build_list_params
from toconline_mcp.tools.sales_documents import SalesDocumentLine


def _register(module) -> tuple[dict, AsyncMock]:
    client = TocClient()
    client.request = AsyncMock(return_value={"id": "1"})  # type: ignore[method-assign]
    mcp = FastMCP(name="test")
    module.register(mcp, client)
    tools = {name: tool.fn for name, tool in mcp._tool_manager._tools.items()}
    return tools, client.request


async def test_create_supplier_builds_envelope_and_drops_nulls():
    tools, request = _register(suppliers)
    await tools["create_supplier"](
        business_name="ACME Lda", tax_registration_number="500000000", is_tax_exempt=True
    )
    method, path = request.call_args.args
    body = request.call_args.kwargs["json"]
    assert (method, path) == ("POST", "/api/suppliers")
    assert body["data"]["type"] == "suppliers"
    attrs = body["data"]["attributes"]
    assert attrs == {
        "business_name": "ACME Lda",
        "tax_registration_number": "500000000",
        "is_tax_exempt": True,
    }  # every unset optional dropped
    assert "id" not in body["data"]


async def test_update_supplier_sets_id_and_patches():
    tools, request = _register(suppliers)
    await tools["update_supplier"](id="42", website="https://x.pt")
    method, path = request.call_args.args
    body = request.call_args.kwargs["json"]
    assert (method, path) == ("PATCH", "/api/suppliers/42")
    assert body["data"]["id"] == "42"
    assert body["data"]["attributes"] == {"website": "https://x.pt"}


async def test_create_product_sets_item_family_id_attribute():
    # Docs set item_family via the `item_family_id` attribute, not a relationship.
    tools, request = _register(products)
    await tools["create_product"](
        item_code="P1", item_description="Widget", sales_price=9.9, item_family_id="7"
    )
    body = request.call_args.kwargs["json"]
    assert body["data"]["attributes"] == {
        "type": "Product",  # required attribute; server rejects items without it
        "item_code": "P1",
        "item_description": "Widget",
        "sales_price": 9.9,
        "item_family_id": "7",
    }
    assert "relationships" not in body["data"]


def test_sales_line_accepts_item_description_alias_and_canonicalizes():
    # The API field is `description`; callers often send `item_description`.
    line = SalesDocumentLine(item_description="Consulting", quantity=1, unit_price=10)
    assert line.description == "Consulting"
    assert line.model_dump(exclude_none=True)["description"] == "Consulting"
    assert "item_description" not in line.model_dump()  # canonicalized


def test_sales_line_rejects_line_with_neither_description_nor_item():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SalesDocumentLine(quantity=1, unit_price=10)  # API would reject this line
    # item_id alone is fine (item supplies the description)
    assert SalesDocumentLine(item_id="7", item_type="Service", quantity=1, unit_price=10).item_id == "7"


async def test_create_draft_sets_series_relationship():
    # Series is chosen via a relationship (an attribute raises JA000).
    tools, request = _register(sales_documents)
    await tools["create_sales_document"](
        document_type="FT", customer_id="125", date="2026-06-28",
        lines=[SalesDocumentLine(description="X", quantity=1, unit_price=10)],
        series_id="361",
    )
    header_post = next(
        c for c in request.call_args_list
        if c.args[0] == "POST" and c.args[1] == "/api/commercial_sales_documents"
    )
    rel = header_post.kwargs["json"]["data"]["relationships"]["commercial_document_series"]
    assert rel == {"data": {"type": "commercial_document_series", "id": "361"}}


async def test_get_sales_document_fetches_lines_via_nested_route():
    # flat ?filter[document_id] raises JA011; must use /{id}/lines.
    tools, request = _register(sales_documents)
    await tools["get_sales_document"](id="5")
    paths = [call.args[1] for call in request.call_args_list]
    assert "/api/commercial_sales_documents/5/lines" in paths
    assert not any("commercial_sales_document_lines" in p for p in paths)  # no flat filter route


def test_refresh_reuses_previous_refresh_token_when_response_omits_it():
    # The core TKT-9 bug: a refresh response with only access_token must reuse
    # the existing refresh token instead of failing.
    from toconline_mcp.auth.oauth import _parse_token_payload

    tok = _parse_token_payload({"access_token": "new-at"}, fallback_refresh_token="old-rt")
    assert tok.access_token == "new-at"
    assert tok.refresh_token == "old-rt"


def test_initial_token_still_requires_refresh_token():
    from pydantic import ValidationError  # noqa: F401  (keep imports tidy)

    from toconline_mcp.auth.oauth import _parse_token_payload
    from toconline_mcp.util.errors import AuthError

    with pytest.raises(AuthError):
        _parse_token_payload({"access_token": "x"})  # no fallback, no refresh_token


def test_missing_expires_in_falls_back_to_default():
    import time as _time

    from toconline_mcp.auth.oauth import _parse_token_payload

    tok = _parse_token_payload({"access_token": "a", "refresh_token": "b"})
    assert tok.expires_at - int(_time.time()) >= 3500  # ~1h default, not an error


def test_sparse_fields_drops_relationship_tokens():
    # Relationship-derived names (*_id / *_ids) raise JA011 in sparse fieldsets.
    params = build_list_params(
        fields={"customers": "business_name,main_address_id,addresses_ids,tax_registration_number"}
    )
    assert params["fields[customers]"] == "business_name,tax_registration_number"


def test_sales_line_carries_item_reference_and_tax_code():
    line = SalesDocumentLine(
        item_id="2", item_type="Service", description="Consulting",
        quantity=1, unit_price=25, tax_code="NOR",
    )
    dumped = line.model_dump(exclude_none=True)
    assert dumped["item_id"] == "2"
    assert dumped["item_type"] == "Service"
    assert dumped["tax_code"] == "NOR"


async def test_list_addresses_uses_nested_route_for_customer():
    # flat /api/addresses?filter[customer_id] raises JA011; use /customers/{id}/addresses.
    tools, request = _register(addresses)
    await tools["list_addresses"](customer_id="9")
    path = request.call_args.args[1]
    assert path == "/api/customers/9/addresses"


async def test_create_address_refetches_for_truthful_record():
    # POST echo omits the resolved parent link; tool re-fetches by id.
    tools, request = _register(addresses)
    await tools["create_address"](customer_id="9", address_detail="Rua X", city="Lisboa")
    calls = [(c.args[0], c.args[1]) for c in request.call_args_list]
    assert ("POST", "/api/addresses") in calls
    assert ("GET", "/api/addresses/1") in calls  # re-fetch of the created id


async def test_create_address_dedupes_existing():
    # If the parent already has a matching detail+postcode, return it, no POST.
    tools, request = _register(addresses)

    def _resp(method, path, **kw):
        if method == "GET" and path == "/api/customers/9/addresses":
            return {"items": [{"id": "55", "address_detail": "Rua X", "postcode": "1000-001"}]}
        return {"id": "1"}

    request.side_effect = _resp
    result = await tools["create_address"](
        customer_id="9", address_detail="Rua X", city="Lisboa", postcode="1000-001"
    )
    assert result["id"] == "55"
    assert all(c.args[0] != "POST" for c in request.call_args_list)  # nothing created


async def test_delete_product_requires_confirm_then_deletes():
    tools, request = _register(products)
    with pytest.raises(ValueError):
        await tools["delete_product"](id="9")  # confirm defaults to False
    request.assert_not_called()
    result = await tools["delete_product"](id="9", confirm=True)
    assert request.call_args.args == ("DELETE", "/api/products/9")
    assert result == {"status": "deleted", "id": "9"}


async def test_create_sales_receipt_line_builds_settlement_payload():
    tools, request = _register(sales_receipts)
    await tools["create_sales_receipt_line"](
        receipt_id="13", receivable_id="12", received_value=10.69, gross_total=10.69
    )
    method, path = request.call_args.args
    body = request.call_args.kwargs["json"]
    assert (method, path) == ("POST", "/api/commercial_sales_receipt_lines")
    assert body["data"]["type"] == "commercial_sales_receipt_lines"
    assert body["data"]["attributes"] == {
        "receipt_id": "13",
        "receivable_id": "12",
        "receivable_type": "Document",  # default
        "received_value": 10.69,
        "gross_total": 10.69,
    }  # unset optionals (net/retention/settlement/cashed_vat) dropped


async def test_create_purchase_payment_line_settles_a_document_line():
    tools, request = _register(purchases)
    await tools["create_purchase_payment_line"](
        payment_id="5", payable_id="6", paid_value=20
    )
    method, path = request.call_args.args
    body = request.call_args.kwargs["json"]
    assert (method, path) == ("POST", "/api/commercial_purchases_payment_lines")
    # purchases settle a document LINE, not a whole document
    assert body["data"]["attributes"]["payable_type"] == "Purchases::DocumentLine"
    assert body["data"]["attributes"]["payable_id"] == "6"
    assert body["data"]["attributes"]["paid_value"] == 20


async def test_create_service_without_family_drops_item_family_id():
    tools, request = _register(services)
    await tools["create_service"](item_code="S1", item_description="Consulting")
    body = request.call_args.kwargs["json"]
    assert body["data"]["type"] == "services"
    assert body["data"]["attributes"]["type"] == "Service"
    assert "item_family_id" not in body["data"]["attributes"]  # None dropped
    assert "relationships" not in body["data"]


async def test_reference_tables_register_and_hit_correct_paths():
    tools, request = _register(reference)
    expected = {
        "list_countries": "/api/countries",
        "list_item_families": "/api/item_families",
        "list_units_of_measure": "/api/units_of_measure",
        "list_tax_descriptors": "/api/tax_descriptors",
        "list_cash_accounts": "/api/cash_accounts",
    }
    assert expected.keys() <= tools.keys()
    for name, path in expected.items():
        request.reset_mock()
        await tools[name]()
        method, called_path = request.call_args.args
        assert (method, called_path) == ("GET", path)


async def test_at_communication_requires_confirm():
    tools, request = _register(document_actions)
    with pytest.raises(ValueError):
        await tools["communicate_sales_document_at"](id="9")
    request.assert_not_called()
    await tools["communicate_sales_document_at"](id="9", confirm=True)
    method, path = request.call_args.args
    assert method == "PATCH"
    assert path == "/api/v1/commercial_sales_documents/9/send_document_at_webservice"
    # v1 action endpoints must override the default JSON:API Content-Type.
    assert request.call_args.kwargs["headers"] == {"Content-Type": "application/json"}
