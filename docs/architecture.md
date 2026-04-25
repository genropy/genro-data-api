# Architecture

## Design goals

1. **Server-agnostic request handler** — the core entry point accepts
   `(method, path, query_params, request_headers)` and returns
   `(status, headers, body)`. Any transport (WSGI, ASGI, test harness)
   can drive it.

2. **Protocol-extensible** — the OData v4 implementation is isolated
   under `odata/`. A sibling GraphQL implementation lives under
   `graphql/` and shares the same backend protocol (experimental).

3. **Read-only first** — the backend protocol intentionally exposes
   only `entity_sets`, `entity_metadata`, `query`, `get_entity`.
   Write operations are a future opt-in that does not change the
   existing surface.

4. **Zero runtime dependencies in the core** — the `core/` and
   `odata/` packages use only the Python standard library. Backend
   adapters (e.g. the GenroPy one) live outside this repository and
   can pull in framework-specific dependencies without polluting the
   core.

## Package layout

```
genro_data_api/
├── core/
│   ├── backend.py         DataApiBackend Protocol, QueryOptions, QueryResult
│   └── type_map.py        GenroPy dtype → Edm / GraphQL type translation
├── odata/
│   ├── request_handler.py Dispatch, content negotiation, error mapping
│   ├── apply_parser.py    $apply pipeline parser (filter / groupby / aggregate)
│   ├── filter_parser.py   $filter recursive-descent parser with lambdas
│   ├── expand_resolver.py $expand nested query resolution
│   ├── csdl_renderer.py   CSDL 4.0 XML generation from entity_metadata
│   ├── response.py        JSON formatter, @odata.* annotations
│   └── skiptoken.py       Opaque server-driven pagination token v1
└── graphql/               Experimental GraphQL surface (schema + resolver)
```

## Request flow

```
HTTP request
    │
    ▼
ODataRequestHandler.handle(method, path, query_params, request_headers)
    │
    ├── GET /$metadata
    │       └── csdl_renderer.render(backend) → CSDL XML
    │
    ├── GET /$metadata?$format=json   → 406 (JSON CSDL not supported)
    ├── POST / PATCH / DELETE          → 405 (read-only)
    │
    ├── GET /EntitySet
    │       ├── _build_query_options: parse $filter, $apply, $orderby, $top, $skip
    │       ├── _apply_prefer_maxpagesize: clamp to Prefer: odata.maxpagesize=N
    │       ├── _resolve_skiptoken: decode token, verify filter_hash
    │       ├── backend.query(entity, options)
    │       └── response.format_collection(result)   → JSON + @odata.nextLink?
    │
    ├── GET /EntitySet/$count          → backend.query + records.length
    │
    ├── GET /EntitySet(key)
    │       ├── backend.get_entity(entity, key)
    │       └── response.format_entity(result)
    │
    ├── GET /EntitySet(key)/segment
    │       ├── property  → scalar value
    │       ├── single Nav (many-to-one) → single entity
    │       └── collection Nav (one-to-many) → collection via FK-filtered query
    │
    └── GET /EntitySet(key)/Nav/$count → _handle_count on the filtered subset
```

Errors inside the handler are converted to standard OData error
bodies (`{"error": {"code": "...", "message": "..."}}`). Unhandled
exceptions in the webpage wrapper are routed to the GenroPy
`site.errorHandler` which returns an opaque `error_id`; the response
body never contains a traceback.

## Backend protocol

```python
class DataApiBackend(Protocol):
    def entity_sets(self) -> list[dict]: ...
    def entity_metadata(self, entity_name: str) -> dict: ...
    def query(self, entity_name: str, options: QueryOptions) -> QueryResult: ...
    def get_entity(self, entity_name: str, key: Any) -> dict | None: ...
```

`QueryOptions` is a dataclass carrying the parsed query parameters
(`select`, `filter_expr`, `order_by`, `top`, `skip`, `count`,
`expand`, `apply`). The backend translates them into its native
query language; it is not exposed to the raw URL.

The reference adapter `GnrSqlDataApiAdapter` (in the `data_api`
GenroPy package) wraps a `GnrSqlDb` instance. Permission filtering
(hidden tables, forbidden columns) and localisation resolution are
handled inside the adapter — the request handler sees only a backend
that already honours them.

## `$filter` parsing

`filter_parser.py` is a recursive-descent parser that produces a
`FilterNode` tree. The adapter walks the tree in
`_filter_node_to_gnr` and emits GenroPy `where` fragments with
parametric bindings.

Supported constructs:

- Comparisons `eq / ne / gt / ge / lt / le / in` on columns,
  scalar-function results, or literals.
- Logical combinators `and / or / not` with OData precedence.
- Boolean functions `contains / startswith / endswith` that compile
  to `ILIKE`.
