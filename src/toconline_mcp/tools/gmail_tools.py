from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from toconline_mcp.gmail.client import GmailClient
from toconline_mcp.gmail.setup import GmailSetupInputs, run_gmail_setup
from toconline_mcp.gmail.store import gmail_credentials_path, load_gmail_credentials
from toconline_mcp.util.errors import TocError

_LOGIN_TIMEOUT_SECONDS = 180.0

# Single shared client per MCP session (token refresh is cached in memory).
_client = GmailClient()


def register(mcp: FastMCP) -> None:
    _login_lock = asyncio.Lock()

    # ---------- Auth ----------

    @mcp.tool()
    async def gmail_auth_status() -> dict[str, Any]:
        """Report whether Gmail credentials are configured and their expiry."""
        path = gmail_credentials_path()
        try:
            creds = load_gmail_credentials(path)
        except TocError as exc:
            return {"authenticated": False, "credentials_path": str(path), "reason": str(exc)}
        now = int(time.time())
        return {
            "authenticated": True,
            "credentials_path": str(path),
            "client_id": creds.client_id,
            "scope": creds.scope,
            "token_expires_in_seconds": creds.expires_at - now,
            "token_obtained_at": creds.obtained_at,
        }

    @mcp.tool()
    async def gmail_login(
        client_id: Annotated[str, Field(description="Google OAuth Client ID (Desktop or Web app).")],
        client_secret: Annotated[str, Field(description="Google OAuth Client Secret.")],
        redirect_port: Annotated[
            int, Field(description="Local port for the OAuth callback listener.", ge=1024, le=65535),
        ] = 53683,
    ) -> dict[str, Any]:
        """Run the Google OAuth browser flow and store Gmail credentials.

        You must register `http://127.0.0.1:<redirect_port>/callback` as a
        redirect URI on your Google Cloud OAuth client, and enable the
        Gmail API for the project. Scope used: gmail.modify (read + label
        changes; does not allow permanent delete or send).

        Blocks for up to 3 minutes waiting for the browser callback.
        """
        async with _login_lock:
            inputs = GmailSetupInputs(
                client_id=client_id, client_secret=client_secret, redirect_port=redirect_port
            )
            await asyncio.to_thread(run_gmail_setup, inputs, True, _LOGIN_TIMEOUT_SECONDS)
            await _client.invalidate()
        return {"status": "ok", "credentials_path": str(gmail_credentials_path())}

    @mcp.tool()
    async def gmail_logout() -> dict[str, Any]:
        """Delete stored Gmail credentials and drop in-memory tokens."""
        path = gmail_credentials_path()
        existed = path.exists()
        if existed:
            path.unlink()
        await _client.invalidate()
        return {
            "status": "ok" if existed else "no-op",
            "message": "Credentials deleted." if existed else "No Gmail credentials were stored.",
            "credentials_path": str(path),
        }

    # ---------- Messages ----------

    @mcp.tool()
    async def gmail_search_messages(
        query: Annotated[
            str,
            Field(
                description=(
                    "Gmail search query — same syntax as the Gmail search bar. "
                    "Examples: `has:attachment filename:pdf from:billing@ after:2026/01/01`, "
                    "`label:UNREAD has:attachment`, `subject:invoice`."
                )
            ),
        ],
        max_results: Annotated[
            int,
            Field(description="Max messages to return (1-100).", ge=1, le=100),
        ] = 25,
        include_attachments: Annotated[
            bool,
            Field(description="If true, expand each result with attachment metadata."),
        ] = True,
    ) -> dict[str, Any]:
        """Search Gmail and return compact message metadata.

        Each item has `id`, `thread_id`, `from`, `subject`, `date`, `snippet`,
        `label_ids`. If `include_attachments=true`, each item also has
        `attachments`: a list of `{filename, mime_type, attachment_id, size}`
        you can feed to `gmail_download_attachment`.
        """
        listing = await _client.list_messages(query=query, max_results=max_results)
        ids = [m["id"] for m in (listing.get("messages") or []) if m.get("id")]
        if not ids:
            return {"query": query, "items": [], "next_page_token": listing.get("nextPageToken")}

        fmt = "full" if include_attachments else "metadata"
        messages = await asyncio.gather(*(_client.get_message(i, fmt=fmt) for i in ids))

        items = []
        for msg in messages:
            item = _client.extract_message_metadata(msg)
            if include_attachments:
                item["attachments"] = [
                    {"filename": fn, "mime_type": mt, "attachment_id": aid, "size": sz}
                    for (fn, mt, aid, sz) in _client.iter_attachment_parts(msg.get("payload"))
                ]
            items.append(item)
        return {
            "query": query,
            "items": items,
            "next_page_token": listing.get("nextPageToken"),
            "result_size_estimate": listing.get("resultSizeEstimate"),
        }

    @mcp.tool()
    async def gmail_get_message(
        message_id: Annotated[str, Field(description="Gmail message id.")],
        include_attachments: Annotated[
            bool,
            Field(description="Include attachment metadata (filename, size, attachment_id)."),
        ] = True,
    ) -> dict[str, Any]:
        """Fetch one message's metadata and attachment list."""
        msg = await _client.get_message(message_id, fmt="full")
        item = _client.extract_message_metadata(msg)
        if include_attachments:
            item["attachments"] = [
                {"filename": fn, "mime_type": mt, "attachment_id": aid, "size": sz}
                for (fn, mt, aid, sz) in _client.iter_attachment_parts(msg.get("payload"))
            ]
        return item

    # ---------- Attachments ----------

    @mcp.tool()
    async def gmail_download_attachment(
        message_id: Annotated[str, Field(description="Gmail message id.")],
        attachment_id: Annotated[
            str,
            Field(description="Attachment id from gmail_search_messages / gmail_get_message."),
        ],
        save_dir: Annotated[
            str,
            Field(
                description=(
                    "Absolute path to an existing directory where the file will be saved. "
                    "Point at a Google-Drive/iCloud-synced folder if you want cloud sync — "
                    "the OS syncs transparently."
                )
            ),
        ],
        filename: Annotated[
            str | None,
            Field(
                description=(
                    "Override the saved filename. If omitted, uses the filename from the "
                    "email (sanitized). If a file of that name already exists, ` (N)` is "
                    "appended before the extension to avoid overwriting."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Download one attachment to `save_dir`. Returns the saved path and size.

        Filename resolution:
          * If `filename` is not provided, we fetch the message and look up the
            attachment part — using both its filename header and its MIME type
            to produce a meaningful extension (e.g. `.pdf`, `.jpg`, `.xlsx`).
          * A user-provided `filename` is used as-is unless it lacks an
            extension or ends in `.bin` — then the part's MIME type supplies
            the correct extension.
        """
        from toconline_mcp.gmail.client import _ensure_extension

        directory = Path(save_dir).expanduser()
        if not directory.is_absolute():
            raise ValueError("save_dir must be an absolute path")
        if not directory.is_dir():
            raise ValueError(f"save_dir does not exist or is not a directory: {directory}")

        # Look up the part once — we need its mime_type regardless of whether
        # the caller passed a filename.
        msg = await _client.get_message(message_id, fmt="full")
        part = next(
            ((fn, mt) for (fn, mt, aid, _sz) in _client.iter_attachment_parts(msg.get("payload"))
             if aid == attachment_id),
            None,
        )
        part_filename = part[0] if part else None
        part_mime_type = part[1] if part else None

        resolved = filename or part_filename or "attachment"
        resolved = _ensure_extension(resolved, part_mime_type)

        data = await _client.get_attachment_bytes(message_id, attachment_id)
        path = _client.unique_save_path(directory, resolved)
        path.write_bytes(data)
        return {
            "saved_path": str(path),
            "size": len(data),
            "filename": path.name,
            "mime_type": part_mime_type,
        }

    # ---------- Labels ----------

    @mcp.tool()
    async def gmail_list_labels() -> dict[str, Any]:
        """List Gmail labels (system + user) with their ids.

        Use this to resolve a name like `Imported/TOCOnline` to its id before
        calling `gmail_add_label_to_message`.
        """
        return await _client.list_labels()

    @mcp.tool()
    async def gmail_create_label(
        name: Annotated[
            str,
            Field(
                description=(
                    "Label name. Use `/` for nested labels (e.g. `Imported/TOCOnline`). "
                    "Returns the created label including its `id`."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Create a Gmail label. Fails if a label of the same name already exists."""
        return await _client.create_label(name=name)

    @mcp.tool()
    async def gmail_add_label_to_message(
        message_id: Annotated[str, Field(description="Gmail message id.")],
        label_id: Annotated[
            str,
            Field(description="Label id (from gmail_list_labels or gmail_create_label)."),
        ],
    ) -> dict[str, Any]:
        """Add a label to a message — useful to mark it as processed/imported."""
        result = await _client.modify_message_labels(message_id, add_label_ids=[label_id])
        return {"status": "ok", "message_id": message_id, "label_ids": result.get("labelIds") or []}

    @mcp.tool()
    async def gmail_remove_label_from_message(
        message_id: Annotated[str, Field(description="Gmail message id.")],
        label_id: Annotated[str, Field(description="Label id to remove.")],
    ) -> dict[str, Any]:
        """Remove a label from a message."""
        result = await _client.modify_message_labels(message_id, remove_label_ids=[label_id])
        return {"status": "ok", "message_id": message_id, "label_ids": result.get("labelIds") or []}
