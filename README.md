# TOCOnline MCP

> **Unofficial.** This is an independent, community-built project. It is **not**
> affiliated with, endorsed by, or supported by TOCOnline or Cloudware S.A.
> "TOCOnline" is a trademark of its respective owner. Use at your own risk —
> see the [warranty disclaimer](#license).

Local [MCP](https://modelcontextprotocol.io) server wrapping the [TOCOnline](https://toconline.pt)
accounting/invoicing API. Lets AI assistants list customers, look up products, draft
sales documents, and call arbitrary TOCOnline endpoints on your behalf — after a
one-time OAuth login.

## Status

Alpha. Covers the most common read and write operations for customers, suppliers,
products, and commercial sales documents, plus a generic `api_request` escape
hatch.

## Prerequisites

- macOS or Linux (Windows untested).
- Python 3.11+.
- A TOCOnline account with **admin access** and, for anything beyond `GET`
  requests, an **active GC (Gestão Comercial) license**. `GET`-only use works
  on any plan.
- An API integration configured in TOCOnline — see
  [Getting TOCOnline API credentials](#getting-toconline-api-credentials) below.
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pipx` or plain `python3 -m venv`.

## Install

Not yet published to PyPI — install from source:

```bash
git clone https://github.com/miguelamador/toconline-mcp.git
cd toconline-mcp

# Recommended: uv
uv tool install --from . toconline-mcp
# → installs to ~/.local/share/uv/tools/toconline-mcp/
# → launcher at /Users/<you>/.local/bin/toconline-mcp

# Or pipx
pipx install .

# Or vanilla Python
python3 -m venv ~/.local/toconline-mcp
~/.local/toconline-mcp/bin/pip install .
```

> **macOS sandbox note.** Claude Desktop is sandboxed and cannot execute
> binaries whose Python installation lives under `~/Documents/`, `~/Desktop/`,
> or `~/Downloads/`. The server will fail to start with
> `PermissionError: … /.venv/pyvenv.cfg`. Always install via one of the methods
> above — they all land outside the TCC-protected folders. **Do not** point
> Claude Desktop at a `.venv/bin/toconline-mcp` that lives inside your cloned
> repo if the repo sits in `~/Documents/`.

### Updating after code changes

When you pull new commits or edit the source, refresh the installed tool:

```bash
uv tool install --from . toconline-mcp --reinstall
```

Then restart whichever client is using the server.

## Getting TOCOnline API credentials

Based on the [official TOCOnline API docs](https://api-docs.toconline.pt/).
These steps are one-time per company/tenant.

### 1. Request API access

In the TOCOnline web app, go to **Empresa → Configurações → Dados API**
(*Company → Settings → API Data*). Fill in the integrator details (company
info + contact email) and submit.

TOCOnline will email the integrator address a **temporary link** (valid ~72h)
where you can view and edit the API credentials and integration settings.

### 2. Read the values off the email link page

The link page shows five values you will need:

| TOCOnline variable | What it is | Use in this MCP |
|---|---|---|
| `OAUTH_CLIENT_ID` | OAuth client id | `client_id` |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | `client_secret` |
| `OAUTH_URL` | Your tenant's OAuth base URL | `auth_url` = `<OAUTH_URL>/auth`, `token_url` = `<OAUTH_URL>/token` |
| `API_URL` | Your tenant's API base URL | `api_base` |
| `OAUTH_REDIRECT_URL` | Callback URL (pre-set by TOCOnline; editable) | must match what this MCP uses — see next step |

> The `OAUTH_URL` / `API_URL` values are **tenant-specific**. Use the exact
> values shown on the email link page — the default `api_base` baked into
> this tool (`https://apiv1.toconline.com`) is a generic placeholder and may
> not match your tenant.

### 3. Set the redirect URL to match this MCP

This is the single step most people get wrong. TOCOnline pre-fills
`OAUTH_REDIRECT_URL` with something like `http://127.0.0.1:4080/oauth/callback`.
**This MCP expects `http://127.0.0.1:53682/callback`** (different port,
different path).

On the email link page (or later, back in *Empresa → Configurações → Dados API*),
overwrite `OAUTH_REDIRECT_URL` with exactly:

```
http://127.0.0.1:53682/callback
```

Save. That's it.

If port 53682 is taken on your machine, pick any free port and pass it as
`redirect_port` to the `login` tool (or `--port N` to the CLI). The path
must remain `/callback`.

### 4. Log in

Two equivalent ways — pick whichever fits your workflow.

#### A. From inside your AI client (recommended)

After [registering the server with Claude](#register-with-claude), ask:

> Log in to TOCOnline. Here are the values from *Empresa → Configurações → Dados API*:
> client_id = `...`, client_secret = `...`,
> auth_url = `<OAUTH_URL>/auth`, token_url = `<OAUTH_URL>/token`,
> api_base = `<API_URL>`.

Claude invokes the `login` tool, your browser opens to TOCOnline consent,
you approve, and credentials land in
`~/.config/toconline-mcp/credentials.json` (mode `0600`). No separate
terminal step.

Any time later, ask Claude to run `auth_status` to see whether credentials
are configured and how long until the access token expires, or `logout`
to clear them.

#### B. From the command line

```bash
toconline-mcp setup
```

Prompts for each value interactively, opens the browser, writes the
credentials file. You can also set them in the environment first to skip
the prompts:

```bash
export TOCONLINE_CLIENT_ID='...'
export TOCONLINE_CLIENT_SECRET='...'
export TOCONLINE_AUTH_URL='<OAUTH_URL>/auth'
export TOCONLINE_TOKEN_URL='<OAUTH_URL>/token'
export TOCONLINE_API_BASE='<API_URL>'
toconline-mcp setup
```

### Token lifetime

Access tokens issued by TOCOnline are long-lived (~91 days) and this MCP
refreshes them automatically before each request. You should only need to
re-run `login` / `setup` if you revoke the integration, rotate the client
secret, or change `OAUTH_REDIRECT_URL`.

## Register with Claude

Both clients need the **absolute path** to the installed launcher. Find yours
with:

```bash
which toconline-mcp
# → e.g. /Users/<you>/.local/bin/toconline-mcp
```

### Claude Code

```bash
claude mcp add toconline -- /Users/<you>/.local/bin/toconline-mcp
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and
add the `toconline` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "toconline": {
      "command": "/Users/<you>/.local/bin/toconline-mcp"
    }
  }
}
```

**Fully quit** Claude Desktop (⌘Q — closing the window is not enough) and
reopen it. `toconline` should now appear in your connectors list with a
`DESKTOP` badge.

#### If the server doesn't show up

Check the log:

```bash
tail -50 ~/Library/Logs/Claude/mcp-server-toconline.log
```

Two common errors:

- `PermissionError: … /.venv/pyvenv.cfg` — sandbox blocked the venv. Install
  via `uv tool install --from . toconline-mcp` (see above) and point the
  config at `~/.local/bin/toconline-mcp`, not a `.venv` under `~/Documents/`.
- `ENOENT` / command not found — the path in the config is wrong. Run
  `which toconline-mcp` again and paste that exact path into the config.

### Once this package is published to PyPI

After a `uv publish`, the config can use the shorter portable form that doesn't
depend on a specific user's filesystem:

```json
{
  "mcpServers": {
    "toconline": { "command": "uvx", "args": ["toconline-mcp"] }
  }
}
```

## Tools

34 typed tools plus a generic escape hatch. All filters are exact match —
TOCOnline does not expose range or substring operators.

### Authentication
| Tool | Purpose |
|---|---|
| `auth_status` | Check whether credentials are configured and when the access token expires. |
| `login` | Run the OAuth browser flow and store credentials. |
| `logout` | Delete stored credentials. |

### Customers, suppliers, products
| Tool | Purpose |
|---|---|
| `list_customers` / `get_customer` / `create_customer` / `update_customer` | Customer CRUD. |
| `list_suppliers` / `get_supplier` | Suppliers read-only. |
| `list_products` / `get_product` | Products/services read-only. |

### Addresses & contacts
Addresses and contacts are separate JSON:API resources with an owning
`customer_id` or `supplier_id` (exactly one, not both).

| Tool | Purpose |
|---|---|
| `list_addresses` / `get_address` / `create_address` / `update_address` / `delete_address` | Address CRUD. Scope listings by `customer_id` or `supplier_id`. |
| `list_contacts` / `get_contact` / `create_contact` / `update_contact` / `delete_contact` | Contact CRUD with the same scoping. |

`delete_address` / `delete_contact` require `confirm=true`.

### Sales documents & receipts
| Tool | Purpose |
|---|---|
| `list_sales_documents` | Filter by `document_type` / `customer_id` / `date`. |
| `get_sales_document` | Single document, with its line items merged by default. |
| `create_sales_document` | Draft document with line items. For credit/debit notes, set `document_type='NC'` or `'ND'` and pass `parent_document_id` to reference the original. |
| `list_sales_receipts` / `get_sales_receipt` / `create_sales_receipt` | Customer-payment receipts. |

### Purchases
| Tool | Purpose |
|---|---|
| `list_purchase_documents` / `get_purchase_document` / `create_purchase_document` | Supplier invoices. |
| `list_purchase_payments` / `get_purchase_payment` / `create_purchase_payment` | Supplier payments. |

### Escape hatch
| Tool | Purpose |
|---|---|
| `api_request` | Generic `/api/*` passthrough for endpoints without typed tools. `POST`/`PATCH`/`PUT`/`DELETE` require `confirm=true`. |

### Response shape

Responses are flattened from JSON:API — `data.attributes.*` fields are hoisted
to the top level, and `relationships.<name>.data.id` becomes `<name>_id`:

```json
{
  "items": [
    {"id": "1", "type": "customers", "business_name": "ACME", "country_code": "PT"}
  ],
  "meta": {"total": 1}
}
```

### Document actions (PDF, email, finalize, void)

| Tool | Purpose |
|---|---|
| `get_document_pdf_url` | Get a signed public URL to the PDF of a sales document, sales receipt, or purchase document. The URL works unauthenticated for a short time — share it with a user and they can download. |
| `send_document_email` | Email a sales document or receipt to a recipient via TOCOnline's mail servers. |
| `finalize_sales_document` / `finalize_purchase_document` | Issue a draft document. Irreversible — requires `confirm=true`. |
| `void_sales_receipt` / `void_purchase_document` | Void (anular) a document. Irreversible — requires `confirm=true`. |

These endpoints aren't in the public API docs but are discoverable via the
Postman collection TOCOnline provides from *Empresa → Configurações → Dados API*.

### Not yet implemented

- **AT document communication** (Portuguese tax authority reporting) —
  endpoint is `PATCH /api/send_document_at_webservice` but requires a
  pre-existing communication status/code workflow we haven't mapped.
- **Settlement linking** between a payment/receipt and the documents it
  settles — `create_*_payment` / `create_*_receipt` create the payment
  record itself but don't attach settlement lines. TOCOnline exposes
  `commercial_*_payment_lines` / `commercial_sales_receipt_lines` for this;
  use `api_request` until we add typed tools.
- **Product create/update**, **supplier create/update** — endpoints exist
  (`POST/PATCH /api/products`, `POST/PATCH /api/suppliers`) and can be
  called via `api_request`.
- **Auxiliary APIs** as typed tools (tax descriptors at
  `/api/tax_descriptors`, item families at `/api/item_families`, countries,
  units of measure, bank accounts, cash accounts) — all readable via
  `api_request`.

If any of these becomes important, ask and we'll promote it to a typed tool.

## Gmail integration (optional)

This MCP can also search Gmail and download attachments — useful for pulling
supplier-invoice PDFs out of email and archiving them into a folder (local
or Google-Drive/iCloud-synced). It's completely independent of the TOCOnline
tools; use it or don't.

### One-time Google Cloud setup

1. Go to <https://console.cloud.google.com/> and create (or pick) a project.
2. **APIs & Services → Library** → enable **Gmail API**.
3. **APIs & Services → OAuth consent screen** → set up a "Desktop"/"External"
   consent screen with your email as a test user.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → *Desktop app* (or *Web app*). Register
   `http://127.0.0.1:53683/callback` as an Authorized redirect URI.
5. Copy the **Client ID** and **Client secret**.

### Log in

Either from the CLI:

```bash
toconline-mcp gmail-setup
```

or from Claude (same shape as TOCOnline's `login`):

> Log in to Gmail. client_id = `…`, client_secret = `…`

Tokens are saved to `~/.config/toconline-mcp/gmail-credentials.json` (0600),
separate from the TOCOnline credentials.

### Scope

`gmail.modify` — covers reading messages, downloading attachments, and
adding/removing labels. It does **not** allow permanent deletion or sending
messages. Narrower scopes (like `gmail.readonly` or `gmail.labels`) can't
label messages, which breaks the "mark as imported" workflow.

### Gmail tools (10)

| Tool | Purpose |
|---|---|
| `gmail_auth_status` / `gmail_login` / `gmail_logout` | Auth lifecycle (mirrors TOCOnline's auth trio). |
| `gmail_search_messages` | Search with Gmail query syntax (`has:attachment filename:pdf from:billing@…`). Returns compact metadata + attachment list per message. |
| `gmail_get_message` | Fetch a single message's metadata + attachment list. |
| `gmail_download_attachment` | Download one attachment to an absolute local path. Handles filename collisions with ` (2)`, ` (3)`… suffixes. |
| `gmail_list_labels` / `gmail_create_label` | Discover and create labels. |
| `gmail_add_label_to_message` / `gmail_remove_label_from_message` | Mark messages as processed (e.g. apply an `Imported/TOCOnline` label). |

### Example workflow: bulk-download supplier invoices

Ask Claude:

> Search my Gmail for unread messages from `billing@` senders with PDF
> attachments since 2026-04-01. For each one, download every PDF to
> `/Users/me/Google Drive/Invoices/2026-04/` and apply the label
> `Imported/TOCOnline`. Then print a summary table.

Claude uses: `gmail_search_messages` → `gmail_list_labels` (or `gmail_create_label`
if missing) → for each result `gmail_download_attachment` + `gmail_add_label_to_message`.
Using a Google-Drive-synced folder for `save_dir` gives you cloud sync for free.

### Gmail env vars

- `TOCONLINE_GMAIL_CREDENTIALS_PATH` — override the credentials file location.
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` — skip the CLI prompts during
  `gmail-setup`.

## Config file (`~/.config/toconline-mcp/.env`)

Rather than exporting env vars in your shell every time, drop them in a
`.env` file and the MCP loads it at startup. Values from real environment
variables always win — the file is a fallback.

Loader checks these paths in order (first existing one wins):

1. Whatever `TOCONLINE_ENV_FILE` points at (if set).
2. `~/.config/toconline-mcp/.env`  — primary location (next to `credentials.json`).
3. `./.env` in the current working directory (dev convenience).

Example file — all fields optional, include only what you want cached:

```bash
# ~/.config/toconline-mcp/.env

# --- TOCOnline ---
TOCONLINE_CLIENT_ID=ptNNNNNNNNN_cNNNNNN-xxxxxxxxxxxxxxxx
TOCONLINE_CLIENT_SECRET=your-rotated-secret
TOCONLINE_AUTH_URL=https://app14.toconline.pt/oauth/auth
TOCONLINE_TOKEN_URL=https://app14.toconline.pt/oauth/token
TOCONLINE_API_BASE=https://api14.toconline.pt

# --- Gmail (Google OAuth client from console.cloud.google.com) ---
GMAIL_CLIENT_ID=1234...apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxx
```

Format:
- `KEY=VALUE` per line.
- `#` comments and blank lines are fine.
- Quote values with spaces: `NAME="with spaces"`.
- `export KEY=VALUE` is accepted (for shell-compatibility).
- **No variable interpolation** (`$VAR` / `${VAR}`) — export from shell if you need that.

After creating the file, `toconline-mcp setup` and `toconline-mcp gmail-setup`
skip the interactive prompts for any field the file already provides.

**Permissions**: the file contains OAuth client secrets, which are less
sensitive than access tokens but still not public. Chmod it:

```bash
chmod 600 ~/.config/toconline-mcp/.env
```

The MCP prints a `warning:` on stderr if it detects looser permissions.

## Development

```bash
uv venv --python 3.11
uv pip install -e '.[dev]'
pytest
```

Environment variables:

- `TOCONLINE_CREDENTIALS_PATH` — override the credentials file location.
- `TOCONLINE_LOG_LEVEL` — `DEBUG`, `INFO`, `WARNING`, etc. Logs go to stderr.

### Iteration workflow (picking up code changes)

`uv tool install --reinstall` updates the binary on disk, but **does not
restart already-running MCP processes** — Python imports modules at startup,
so a live server keeps serving the old code until killed. After editing the
source:

```bash
# 1. Run the test suite (catches regressions before they hit the live server)
pytest

# 2. Refresh the installed launcher
uv tool install --from . toconline-mcp --reinstall

# 3. Find Claude Desktop's MCP server process and kill it
ps aux | grep toconline-mcp | grep -v grep
kill <pid>

# 4. Start a new chat in Claude Desktop (Cmd-N). The first tool call
#    in that new chat causes Claude Desktop to respawn the MCP with the
#    new code — and the new chat's LLM is given the fresh tool list.
```

#### Why "new chat" matters even more than "kill the server"

There are two layers that cache things:

1. **The MCP server process** caches the registered tool list in memory
   (modules are imported at startup). Killing the process forces a
   respawn that re-imports the latest code.
2. **The chat session** caches the tool list it got from the server at
   chat start, baked into the LLM's context. Newly-added tools don't
   appear in an *existing* chat even after the server respawns.

So if you've added a tool (`list_services` for example) and you want the
LLM to be able to call it, you need both:
- The kill+respawn (so the server exposes the new tool at all), AND
- A new chat (so the LLM is told the new tool exists).

Editing an existing tool's behaviour or fixing a bug is different — the
tool's name is the same, the LLM already knows about it, so just kill+respawn
is enough; the next call hits the new code. **Adding** or **renaming** tools
requires a new chat.

The same applies to Claude Code: the deferred tools list shown at session
start is locked in for that chat. New tools require a new Claude Code session
(`/clear` or starting fresh).

#### Stale processes

Stray `uvx toconline-mcp` processes from old terminals can linger and serve
stale code. `ps aux | grep toconline-mcp` shows them; `kill <pid>` clears
them. They're harmless when idle but confusing if you `claude mcp add` more
than one server pointing at the same binary.

## Security

- Tokens and client secrets stored in `~/.config/toconline-mcp/credentials.json`
  (`0600`). The server refuses to start if permissions are looser.
- All logging is to stderr (stdout is reserved for MCP stdio framing).
  Authorization headers and token fields are redacted from log messages.
- `api_request` path is constrained to `^/api/...` with no `..`; write methods
  require an explicit `confirm=true`.

## License

MIT.
