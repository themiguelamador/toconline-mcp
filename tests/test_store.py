from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from toconline_mcp.auth.store import Credentials, load_credentials, save_credentials
from toconline_mcp.util.errors import AuthError


def _sample_creds() -> Credentials:
    return Credentials(
        profile="default",
        api_base="https://api.example.com",
        client_id="cid",
        client_secret="csec",
        token_url="https://oauth.example.com/token",
        access_token="tok",
        refresh_token="ref",
        expires_at=9999999999,
        obtained_at=1,
    )


def test_save_then_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(path))
    creds = _sample_creds()
    save_credentials(creds)
    loaded = load_credentials()
    assert loaded == creds


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_save_sets_0600_permissions(tmp_path: Path):
    path = tmp_path / "credentials.json"
    save_credentials(_sample_creds(), path=path)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_load_rejects_world_readable_file(tmp_path: Path):
    path = tmp_path / "credentials.json"
    save_credentials(_sample_creds(), path=path)
    os.chmod(path, 0o644)
    with pytest.raises(AuthError):
        load_credentials(path)


def test_load_missing_file_has_clear_message(tmp_path: Path):
    path = tmp_path / "nope.json"
    with pytest.raises(AuthError) as exc:
        load_credentials(path)
    assert "setup" in str(exc.value).lower()


def test_save_leaves_no_tmp_file_on_success(tmp_path: Path):
    path = tmp_path / "credentials.json"
    save_credentials(_sample_creds(), path=path)
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_save_creates_parent_dir_with_0700(tmp_path: Path):
    nested = tmp_path / "nested" / "credentials.json"
    save_credentials(_sample_creds(), path=nested)
    mode = nested.parent.stat().st_mode & 0o777
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0
