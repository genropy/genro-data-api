# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 application for genro-asgi.

Thin ASGI wrapper around ODataRequestHandler. Mounts as a standard
genro-asgi application on a URL prefix (e.g. /odata/) and delegates
all request handling to the server-agnostic handler from genro-data-api.

Usage in config.yaml::

    apps:
        odata:
            module: genro_data_api_asgi:ODataApplication

Or programmatically::

    from genro_data_api_asgi import ODataApplication
    app = ODataApplication(backend=my_backend)
    server.mount("/odata", app)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

from genro_asgi.applications.asgi_application import AsgiApplication
from genro_data_api.core.backend import DataApiBackend
from genro_data_api.odata import ODataRequestHandler

if TYPE_CHECKING:
    from genro_asgi.types import Receive, Scope, Send


class ODataApplication(AsgiApplication):
    """ASGI application serving OData v4 endpoints.

    Wraps :class:`ODataRequestHandler` as a genro-asgi application.
    Participates in the full middleware chain (auth, CORS, errors).
    """

    def on_init(self, **kwargs: Any) -> None:
        """Initialize with a DataApiBackend instance.

        Args:
            **kwargs: Must include 'backend' (DataApiBackend instance)
                or it will be set later via set_backend().
        """
        backend = kwargs.pop("backend", None)
        self._handler: ODataRequestHandler | None = None
        if backend is not None:
            self.set_backend(backend)

    def set_backend(self, backend: DataApiBackend) -> None:
        """Configure the data backend and create the request handler."""
        mount_name = getattr(self, "_mount_name", "odata")
        self._handler = ODataRequestHandler(backend, service_root="")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point — translate scope to handler.handle() call."""
        if scope["type"] != "http":
            return

        if self._handler is None:
            await self._send_error(send, 503, "OData backend not configured")
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        # Strip the mount prefix to get the OData-relative path
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            path = path[len(root_path):]

        query_string = scope.get("query_string", b"")
        if isinstance(query_string, bytes):
            query_string = query_string.decode("utf-8")
        parsed_qs = parse_qs(query_string)
        query_params = {k: v[0] for k, v in parsed_qs.items()}

        status_code, headers, body = self._handler.handle(method, path, query_params)

        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        response_headers = [
            [k.encode(), v.encode()] for k, v in headers.items()
        ]
        response_headers.append([b"content-length", str(len(body_bytes)).encode()])

        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": response_headers,
        })
        await send({
            "type": "http.response.body",
            "body": body_bytes,
        })

    async def _send_error(self, send: Send, status: int, message: str) -> None:
        """Send a JSON error response."""
        import json
        body = json.dumps({"error": {"code": str(status), "message": message}}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({"type": "http.response.body", "body": body})
