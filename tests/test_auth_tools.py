from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from toconline_mcp.auth.store import Credentials, save_credentials
from toconline_mcp.http.client import TocClient
from toconline_mcp.tools import auth as auth_tools


def _sample_creds() -> Credentials:
    now = int(time.time())
    return Credentials(
        profile="default",
        api_base="https://api.example.com",
        client_id="cid",
        client_secret="csec",
        token_url="https://oauth.example.com/token",
        access_token="tok",
        refresh_token="ref",
        expires_at=now + 3600,
        obtained_at=now,
    )


def _register(mcp: FastMCP, client: TocClient) -> dict[str, object]:
    """Register auth tools and return the registered tool callables."""
    auth_tools.register(mcp, client)
    # FastMCP stores tools in `_tool_manager._tools` on current SDK versions.
    manager = getattr(mcp, "_tool_manager", None)
    assert manager is not None, "FastMCP tool manager layout changed"
    return {name: tool.fn for name, tool in manager._tools.items()}


async def test_auth_status_reports_unconfigured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    tools = _register(FastMCP(name="test"), TocClient())
    out = await tools["auth_status"]()
    assert out["authenticated"] is False
    assert "setup" in out["reason"].lower() or "no toconline credentials" in out["reason"].lower()
    assert out["credentials_path"] == str(path)


async def test_auth_status_reports_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    save_credentials(_sample_creds(), path=path)
    tools = _register(FastMCP(name="test"), TocClient())
    out = await tools["auth_status"]()
    assert out["authenticated"] is True
    assert out["profile"] == "default"
    assert out["api_base"] == "https://api.example.com"
    assert out["client_id"] == "cid"
    assert out["token_expires_in_seconds"] > 0
    # Must never leak tokens or secrets.
    assert "access_token" not in out
    assert "refresh_token" not in out
    assert "client_secret" not in out


async def test_logout_noop_when_unconfigured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    client = TocClient()
    client.invalidate = AsyncMock()  # type: ignore[method-assign]
    tools = _register(FastMCP(name="test"), client)
    out = await tools["logout"]()
    assert out["status"] == "no-op"
    assert not path.exists()
    client.invalidate.assert_awaited_once()


async def test_logout_deletes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    save_credentials(_sample_creds(), path=path)
    client = TocClient()
    client.invalidate = AsyncMock()  # type: ignore[method-assign]
    tools = _register(FastMCP(name="test"), client)
    out = await tools["logout"]()
    assert out["status"] == "ok"
    assert not path.exists()
    client.invalidate.assert_awaited_once()


async def test_login_runs_setup_in_thread_and_invalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))

    captured: dict[str, object] = {}

    def fake_run_setup(inputs, open_browser, timeout):  # noqa: ANN001
        captured["client_id"] = inputs.client_id
        captured["api_base"] = inputs.api_base
        captured["redirect_port"] = inputs.redirect_port
        captured["timeout"] = timeout
        save_credentials(_sample_creds(), path=path)

    monkeypatch.setattr(auth_tools, "run_setup", fake_run_setup)
    client = TocClient()
    client.invalidate = AsyncMock()  # type: ignore[method-assign]
    tools = _register(FastMCP(name="test"), client)

    out = await tools["login"](
        client_id="CID",
        client_secret="CSEC",
        auth_url="https://oauth.example.com/auth",
        token_url="https://oauth.example.com/token",
        redirect_port=53683,
    )

    assert out["status"] == "ok"
    assert captured["client_id"] == "CID"
    assert captured["redirect_port"] == 53683
    assert captured["timeout"] == 180.0
    assert captured["api_base"] == "https://apiv1.toconline.com"
    client.invalidate.assert_awaited_once()
    assert path.exists()
