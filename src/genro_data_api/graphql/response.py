# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""GraphQL response formatter.

Serializes graphql.ExecutionResult objects to JSON strings,
handling datetime, Decimal, and other non-JSON-native types.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from typing import Any

from graphql import ExecutionResult, GraphQLError


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
    """JSON serialize with safe type handling."""
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


class GraphQLResponseFormatter:
    """Formats GraphQL execution results as JSON strings."""

    def format(self, result: ExecutionResult) -> str:
        """Serialize an ExecutionResult as a GraphQL JSON response.

        Args:
            result: The result from graphql.graphql_sync().

        Returns:
            JSON string with 'data' and optional 'errors' keys.
        """
        payload: dict[str, Any] = {"data": result.data}
        if result.errors:
            payload["errors"] = [self._format_error(e) for e in result.errors]
        return _dumps(payload)

    def format_error(self, message: str) -> str:
        """Serialize a plain error message as a GraphQL JSON response.

        Args:
            message: Human-readable error message.

        Returns:
            JSON string with 'data': null and 'errors' list.
        """
        payload: dict[str, Any] = {
            "data": None,
            "errors": [{"message": message}],
        }
        return _dumps(payload)

    def _format_error(self, error: GraphQLError) -> dict[str, Any]:
        """Convert a GraphQLError to a serializable dict."""
        result: dict[str, Any] = {"message": str(error)}
        if error.locations:
            result["locations"] = [
                {"line": loc.line, "column": loc.column} for loc in error.locations
            ]
        if error.path:
            result["path"] = list(error.path)
        return result
