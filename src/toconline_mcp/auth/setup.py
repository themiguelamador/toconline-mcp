from __future__ import annotations

import html
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from toconline_mcp.auth.oauth import exchange_code
from toconline_mcp.auth.store import Credentials, save_credentials
from toconline_mcp.config import SetupInputs
from toconline_mcp.util.errors import AuthError

_SUCCESS_HTML = b"""<!doctype html><html><head><meta charset="utf-8">
<title>TOCOnline MCP</title></head><body style="font-family:system-ui;padding:2rem;">
<h1>Login complete</h1><p>You can close this tab and return to your terminal.</p>
</body></html>"""

_ERROR_TEMPLATE = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>TOCOnline MCP</title></head><body style=\"font-family:system-ui;padding:2rem;\">"
    "<h1>Login failed</h1><p>{message}</p></body></html>"
)


def _render_error(message: str) -> bytes:
    return _ERROR_TEMPLATE.format(message=html.escape(message, quote=True)).encode("utf-8")


class _Capture:
    def __init__(self, expected_state: str) -> None:
        self.expected_state = expected_state
        self.code: str | None = None
        self.error: str | None = None
        self.event = threading.Event()


def _make_handler(capture: _Capture, path: str):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs) -> None:  # silence stderr
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
            if err:
                capture.error = f"{err}: {err_desc}" if err_desc else err
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_render_error(capture.error))
            elif state != capture.expected_state:
                capture.error = "state mismatch"
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_render_error("state mismatch"))
            elif not code:
                capture.error = "missing code"
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_render_error("missing code"))
            else:
                capture.code = code
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_SUCCESS_HTML)
            capture.event.set()

    return _Handler


def _build_auth_url(inputs: SetupInputs, redirect_uri: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": inputs.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": inputs.scope,
            "state": state,
        }
    )
    separator = "&" if "?" in inputs.auth_url else "?"
    return f"{inputs.auth_url}{separator}{query}"


def run_setup(inputs: SetupInputs, open_browser: bool = True, timeout: float = 300.0) -> None:
    redirect_path = "/callback"
    redirect_uri = f"http://127.0.0.1:{inputs.redirect_port}{redirect_path}"
    state = secrets.token_urlsafe(24)
    capture = _Capture(expected_state=state)

    try:
        server = HTTPServer(("127.0.0.1", inputs.redirect_port), _make_handler(capture, redirect_path))
    except OSError as exc:
        raise AuthError(
            f"Could not bind {redirect_uri}: {exc}. "
            "Close whatever is using the port or pass --port."
        ) from exc

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        auth_url = _build_auth_url(inputs, redirect_uri, state)
        print(f"Opening browser to authorize TOCOnline access...", file=sys.stderr)
        print(f"If the browser does not open, visit:\n  {auth_url}\n", file=sys.stderr)
        if open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception:
                pass
        if not capture.event.wait(timeout=timeout):
            raise AuthError(f"Timed out after {timeout:.0f}s waiting for authorization callback.")
        if capture.error:
            raise AuthError(f"Authorization failed: {capture.error}")
        assert capture.code, "capture.code missing but no error reported"
    finally:
        server.shutdown()
        server.server_close()

    tokens = exchange_code(
        token_url=inputs.token_url,
        client_id=inputs.client_id,
        client_secret=inputs.client_secret,
        code=capture.code,
        redirect_uri=redirect_uri,
    )
    creds = Credentials(
        profile="default",
        api_base=inputs.api_base,
        client_id=inputs.client_id,
        client_secret=inputs.client_secret,
        token_url=inputs.token_url,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.expires_at,
        obtained_at=tokens.obtained_at,
    )
    path = save_credentials(creds)
    print(f"\nCredentials saved to {path}", file=sys.stderr)
    print("You can now register the MCP server with Claude:", file=sys.stderr)
    print("  claude mcp add toconline -- uvx toconline-mcp", file=sys.stderr)


def prompt_inputs() -> SetupInputs:
    existing = SetupInputs.from_env()
    if existing is not None:
        return existing
    print("TOCOnline MCP setup", file=sys.stderr)
    print("-------------------", file=sys.stderr)
    print("Get these from TOCOnline: Company > Settings > API integrations.\n", file=sys.stderr)

    def ask(label: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        while True:
            value = input(f"{label}{suffix}: ").strip()
            if value:
                return value
            if default:
                return default
            print("  required, please try again", file=sys.stderr)

    client_id = ask("Client ID")
    client_secret = ask("Client Secret")
    auth_url = ask("Authorization URL (OAUTH_URL/auth)")
    token_url = ask("Token URL (OAUTH_URL/token)")
    api_base = ask("API base URL", default="https://apiv1.toconline.com")
    return SetupInputs(
        client_id=client_id,
        client_secret=client_secret,
        auth_url=auth_url,
        token_url=token_url,
        api_base=api_base,
    )
