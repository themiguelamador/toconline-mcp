from __future__ import annotations

import pytest

from toconline_mcp.tools._helpers import (
    build_list_params,
    require_id,
    require_iso_date,
)


@pytest.mark.parametrize("value", ["1", "abc_123", "abc-123", "XYZ"])
def test_require_id_accepts(value: str):
    assert require_id(value, "id") == value


@pytest.mark.parametrize(
    "value",
    [
        "1 OR 1=1",
        "1; DROP TABLE x",
        "1/../2",
        "1 ",
        "",
        "'; --",
        "../../etc",
        "a.b",
    ],
)
def test_require_id_rejects(value: str):
    with pytest.raises(ValueError):
        require_id(value, "id")


@pytest.mark.parametrize("value", ["2025-01-15", "1999-12-31", "2100-06-30"])
def test_require_iso_date_accepts(value: str):
    assert require_iso_date(value, "date") == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2025/01/15",
        "2025-1-15",
        "2025-01-15 00:00",
        "abc",
        "2025-01-15' OR 1=1 --",
    ],
)
def test_require_iso_date_rejects(value: str):
    with pytest.raises(ValueError):
        require_iso_date(value, "date")


def test_build_list_params_no_args_is_empty():
    assert build_list_params() == {}


def test_build_list_params_page_size_clamped():
    assert build_list_params(page_size=0)["page[size]"] == 1
    assert build_list_params(page_size=999)["page[size]"] == 100
    assert build_list_params(page_size=25)["page[size]"] == 25


def test_build_list_params_emits_bracketed_filter_keys():
    params = build_list_params(
        page_size=10,
        filters={"document_type": "FT", "customer_id": "3"},
    )
    assert params["page[size]"] == 10
    assert params["filter[document_type]"] == "FT"
    assert params["filter[customer_id]"] == "3"


def test_build_list_params_skips_none_and_empty_values():
    params = build_list_params(filters={"a": None, "b": "", "c": "x"})
    assert "filter[a]" not in params
    assert "filter[b]" not in params
    assert params["filter[c]"] == "x"


def test_build_list_params_stringifies_values():
    params = build_list_params(filters={"id": 42, "active": True})
    assert params["filter[id]"] == "42"
    assert params["filter[active]"] == "True"
