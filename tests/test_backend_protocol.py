# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for the DataApiBackend protocol and data structures."""

from genro_data_api.core.backend import DataApiBackend, QueryOptions, QueryResult


class TestQueryOptions:
    """QueryOptions dataclass tests."""

    def test_defaults(self):
        opts = QueryOptions()
        assert opts.select is None
        assert opts.filter_expr is None
        assert opts.order_by is None
        assert opts.top is None
        assert opts.skip is None
        assert opts.count is False
        assert opts.expand is None

    def test_with_values(self):
        opts = QueryOptions(
            select=["name", "email"],
            filter_expr="Price gt 20",
            order_by=[("name", "asc")],
            top=10,
            skip=20,
            count=True,
        )
        assert opts.select == ["name", "email"]
        assert opts.top == 10
        assert opts.count is True

    def test_nested_expand(self):
        inner = QueryOptions(select=["id", "total"])
        opts = QueryOptions(expand={"orders": inner})
        assert opts.expand is not None
        assert opts.expand["orders"].select == ["id", "total"]


class TestQueryResult:
    """QueryResult dataclass tests."""

    def test_empty(self):
        result = QueryResult()
        assert result.records == []
        assert result.total_count is None

    def test_with_records(self):
        records = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = QueryResult(records=records, total_count=100)
        assert len(result.records) == 2
        assert result.total_count == 100


class TestProtocol:
    """DataApiBackend protocol compliance tests."""

    def test_protocol_is_runtime_checkable(self):
        class MockBackend:
            def entity_sets(self):
                return []

            def entity_metadata(self, entity_name):
                return {}

            def query(self, entity_name, options):
                return QueryResult()

            def get_entity(self, entity_name, key):
                return None

        backend = MockBackend()
        assert isinstance(backend, DataApiBackend)

    def test_non_compliant_object_fails_check(self):
        class Incomplete:
            def entity_sets(self):
                return []

        obj = Incomplete()
        assert not isinstance(obj, DataApiBackend)
