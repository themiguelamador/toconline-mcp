"""Tiny `.env` loader — no external dependency.

Supported locations (first one found wins):

  1. `$TOCONLINE_ENV_FILE` if set
  2. `~/.config/toconline-mcp/.env` (primary — next to credentials.json)
  3. `./.env` in the current working directory (dev convenience)

Real environment variables **always win** over file values — the file is
only a fallback, so you can override a single var at launch time.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from toconline_mcp.config import credentials_path


def _candidate_paths() -> list[Path]:
    override = os.environ.get("TOCONLINE_ENV_FILE")
    paths: list[Path] = []
    if override:
        paths.append(Path(override).expanduser())
    paths.append(credentials_path().parent / ".env")
    paths.append(Path.cwd() / ".env")
    return paths


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines. Supports `#` comments and single/double quoted values.

    Does NOT support variable interpolation (`$VAR`, `${VAR}`) — if you need
    that, export from a shell instead.
    """
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Allow `export KEY=...` (common convention)
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        # Strip matching surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def _warn_loose_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            f"warning: {path} has mode {oct(mode)} — it holds OAuth secrets. "
            f"Tighten with: chmod 600 {path}",
            file=sys.stderr,
        )


def load_env() -> Path | None:
    """Load the first existing .env into os.environ. Returns the path used.

    Existing os.environ entries are NOT overridden — real env takes priority.
    """
    for path in _candidate_paths():
        if path.is_file():
            try:
                text = path.read_text()
            except OSError:
                continue
            _warn_loose_permissions(path)
            values = _parse_dotenv(text)
            for key, value in values.items():
                os.environ.setdefault(key, value)
            return path
    return None
