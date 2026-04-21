from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_BASE = "https://apiv1.toconline.com"
DEFAULT_REDIRECT_PORT = 53682
DEFAULT_SCOPE = "commercial"


def credentials_path() -> Path:
    override = os.environ.get("TOCONLINE_CREDENTIALS_PATH")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "toconline-mcp" / "credentials.json"


@dataclass(frozen=True)
class SetupInputs:
    """Values the user provides (interactively or via env) at setup time."""

    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    api_base: str = DEFAULT_API_BASE
    scope: str = DEFAULT_SCOPE
    redirect_port: int = DEFAULT_REDIRECT_PORT

    @classmethod
    def from_env(cls) -> "SetupInputs | None":
        keys = ("TOCONLINE_CLIENT_ID", "TOCONLINE_CLIENT_SECRET",
                "TOCONLINE_AUTH_URL", "TOCONLINE_TOKEN_URL")
        if not all(os.environ.get(k) for k in keys):
            return None
        port_raw = os.environ.get("TOCONLINE_REDIRECT_PORT", str(DEFAULT_REDIRECT_PORT))
        return cls(
            client_id=os.environ["TOCONLINE_CLIENT_ID"],
            client_secret=os.environ["TOCONLINE_CLIENT_SECRET"],
            auth_url=os.environ["TOCONLINE_AUTH_URL"],
            token_url=os.environ["TOCONLINE_TOKEN_URL"],
            api_base=os.environ.get("TOCONLINE_API_BASE", DEFAULT_API_BASE),
            scope=os.environ.get("TOCONLINE_SCOPE", DEFAULT_SCOPE),
            redirect_port=int(port_raw),
        )
