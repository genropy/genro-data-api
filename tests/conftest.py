# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for genro-data-api tests."""

from __future__ import annotations

from typing import Any

import pytest

from genro_data_api.core.backend import QueryOptions, QueryResult
from genro_data_api.odata.filter_parser import (
    ComparisonNode,
    FilterNode,
    FunctionCallNode,
    FunctionNode,
    InNode,
    LambdaNode,
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
            {
                "name": "customer",
                "title": "Customers",
                "description": "Accounts that can place orders",
            },
            {"name": "order", "title": "Orders", "description": ""},
        ]

    def entity_metadata(self, entity_name: str) -> dict[str, Any]:
        if entity_name == "customer":
            return {
                "name": "customer",
                "label": "Customer",
                "description": "An account that can place orders",
                "key": ["id"],
                "properties": [
                    {
                        "name": "id",
                        "type": "I",
                        "nullable": False,
                        "label": "Identifier",
                    },
                    {
                        "name": "name",
                        "type": "A",
                        "nullable": True,
                        "maxLength": 100,
                        "label": "Company name",
                        "description": "Legal business name",
                    },
                    {"name": "country", "type": "A", "nullable": True, "maxLength": 2},
                    {"name": "active", "type": "B", "nullable": True},
                    {
                        "name": "orders_count",
                        "type": "I",
                        "nullable": True,
                        "computed": True,
                        "label": "Order count",
                    },
                ],
                "navigation": [
                    {
                        "name": "Orders",
                        "target": "order",
                        "collection": True,
                        "label": "Customer orders",
                    },
                ],
            }
        if entity_name == "order":
            return {
                "name": "order",
                "label": "Order",
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
                records = [
                    r for r in records if self._eval_node(node, r, entity_name)
                ]
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

    # Navigation map: (source_record_entity, relation_@path) -> (target_entity, parent_fk, child_fk)
    _NAV_MAP: dict[tuple[str, str], tuple[str, str, str]] = {
        ("customer", "@Orders"): ("order", "id", "customer_id"),
    }

    def _eval_node(
        self, node: FilterNode, record: dict[str, Any], entity: str = "customer"
    ) -> bool:
        if isinstance(node, ComparisonNode):
            return self._eval_comparison(node, record)
        if isinstance(node, InNode):
            return self._eval_in(node, record)
        if isinstance(node, LogicalNode):
            return self._eval_logical(node, record, entity)
        if isinstance(node, FunctionNode):
            return self._eval_function(node, record)
        if isinstance(node, LambdaNode):
            return self._eval_lambda(node, record, entity)
        return False

    def _eval_lambda(
        self, node: LambdaNode, record: dict[str, Any], entity: str
    ) -> bool:
        key = (entity, node.path)
        if key not in self._NAV_MAP:
            raise ValueError(f"Unknown navigation {node.path!r} on {entity!r}")
        target_entity, parent_fk, child_fk = self._NAV_MAP[key]
        parent_val = record.get(parent_fk)
        data_map = {"customer": self._customers, "order": self._orders}
        related = [
            r for r in data_map[target_entity] if r.get(child_fk) == parent_val
        ]
        if node.quantifier == "any":
            return any(self._eval_node(node.body, r, target_entity) for r in related)
        if node.quantifier == "all":
            return all(self._eval_node(node.body, r, target_entity) for r in related)
        return False

    def _eval_expr(self, expr: Any, record: dict[str, Any]) -> Any:
        """Evaluate a parsed expression against a record.

        Field refs are marked by the parser with ``$`` (local column) or
        ``@`` (navigation path); everything else is a literal value.
        """
        if isinstance(expr, FunctionCallNode):
            return self._eval_function_call(expr, record)
        if isinstance(expr, str) and expr[:1] == "$":
            return record.get(expr[1:])
        if isinstance(expr, str) and expr[:1] == "@":
            # minimal navigation support: flat lookup using the dotted path as key
            return record.get(expr[1:])
        return expr

    def _eval_function_call(
        self, node: FunctionCallNode, record: dict[str, Any]
    ) -> Any:
        args = [self._eval_expr(a, record) for a in node.args]
        if node.name == "tolower":
            return (args[0] or "").lower()
        if node.name == "toupper":
            return (args[0] or "").upper()
        if node.name == "trim":
            return (args[0] or "").strip()
        if node.name == "length":
            return len(args[0] or "")
        if node.name == "concat":
            return "".join(str(a or "") for a in args)
        if node.name == "year":
            v = args[0]
            return v.year if v is not None else None
        if node.name == "month":
            v = args[0]
            return v.month if v is not None else None
        if node.name == "day":
            v = args[0]
            return v.day if v is not None else None
        if node.name == "now":
            import datetime
            return datetime.datetime.now(datetime.timezone.utc)
        if node.name == "round":
            return round(args[0]) if args[0] is not None else None
        if node.name == "floor":
            import math
            return math.floor(args[0]) if args[0] is not None else None
        if node.name == "ceiling":
            import math
            return math.ceil(args[0]) if args[0] is not None else None
        return None

    def _eval_comparison(self, node: ComparisonNode, record: dict[str, Any]) -> bool:
        field_val = self._eval_expr(node.field, record)
        val = self._eval_expr(node.value, record)
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

    def _eval_in(self, node: InNode, record: dict[str, Any]) -> bool:
        field_val = self._eval_expr(node.field, record)
        return field_val in node.values

    def _eval_logical(
        self, node: LogicalNode, record: dict[str, Any], entity: str
    ) -> bool:
        if node.op == "and":
            return all(self._eval_node(c, record, entity) for c in node.children)
        if node.op == "or":
            return any(self._eval_node(c, record, entity) for c in node.children)
        if node.op == "not":
            return not self._eval_node(node.children[0], record, entity)
        return False

    def _eval_function(self, node: FunctionNode, record: dict[str, Any]) -> bool:
        raw = self._eval_expr(node.field, record)
        field_val = str(raw or "")
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
