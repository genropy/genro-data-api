# genro-data-api

Standardized data API protocols for the [Genropy](https://www.genropy.org/) framework.

Exposes database data through industry-standard protocols, starting with
**OData v4** and with **GraphQL** available as an experimental layer.

## Key features

- **Server-agnostic**: works with WSGI (GenroPy) and can be wrapped in
  ASGI adapters.
- **Read-only by design**: safe exposure for reporting, BI tools,
  dashboards. No writes, no mutations.
- **Protocol-based backend**: any data source can implement the
  `DataApiBackend` protocol — the default adapter wraps GenroPy's
  `GnrSqlDb`, but third-party backends are possible.
- **Zero runtime dependencies** on GenroPy itself inside the core and
  OData packages. Only the reference adapter depends on GenroPy.
- **OData v4 compliant** surface: `$metadata`, `$filter` (with scalar
  functions and lambda quantifiers), `$select`, `$orderby`, `$top`,
  `$skip`, `$expand`, `$count`, `$apply` (groupby / aggregate),
  server-driven pagination via opaque `$skiptoken`.

## Architecture

```
                    GenroPy SQL (or any backend)
                              |
                    GnrSqlDataApiAdapter (or custom)
                              |
                 core/ (DataApiBackend protocol)
                              |
              +---------------+---------------+
              |                               |
          odata/                          graphql/
     (OData v4 protocol)          (experimental)
              |
    request_handler.py
    (method, path, params, headers)
                 -> (status, headers, body)
              |
     +--------+--------+
     |                  |
  WSGI wrapper      ASGI wrapper
  (GenroPy webpage) (external)
```

Detailed component notes in [docs/architecture.md](docs/architecture.md).

## Installation

```bash
pip install genro-data-api
```

For the GenroPy integration, install the `data_api` package
(from the Softwell gnrdbextra repository) which provides the adapter
and the webpage layer.

## Quickstart

The library needs a backend object that satisfies the
`DataApiBackend` protocol and an `ODataRequestHandler` in front of it.
Minimal WSGI-agnostic snippet:

```python
from genro_data_api.odata import ODataRequestHandler
from genro_data_api.core.backend import DataApiBackend

class MyBackend:
    def entity_sets(self): ...
    def entity_metadata(self, name): ...
    def query(self, name, options): ...
    def get_entity(self, name, key): ...

backend: DataApiBackend = MyBackend()
handler = ODataRequestHandler(backend, service_root="/odata")

status, headers, body = handler.handle(
    method="GET",
    path="/odata/customer",
    query_params={"$filter": "country eq 'IT'", "$top": "50"},
    request_headers={"Accept": "application/json"},
)
```

With GenroPy the pattern above is already wrapped by a webpage; see
the `data_api` package in `gnrdbextra` for the full integration.

## OData feature coverage

All clauses below are implemented and covered by unit tests
(379 tests green, 93% global coverage).

| Feature                  | Scope                                                                |
|--------------------------|----------------------------------------------------------------------|
| `$metadata`              | CSDL 4.0 XML with `Core.Description`, `Capabilities.*`, `Computed`  |
| `$filter` comparisons    | `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `in`                            |
| `$filter` logicals       | `and`, `or`, `not` (with proper precedence)                         |
| `$filter` functions      | `contains`, `startswith`, `endswith`                                 |
| `$filter` scalar fns     | `tolower`, `toupper`, `trim`, `length`, `indexof`, `substring`,      |
|                          | `concat`, `year`, `month`, `day`, `hour`, `minute`, `second`,        |
|                          | `date`, `now`, `round`, `floor`, `ceiling`, `cast`                   |
| `$filter` lambdas        | `Nav/any(v: body)` and `Nav/all(v: body)`, including nested forms    |
| `$filter` navigation     | `@rel.col` paths (many-to-one) and `Nav/any` (one-to-many)          |
| `$orderby`               | multi-column with `asc`/`desc`                                      |
| `$select`                | property projection (forbidden columns are stripped)                |
| `$top` / `$skip`         | classic paging                                                      |
| `$skiptoken`             | opaque server-driven pagination (v1: offset + filter-hash tamper    |
|                          | detection). Transparent future upgrade path to keyset pagination.   |
| `Prefer: odata.maxpagesize` | server caps page size; echoed back as `Preference-Applied`       |
| `$expand`                | nested collection expansion with per-level options                  |
| `$count`                 | inline `$count=true` and standalone `/Entity/$count`                |
| `$apply`                 | `filter(...)`, `groupby((keys), aggregate(...))`, `aggregate(...)`, |
|                          | methods: `sum`, `average`, `min`, `max`, `countdistinct`, `$count`  |
| Navigation segments      | `/Entity(key)/property`, `/Entity(key)/Nav`, `/Entity(key)/Nav/$count` |
| Headers                  | `OData-Version`, `OData-MaxVersion`, `Content-Type` negotiation     |
| Format                   | JSON (default). XML accepted only on `$metadata`                    |

The current **deliberately out-of-scope** OData v4 features are
`$search`, `$compute`, `$levels`, ETag / `If-Match`, `$batch`,
arithmetic operators in `$filter`, and residual `Prefer` tokens.
They can be added when a downstream client needs them.

## OData v4 compliance notes

The implementation targets the subset needed by BI clients (Power BI,
Excel, Tableau) and is intentionally not a full OData v4 server.
Known deviations from the specification:

- **`$orderby` does not accept scalar function calls.** Sorting uses
  bare column names plus an optional `asc` / `desc`. Sorting by a
  computed expression (`year(date) desc`, `length(name)`) is
  achieved by materialising the value in a `$apply` step and sorting
  on its alias:

  ```
  ?$apply=aggregate(...)&$orderby=Revenue desc
  ```

  The same scalar functions remain fully usable inside `$filter`.

- **`OData-EntityId` response header is not emitted.** The spec
  suggests it on single-entity responses to advertise the canonical
  URL; clients can derive it from `@odata.id` or from the request
  URL.

- **`@odata.type` inline annotation is not emitted.** The current
  CSDL has no entity inheritance, so every row in a given entity set
  has a single static type already declared in `$metadata`. The
  annotation would be redundant.

## Request examples

```
GET /odata/customer
GET /odata/customer?$filter=country eq 'IT'
GET /odata/customer?$filter=contains(name, 'Corp')
GET /odata/customer?$filter=year(birth_date) eq 1980
GET /odata/customer?$filter=Orders/any(o: o/amount gt 2000)
GET /odata/customer?$orderby=name asc&$top=50
GET /odata/customer/$count?$filter=active eq true
GET /odata/customer(123)/Orders
GET /odata/customer?$apply=groupby((country),aggregate($count as N))
GET /odata/customer?$apply=aggregate(amount with sum as Revenue)
GET /odata/$metadata
```

## Security

The stack layers three independent defences against **SQL injection**
through user input:

1. **Identifier whitelist** — the `$apply` parser validates all
   column and alias tokens against `^[A-Za-z_][A-Za-z0-9_]*$` before
   they can reach the adapter.
2. **Parametric binding** — every literal in `$filter` is bound as a
   named parameter; literal concatenation is never used for values.
3. **Backend-driven resolution** — the GenroPy adapter passes column
   references as `$name` / `@rel.name` tokens that GenroPy resolves
   against its own metadata. Unknown identifiers raise a column
   resolution error before any SQL is compiled.

Unhandled exceptions are routed through GenroPy's `site.errorHandler`,
which logs the full context to `sys.error` and returns an opaque
`error_id` to the client. Response bodies never contain tracebacks,
internal paths, or SQL text.

### Pagination token

`$skiptoken` values are opaque `base64url(json)` payloads. They carry
the current offset together with a SHA-256 digest of the
`$filter` / `$orderby` / `$apply` that produced the result set. If the
client alters those parameters and reuses a stale token, the server
detects the mismatch and refuses the request with a 400 rather than
returning inconsistent rows. The token format is designed to migrate
to keyset pagination without breaking existing clients — they just
keep round-tripping whatever `@odata.nextLink` is returned.

The token is **not signed**. Forging or mutating a token only lets a
client jump to an arbitrary offset of a result set that is already
subject to normal permission filtering and row-level access control,
so HMAC protection was judged unnecessary for the targeted BI use
case. Deployments that need stricter guarantees can add an HMAC layer
on the edge.

### Permissions

When the adapter is instantiated with a `group_code`, it reads
GenroPy's per-group `user_config` rules and applies them transparently:

- Tables flagged `hidden` are excluded from `$metadata` and from the
  service document, and requests that target them by name respond
  with 404 — the same response as an unknown table.
- Columns flagged `forbidden` or `blurred` are stripped from the
  metadata of their entity set and scrubbed from query results,
  including `$select` projections.

## Tested database backends

The OData parsers and handlers are database-agnostic and exercised
end-to-end in the unit suite using an in-memory mock backend.

The reference GenroPy adapter (`GnrSqlDataApiAdapter`) is developed
and tested against **PostgreSQL**. Other GenroPy backends are likely
to work but have not been verified; support for them is best-effort
until a CI matrix is in place.

## Ecosystem

Part of the [Genro Modules](https://github.com/softwellsrl/meta-genro-modules)
ecosystem:

- **genro-bag**: XML serialization for CSDL metadata generation
- **genro-toolbox**: SmartOptions for adapter configuration
- **genro-tytx**: typed serialization for query results

## Project status

The OData v4 surface documented above is implemented, test-covered,
and in active use for BI scenarios. The GraphQL layer is an
experimental companion and is not part of the stability guarantees.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

Copyright 2025 Softwell S.r.l.
