# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Backend protocol and data structures for genro-data-api.

Defines the contract that any data source must implement to be
exposed through OData, GraphQL, or other protocols. The protocol
is read-only by design; write operations will be added as an
optional extension.

The data structures (QueryOptions, QueryResult) use plain Python
types with no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DataApiBackend(Protocol):
    """Contract for data sources exposed via genro-data-api.

    Any object implementing these four methods can serve as a backend
    for OData, GraphQL, or other protocol handlers. The backend knows
    how to describe its entities and how to query them; it knows nothing
    about HTTP or protocol-specific serialization.
    """

    def entity_sets(self) -> list[dict[str, Any]]:
        """List available entity sets (tables/collections).

        Returns:
            List of dicts, each with at least 'name' and optionally
            'title', 'description'.
            Example: [{'name': 'pkg.customer', 'title': 'Customers'}]
        """
        ...

    def entity_metadata(self, entity_name: str) -> dict[str, Any]:
        """Describe the structure of a single entity set.

        Returns:
            Dict with:
            - 'name': entity name
            - 'key': list of primary key property names
            - 'properties': list of property dicts with 'name', 'type',
              'nullable', and optional 'maxLength', 'precision', 'scale'
            - 'navigation': list of navigation property dicts with
              'name', 'target', 'collection' (bool)
        """
        ...

    def query(self, entity_name: str, options: QueryOptions) -> QueryResult:
        """Query an entity set with structured options.

        Args:
            entity_name: Fully qualified entity name (e.g. 'pkg.customer').
            options: Structured query parameters.

        Returns:
            QueryResult with records and optional total count.
        """
        ...

    def get_entity(self, entity_name: str, key: Any) -> dict[str, Any] | None:
        """Fetch a single entity by primary key.

        Args:
            entity_name: Fully qualified entity name.
            key: Primary key value (string, int, or composite dict).

        Returns:
            Entity as dict, or None if not found.
        """
        ...


@dataclass
class QueryOptions:
    """Structured query parameters, protocol-agnostic.

    These are the parsed, validated parameters that a protocol handler
    (OData, GraphQL) passes to the backend. The backend translates them
    to native query operations.
    """

    select: list[str] | None = None
    """Property names to include. None means all properties."""

    filter_expr: str | None = None
    """Raw filter expression from the protocol (e.g. OData $filter string).
    The backend is responsible for parsing this into native query syntax."""

    order_by: list[tuple[str, str]] | None = None
    """Sort directives as (property_name, direction) tuples.
    Direction is 'asc' or 'desc'."""

    top: int | None = None
    """Maximum number of records to return."""

    skip: int | None = None
    """Number of records to skip (for pagination)."""

    count: bool = False
    """If True, include total record count in the result."""

    expand: dict[str, QueryOptions] | None = None
    """Navigation properties to expand, each with optional nested options."""


@dataclass
class QueryResult:
    """Result of a backend query.

    Contains the records and optional metadata about the result set.
    """

    records: list[dict[str, Any]] = field(default_factory=list)
    """List of entity records as dicts."""

    total_count: int | None = None
    """Total number of matching records (only set when count=True in options)."""
