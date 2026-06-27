from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import (
    document_actions,
    products,
    purchases,
    reference,
    sales_receipts,
    services,
    suppliers,
)


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
