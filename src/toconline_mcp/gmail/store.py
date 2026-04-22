from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from toconline_mcp.auth.store import _check_permissions, _secure_write
from toconline_mcp.config import credentials_path as toconline_credentials_path
from toconline_mcp.util.errors import AuthError


def gmail_credentials_path() -> Path:
    """Sibling file next to the TOCOnline credentials file."""
    override = os.environ.get("TOCONLINE_GMAIL_CREDENTIALS_PATH")
    if override:
        return Path(override).expanduser()
    return toconline_credentials_path().parent / "gmail-credentials.json"


@dataclass
class GmailCredentials:
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    scope: str
    expires_at: int
    obtained_at: int

    def with_tokens(
        self, access_token: str, refresh_token: str, expires_at: int, obtained_at: int
    ) -> "GmailCredentials":
        return replace(
            self,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            obtained_at=obtained_at,
        )


def save_gmail_credentials(creds: GmailCredentials, path: Path | None = None) -> Path:
    path = path or gmail_credentials_path()
    _secure_write(path, json.dumps(asdict(creds), indent=2))
    return path


def load_gmail_credentials(path: Path | None = None) -> GmailCredentials:
    path = path or gmail_credentials_path()
    if not path.exists():
        raise AuthError(
            f"No Gmail credentials found at {path}. Run `toconline-mcp gmail-setup` first."
        )
    _check_permissions(path)
    with path.open() as fh:
        data = json.load(fh)
    try:
        return GmailCredentials(**data)
    except TypeError as exc:
        raise AuthError(f"Gmail credentials file at {path} has unexpected shape: {exc}") from exc
