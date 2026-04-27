# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 request handler — server-agnostic HTTP dispatcher.

Receives (method, path, query_params) and returns (status, headers, body).
Routes OData v4 GET requests to the appropriate backend operations.
Write operations (POST, PATCH, DELETE) return 405 Method Not Allowed.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from typing import Any

from genro_data_api.core.backend import DataApiBackend, QueryOptions
from genro_data_api.odata import skiptoken as skiptoken_module
from genro_data_api.odata.apply_parser import ODataApplyParser
from genro_data_api.odata.csdl_renderer import CsdlRenderer
from genro_data_api.odata.expand_resolver import ExpandResolver
from genro_data_api.odata.filter_parser import ODataFilterParser
from genro_data_api.odata.response import ODataResponseFormatter

_JSON_CT = "application/json;charset=UTF-8"
_XML_CT = "application/xml"
_TEXT_CT = "text/plain"

_ODATA_VERSION = "4.0"


def _json_default(obj: object) -> str | float:
    """JSON serializer for types not handled by stdlib json."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, datetime.time):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _dumps(obj: object) -> str:
    """JSON serialize with OData-safe type handling."""
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


def _parse_path(relative: str) -> list[dict[str, Any]] | None:
    """Split an entity path into typed steps.

    Accepts paths shaped like::

        /Entity
        /Entity(key)
        /Entity(key)/segment
        /Entity(key)/segment/$value
        /Entity(key)/rel/$count
        /Entity/$count

    The returned list is empty on the root path ("/" or ""). ``None`` is
    returned for malformed paths (unbalanced parens, empty segments,
    invalid key formats).

    Step kinds:
        entity_set  — always the first step; ``name`` carries the name
        key         — optional second step; ``value`` is int | str
        segment     — any intermediate or terminal property / navigation
        value       — ``$value`` terminator (raw content)
        count       — ``$count`` terminator (plain integer)
    """
    if relative in ("", "/"):
        return []
    if not relative.startswith("/"):
        return None
    raw_segments = relative[1:].split("/")
    if any(s == "" for s in raw_segments):
        return None

    steps: list[dict[str, Any]] = []
    first = raw_segments[0]
    entity_name, key_literal = _split_key(first)
    if entity_name is None:
        return None
    steps.append({"kind": "entity_set", "name": entity_name})
    if key_literal is not None:
        parsed_key = _parse_key_literal(key_literal)
        if parsed_key is None:
            return None
        steps.append({"kind": "key", "value": parsed_key})

    for seg in raw_segments[1:]:
        if seg == "$value":
            steps.append({"kind": "value"})
        elif seg == "$count":
            steps.append({"kind": "count"})
        else:
            if "(" in seg or ")" in seg:
                return None
            steps.append({"kind": "segment", "name": seg})

    return steps


def _split_key(segment: str) -> tuple[str | None, str | None]:
    """Split ``Entity`` or ``Entity(key)`` into (name, key_literal_or_None)."""
    if "(" not in segment:
        if ")" in segment:
            return None, None
        return segment, None
    if not segment.endswith(")"):
        return None, None
    name, _, rest = segment.partition("(")
    if not name:
        return None, None
    key_literal = rest[:-1]
    if "(" in key_literal or ")" in key_literal:
        return None, None
    return name, key_literal


def _parse_key_literal(literal: str) -> int | str | None:
    """Parse a key literal: numeric (``42``) or quoted string (``'ABC'``).

    Returns None for unsupported formats (composite keys, unbalanced quotes,
    empty literals).
    """
    stripped = literal.strip()
    if not stripped:
        return None
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        return stripped[1:-1]
    try:
        return int(stripped)
    except ValueError:
        return None


class ODataRequestHandler:
    """Server-agnostic OData v4 request dispatcher.

    Usage::

        handler = ODataRequestHandler(backend, service_root="/odata")
        status, headers, body = handler.handle("GET", "/odata/customer", {})
    """

    def __init__(self, backend: DataApiBackend, service_root: str = "/odata") -> None:
        self._backend = backend
        self._service_root = service_root.rstrip("/")
        self._filter_parser = ODataFilterParser()
        self._apply_parser = ODataApplyParser()
        self._expand_resolver = ExpandResolver()
        self._csdl_renderer = CsdlRenderer()
        self._formatter = ODataResponseFormatter()

    def handle(
        self,
        method: str,
        path: str,
        query_params: dict[str, str],
        request_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        """Dispatch an HTTP request and return (status, headers, body).

        Args:
            method: HTTP method string (e.g. "GET", "POST").
            path: Request path (e.g. "/odata/customer?..." — without query string).
            query_params: Parsed query parameters as a flat string dict.
            request_headers: Incoming HTTP headers (case-insensitive access via
                normalized lowercase keys when read through :meth:`_get_header`).

        Returns:
            Tuple of (status_code, headers_dict, body_string).
        """
        if method not in ("GET", "HEAD"):
            return self._error(405, "Method Not Allowed", {"Allow": "GET"})

        version_err = self._check_odata_version(request_headers)
        if version_err is not None:
            return version_err

        format_override = query_params.get("$format")
        if format_override is not None:
            query_params = {k: v for k, v in query_params.items() if k != "$format"}
            fmt = format_override.lower()
            if fmt not in ("json", "xml"):
                return self._error(400, f"Unsupported $format: {format_override!r}")

        relative = self._strip_root(path)
        if relative is None:
            return self._error(404, "Not Found")

        if relative in ("", "/"):
            if format_override == "xml":
                return self._error(406, "XML format not supported for service document")
            return self._handle_service_document()

        if relative == "/$metadata":
            if format_override == "json":
                return self._error(
                    406, "JSON CSDL not supported on $metadata; use Accept: application/xml"
                )
            return self._handle_metadata()

        steps = _parse_path(relative)
        if steps is None or not steps:
            return self._error(404, "Not Found")

        entity_name = steps[0]["name"]
        if not self._entity_exists(entity_name):
            return self._error(404, f"Entity set {entity_name!r} not found")

        return self._dispatch_steps(
            steps, query_params, format_override, request_headers
        )

    def _dispatch_steps(
        self,
        steps: list[dict[str, Any]],
        query_params: dict[str, str],
        format_override: str | None,
        request_headers: dict[str, str] | None,
    ) -> tuple[int, dict[str, str], str]:
        """Dispatch a parsed path step list to the right handler."""
        entity_name = steps[0]["name"]

        # /Entity   or   /Entity/$count  (collection-level endpoints)
        if len(steps) == 1 or (len(steps) == 2 and steps[1]["kind"] == "count"):
            if format_override == "xml":
                return self._error(406, "XML format not supported for this resource")
            if len(steps) == 2:
                return self._handle_count(entity_name, query_params)
            return self._handle_collection(entity_name, query_params, request_headers)

        if steps[1]["kind"] != "key":
            return self._error(404, "Not Found")
        key = steps[1]["value"]

        if format_override == "xml":
            return self._error(406, "XML format not supported for this resource")

        # /Entity(key)
        if len(steps) == 2:
            return self._handle_single(entity_name, key)

        # Everything beyond the key: segments, $value, $count.
        return self._walk_segments(entity_name, key, steps[2:], query_params)

    def _walk_segments(
        self,
        entity_name: str,
        key: Any,
        tail: list[dict[str, Any]],
        query_params: dict[str, str],
    ) -> tuple[int, dict[str, str], str]:
        """Walk the post-key path one step at a time.

        Handles four terminal shapes:
            */scalar               — JSON {"value": ...}
            */scalar/$value        — raw text/plain
            */navSingle            — full entity JSON
            */navMany              — collection JSON with query options
            */navMany/$count       — plain integer
        """
        current_entity = entity_name
        current_key: Any = key
        meta = self._backend.entity_metadata(current_entity)

        # Walk through nav-single segments, ending when we hit either a
        # scalar property or a nav-many collection.
        for i, step in enumerate(tail):
            if step["kind"] in ("value", "count"):
                return self._error(404, "Not Found")
            if step["kind"] != "segment":
                return self._error(404, "Not Found")
            seg = step["name"]
            kind = self._classify_segment(meta, seg)
            remaining = tail[i + 1 :]

            if kind == "property":
                if not remaining:
                    return self._handle_property(current_entity, current_key, seg)
                if len(remaining) == 1 and remaining[0]["kind"] == "value":
                    return self._handle_property_value(current_entity, current_key, seg)
                return self._error(404, "Not Found")

            if kind == "nav_single":
                target = self._navigate_single(current_entity, current_key, seg)
                if target is None:
                    return self._error(404, "Navigation target not found")
                if not remaining:
                    return self._render_entity(target["entity"], target["record"])
                current_entity = target["entity"]
                current_key = target["key"]
                meta = self._backend.entity_metadata(current_entity)
                continue

            if kind == "nav_collection":
                if not remaining:
                    return self._handle_navigation_collection(
                        current_entity, current_key, seg, query_params, count_only=False
                    )
                if len(remaining) == 1 and remaining[0]["kind"] == "count":
                    return self._handle_navigation_collection(
                        current_entity, current_key, seg, query_params, count_only=True
                    )
                return self._error(404, "Not Found")

            return self._error(404, f"Unknown segment {seg!r}")

        return self._error(404, "Not Found")

    @staticmethod
    def _get_header(headers: dict[str, str] | None, name: str) -> str | None:
        if not headers:
            return None
        target = name.lower()
        for key, value in headers.items():
            if key.lower() == target:
                return value
        return None

    def _check_odata_version(
        self, headers: dict[str, str] | None
    ) -> tuple[int, dict[str, str], str] | None:
        """Reject clients declaring OData-MaxVersion below 4.0.

        Returns an error tuple to short-circuit the request, or None to proceed.
        """
        max_ver = self._get_header(headers, "OData-MaxVersion")
        if max_ver is None:
            return None
        try:
            major = int(max_ver.split(".", 1)[0])
        except (AttributeError, ValueError):
            return self._error(400, f"Invalid OData-MaxVersion: {max_ver!r}")
        if major < 4:
            return self._error(
                400,
                f"OData v4 required; client declared OData-MaxVersion: {max_ver!r}",
            )
        return None

    def _base_headers(self, content_type: str) -> dict[str, str]:
        """Return the set of headers emitted on every response."""
        return {"Content-Type": content_type, "OData-Version": _ODATA_VERSION}

    def _strip_root(self, path: str) -> str | None:
        if not path.startswith(self._service_root):
            return None
        return path[len(self._service_root):]

    def _entity_exists(self, entity_name: str) -> bool:
        names = {es["name"] for es in self._backend.entity_sets()}
        return entity_name in names

    def _handle_service_document(self) -> tuple[int, dict[str, str], str]:
        entity_sets = self._backend.entity_sets()
        value = [
            {
                "name": es["name"],
                "url": es["name"],
                "title": es.get("title", es["name"]),
            }
            for es in entity_sets
        ]
        body = _dumps({
            "@odata.context": f"{self._service_root}/$metadata",
            "value": value,
        })
        return 200, self._base_headers(_JSON_CT), body

    def _handle_metadata(self) -> tuple[int, dict[str, str], str]:
        xml_str = self._csdl_renderer.render(self._backend)
        return 200, self._base_headers(_XML_CT), xml_str

    def _handle_collection(
        self,
        entity_name: str,
        query_params: dict[str, str],
        request_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        try:
            opts = self._build_query_options(entity_name, query_params)
        except ValueError as exc:
            return self._error(400, str(exc))

        max_page_size = self._parse_maxpagesize(request_headers)
        preference_applied = False
        if max_page_size is not None and (opts.top is None or opts.top > max_page_size):
            opts.top = max_page_size
            preference_applied = True

        result = self._backend.query(entity_name, opts)
        if opts.apply is not None:
            payload = self._formatter.format_apply_result(
                entity_name,
                result,
                self._service_root,
                opts.apply.result_columns(),
            )
        else:
            payload = self._formatter.format_collection(
                entity_name,
                result,
                self._service_root,
                opts.skip,
                opts.top,
                query_params=query_params,
            )
        headers = self._base_headers(_JSON_CT)
        if preference_applied:
            headers["Preference-Applied"] = f"odata.maxpagesize={max_page_size}"
        return 200, headers, _dumps(payload)

    def _parse_maxpagesize(
        self, request_headers: dict[str, str] | None
    ) -> int | None:
        """Extract the ``odata.maxpagesize`` value from a Prefer header, if any.

        Ignores malformed values silently — pagination is an optional hint;
        returning None falls back to the client-supplied ``$top`` (or no
        limit).
        """
        prefer = self._get_header(request_headers, "Prefer")
        if not prefer:
            return None
        for part in prefer.split(","):
            token = part.strip()
            if token.lower().startswith("odata.maxpagesize="):
                _, _, value = token.partition("=")
                try:
                    size = int(value.strip())
                    if size > 0:
                        return size
                except ValueError:
                    return None
        return None

    def _handle_single(
        self, entity_name: str, key: Any
    ) -> tuple[int, dict[str, str], str]:
        record = self._backend.get_entity(entity_name, key)
        if record is None:
            return self._error(404, f"{entity_name}({key!r}) not found")
        return self._render_entity(entity_name, record)

    def _render_entity(
        self, entity_name: str, record: dict[str, Any]
    ) -> tuple[int, dict[str, str], str]:
        payload = self._formatter.format_entity(entity_name, record, self._service_root)
        return 200, self._base_headers(_JSON_CT), _dumps(payload)

    def _classify_segment(
        self, meta: dict[str, Any], name: str
    ) -> str | None:
        """Classify a URL segment against an entity's metadata.

        Returns one of 'property', 'nav_single', 'nav_collection', or None.
        Navigation wins when a name matches both a property and a relation
        — this is the usual OData drill-down expectation.
        """
        for nav in meta.get("navigation", []):
            if nav.get("name") == name:
                return "nav_collection" if nav.get("collection") else "nav_single"
        for prop in meta.get("properties", []):
            if prop.get("name") == name:
                return "property"
        return None

    def _handle_property(
        self, entity_name: str, key: Any, prop: str
    ) -> tuple[int, dict[str, str], str]:
        record = self._backend.get_entity(entity_name, key)
        if record is None:
            return self._error(404, f"{entity_name}({key!r}) not found")
        if prop not in record:
            return self._error(404, f"Property {prop!r} not found")
        context = (
            f"{self._service_root}/$metadata#{entity_name}({key!r})/{prop}"
        )
        body = _dumps({"@odata.context": context, "value": record[prop]})
        return 200, self._base_headers(_JSON_CT), body

    def _handle_property_value(
        self, entity_name: str, key: Any, prop: str
    ) -> tuple[int, dict[str, str], str]:
        record = self._backend.get_entity(entity_name, key)
        if record is None:
            return self._error(404, f"{entity_name}({key!r}) not found")
        if prop not in record:
            return self._error(404, f"Property {prop!r} not found")
        value = record[prop]
        if value is None:
            return 204, self._base_headers(_TEXT_CT), ""
        if isinstance(value, (bytes, bytearray)):
            return (
                200,
                self._base_headers("application/octet-stream"),
                value.decode("latin-1"),
            )
        return 200, self._base_headers(_TEXT_CT), str(value)

    def _navigate_single(
        self, entity_name: str, key: Any, rel: str
    ) -> dict[str, Any] | None:
        """Resolve a single-valued navigation and return target entity+record.

        Backends expose this via an optional ``navigate_single`` method.
        Returns ``{'entity': str, 'key': Any, 'record': dict}`` or ``None``.
        """
        method = getattr(self._backend, "navigate_single", None)
        if method is None:
            return None
        result = method(entity_name, key, rel)
        if result is None:
            return None
        return result

    def _handle_navigation_collection(
        self,
        entity_name: str,
        key: Any,
        rel: str,
        query_params: dict[str, str],
        count_only: bool,
    ) -> tuple[int, dict[str, str], str]:
        """Serve /Entity(key)/navMany and /Entity(key)/navMany/$count.

        Resolves the target entity set, then delegates to the backend's
        ``navigate_collection`` method which applies the FK filter plus
        standard query options (``$filter``, ``$orderby``, ``$top``, ...).
        """
        method = getattr(self._backend, "navigate_collection", None)
        if method is None:
            return self._error(
                501, "Navigation collection not supported by backend"
            )
        meta = self._backend.entity_metadata(entity_name)
        target_entity: str | None = None
        for nav in meta.get("navigation", []):
            if nav.get("name") == rel and nav.get("collection"):
                target_entity = nav.get("target")
                break
        if target_entity is None:
            return self._error(404, f"Navigation {rel!r} not found")

        try:
            opts = self._build_query_options(target_entity, query_params)
        except ValueError as exc:
            return self._error(400, str(exc))

        if count_only:
            opts.count = True
            opts.top = None
            opts.skip = None

        try:
            result = method(entity_name, key, rel, opts)
        except ValueError as exc:
            return self._error(400, str(exc))

        if count_only:
            count = (
                result.total_count
                if result.total_count is not None
                else len(result.records)
            )
            return 200, self._base_headers(_TEXT_CT), str(count)

        payload = self._formatter.format_collection(
            target_entity, result, self._service_root, opts.skip, opts.top
        )
        return 200, self._base_headers(_JSON_CT), _dumps(payload)

    def _handle_count(
        self, entity_name: str, query_params: dict[str, str]
    ) -> tuple[int, dict[str, str], str]:
        try:
            opts = self._build_query_options(entity_name, query_params)
        except ValueError as exc:
            return self._error(400, str(exc))

        opts.count = True
        opts.top = None
        opts.skip = None
        result = self._backend.query(entity_name, opts)
        count = result.total_count if result.total_count is not None else len(result.records)
        return 200, self._base_headers(_TEXT_CT), str(count)

    def _build_query_options(
        self, entity_name: str, params: dict[str, str]
    ) -> QueryOptions:
        opts = QueryOptions()

        if "$select" in params:
            opts.select = [f.strip() for f in params["$select"].split(",") if f.strip()]

        if "$filter" in params:
            filter_str = params["$filter"]
            self._filter_parser.parse(filter_str)  # validate; raises ValueError on bad syntax
            opts.filter_expr = filter_str

        if "$orderby" in params:
            opts.order_by = self._parse_orderby(params["$orderby"])

        # $skiptoken carries the paginator state; when present it supersedes
        # inline $top/$skip. Reject tokens whose filter_hash does not match
        # the current query — the client shifted the filter between pages.
        if "$skiptoken" in params:
            state = skiptoken_module.decode(params["$skiptoken"])
            expected_hash = skiptoken_module.filter_hash(params)
            if state.get("filter_hash") != expected_hash:
                raise ValueError(
                    "$skiptoken is not coherent with current query parameters"
                )
            opts.top = state.get("top")
            opts.skip = state.get("skip")
        else:
            if "$top" in params:
                try:
                    opts.top = int(params["$top"])
                except ValueError:
                    raise ValueError("$top must be a non-negative integer") from None

            if "$skip" in params:
                try:
                    opts.skip = int(params["$skip"])
                except ValueError:
                    raise ValueError("$skip must be a non-negative integer") from None

        if "$count" in params:
            opts.count = params["$count"].lower() == "true"

        if "$expand" in params:
            meta = self._backend.entity_metadata(entity_name)
            opts.expand = self._expand_resolver.resolve(params["$expand"], meta)

        if "$apply" in params:
            if "$expand" in params:
                raise ValueError("$apply cannot be combined with $expand")
            if "$select" in params:
                raise ValueError("$apply cannot be combined with $select")
            opts.apply = self._apply_parser.parse(params["$apply"])

        return opts

    def _parse_orderby(self, orderby_str: str) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for item in orderby_str.split(","):
            parts = item.strip().split()
            if len(parts) == 1:
                result.append((parts[0], "asc"))
            elif len(parts) == 2:
                direction = parts[1].lower()
                if direction not in ("asc", "desc"):
                    raise ValueError(f"Invalid $orderby direction: {parts[1]!r}")
                result.append((parts[0], direction))
            else:
                raise ValueError(f"Invalid $orderby clause: {item!r}")
        return result

    def _error(
        self,
        status: int,
        message: str,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        body = _dumps({"error": {"code": str(status), "message": message}})
        headers = self._base_headers(_JSON_CT)
        if extra_headers:
            headers.update(extra_headers)
        return status, headers, body
