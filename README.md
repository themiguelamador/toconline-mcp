# TOCOnline MCP

> **Unofficial.** This is an independent, community-built project. It is **not**
> affiliated with, endorsed by, or supported by TOCOnline or Cloudware S.A.
> "TOCOnline" is a trademark of its respective owner. Use at your own risk —
> see the [warranty disclaimer](#license).

Local [MCP](https://modelcontextprotocol.io) server wrapping the [TOCOnline](https://toconline.pt)
accounting/invoicing API. Lets AI assistants list customers, look up products, draft
sales documents, and call arbitrary TOCOnline endpoints on your behalf — after a
one-time OAuth login.

## Quick start

The whole setup is four steps. Each links to its full section below.

1. **Install the launcher** (needs Python 3.11+ and [`uv`](https://github.com/astral-sh/uv)):
   ```bash
   git clone https://github.com/themiguelamador/toconline-mcp.git
   cd toconline-mcp && uv tool install --from . toconline-mcp
   ```
   → puts a `toconline-mcp` launcher on your `PATH`. [Details](#install).

2. **Get your TOCOnline API credentials** — in the TOCOnline web app,
   *Empresa → Configurações → Dados API*, request access and set the redirect
   URL to `http://127.0.0.1:53682/callback`. You'll end up with five values
   (`client_id`, `client_secret`, two OAuth URLs, an API URL).
   [Details](#getting-toconline-api-credentials).

3. **Register the server with your client** — one line for Claude Code, a small
   JSON block for Claude Desktop. [Details](#register-with-claude).

4. **Log in** — ask your assistant "Log in to TOCOnline" (paste the five
   values), or run `toconline-mcp setup`. A browser opens, you approve, done.
   [Details](#4-log-in).

That's it — read-only use works on any plan. Creating/editing documents needs
an active GC license. **Gmail is a separate, optional add-on** for archiving
invoice PDFs from email — skip it unless you want it
([details](#gmail-integration-optional)).

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
git clone https://github.com/themiguelamador/toconline-mcp.git
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

When you pull new commits or edit the source, three steps — and which you need
depends on what changed:

```bash
# 1. Rebuild the installed launcher (always)
uv tool install --from . toconline-mcp --reinstall
```

2. **Restart the server** — fully quit the client (Claude Desktop: ⌘Q, not
   just the window) and reopen, or kill the running `toconline-mcp` process so
   it respawns with the new code.
3. **Start a new chat** — *only needed when you added or renamed a tool.* The
   chat caches the tool list it got at startup, so a new tool won't appear in
   an existing conversation even after the server restarts.

Editing an existing tool's behaviour needs only steps 1–2; **adding or
renaming** a tool needs all three. See
[Iteration workflow](#iteration-workflow-picking-up-code-changes) for the full
explanation and how to find/kill stale processes.

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

> If the MCP server is already running in your client, restart/reconnect it
> afterwards — it caches credentials in memory at startup, so `auth_status`
> will show the fresh token while real calls still fail with
> `unauthorized_client` until the server reloads the file.

### Token lifetime

Per TOCOnline's [auth docs](https://api-docs.toconline.pt/autenticacao-detalhada),
the **access token lasts 4 hours** (`expires_in: 14400`) and the **refresh
token 8 hours**. This MCP refreshes the access token automatically (2 minutes
before expiry) whenever you make a request, so during active use you never
notice.

The catch is the 8-hour refresh window: if the server sits **idle for more
than 8 hours**, the refresh token expires and the next call fails with a
401 — you'll need to re-run `login` / `setup`. (This is a TOCOnline limit, not
something this MCP can extend.) You also re-login if you revoke the
integration, rotate the client secret, or change `OAUTH_REDIRECT_URL`.

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

## API coverage

Targets the **TOCOnline Open API v1.0.0** (JSON:API), documented at
[api-docs.toconline.pt](https://api-docs.toconline.pt/) with the full
[OpenAPI 3.0.3 spec on SwaggerHub](https://app.swaggerhub.com/apis-docs/toconline.pt/toc-online_open_api/1.0.0)
(68 paths). The base URL is
region-specific — e.g. `https://api14.toconline.pt` (the digits match your
account's region). A few document actions (finalize, email) use TOCOnline's
legacy **v1 action** endpoints, which aren't in the public docs but ship in the
Postman collection from *Empresa → Configurações → Dados API*.

Mapped against the public docs — ✅ typed tool, ⚠️ partial, ❌ `api_request` only:

| API section (docs) | Resource | Coverage |
|---|---|---|
| Empresa | Clientes (+ morada, e-mail) | ✅ full CRUD + addresses/contacts |
| Empresa | Fornecedores (+ morada, e-mail) | ✅ full CRUD + addresses/contacts |
| Empresa | Produtos e Serviços | ✅ full CRUD |
| Vendas | Documentos de Venda | ✅ list/get/create/delete |
| Vendas | Recibos de Venda | ✅ list/get/create + void |
| Vendas | PDF (documento + recibo) | ✅ `get_document_pdf_url` |
| Vendas | Envio por e-mail | ✅ `send_document_email` |
| Vendas | Comunicação à AT | ✅ `communicate_sales_document_at` |
| Compras | Documentos de Compra | ✅ list/get/create + finalize/void |
| Compras | Pagamentos | ✅ list/get/create |
| Compras | PDF / Comunicação à AT | ✅ pdf url + `communicate_purchase_document_at` |
| Auxiliares | Descritores de Taxa | ✅ `list_tax_descriptors` |
| Auxiliares | Família de Itens | ✅ `list_item_families` |
| Auxiliares | Países | ✅ `list_countries` |
| Auxiliares | Unidades de Medida | ✅ `list_units_of_measure` |
| Auxiliares | Contas Bancárias | ✅ `list_bank_accounts` / `get` |
| Auxiliares | Caixa Associada | ✅ `list_cash_accounts` |
| Auxiliares | Unidade Monetária (moedas) | ❌ `api_request` |
| Auxiliares | Taxas (tax rates) | ❌ `api_request` |
| Auxiliares | Categorias de Despesa | ❌ `api_request` |
| Auxiliares | Documentos de Série | ❌ `api_request` |
| Auxiliares | OSS (países e taxas) | ❌ `api_request` |
| Vendas/Compras | Settlement / payment lines | ✅ `create_sales_receipt_line` / `create_purchase_payment_line` |

Anything ❌ works today through `api_request` with no new code — the four
uncovered auxiliary tables are read-only lookups. Ask if you want any promoted
to a typed tool.

### Validation status

How far each recently added/changed tool has been verified — **live** = a real
call against the API succeeded; **unit** = payload shape covered by tests but not
run against the API; **untested** = no automated or live check yet.

| Tool(s) | Status |
|---|---|
| `list_countries`, `list_item_families`, `list_units_of_measure`, `list_tax_descriptors`, `list_cash_accounts` | ✅ live |
| `create_product` (incl. required `type` + `item_family_id`) | ✅ live |
| `delete_product` | ✅ live |
| `create_service`, `delete_service` | ✅ live |
| `update_product`, `update_service` | 🧪 unit |
| `create_customer` / `update_customer` / `delete_customer` | 🧪 unit |
| `create_supplier` / `update_supplier` / `delete_supplier` | 🧪 unit |
| `create_sales_receipt_line`, `create_purchase_payment_line` | 🧪 unit — money path, not run live (settles real documents) |
| `communicate_sales_document_at`, `communicate_purchase_document_at` | ⏳ untested — binding AT submission |

## Tools

53 typed tools plus a generic escape hatch. The typed tools expose exact-match
filters only, but the underlying API
[supports comparison operators](https://api-docs.toconline.pt/caracteristicas-dos-pedidos)
— e.g. `filter="documents.pending_total>0"` or
`document_lines.created_at>'2022-01-01'::date`. Reach for `api_request` with a
raw `filter` param when you need ranges or date comparisons.

### Authentication
| Tool | Purpose |
|---|---|
| `auth_status` | Check whether credentials are configured and when the access token expires. |
| `login` | Run the OAuth browser flow and store credentials. |
| `logout` | Delete stored credentials. |

### Customers, suppliers, products
| Tool | Purpose |
|---|---|
| `list_customers` / `get_customer` / `create_customer` / `update_customer` / `delete_customer` | Customer CRUD. |
| `list_suppliers` / `get_supplier` / `create_supplier` / `update_supplier` / `delete_supplier` | Supplier CRUD. |
| `list_products` / `get_product` / `create_product` / `update_product` / `delete_product` | Product CRUD. |
| `list_services` / `get_service` / `create_service` / `update_service` / `delete_service` | Service CRUD. |

`delete_*` require `confirm=true`. Create/update set the API-required item
`type` attribute (`Product`/`Service`) automatically.

### Reference tables (read-only)
Lookup resources used when building documents and items.

| Tool | Purpose |
|---|---|
| `list_countries` | ISO country codes and names. |
| `list_item_families` | Item families for categorizing products/services (`item_family_id`). |
| `list_units_of_measure` | Units (unidades) for document lines. |
| `list_tax_descriptors` | VAT rates and their codes (`NOR`, `INT`, `RED`, `ISE`). |
| `list_cash_accounts` | Cash accounts (caixas) for receipts/payments. |

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
| `create_sales_receipt_line` | Settle a sales document against a receipt (settlement line). |

### Purchases
| Tool | Purpose |
|---|---|
| `list_purchase_documents` / `get_purchase_document` / `create_purchase_document` | Supplier invoices. |
| `list_purchase_payments` / `get_purchase_payment` / `create_purchase_payment` | Supplier payments. |
| `create_purchase_payment_line` | Settle a purchase document line against a payment (settlement line). |

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

### Document actions (PDF, email, finalize, void, AT)

| Tool | Purpose |
|---|---|
| `get_document_pdf_url` | Get a signed public URL to the PDF of a sales document, sales receipt, or purchase document. The URL works unauthenticated for a short time — share it with a user and they can download. |
| `send_document_email` | Email a sales document or receipt to a recipient via TOCOnline's mail servers. |
| `finalize_sales_document` / `finalize_purchase_document` | Issue a draft document. Irreversible — requires `confirm=true`. |
| `void_sales_receipt` / `void_purchase_document` | Void (anular) a document. Irreversible — requires `confirm=true`. |
| `communicate_sales_document_at` / `communicate_purchase_document_at` | Report a finalized document to the AT (tax authority). Binding — requires `confirm=true`. |

These endpoints aren't in the public API docs but are discoverable via the
Postman collection TOCOnline provides from *Empresa → Configurações → Dados API*.

### Settlement linking

`create_sales_receipt_line` / `create_purchase_payment_line` attach a receipt or
payment to the document it settles (so the document is marked paid). The two are
asymmetric, per the API:

- **Sales** settle a whole **document**: `receivable_type="Document"`,
  `receivable_id` = the sales document id.
- **Purchases** settle a document **line**: `payable_type="Purchases::DocumentLine"`,
  `payable_id` = a purchase document *line* id (not the document id).

The tools build the documented payload; the settlement amounts (`received_value`
/ `paid_value`, `settlement_amount`, `retention_total`, …) are the caller's
responsibility.

The four uncovered auxiliary read tables (currencies, taxes, expense categories,
document series, OSS) stay on `api_request` — ask and we'll promote any to a
typed tool.

## Gmail integration (optional)

**Most people don't need this.** It's a separate add-on for one workflow:
pulling supplier-invoice PDFs out of email and archiving them into a folder
(local or Google-Drive/iCloud-synced), so you can then enter them in TOCOnline.
It's invoice-archiving only — not a general Gmail client (no send, no delete).
Completely independent of the TOCOnline tools.

> **Off by default — nothing to do if you don't want it.** The 10 `gmail_*`
> tools only appear once Gmail credentials exist (or you set `TOCONLINE_GMAIL=1`).
> If you do want it, the three steps are below:
>
> 1. **One-time Google Cloud setup** — create an OAuth client (you bring your
>    own Google credentials).
> 2. **Log in once via the CLI** — `toconline-mcp gmail-setup`.
> 3. **Restart your client** — the `gmail_*` tools now show up.

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

First login must use the CLI (the in-Claude `gmail_*` tools don't exist until
credentials are present):

```bash
toconline-mcp gmail-setup
```

Tokens are saved to `~/.config/toconline-mcp/gmail-credentials.json` (0600),
separate from the TOCOnline credentials. Restart your client afterwards — the
`gmail_*` tools (including `gmail_login` for re-auth) now appear.

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
