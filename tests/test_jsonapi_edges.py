from toconline_mcp.http.jsonapi import flatten_resource, flatten_response


def test_flatten_resource_handles_non_dict_attributes():
    res = {"id": "1", "type": "x", "attributes": None}
    assert flatten_resource(res) == {"id": "1", "type": "x"}
    res2 = {"id": "1", "type": "x", "attributes": ["not", "a", "dict"]}
    assert flatten_resource(res2) == {"id": "1", "type": "x"}


def test_flatten_resource_handles_non_dict_relationships():
    res = {"id": "1", "type": "x", "relationships": ["malformed"]}
    assert flatten_resource(res) == {"id": "1", "type": "x"}


def test_flatten_resource_handles_relationship_data_as_scalar():
    # If `data` is a weird scalar instead of dict/list, flatten to None.
    res = {"id": "1", "type": "x", "relationships": {"owner": {"data": "suspicious"}}}
    assert flatten_resource(res)["owner_id"] is None


def test_flatten_resource_preserves_relationship_type():
    res = {
        "id": "1",
        "type": "sales_doc",
        "relationships": {"customer": {"data": {"type": "customers", "id": "42"}}},
    }
    flat = flatten_resource(res)
    assert flat["customer_id"] == "42"
    assert flat["customer_type"] == "customers"


def test_flatten_response_passes_through_unknown_shape():
    # If the payload doesn't have a `data` key we leave it alone.
    payload = {"weird": True, "not_jsonapi": 1}
    assert flatten_response(payload) == payload


def test_flatten_resource_empty_to_many_relationship():
    res = {
        "id": "1",
        "type": "x",
        "relationships": {"tags": {"data": []}},
    }
    flat = flatten_resource(res)
    assert flat["tags_ids"] == []
