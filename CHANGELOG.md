# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Commits follow [Conventional Commits](https://www.conventionalcommits.org/); a
release groups them under the headings below. While pre-1.0, breaking changes
may land in minor versions.

## [Unreleased]

## [0.2.0] - 2026-06-28

Expanded the typed-tool surface to broad CRUD coverage, added the AT
communication and settlement-linking flows, and fixed several correctness bugs
found while dogfooding real invoice emission.

### Added
- Full CRUD for customers, suppliers, products, and services, including
  `delete_*` tools (guarded by `confirm=true`).
- Settlement linking: `create_sales_receipt_line` and
  `create_purchase_payment_line`.
- AT (tax authority) document communication:
  `communicate_sales_document_at` / `communicate_purchase_document_at`.
- Reference-table reads: `list_countries`, `list_item_families`,
  `list_units_of_measure`, `list_tax_descriptors`, `list_cash_accounts`.
- Address and contact CRUD tools.
- Document actions: signed PDF URL, email delivery, finalize, and void.
- Bank account / transaction tools and company tools.
- Optional Gmail integration, gated behind credentials or `TOCONLINE_GMAIL=1`.
- JSON:API pagination, sort, and sparse fieldsets across list tools.
- MIT license, an API coverage map, and a per-tool validation-status table in
  the README.

### Fixed
- Products and services now send the API-required item `type` attribute
  (`Product` / `Service`); items were previously rejected without it.
- `item_family` is set via the `item_family_id` attribute rather than a
  JSON:API relationship.
- Sales/purchase document lines accept `item_description` as an alias for
  `description`, and a line with neither `description` nor `item_id` is rejected
  up front — no more orphan document headers.
- Document line fetches use the nested `/{id}/lines` route, fixing the JA011
  error on `get_*_document(include_lines=true)` and on draft refetch.
- v1 action endpoints send the correct `Content-Type`.

### Changed
- Extracted a shared `item_attributes` helper for products and services.

### Documentation
- `create_address` "já existe" idempotency quirk, draft customer-address
  denormalization, certified-series date constraint, the update cycle, and
  corrected token-lifetime notes.

## [0.1.0] - 2026-04-21

### Added
- Initial TOCOnline MCP server: OAuth login, customer and sales-document tools,
  purchases, and a generic `api_request` escape hatch.

[Unreleased]: https://github.com/themiguelamador/toconline-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/themiguelamador/toconline-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/themiguelamador/toconline-mcp/releases/tag/v0.1.0
