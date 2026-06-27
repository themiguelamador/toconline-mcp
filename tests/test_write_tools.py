from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import (
    document_actions,
    products,
    reference,
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


async def test_create_product_attaches_item_family_relationship():
    tools, request = _register(products)
    await tools["create_product"](
        item_code="P1", item_description="Widget", sales_price=9.9, item_family_id="7"
    )
    body = request.call_args.kwargs["json"]
    assert body["data"]["attributes"] == {
        "item_code": "P1",
        "item_description": "Widget",
        "sales_price": 9.9,
    }
    assert body["data"]["relationships"]["item_family"]["data"] == {
        "type": "item_families",
        "id": "7",
    }


async def test_create_service_without_family_has_no_relationships():
    tools, request = _register(services)
    await tools["create_service"](item_code="S1", item_description="Consulting")
    body = request.call_args.kwargs["json"]
    assert body["data"]["type"] == "services"
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
