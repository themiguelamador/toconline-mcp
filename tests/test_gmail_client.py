from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx
import pytest
import respx

from toconline_mcp.gmail.client import (
    GmailClient,
    _b64url_decode,
    _ensure_extension,
    _extension_for_mime,
    _sanitize_filename,
)
from toconline_mcp.gmail.store import GmailCredentials, save_gmail_credentials
from toconline_mcp.util.errors import ApiError, AuthError


def _write_gmail_creds(path: Path, expires_at: int | None = None, access: str = "gtok1") -> None:
    now = int(time.time())
    creds = GmailCredentials(
        client_id="cid",
        client_secret="csec",
        access_token=access,
        refresh_token="ref1",
        scope="https://www.googleapis.com/auth/gmail.modify",
        expires_at=expires_at if expires_at is not None else now + 3600,
        obtained_at=now,
    )
    save_gmail_credentials(creds, path=path)


@pytest.fixture
def gmail_creds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "gmail-credentials.json"
    monkeypatch.setenv("TOCONLINE_GMAIL_CREDENTIALS_PATH", str(path))
    _write_gmail_creds(path)
    return path


# --- pure helpers ---

def test_b64url_decode_roundtrip():
    data = b"\x00\x01\x02PDF-ish-bytes\xff\xfe"
    encoded = base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    assert _b64url_decode(encoded) == data


def test_sanitize_filename_strips_path_separators_and_specials():
    # Path separators replaced with `_`, traversal is therefore contained
    assert "/" not in _sanitize_filename("../etc/passwd")
    assert "\\" not in _sanitize_filename("..\\etc\\passwd")
    assert _sanitize_filename("../etc/passwd") == "_etc_passwd"
    assert _sanitize_filename("weird:name?.pdf") == "weird_name_.pdf"
    assert _sanitize_filename("ok file (1).pdf") == "ok file (1).pdf"


def test_sanitize_filename_falls_back_on_empty():
    # Fallback has no extension — it's the caller's job (iter_attachment_parts /
    # gmail_download_attachment) to add the right extension from mime_type.
    assert _sanitize_filename("") == "attachment"
    assert _sanitize_filename("...") == "attachment"


def test_unique_save_path_appends_suffix_when_exists(tmp_path: Path):
    (tmp_path / "invoice.pdf").write_bytes(b"")
    chosen = GmailClient.unique_save_path(tmp_path, "invoice.pdf")
    assert chosen == tmp_path / "invoice (2).pdf"
    (tmp_path / "invoice (2).pdf").write_bytes(b"")
    chosen = GmailClient.unique_save_path(tmp_path, "invoice.pdf")
    assert chosen == tmp_path / "invoice (3).pdf"


def test_iter_attachment_parts_recurses():
    payload = {
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [{"mimeType": "text/plain", "body": {}, "filename": ""}],
            },
            {
                "mimeType": "application/pdf",
                "filename": "invoice.pdf",
                "body": {"attachmentId": "AID_PDF", "size": 12345},
            },
            {
                "mimeType": "image/png",
                "filename": "logo.png",
                "body": {"attachmentId": "AID_PNG", "size": 400},
            },
        ]
    }
    atts = list(GmailClient.iter_attachment_parts(payload))
    assert atts == [
        ("invoice.pdf", "application/pdf", "AID_PDF", 12345),
        ("logo.png", "image/png", "AID_PNG", 400),
    ]


def test_iter_attachment_parts_fabricates_name_when_missing():
    payload = {
        "parts": [
            {
                "mimeType": "application/pdf",
                "filename": "",  # sender didn't set a filename (inline-ish PDF)
                "body": {"attachmentId": "AID_NO_NAME", "size": 99},
            },
            {
                "mimeType": "application/octet-stream",
                "filename": "",
                "body": {"attachmentId": "AID_UNKNOWN", "size": 1},
            },
        ]
    }
    atts = list(GmailClient.iter_attachment_parts(payload))
    assert atts == [
        ("attachment.pdf", "application/pdf", "AID_NO_NAME", 99),
        ("attachment.bin", "application/octet-stream", "AID_UNKNOWN", 1),
    ]


def test_iter_attachment_parts_upgrades_bin_extension_from_mime():
    payload = {
        "parts": [
            {
                "mimeType": "application/pdf",
                "filename": "invoice.bin",  # mislabeled by sender
                "body": {"attachmentId": "AID", "size": 10},
            }
        ]
    }
    atts = list(GmailClient.iter_attachment_parts(payload))
    assert atts == [("invoice.pdf", "application/pdf", "AID", 10)]


