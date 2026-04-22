from __future__ import annotations

import argparse
import dataclasses
import sys

from toconline_mcp import __version__
from toconline_mcp.auth.setup import prompt_inputs, run_setup
from toconline_mcp.auth.store import load_credentials
from toconline_mcp.config import credentials_path
from toconline_mcp.util.errors import TocError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toconline-mcp",
        description="Local MCP server for the TOCOnline API.",
    )
    parser.add_argument("--version", action="version", version=f"toconline-mcp {__version__}")
    sub = parser.add_subparsers(dest="command")

    setup = sub.add_parser("setup", help="One-time OAuth login (opens browser).")
    setup.add_argument("--port", type=int, default=None, help="Redirect URI port (default 53682).")
    setup.add_argument("--no-browser", action="store_true", help="Print URL instead of launching a browser.")

    sub.add_parser("whoami", help="Show the currently configured credential profile.")
    sub.add_parser("serve", help="Run the MCP stdio server (default if no command given).")

    gmail_setup = sub.add_parser("gmail-setup", help="One-time Google OAuth login for Gmail.")
    gmail_setup.add_argument("--port", type=int, default=None, help="Redirect URI port (default 53683).")
    gmail_setup.add_argument("--no-browser", action="store_true", help="Print URL instead of launching a browser.")

    return parser


def _cmd_setup(port: int | None, no_browser: bool) -> int:
    inputs = prompt_inputs()
    if port is not None:
        inputs = dataclasses.replace(inputs, redirect_port=port)
    run_setup(inputs, open_browser=not no_browser)
    return 0


def _cmd_whoami() -> int:
    path = credentials_path()
    try:
        creds = load_credentials(path)
    except TocError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Profile:  {creds.profile}")
    print(f"API base: {creds.api_base}")
    print(f"Client:   {creds.client_id}")
    print(f"Stored:   {path}")
    return 0


def _cmd_serve() -> int:
    from toconline_mcp.server import run  # imported lazily to avoid mcp import for setup-only flows
    run()
    return 0


def _cmd_gmail_setup(port: int | None, no_browser: bool) -> int:
    from toconline_mcp.gmail.setup import prompt_gmail_inputs, run_gmail_setup
    inputs = prompt_gmail_inputs()
    if port is not None:
        inputs = dataclasses.replace(inputs, redirect_port=port)
    run_gmail_setup(inputs, open_browser=not no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "serve"
    try:
        if command == "setup":
            return _cmd_setup(args.port, args.no_browser)
        if command == "whoami":
            return _cmd_whoami()
        if command == "serve":
            return _cmd_serve()
        if command == "gmail-setup":
            return _cmd_gmail_setup(args.port, args.no_browser)
        parser.error(f"unknown command: {command}")
    except TocError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
