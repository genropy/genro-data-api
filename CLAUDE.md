# Claude Code Instructions - genro-data-api

**Parent Document**: This project follows all policies from the central [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)

## Project-Specific Context

### Current Status
- Development Status: Pre-Alpha
- Has Implementation: No (scaffolding only)

### Project Description
Standardized data API protocols for the Genropy framework. Exposes database
data through industry-standard protocols (OData v4 initially, GraphQL planned)
via a server-agnostic request handler.

### Architecture
- `core/` — Protocol definitions, query options, type mappings (shared by all protocols)
- `odata/` — OData v4 implementation (CSDL renderer, filter parser, request handler)
- Future: `graphql/` — GraphQL implementation

### Key Design Decisions
- **Read-only initially**: no insert/update/delete support
- **Server-agnostic**: request handler works with plain (method, path, params) tuples
- **Zero core dependencies**: Protocol-based, no imports from GenroPy in core
- **Reuses OrmExtractor**: model metadata comes from GenroPy migration JSON struct

---

**All general policies are inherited from the parent document.**