def test_extension_for_mime_known_types():
    assert _extension_for_mime("application/pdf") == ".pdf"
    assert _extension_for_mime("image/jpeg") == ".jpg"
    assert _extension_for_mime("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == ".xlsx"


def test_extension_for_mime_returns_none_for_octet_stream():
    # octet-stream means "unknown binary" — we must NOT turn it into .bin,
    # because that would silently undo user-provided sensible filenames.
    assert _extension_for_mime("application/octet-stream") is None
    assert _extension_for_mime("") is None
    assert _extension_for_mime(None) is None


def test_extension_for_mime_strips_parameters():
    assert _extension_for_mime("application/pdf; charset=binary") == ".pdf"


def test_ensure_extension_keeps_good_filenames_untouched():
    assert _ensure_extension("invoice.pdf", "application/pdf") == "invoice.pdf"
    assert _ensure_extension("report.docx", "application/pdf") == "report.docx"  # trust sender


def test_ensure_extension_adds_when_missing():
    assert _ensure_extension("invoice", "application/pdf") == "invoice.pdf"
    assert _ensure_extension("photo", "image/jpeg") == "photo.jpg"


def test_ensure_extension_upgrades_bin():
    assert _ensure_extension("invoice.bin", "application/pdf") == "invoice.pdf"
    assert _ensure_extension("attachment.bin", "image/png") == "attachment.png"


def test_ensure_extension_noop_when_mime_unknown():
    assert _ensure_extension("blob.bin", "application/octet-stream") == "blob.bin"
    assert _ensure_extension("blob", None) == "blob"


def test_extract_message_metadata_indexes_headers_case_insensitive():
    msg = {
        "id": "M1",
        "threadId": "T1",
        "snippet": "Hello",
        "internalDate": "1700000000000",
        "sizeEstimate": 4242,
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "FROM", "value": "Alice <a@ex>"},
                {"name": "Subject", "value": "Your invoice"},
                {"name": "To", "value": "me@ex"},
                {"name": "Date", "value": "Wed, 1 Jan 2026 10:00:00 +0000"},
            ]
        },
    }
    m = GmailClient.extract_message_metadata(msg)
    assert m["id"] == "M1"
    assert m["from"] == "Alice <a@ex>"
    assert m["subject"] == "Your invoice"
    assert m["to"] == "me@ex"
    assert m["date"] == "Wed, 1 Jan 2026 10:00:00 +0000"


# --- HTTP client integration (respx-mocked) ---

@respx.mock
async def test_list_messages_uses_bearer_and_q(gmail_creds: Path):
    route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "M1"}], "resultSizeEstimate": 1}),
    )
    client = GmailClient()
    try:
        r = await client.list_messages(query="has:attachment", max_results=5)
    finally:
        await client.aclose()
    assert r["messages"] == [{"id": "M1"}]
    call = route.calls[0].request
    assert call.headers["authorization"] == "Bearer gtok1"
    assert dict(call.url.params) == {"maxResults": "5", "q": "has:attachment"}


@respx.mock
async def test_get_attachment_bytes_decodes_b64url(gmail_creds: Path):
    payload = b"%PDF-1.4 stub bytes\x00\xff"
    b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    respx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/M1/attachments/A1"
    ).mock(return_value=httpx.Response(200, json={"data": b64, "size": len(payload)}))
    client = GmailClient()
    try:
        got = await client.get_attachment_bytes("M1", "A1")
    finally:
        await client.aclose()
    assert got == payload


@respx.mock
async def test_401_triggers_refresh_and_retry(gmail_creds: Path):
    first = httpx.Response(401, json={"error": {"message": "expired"}})
    second = httpx.Response(200, json={"messages": []})
    api_route = respx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    ).mock(side_effect=[first, second])
    token_route = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fresh", "refresh_token": "ref2", "expires_in": 3600},
        ),
    )
    client = GmailClient()
    try:
        r = await client.list_messages()
    finally:
        await client.aclose()
    assert r == {"messages": []}
    assert api_route.call_count == 2
    assert token_route.called
    assert api_route.calls[1].request.headers["authorization"] == "Bearer fresh"


@respx.mock
async def test_modify_labels_requires_at_least_one_change(gmail_creds: Path):
    client = GmailClient()
    try:
        with pytest.raises(ValueError):
            await client.modify_message_labels("M1")
    finally:
        await client.aclose()


@respx.mock
async def test_refresh_failure_surfaces_auth_error(gmail_creds: Path):
    respx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    ).mock(return_value=httpx.Response(401))
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = GmailClient()
    try:
        with pytest.raises(AuthError):
            await client.list_messages()
    finally:
        await client.aclose()


@respx.mock
async def test_api_error_extracts_google_error_message(gmail_creds: Path):
    respx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    ).mock(return_value=httpx.Response(
        403, json={"error": {"code": 403, "message": "Quota exceeded"}}
    ))
    client = GmailClient()
    try:
        with pytest.raises(ApiError) as exc_info:
            await client.list_labels()
    finally:
        await client.aclose()
    assert "Quota exceeded" in str(exc_info.value)
    assert exc_info.value.status == 403
