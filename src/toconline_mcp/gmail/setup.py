from __future__ import annotations

import html
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

from toconline_mcp.gmail.oauth import AUTH_URL, GMAIL_DEFAULT_SCOPE, exchange_code
from toconline_mcp.gmail.store import GmailCredentials, save_gmail_credentials
from toconline_mcp.util.errors import AuthError

_DEFAULT_REDIRECT_PORT = 53683  # distinct from TOCOnline's 53682

_SUCCESS_HTML = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Gmail (TOCOnline MCP)</title></head><body style="font-family:system-ui;padding:2rem;">
<h1>Gmail login complete</h1><p>You can close this tab and return to your terminal.</p>
</body></html>"""

_ERROR_TEMPLATE = (
    '<!doctype html><html><head><meta charset="utf-8">'
    "<title>Gmail (TOCOnline MCP)</title></head><body style=\"font-family:system-ui;padding:2rem;\">"
    "<h1>Gmail login failed</h1><p>{message}</p></body></html>"
)


def _render_error(message: str) -> bytes:
    return _ERROR_TEMPLATE.format(message=html.escape(message, quote=True)).encode("utf-8")


@dataclass(frozen=True)
class GmailSetupInputs:
    client_id: str
    client_secret: str
    scope: str = GMAIL_DEFAULT_SCOPE
    redirect_port: int = _DEFAULT_REDIRECT_PORT


class _Capture:
    def __init__(self, expected_state: str) -> None:
        self.expected_state = expected_state
        self.code: str | None = None
        self.error: str | None = None
        self.event = threading.Event()


def _make_handler(capture: _Capture, path: str):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs) -> None:  # silence
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != path:
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            state = (params.get("state") or [""])[0]
            code = (params.get("code") or [""])[0]
            err = (params.get("error") or [""])[0]
            err_desc = (params.get("error_description") or [""])[0]
            body: bytes
            status: int
            if err:
                capture.error = f"{err}: {err_desc}" if err_desc else err
                status, body = 400, _render_error(capture.error)
            elif state != capture.expected_state:
                capture.error = "state mismatch"
                status, body = 400, _render_error("state mismatch")
            elif not code:
                capture.error = "missing code"
                status, body = 400, _render_error("missing code")
            else:
                capture.code = code
                status, body = 200, _SUCCESS_HTML
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            capture.event.set()

    return _Handler


def _build_auth_url(inputs: GmailSetupInputs, redirect_uri: str, state: str) -> str:
    # access_type=offline + prompt=consent are required for Google to issue a refresh_token.
    query = urllib.parse.urlencode(
        {
            "client_id": inputs.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": inputs.scope,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
    )
    return f"{AUTH_URL}?{query}"


def run_gmail_setup(
    inputs: GmailSetupInputs, open_browser: bool = True, timeout: float = 300.0
) -> None:
    redirect_path = "/callback"
    redirect_uri = f"http://127.0.0.1:{inputs.redirect_port}{redirect_path}"
    state = secrets.token_urlsafe(24)
    capture = _Capture(expected_state=state)

    try:
        server = HTTPServer(
            ("127.0.0.1", inputs.redirect_port), _make_handler(capture, redirect_path)
        )
    except OSError as exc:
        raise AuthError(
            f"Could not bind {redirect_uri}: {exc}. "
            "Close whatever is using the port or pass --port."
        ) from exc

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        auth_url = _build_auth_url(inputs, redirect_uri, state)
        print("Opening browser to authorize Gmail access...", file=sys.stderr)
        print(f"If it does not open, visit:\n  {auth_url}\n", file=sys.stderr)
        if open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception:
                pass
        if not capture.event.wait(timeout=timeout):
            raise AuthError(f"Timed out after {timeout:.0f}s waiting for Gmail callback.")
        if capture.error:
            raise AuthError(f"Gmail authorization failed: {capture.error}")
        assert capture.code
    finally:
        server.shutdown()
        server.server_close()

    tokens = exchange_code(
        client_id=inputs.client_id,
        client_secret=inputs.client_secret,
        code=capture.code,
        redirect_uri=redirect_uri,
    )
    assert tokens.refresh_token  # enforced inside exchange_code
    creds = GmailCredentials(
        client_id=inputs.client_id,
        client_secret=inputs.client_secret,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        scope=inputs.scope,
        expires_at=tokens.expires_at,
        obtained_at=tokens.obtained_at,
    )
    path = save_gmail_credentials(creds)
    print(f"\nGmail credentials saved to {path}", file=sys.stderr)


def prompt_gmail_inputs() -> GmailSetupInputs:
    import os
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    scope = os.environ.get("GMAIL_SCOPE", GMAIL_DEFAULT_SCOPE)
    if not (client_id and client_secret):
        print("Gmail MCP setup", file=sys.stderr)
        print("---------------", file=sys.stderr)
        print(
            "Create a Google Cloud OAuth 2.0 Client ID (Desktop app or Web app).\n"
            f"Register redirect URI:  http://127.0.0.1:{_DEFAULT_REDIRECT_PORT}/callback\n"
            f"Enable: Gmail API for the project.\n"
            "Then paste the credentials below.\n",
            file=sys.stderr,
        )

        def ask(label: str) -> str:
            while True:
                value = input(f"{label}: ").strip()
                if value:
                    return value
                print("  required", file=sys.stderr)

        client_id = ask("Google OAuth Client ID")
        client_secret = ask("Google OAuth Client Secret")
    return GmailSetupInputs(client_id=client_id, client_secret=client_secret, scope=scope)
