# TOCOnline MCP

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

### Not yet implemented

The following are on the TOCOnline docs sitemap but are **not** exposed as
typed tools — and our `api_request` escape hatch may not work for them
either (PDF/email require non-JSON response handling, which the HTTP client
does not currently support):

- **PDF download** for sales/purchase documents and receipts.
- **Email send** for documents and receipts.
- **AT document communication** (Portuguese tax authority reporting).
- **Finalize/issue** a draft sales or purchase document (no documented
  endpoint; changing `status` via `api_request` PATCH may work but is
  untested).
- **Settlement linking** between a payment/receipt and the documents it
  settles (the `create_*_payment`/`create_*_receipt` tools create the
  payment record itself but do not attach settlement lines).
- **Product create/update**, **supplier create/update**.
- **Auxiliary APIs** as typed tools (tax rate descriptors, item families,
  countries, units of measure, bank accounts, expense categories, series
  documents) — you can still read them with `api_request` on the
  corresponding paths, e.g. `api_request method=GET path=/api/countries`.

If any of these becomes important, ask and we'll add a typed tool (with a
new code path for binary responses in the PDF/email case).

## Development

```bash
uv venv --python 3.11
uv pip install -e '.[dev]'
pytest
```

Environment variables:

- `TOCONLINE_CREDENTIALS_PATH` — override the credentials file location.
- `TOCONLINE_LOG_LEVEL` — `DEBUG`, `INFO`, `WARNING`, etc. Logs go to stderr.

## Security

- Tokens and client secrets stored in `~/.config/toconline-mcp/credentials.json`
  (`0600`). The server refuses to start if permissions are looser.
- All logging is to stderr (stdout is reserved for MCP stdio framing).
  Authorization headers and token fields are redacted from log messages.
- `api_request` path is constrained to `^/api/...` with no `..`; write methods
  require an explicit `confirm=true`.

## License

MIT.
