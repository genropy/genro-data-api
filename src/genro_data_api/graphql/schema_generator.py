# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""GraphQL schema generator for genro-data-api.

Builds a read-only GraphQL schema from a DataApiBackend.
Creates one ObjectType per entity and a root Query type with
collection and byKey fields for each entity.
"""

from __future__ import annotations

import re
from typing import Any

from graphql import (
    GraphQLArgument,
    GraphQLBoolean,
    GraphQLField,
    GraphQLFloat,
    GraphQLInt,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLString,
)

from genro_data_api.core.backend import DataApiBackend, QueryOptions
from genro_data_api.core.type_map import get_graphql_type

_SCALAR_MAP: dict[str, GraphQLScalarType] = {
    "String": GraphQLString,
    "Int": GraphQLInt,
    "Float": GraphQLFloat,
    "Boolean": GraphQLBoolean,
}


class GraphQLSchemaGenerator:
    """Builds a read-only GraphQL schema from a DataApiBackend.

    Usage::

        gen = GraphQLSchemaGenerator()
        schema = gen.generate(backend)
    """

    def generate(self, backend: DataApiBackend) -> GraphQLSchema:
        """Build and return a GraphQLSchema from the backend.

        Args:
            backend: Data source implementing DataApiBackend.

        Returns:
            Read-only GraphQL schema with one type per entity and
            collection/byKey query fields.
        """
        entity_sets = backend.entity_sets()
        meta_by_name = {es["name"]: backend.entity_metadata(es["name"]) for es in entity_sets}
        types_by_name: dict[str, GraphQLObjectType] = {}

        for entity_name, meta in meta_by_name.items():
            types_by_name[entity_name] = self._make_entity_type(
                entity_name, meta, types_by_name, backend
            )

        query_fields: dict[str, GraphQLField] = {}
        for entity_name in meta_by_name:
            entity_type = types_by_name[entity_name]
            field_name = self._field_name(entity_name)
            query_fields[field_name] = self._make_collection_field(entity_name, entity_type, backend)
            query_fields[f"{field_name}_byKey"] = self._make_bykey_field(
                entity_name, entity_type, backend
            )

        return GraphQLSchema(query=GraphQLObjectType("Query", query_fields))

    def _type_name(self, entity_name: str) -> str:
        """Convert entity name to GraphQL PascalCase type name."""
        parts = re.split(r"[.\-_]", entity_name)
        return "".join(p.capitalize() for p in parts if p)

    def _field_name(self, entity_name: str) -> str:
        """Convert entity name to snake_case GraphQL field name."""
        return re.sub(r"[.\-]", "_", entity_name)

    def _scalar_for_prop(self, prop: dict[str, Any]) -> GraphQLScalarType | GraphQLNonNull:
        """Get the GraphQL scalar type for a property dict."""
        gnr_type = prop.get("type", "A")
        graphql_type_name = get_graphql_type(gnr_type, fallback="String")
        scalar = _SCALAR_MAP.get(graphql_type_name, GraphQLString)
        if prop.get("nullable", True):
            return scalar
        return GraphQLNonNull(scalar)

    def _make_entity_type(
        self,
        entity_name: str,
        meta: dict[str, Any],
        types_by_name: dict[str, GraphQLObjectType],
        backend: DataApiBackend,
    ) -> GraphQLObjectType:
        """Build a GraphQLObjectType for an entity using a thunk for fields.

        The thunk (callable) defers field construction until schema build time,
        which allows forward references between entity types (navigation).
        """
        type_name = self._type_name(entity_name)

        def fields() -> dict[str, GraphQLField]:
            result: dict[str, GraphQLField] = {}
            for prop in meta.get("properties", []):
                result[prop["name"]] = GraphQLField(self._scalar_for_prop(prop))
            for nav in meta.get("navigation", []):
                target = nav["target"]
                target_type = types_by_name.get(target)
                if target_type is None:
                    continue
                is_collection = nav.get("collection", False)
                if is_collection:
                    nav_gql_type: Any = GraphQLList(GraphQLNonNull(target_type))
                else:
                    nav_gql_type = target_type
                nav_name = nav["name"]
                resolver = self._make_nav_resolver(nav_name, is_collection)
                result[nav_name] = GraphQLField(nav_gql_type, resolve=resolver)
            return result

        return GraphQLObjectType(type_name, fields)

    def _make_nav_resolver(self, nav_name: str, is_collection: bool) -> Any:
        """Create a resolver for a navigation property.

        Returns pre-fetched nav data if already present in the parent record
        (populated by a backend expand), otherwise returns [] or None.
        """

        def resolver(root: dict[str, Any], info: Any) -> Any:
            if nav_name in root:
                return root[nav_name]
            return [] if is_collection else None

        return resolver

    def _make_collection_field(
        self,
        entity_name: str,
        entity_type: GraphQLObjectType,
        backend: DataApiBackend,
    ) -> GraphQLField:
        """Build the collection query field for an entity."""

        def resolver(root: Any, info: Any, **kwargs: Any) -> list[dict[str, Any]]:
            opts = self._build_query_options(kwargs)
            result = backend.query(entity_name, opts)
            return result.records

        return GraphQLField(
            GraphQLList(GraphQLNonNull(entity_type)),
            args={
                "top": GraphQLArgument(GraphQLInt),
                "skip": GraphQLArgument(GraphQLInt),
                "filter": GraphQLArgument(GraphQLString),
                "orderby": GraphQLArgument(GraphQLString),
                "count": GraphQLArgument(GraphQLBoolean),
            },
            resolve=resolver,
        )

    def _make_bykey_field(
        self,
        entity_name: str,
        entity_type: GraphQLObjectType,
        backend: DataApiBackend,
    ) -> GraphQLField:
        """Build the byKey query field for single-entity lookup."""

        def resolver(root: Any, info: Any, **kwargs: Any) -> dict[str, Any] | None:
            key = kwargs.get("key")
            return backend.get_entity(entity_name, key)

        return GraphQLField(
            entity_type,
            args={"key": GraphQLArgument(GraphQLNonNull(GraphQLString))},
            resolve=resolver,
        )

    def _build_query_options(self, kwargs: dict[str, Any]) -> QueryOptions:
        """Build QueryOptions from GraphQL argument dict."""
        opts = QueryOptions(
            top=kwargs.get("top"),
            skip=kwargs.get("skip"),
            filter_expr=kwargs.get("filter"),
            count=bool(kwargs.get("count", False)),
        )
        orderby = kwargs.get("orderby")
        if orderby:
            opts.order_by = self._parse_orderby(orderby)
        return opts

    def _parse_orderby(self, orderby_str: str) -> list[tuple[str, str]]:
        """Parse 'name asc, age desc' into [('name', 'asc'), ('age', 'desc')]."""
        result: list[tuple[str, str]] = []
        for item in orderby_str.split(","):
            parts = item.strip().split()
            if len(parts) == 1:
                result.append((parts[0], "asc"))
            elif len(parts) == 2:
                direction = parts[1].lower()
                if direction not in ("asc", "desc"):
                    raise ValueError(f"Invalid orderby direction: {parts[1]!r}")
                result.append((parts[0], direction))
        return result
