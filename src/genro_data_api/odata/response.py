# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 JSON response formatter.

Formats QueryResult objects and entity dicts into OData v4 JSON payloads,
including @odata.context, @odata.count, and @odata.nextLink annotations.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from genro_data_api.core.backend import DataApiBackend, QueryResult
from genro_data_api.core.type_map import get_edm_type
from genro_data_api.odata import skiptoken as skiptoken_module


def _encode_query_component(value: str) -> str:
    """Percent-encode a query-string key or value, preserving typical OData chars."""
    # Keep ``$`` unescaped — every OData system param starts with it and
    # clients / URL tooling expect it verbatim. Everything else that would
    # break query parsing (``&``, ``=``, ``#``, space, etc.) gets encoded.
    return quote(value, safe="$=,()'/: ")


class ODataResponseFormatter:
    """Formats query results as OData v4 JSON payloads."""

    def format_collection(
        self,
        entity_name: str,
        result: QueryResult,
        context_url: str,
        skip: int | None = None,
        top: int | None = None,
        query_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Format a collection query result as OData v4 JSON.

        Args:
            entity_name: Name of the queried entity set.
            result: Backend query result with records and optional total_count.
            context_url: OData service root URL (e.g. "/odata").
            skip: Number of records skipped (used for nextLink computation).
            top: Page size requested (used for nextLink computation).
            query_params: Raw query parameters from the current request;
                needed to preserve $filter/$orderby in ``nextLink`` and to
                compute a stable ``filter_hash`` for the opaque skiptoken.

        Returns:
            Dict ready for JSON serialization, with @odata annotations.
        """
        payload: dict[str, Any] = {
            "@odata.context": f"{context_url}/$metadata#{entity_name}",
            "value": result.records,
        }
        if result.total_count is not None:
            payload["@odata.count"] = result.total_count

        next_link = self._compute_next_link(
            entity_name, context_url, result, skip, top, query_params
        )
        if next_link is not None:
            payload["@odata.nextLink"] = next_link

        return payload

    def format_apply_result(
        self,
        entity_name: str,
        result: QueryResult,
        context_url: str,
        apply_columns: list[str],
    ) -> dict[str, Any]:
        """Format an aggregated $apply result as OData v4 JSON.

        Shape matches the reference Microsoft TripPinRESTierService:
        ``@odata.context`` carries a projection clause ``#EntitySet(col1,col2)``
        and each row is tagged with ``@odata.id: null`` to signal that the
        aggregated row is not an addressable entity.
        """
        cols = ",".join(apply_columns)
        value = [{"@odata.id": None, **record} for record in result.records]
        payload: dict[str, Any] = {
            "@odata.context": f"{context_url}/$metadata#{entity_name}({cols})",
            "value": value,
        }
        if result.total_count is not None:
            payload["@odata.count"] = result.total_count
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
        query_params: dict[str, str] | None = None,
    ) -> str | None:
        if top is None or result.total_count is None:
            return None
        current_skip = skip or 0
        if current_skip + top >= result.total_count:
            return None
        next_skip = current_skip + top

        params = query_params or {}
        token = skiptoken_module.encode({
            "skip": next_skip,
            "top": top,
            "filter_hash": skiptoken_module.filter_hash(params),
        })

        # Preserve the filter-shaping parameters in the next link so the URL
        # stays self-describing. Pagination params ($top/$skip/$skiptoken)
        # are intentionally dropped — they live inside the opaque token.
        preserved: list[tuple[str, str]] = []
        for key in ("$filter", "$orderby", "$apply", "$select", "$expand"):
            if key in params:
                preserved.append((key, params[key]))
        preserved.append(("$skiptoken", token))

        query_string = "&".join(
            f"{_encode_query_component(k)}={_encode_query_component(v)}"
            for k, v in preserved
        )
        return f"{context_url}/{entity_name}?{query_string}"
