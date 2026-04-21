from toconline_mcp.http.jsonapi import (
    build_resource_envelope,
    flatten_resource,
    flatten_response,
)


def test_flatten_resource_merges_attributes():
    res = {
        "id": "42",
        "type": "customers",
        "attributes": {"business_name": "ACME", "email": "a@b.pt"},
    }
    assert flatten_resource(res) == {
        "id": "42",
        "type": "customers",
        "business_name": "ACME",
        "email": "a@b.pt",
    }


def test_flatten_resource_renames_collisions():
    res = {
        "id": "1",
        "type": "widget",
        "attributes": {"id": "alt", "type": "foo", "name": "w"},
    }
    flat = flatten_resource(res)
    assert flat["id"] == "1"
    assert flat["type"] == "widget"
    assert flat["attr_id"] == "alt"
    assert flat["attr_type"] == "foo"
    assert flat["name"] == "w"


def test_flatten_resource_relationships():
    res = {
        "id": "5",
        "type": "commercial_sales_documents",
        "attributes": {"date": "2025-01-15"},
        "relationships": {
            "customer": {"data": {"type": "customers", "id": "42"}},
            "lines": {"data": [{"type": "lines", "id": "1"}, {"type": "lines", "id": "2"}]},
            "supplier": {"data": None},
        },
    }
    flat = flatten_resource(res)
    assert flat["customer_id"] == "42"
    assert flat["lines_ids"] == ["1", "2"]
    assert flat["supplier_id"] is None


def test_flatten_response_collection_preserves_meta():
    payload = {
        "data": [
            {"id": "1", "type": "customers", "attributes": {"business_name": "A"}},
            {"id": "2", "type": "customers", "attributes": {"business_name": "B"}},
        ],
        "meta": {"total": 2},
    }
    out = flatten_response(payload)
    assert out["items"][0]["business_name"] == "A"
    assert out["meta"] == {"total": 2}


def test_flatten_response_single_resource_embeds_meta_under_prefixed_key():
    payload = {
        "data": {"id": "1", "type": "customers", "attributes": {"business_name": "A"}},
        "meta": {"request_id": "x"},
    }
    out = flatten_response(payload)
    assert out["business_name"] == "A"
    assert out["_meta"] == {"request_id": "x"}


def test_build_resource_envelope_drops_none_and_adds_relationships():
    envelope = build_resource_envelope(
        "customers",
        {"business_name": "ACME", "email": None, "country_code": "PT"},
        relationships={"parent": ("customers", "99")},
    )
    assert envelope == {
        "data": {
            "type": "customers",
            "attributes": {"business_name": "ACME", "country_code": "PT"},
            "relationships": {"parent": {"data": {"type": "customers", "id": "99"}}},
        }
    }
