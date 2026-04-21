from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from toconline_mcp.config import credentials_path
from toconline_mcp.util.errors import AuthError


@dataclass
class Credentials:
    profile: str
    api_base: str
    client_id: str
    client_secret: str
    token_url: str
    access_token: str
    refresh_token: str
    expires_at: int
    obtained_at: int

    def with_tokens(
        self, access_token: str, refresh_token: str, expires_at: int, obtained_at: int
    ) -> "Credentials":
        return replace(
            self,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            obtained_at=obtained_at,
        )


def _ensure_secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _secure_write(path: Path, payload: str) -> None:
    _ensure_secure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
        except BaseException:
            # If os.fdopen itself raised before taking ownership of fd, close it.
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def save_credentials(creds: Credentials, path: Path | None = None) -> Path:
    path = path or credentials_path()
    _secure_write(path, json.dumps(asdict(creds), indent=2))
    return path


def load_credentials(path: Path | None = None) -> Credentials:
    path = path or credentials_path()
    if not path.exists():
        raise AuthError(
            f"No TOCOnline credentials found at {path}. "
            "Run `toconline-mcp setup` first."
        )
    _check_permissions(path)
    with path.open() as fh:
        data = json.load(fh)
    try:
        return Credentials(**data)
    except TypeError as exc:
        raise AuthError(f"Credentials file at {path} has unexpected shape: {exc}") from exc


def _check_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    mode = path.stat().st_mode & 0o777
    world_or_group = mode & (stat.S_IRWXG | stat.S_IRWXO)
    if world_or_group:
        raise AuthError(
            f"Credentials file at {path} has loose permissions (mode {oct(mode)}); "
            "expected 0600. Fix with `chmod 600 <path>` and retry."
        )
