from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_server_stdout_is_only_framed_jsonrpc(tmp_path: Path):
    """Spawn the server, send the MCP handshake, verify stdout contains only JSON-RPC.

    If any library or our own code prints/logs to stdout, the LLM client will
    fail to parse the JSON stream. This test guards against that regression.
    """
    # Point credentials path to an empty file — server shouldn't touch it at
    # startup; only when a tool is invoked. That way we get a clean stdio
    # session without needing real OAuth credentials.
    creds = tmp_path / "does-not-exist.json"
    env = {
        "PATH": "/usr/bin:/bin",
        "TOCONLINE_CREDENTIALS_PATH": str(creds),
        "HOME": str(tmp_path),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "toconline_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        # Initialize + list tools.
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "stdio-clean-test", "version": "0"},
            },
        }
        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        list_tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(init) + "\n")
        proc.stdin.write(json.dumps(initialized) + "\n")
        proc.stdin.write(json.dumps(list_tools) + "\n")
        proc.stdin.flush()

        # Read two responses (one per request-with-id).
        assert proc.stdout is not None
        lines: list[str] = []
        for _ in range(2):
            line = proc.stdout.readline()
            assert line, "server closed stdout prematurely"
            lines.append(line)

        for line in lines:
            stripped = line.strip()
            assert stripped, "empty line on stdout"
            parsed = json.loads(stripped)
            assert parsed.get("jsonrpc") == "2.0"
    finally:
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
