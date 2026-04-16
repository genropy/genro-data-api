# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 JSON response formatter.

Formats QueryResult objects and entity dicts into OData v4 JSON payloads,
including @odata.context, @odata.count, and @odata.nextLink annotations.
"""

from __future__ import annotations

from typing import Any

from genro_data_api.core.backend import DataApiBackend, QueryResult
from genro_data_api.core.type_map import get_edm_type


class ODataResponseFormatter:
    """Formats query results as OData v4 JSON payloads."""

    def format_collection(
        self,
        entity_name: str,
        result: QueryResult,
        context_url: str,
        skip: int | None = None,
        top: int | None = None,
    ) -> dict[str, Any]:
        """Format a collection query result as OData v4 JSON.

        Args:
            entity_name: Name of the queried entity set.
            result: Backend query result with records and optional total_count.
            context_url: OData service root URL (e.g. "/odata").
            skip: Number of records skipped (used for nextLink computation).
            top: Page size requested (used for nextLink computation).

        Returns:
            Dict ready for JSON serialization, with @odata annotations.
        """
        payload: dict[str, Any] = {
            "@odata.context": f"{context_url}/$metadata#{entity_name}",
            "value": result.records,
        }
        if result.total_count is not None:
            payload["@odata.count"] = result.total_count

        next_link = self._compute_next_link(entity_name, context_url, result, skip, top)
        if next_link is not None:
            payload["@odata.nextLink"] = next_link

        return payload

    def format_entity(
        self,
        entity_name: str,
        record: dict[str, Any],
        context_url: str,
    ) -> dict[str, Any]:
        """Format a single entity as OData v4 JSON.

        Args:
            entity_name: Name of the entity set.
            record: Entity data as a plain dict.
            context_url: OData service root URL.

        Returns:
            Dict with @odata.context annotation and all record fields.
        """
        return {
            "@odata.context": f"{context_url}/$metadata#{entity_name}/$entity",
            **record,
        }

    def format_metadata_json(self, backend: DataApiBackend) -> dict[str, Any]:
        """Return a simplified JSON representation of the service metadata.

        This is a minimal JSON CSDL document (not the full JSON CSDL spec).
        Use CsdlRenderer for the authoritative XML $metadata endpoint.

        Args:
            backend: Data backend providing entity sets and metadata.

        Returns:
            Dict with $version and basic entity type information.
        """
        entity_types: dict[str, Any] = {}
        entity_container: dict[str, Any] = {"$Kind": "EntityContainer"}

        for entity_set in backend.entity_sets():
            name = entity_set["name"]
            meta = backend.entity_metadata(name)
            type_def: dict[str, Any] = {"$Kind": "EntityType"}

            key = meta.get("key", [])
            if key:
                type_def["$Key"] = key

            props: dict[str, Any] = {}
            for prop in meta.get("properties", []):
                prop_def: dict[str, Any] = {
                    "$Type": get_edm_type(prop.get("type", "A")),
                    "$Nullable": prop.get("nullable", True),
                }
                if "maxLength" in prop:
                    prop_def["$MaxLength"] = prop["maxLength"]
                props[prop["name"]] = prop_def
            type_def["$Properties"] = props

            entity_types[f"Default.{name}"] = type_def
            entity_container[name] = {
                "$Collection": True,
                "$Type": f"Default.{name}",
            }

        return {
            "$Version": "4.0",
            "$EntityContainer": "Default.DefaultContainer",
            "Default.DefaultContainer": entity_container,
            **entity_types,
        }

    def _compute_next_link(
        self,
        entity_name: str,
        context_url: str,
        result: QueryResult,
        skip: int | None,
        top: int | None,
    ) -> str | None:
        if top is None or result.total_count is None:
            return None
        current_skip = skip or 0
        if current_skip + top >= result.total_count:
            return None
        next_skip = current_skip + top
        return f"{context_url}/{entity_name}?$top={top}&$skip={next_skip}"
