# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for genro-data-api tests."""

from __future__ import annotations

from typing import Any

import pytest

from genro_data_api.core.backend import QueryOptions, QueryResult
from genro_data_api.odata.filter_parser import (
    ComparisonNode,
    FilterNode,
    FunctionNode,
    LogicalNode,
    ODataFilterParser,
)


class MockBackend:
    """In-memory DataApiBackend implementation for testing."""

    def __init__(self) -> None:
        self._customers: list[dict[str, Any]] = [
            {"id": 1, "name": "Alice Corp", "country": "IT", "active": True},
            {"id": 2, "name": "Bob Ltd", "country": "US", "active": True},
            {"id": 3, "name": "Charlie GmbH", "country": "DE", "active": False},
        ]
        self._orders: list[dict[str, Any]] = [
            {"id": 101, "customer_id": 1, "amount": 1500.0, "status": "delivered"},
            {"id": 102, "customer_id": 1, "amount": 250.5, "status": "pending"},
            {"id": 103, "customer_id": 2, "amount": 3200.0, "status": "delivered"},
        ]
        self._filter_parser = ODataFilterParser()

    def entity_sets(self) -> list[dict[str, Any]]:
        return [
            {"name": "customer", "title": "Customers"},
            {"name": "order", "title": "Orders"},
        ]

    def entity_metadata(self, entity_name: str) -> dict[str, Any]:
        if entity_name == "customer":
            return {
                "name": "customer",
                "key": ["id"],
                "properties": [
                    {"name": "id", "type": "I", "nullable": False},
                    {"name": "name", "type": "A", "nullable": True, "maxLength": 100},
                    {"name": "country", "type": "A", "nullable": True, "maxLength": 2},
                    {"name": "active", "type": "B", "nullable": True},
                ],
                "navigation": [
                    {"name": "Orders", "target": "order", "collection": True},
                ],
            }
        if entity_name == "order":
            return {
                "name": "order",
                "key": ["id"],
                "properties": [
                    {"name": "id", "type": "I", "nullable": False},
                    {"name": "customer_id", "type": "I", "nullable": True},
                    {"name": "amount", "type": "N", "nullable": True, "precision": 12, "scale": 2},
                    {"name": "status", "type": "A", "nullable": True, "maxLength": 20},
                ],
                "navigation": [],
            }
        raise KeyError(f"Unknown entity: {entity_name!r}")

    def query(self, entity_name: str, options: QueryOptions) -> QueryResult:
        data_map: dict[str, list[dict[str, Any]]] = {
            "customer": self._customers,
            "order": self._orders,
        }
        records = list(data_map.get(entity_name, []))

        if options.filter_expr:
            try:
                node = self._filter_parser.parse(options.filter_expr)
                records = [r for r in records if self._eval_node(node, r)]
            except ValueError:
                pass  # return unfiltered on parse failure

        if options.select:
            records = [{k: r[k] for k in options.select if k in r} for r in records]

        if options.order_by:
            for field, direction in reversed(options.order_by):
                records.sort(
                    key=lambda r, f=field: (r.get(f) is None, r.get(f, "")),  # type: ignore[misc]
                    reverse=(direction == "desc"),
                )

        total = len(records) if options.count else None

        if options.skip:
            records = records[options.skip :]
        if options.top is not None:
            records = records[: options.top]

        return QueryResult(records=records, total_count=total)

    def get_entity(self, entity_name: str, key: Any) -> dict[str, Any] | None:
        data_map: dict[str, list[dict[str, Any]]] = {
            "customer": self._customers,
            "order": self._orders,
        }
        key_field = {"customer": "id", "order": "id"}.get(entity_name, "id")
        try:
            key_val: Any = int(key) if isinstance(key, str) else key
        except (ValueError, TypeError):
            key_val = key
        for record in data_map.get(entity_name, []):
            if record.get(key_field) == key_val:
                return dict(record)
        return None

    def _eval_node(self, node: FilterNode, record: dict[str, Any]) -> bool:
        if isinstance(node, ComparisonNode):
            return self._eval_comparison(node, record)
        if isinstance(node, LogicalNode):
            return self._eval_logical(node, record)
        if isinstance(node, FunctionNode):
            return self._eval_function(node, record)
        return False

    def _eval_comparison(self, node: ComparisonNode, record: dict[str, Any]) -> bool:
        field_val = record.get(node.field)
        val = node.value
        if node.op == "eq":
            return field_val == val
        if node.op == "ne":
            return field_val != val
        if field_val is None or val is None:
            return False
        if node.op == "gt":
            return field_val > val  # type: ignore[operator]
        if node.op == "ge":
            return field_val >= val  # type: ignore[operator]
        if node.op == "lt":
            return field_val < val  # type: ignore[operator]
        if node.op == "le":
            return field_val <= val  # type: ignore[operator]
        return False

    def _eval_logical(self, node: LogicalNode, record: dict[str, Any]) -> bool:
        if node.op == "and":
            return all(self._eval_node(c, record) for c in node.children)
        if node.op == "or":
            return any(self._eval_node(c, record) for c in node.children)
        if node.op == "not":
            return not self._eval_node(node.children[0], record)
        return False

    def _eval_function(self, node: FunctionNode, record: dict[str, Any]) -> bool:
        field_val = str(record.get(node.field, ""))
        val = node.value
        if node.name == "contains":
            return val in field_val
        if node.name == "startswith":
            return field_val.startswith(val)
        if node.name == "endswith":
            return field_val.endswith(val)
        return False


@pytest.fixture
def mock_backend() -> MockBackend:
    """Provide a fresh MockBackend for each test."""
    return MockBackend()
