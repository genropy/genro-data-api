# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""GraphQL request handler — server-agnostic HTTP dispatcher.

Handles GraphQL queries over HTTP:
- POST / with JSON body {"query": "...", "variables": {...}}
- GET / with ?query=... query param
- GET /schema — return SDL schema as plain text
Other paths or methods return 4xx errors.
"""

from __future__ import annotations

import json
from typing import Any

from graphql import graphql_sync, print_schema

from genro_data_api.core.backend import DataApiBackend
from genro_data_api.graphql.response import GraphQLResponseFormatter
from genro_data_api.graphql.schema_generator import GraphQLSchemaGenerator

_JSON_CT = "application/json;charset=UTF-8"
_TEXT_CT = "text/plain;charset=UTF-8"


class GraphQLRequestHandler:
    """Server-agnostic GraphQL HTTP request handler.

    Usage::

        handler = GraphQLRequestHandler(backend)
        status, headers, body = handler.handle("POST", "/", {}, '{"query": "{ customer { name } }"}')
    """

    def __init__(self, backend: DataApiBackend) -> None:
        self._backend = backend
        self._generator = GraphQLSchemaGenerator()
        self._schema = self._generator.generate(backend)
        self._formatter = GraphQLResponseFormatter()

    def handle(
        self,
        method: str,
        path: str,
        query_params: dict[str, str],
        body: str = "",
    ) -> tuple[int, dict[str, str], str]:
        """Dispatch an HTTP request and return (status, headers, body).

        Args:
            method: HTTP method (e.g. "GET", "POST").
            path: Request path (e.g. "/" or "/schema").
            query_params: Parsed query parameters.
            body: Request body (used for POST).

        Returns:
            Tuple of (status_code, headers_dict, body_string).
        """
        if path == "/schema":
            if method not in ("GET", "HEAD"):
                return self._method_not_allowed({"Allow": "GET"})
            return self._handle_schema()

        if path in ("/", ""):
            if method == "POST":
                return self._handle_post(body)
            if method in ("GET", "HEAD"):
                return self._handle_get(query_params)
            return self._method_not_allowed({"Allow": "GET, POST"})

        return self._not_found()

    def _handle_schema(self) -> tuple[int, dict[str, str], str]:
        sdl = print_schema(self._schema)
        return 200, {"Content-Type": _TEXT_CT}, sdl

    def _handle_post(self, body: str) -> tuple[int, dict[str, str], str]:
        try:
            payload = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError as exc:
            return self._error(400, f"Invalid JSON body: {exc}")

        query_str = payload.get("query", "")
        variables = payload.get("variables") or {}
        return self._execute(query_str, variables)

    def _handle_get(self, query_params: dict[str, str]) -> tuple[int, dict[str, str], str]:
        query_str = query_params.get("query", "")
        variables: dict[str, Any] = {}
        variables_str = query_params.get("variables", "")
        if variables_str:
            try:
                variables = json.loads(variables_str)
            except json.JSONDecodeError:
                return self._error(400, "Invalid JSON in 'variables' query param")
        return self._execute(query_str, variables)

    def _execute(
        self, query_str: str, variables: dict[str, Any]
    ) -> tuple[int, dict[str, str], str]:
        if not query_str.strip():
            return self._error(400, "Missing 'query' in request")
        result = graphql_sync(
            self._schema,
            query_str,
            variable_values=variables or None,
        )
        body = self._formatter.format(result)
        return 200, {"Content-Type": _JSON_CT}, body

    def _method_not_allowed(
        self, extra_headers: dict[str, str]
    ) -> tuple[int, dict[str, str], str]:
        headers: dict[str, str] = {"Content-Type": _JSON_CT}
        headers.update(extra_headers)
        body = self._formatter.format_error("Method Not Allowed")
        return 405, headers, body

    def _not_found(self) -> tuple[int, dict[str, str], str]:
        body = self._formatter.format_error("Not Found")
        return 404, {"Content-Type": _JSON_CT}, body

    def _error(self, status: int, message: str) -> tuple[int, dict[str, str], str]:
        body = self._formatter.format_error(message)
        return status, {"Content-Type": _JSON_CT}, body
