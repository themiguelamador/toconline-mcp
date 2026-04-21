from __future__ import annotations

import pytest

from toconline_mcp.tools.generic import _validate_path


@pytest.mark.parametrize(
    "path",
    [
        "/api/customers",
        "/api/customers/123",
        "/api/commercial_sales_documents",
        "/api/a/b/c",
        "/api/a_b/c-d",
        "/api/a/",
    ],
)
def test_validate_path_accepts_valid(path: str) -> None:
    _validate_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/",
        "/api",
        "/api/",
        "customers",
        "//evil.com/api/x",
        "/api//x",
        "/api/x/../y",
        "/api/..",
        "/api/-foo",
        "/api/foo-",
        "/api/foo?x=1",
        "/api/foo#frag",
        "https://evil.com/api/x",
        "/apix/y",
        "/other/y",
        "/api/x%2F..%2Fy",
        "/api/ x",
    ],
)
def test_validate_path_rejects_invalid(path: str) -> None:
    with pytest.raises(ValueError):
        _validate_path(path)


def test_validate_path_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        _validate_path(None)  # type: ignore[arg-type]
