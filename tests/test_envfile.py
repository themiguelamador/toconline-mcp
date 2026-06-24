from __future__ import annotations

import os
from pathlib import Path

import pytest

from toconline_mcp.envfile import _parse_dotenv, load_env


def test_parse_simple_key_value():
    got = _parse_dotenv("FOO=bar\nBAZ=qux\n")
    assert got == {"FOO": "bar", "BAZ": "qux"}


def test_parse_comments_and_blank_lines():
    text = """
# top comment
FOO=bar
  # indented comment

BAZ=qux
"""
    assert _parse_dotenv(text) == {"FOO": "bar", "BAZ": "qux"}


def test_parse_export_prefix_and_quotes():
    text = """export SINGLE='hello world'
DOUBLE="with spaces"
UNQUOTED=plain
"""
    assert _parse_dotenv(text) == {
        "SINGLE": "hello world",
        "DOUBLE": "with spaces",
        "UNQUOTED": "plain",
    }


def test_parse_skips_malformed_keys():
    text = "valid_key=ok\n-bad key=no\n123=keep\n=\n"
    parsed = _parse_dotenv(text)
    assert parsed["valid_key"] == "ok"
    assert parsed["123"] == "keep"
    assert "-bad key" not in parsed
    assert "" not in parsed


def test_parse_preserves_equals_in_value():
    assert _parse_dotenv("TOKEN=a=b=c\n") == {"TOKEN": "a=b=c"}


def test_load_env_reads_override_path_and_skips_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_path = tmp_path / "custom.env"
    env_path.write_text("FROM_FILE=yes\nALREADY_SET=from_file\n")
    monkeypatch.setenv("TOCONLINE_ENV_FILE", str(env_path))
    monkeypatch.setenv("ALREADY_SET", "from_env")  # real env should win
    monkeypatch.delenv("FROM_FILE", raising=False)

    loaded = load_env()
    assert loaded == env_path
    assert os.environ["FROM_FILE"] == "yes"
    assert os.environ["ALREADY_SET"] == "from_env"


def test_load_env_returns_none_when_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Point at a bogus TOCONLINE_CREDENTIALS_PATH so the sibling .env dir
    # is an empty tmp dir, and cwd has no .env either.
    monkeypatch.setenv(
        "TOCONLINE_CREDENTIALS_PATH", str(tmp_path / "sub" / "credentials.json")
    )
    monkeypatch.delenv("TOCONLINE_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)  # cwd has no .env
    assert load_env() is None


def test_load_env_prefers_config_dir_over_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("WHICH=config\n")
    cwd = tmp_path / "work"
    cwd.mkdir()
    (cwd / ".env").write_text("WHICH=cwd\n")

    monkeypatch.setenv("TOCONLINE_CREDENTIALS_PATH", str(config_dir / "credentials.json"))
    monkeypatch.delenv("TOCONLINE_ENV_FILE", raising=False)
    monkeypatch.delenv("WHICH", raising=False)
    monkeypatch.chdir(cwd)

    load_env()
    assert os.environ["WHICH"] == "config"
