# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 request handler — server-agnostic HTTP dispatcher.

Receives (method, path, query_params) and returns (status, headers, body).
Routes OData v4 GET requests to the appropriate backend operations.
Write operations (POST, PATCH, DELETE) return 405 Method Not Allowed.
"""

from __future__ import annotations

import json
import re

from genro_data_api.core.backend import DataApiBackend, QueryOptions
from genro_data_api.odata.csdl_renderer import CsdlRenderer
from genro_data_api.odata.expand_resolver import ExpandResolver
from genro_data_api.odata.filter_parser import ODataFilterParser
from genro_data_api.odata.response import ODataResponseFormatter

_ENTITY_PATH_RE = re.compile(r"^/([^/(]+)(?:\(([^)]*)\))?(/\$count)?$")

_JSON_CT = "application/json;charset=UTF-8"
_XML_CT = "application/xml;charset=UTF-8"
_TEXT_CT = "text/plain"


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
        self._expand_resolver = ExpandResolver()
        self._csdl_renderer = CsdlRenderer()
        self._formatter = ODataResponseFormatter()

    def handle(
        self,
        method: str,
        path: str,
        query_params: dict[str, str],
    ) -> tuple[int, dict[str, str], str]:
        """Dispatch an HTTP request and return (status, headers, body).

        Args:
            method: HTTP method string (e.g. "GET", "POST").
            path: Request path (e.g. "/odata/customer?..." — without query string).
            query_params: Parsed query parameters as a flat string dict.

        Returns:
            Tuple of (status_code, headers_dict, body_string).
        """
        if method not in ("GET", "HEAD"):
            return self._error(405, "Method Not Allowed", {"Allow": "GET"})

        relative = self._strip_root(path)
        if relative is None:
            return self._error(404, "Not Found")

        if relative in ("", "/"):
            return self._handle_service_document()

        if relative == "/$metadata":
            return self._handle_metadata()

        m = _ENTITY_PATH_RE.match(relative)
        if not m:
            return self._error(404, "Not Found")

        entity_name = m.group(1)
        key_str = m.group(2)
        count_suffix = m.group(3)

        if not self._entity_exists(entity_name):
            return self._error(404, f"Entity set {entity_name!r} not found")

        if count_suffix == "/$count":
            return self._handle_count(entity_name, query_params)
        if key_str is not None:
            return self._handle_single(entity_name, key_str)
        return self._handle_collection(entity_name, query_params)

    def _strip_root(self, path: str) -> str | None:
        if not path.startswith(self._service_root):
            return None
        return path[len(self._service_root) :]

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
        body = json.dumps(
            {
                "@odata.context": f"{self._service_root}/$metadata",
                "value": value,
            }
        )
        return 200, {"Content-Type": _JSON_CT}, body

    def _handle_metadata(self) -> tuple[int, dict[str, str], str]:
        xml_str = self._csdl_renderer.render(self._backend)
        return 200, {"Content-Type": _XML_CT}, xml_str

    def _handle_collection(
        self, entity_name: str, query_params: dict[str, str]
    ) -> tuple[int, dict[str, str], str]:
        try:
            opts = self._build_query_options(entity_name, query_params)
        except ValueError as exc:
            return self._error(400, str(exc))

        result = self._backend.query(entity_name, opts)
        payload = self._formatter.format_collection(
            entity_name, result, self._service_root, opts.skip, opts.top
        )
        return 200, {"Content-Type": _JSON_CT}, json.dumps(payload)

    def _handle_single(
        self, entity_name: str, key_str: str
    ) -> tuple[int, dict[str, str], str]:
        key = self._parse_key(key_str)
        record = self._backend.get_entity(entity_name, key)
        if record is None:
            return self._error(404, f"{entity_name}({key_str!r}) not found")
        payload = self._formatter.format_entity(entity_name, record, self._service_root)
        return 200, {"Content-Type": _JSON_CT}, json.dumps(payload)

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
        return 200, {"Content-Type": _TEXT_CT}, str(count)

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

        return opts

    def _parse_key(self, key_str: str) -> str | int:
        """Parse a key string: remove quotes for strings, convert ints."""
        stripped = key_str.strip()
        if stripped.startswith("'") and stripped.endswith("'"):
            return stripped[1:-1]
        try:
            return int(stripped)
        except ValueError:
            return stripped

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
        body = json.dumps({"error": {"code": str(status), "message": message}})
        headers: dict[str, str] = {"Content-Type": _JSON_CT}
        if extra_headers:
            headers.update(extra_headers)
        return status, headers, body
