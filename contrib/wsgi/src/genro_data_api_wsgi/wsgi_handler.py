# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""WSGI handler for OData v4 endpoints.

Thin wrapper that translates WSGI environ to
ODataRequestHandler.handle(method, path, query_params) and returns
the result as a WSGI response. Server-framework agnostic — works
with any WSGI server (GenroPy, gunicorn, waitress, etc.).

Usage::

    from genro_data_api_wsgi import ODataWsgiHandler
    from genro_data_api.odata import ODataRequestHandler

    handler = ODataWsgiHandler(request_handler)

    # In a WSGI callable:
    def application(environ, start_response):
        return handler(environ, start_response)
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from genro_data_api.odata import ODataRequestHandler

_STATUS_PHRASES = {
    200: "200 OK",
    400: "400 Bad Request",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    500: "500 Internal Server Error",
    501: "501 Not Implemented",
    503: "503 Service Unavailable",
}


class ODataWsgiHandler:
    """WSGI callable wrapping ODataRequestHandler.

    Translates WSGI environ into the handler's (method, path, params)
    interface and sends the response via start_response.
    """

    def __init__(self, request_handler: ODataRequestHandler) -> None:
        self.request_handler = request_handler

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: Any,
    ) -> list[bytes]:
        """WSGI entry point."""
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        query_string = environ.get("QUERY_STRING", "")

        parsed_qs = parse_qs(query_string)
        query_params = {k: v[0] for k, v in parsed_qs.items()}

        status_code, headers, body = self.request_handler.handle(
            method, path, query_params
        )

        body_bytes = body.encode("utf-8") if isinstance(body, str) else body

        status_line = _STATUS_PHRASES.get(status_code, f"{status_code} Unknown")
        response_headers = list(headers.items())
        response_headers.append(("Content-Length", str(len(body_bytes))))

        start_response(status_line, response_headers)
        return [body_bytes]
