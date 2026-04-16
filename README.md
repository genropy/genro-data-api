# genro-data-api

Standardized data API protocols for the [Genropy](https://www.genropy.org/) framework.

Exposes database data through industry-standard protocols, starting with
**OData v4** and with **GraphQL** planned for the future.

## Key Features

- **Server-agnostic**: works with WSGI (GenroPy current) and ASGI (genro-asgi)
- **Read-only by design**: safe exposure of data for reporting, BI tools, dashboards
- **Protocol-based backend**: any data source can implement the backend protocol
- **Zero core dependencies**: the protocol and handlers are pure Python
- **OData v4 compliant**: `$metadata`, `$filter`, `$select`, `$orderby`, `$top/$skip`, `$expand`, `$count`

## Architecture

```
                    GenroPy SQL (or any backend)
                              |
                    OrmExtractor (model extraction)
                              |
                    JSON struct (normalized)
                              |
                 core/ (Protocol + QueryOptions)
                              |
              +---------------+---------------+
              |                               |
          odata/                          graphql/
     (OData v4 protocol)              (future)
              |
    request_handler.py
    (method, path, params) -> (status, headers, body)
              |
     +--------+--------+
     |                  |
  WSGI wrapper      ASGI wrapper
  (GenroPy now)     (genro-asgi)
```

## Installation

```bash
pip install genro-data-api
```

## Development Status

**Pre-Alpha** — project scaffolding, architecture defined, implementation pending.

## Ecosystem Integration

Part of the [Genro Modules](https://github.com/softwellsrl/meta-genro-modules) ecosystem:

- **genro-bag**: XML serialization for CSDL metadata generation
- **genro-toolbox**: SmartOptions for adapter configuration
- **genro-tytx**: typed serialization for query results
- **genro-builders**: potential CsdlBuilder for validated CSDL generation

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

Copyright 2025 Softwell S.r.l.