- Scalar functions: string (`tolower`, `toupper`, `trim`, `length`,
  `indexof`, `substring`, `concat`), temporal (`year`, `month`,
  `day`, `hour`, `minute`, `second`, `date`, `now`), numeric
  (`round`, `floor`, `ceiling`), and type casting (`cast`).
- Lambda quantifiers `Nav/any(v: body)` and `Nav/all(v: body)`,
  compiled to `$fk IN (SELECT ... FROM related WHERE body)` and
  `NOT IN` respectively. Nested lambdas are supported.
- Navigation paths `foo/bar/baz` that map to GenroPy's
  `@foo.bar.baz` column reference syntax.

## `$apply` parsing

`apply_parser.py` accepts the OData v4 `$apply` transformation
pipeline. Grammar (simplified):

```
pipeline  := step ('/' step)*
step      := filter_step | groupby_step | aggregate_step
filter_step    := 'filter' '(' <body> ')'
groupby_step   := 'groupby' '(' '(' key (',' key)* ')'
                           (',' aggregate_step)? ')'
aggregate_step := 'aggregate' '(' entry (',' entry)* ')'
entry     := column 'with' method 'as' alias
           | '$count' 'as' alias
method    := 'sum' | 'average' | 'min' | 'max' | 'countdistinct'
```

Column and alias tokens are validated by `_is_identifier`
(`^[A-Za-z_][A-Za-z0-9_]*$`) before they can reach the adapter,
which is a key SQL injection defence layer (see the README).

## `$expand` and segment navigation

`expand_resolver.py` handles the nested `$expand=Nav($filter=...,$select=...)`
shape by recursively calling `backend.query` on each navigation
target and attaching the results under the parent record.

Segment navigation paths like `/Customer(1)/Orders` are expanded by
the request handler directly (not via `$expand`) into a
collection-style query against the child table, using the FK
relation to filter. This bypasses the cartesian-product trap that
column-path navigation would hit when crossing a one-to-many
relation (see the README for context).

## Pagination

Clients drive pagination through `@odata.nextLink` values. The
server emits an opaque `$skiptoken` rather than exposing `$skip` /
`$top`. The current token version (v1) encodes `skip`, `top`, and a
16-character SHA-256 digest of the `$filter` / `$orderby` / `$apply`
combination that produced the first page; the decoder refuses the
token if the digest no longer matches the incoming request.

The page size is either the client-requested `Prefer:
odata.maxpagesize=N` (capped at a server maximum) or the server
default. When a preference is applied, the response carries
`Preference-Applied: odata.maxpagesize=N`.

Future versions of the token can switch to keyset pagination (last
seen primary key) or to a GenroPy frozen result-set id without
breaking clients, because the contract they see is "round-trip the
token string verbatim".

## Type mapping

| GenroPy dtype | OData Edm type     | Python type |
|---------------|--------------------|-------------|
| `A` text      | `Edm.String`       | `str`       |
| `T` long text | `Edm.String`       | `str`       |
| `C` char      | `Edm.String`       | `str`       |
| `N` numeric   | `Edm.Decimal`      | `Decimal`   |
| `I` int32     | `Edm.Int32`        | `int`       |
| `L` int64     | `Edm.Int64`        | `int`       |
| `R` float     | `Edm.Double`       | `float`     |
| `B` boolean   | `Edm.Boolean`      | `bool`      |
| `D` date      | `Edm.Date`         | `date`      |
| `DH` datetime | `Edm.DateTimeOffset` | `datetime` |
| `H` time      | `Edm.TimeOfDay`    | `time`      |
| `X` xml/bag   | `Edm.String`       | `str`       |

The mapping is defined once in `core/type_map.py` and reused by the
CSDL renderer, the JSON formatter, and the GraphQL schema generator.

## Permissions

When instantiated with a `group_code`, the GenroPy adapter reads
`adm.user_config` entries for that group and transparently applies
them:

- Tables with `tbl_permission=hidden` are removed from
  `entity_sets()` and, by consequence, from the CSDL output and the
  service document. Requests that target them by name receive the
  same 404 as unknown entities.
- Columns flagged `forbidden` or `blurred` are stripped from
  `entity_metadata()` and scrubbed from `query()` results, even if
  explicitly named in `$select`.

## Testing strategy

Unit tests use an in-memory `MockBackend` that implements the
`DataApiBackend` protocol; this exercises the handler, parsers, and
response formatter without a database. The GenroPy adapter is
integration-tested against PostgreSQL using a fixture instance
(`test_invoice_pg`).

Coverage targets: ≥95% on parser modules, ≥90% global. Defensive
branches unreachable from the public API are marked
`# pragma: no cover`.
