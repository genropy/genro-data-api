# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches its first stable release.

## [Unreleased]

### Security

- Route unhandled webpage exceptions through GenroPy `site.errorHandler`
  so response bodies no longer carry Python tracebacks. Clients now
  receive a generic 500 body with an opaque `ref` lookup id.

### Tests

- `apply_parser` coverage 80% → 99% via error-branch tests on
  grammar, aggregate/groupby malformed inputs, and helper utilities.
- `skiptoken` coverage 89% → 100% via non-UTF-8 payload and
  non-object JSON tests.
- `request_handler` `_json_default` serialiser now covered for
  `datetime`, `date`, `time`, `Decimal`, and generic fallback paths.
- Unused `ODataApplyParser._expect` helper removed.
- Global coverage 89% → 93% across 379 passing tests.

## [0.1.0.dev1] — 2026-04-24

First development snapshot containing the full OData v4 read-only
surface used by downstream BI clients.

### Added

- **Core protocol** (`DataApiBackend`, `QueryOptions`, `QueryResult`)
  defining the contract any data source must satisfy to be exposed
  over OData or GraphQL.
- **Type mapping** (`core/type_map.py`) from GenroPy dtype codes to
  OData `Edm.*` types and GraphQL scalars.
- **OData v4 read-only protocol layer**
  - `$metadata` CSDL 4.0 XML generation.
  - Request handler routing `$metadata`, entity sets, single entities,
    `$count`, and segment navigation paths.
  - `$filter` parser with comparison operators (`eq`, `ne`, `gt`,
    `ge`, `lt`, `le`, `in`), logical combinators (`and`, `or`, `not`),
    string functions (`contains`, `startswith`, `endswith`,
    `tolower`, `toupper`, `trim`, `length`, `indexof`, `substring`,
    `concat`), temporal functions (`year`, `month`, `day`, `hour`,
    `minute`, `second`, `date`, `now`), numeric functions (`round`,
    `floor`, `ceiling`), `cast` for type coercion, and
    lambda quantifiers `any` / `all` — including nested forms —
    compiled to `IN (subquery)` / `NOT IN` against the related table.
  - `$filter` navigation paths (`foo/bar/baz` → `@foo.bar.baz`).
  - `$select`, `$orderby`, `$top`, `$skip`, `$count`.
  - `$expand` with per-level options through `ExpandResolver`.
  - `$apply` transformations: `filter`, `groupby((keys), aggregate(...))`,
    standalone `aggregate(...)`, with methods `sum`, `average`, `min`,
    `max`, `countdistinct`, `$count`. Response shape follows the
    TripPin-verified `#EntitySet(col1,col2)` context pattern.
  - Server-driven pagination via opaque `$skiptoken` (v1: offset +
    SHA-256 filter hash for tamper detection).
  - `Prefer: odata.maxpagesize=N` honouring, echoed back as
    `Preference-Applied`.
  - CSDL annotations: `Core.Description`, `Capabilities.*`,
    `Computed`, `Aggregation.ApplySupported`.
  - `OData-Version`, `OData-MaxVersion` strict header enforcement.
  - JSON response formatter with `@odata.context`, `@odata.count`,
    `@odata.nextLink`, and structured error bodies.
- **Experimental GraphQL layer** (`graphql/`) sharing the same
  backend protocol.
- **ASGI and WSGI contrib packages** for server integration.

### Notes

- The package is released as a `0.1.0.dev1` pre-release; the public
  surface is considered stable for the OData subset listed above but
  may grow in backward-compatible ways before 1.0.
- `$skiptoken` payloads are opaque but not cryptographically signed.
  Downstream deployments that need HMAC protection can wrap the
  endpoint at the edge.
- The reference GenroPy adapter is tested against PostgreSQL only.
  Other backends are likely to work but unverified.

[Unreleased]: https://github.com/genropy/genro-data-api/compare/v0.1.0.dev1...HEAD
[0.1.0.dev1]: https://github.com/genropy/genro-data-api/releases/tag/v0.1.0.dev1
