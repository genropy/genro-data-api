# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for ExpandResolver."""

from __future__ import annotations

import pytest

from genro_data_api.core.backend import DataApiBackend, QueryOptions
from genro_data_api.odata.expand_resolver import ExpandResolver


@pytest.fixture
def resolver() -> ExpandResolver:
    return ExpandResolver()


@pytest.fixture
def customer_meta(mock_backend: DataApiBackend) -> dict:  # type: ignore[type-arg]
    return mock_backend.entity_metadata("customer")


@pytest.fixture
def order_meta(mock_backend: DataApiBackend) -> dict:  # type: ignore[type-arg]
    return mock_backend.entity_metadata("order")


class TestSimpleExpand:
    def test_single_nav_property(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        result = resolver.resolve("Orders", customer_meta)
        assert "Orders" in result
        assert isinstance(result["Orders"], QueryOptions)

    def test_default_options_are_empty(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        result = resolver.resolve("Orders", customer_meta)
        opts = result["Orders"]
        assert opts.select is None
        assert opts.filter_expr is None
        assert opts.order_by is None
        assert opts.top is None
        assert opts.skip is None
        assert opts.count is False

    def test_empty_string_returns_empty(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        result = resolver.resolve("", customer_meta)
        assert result == {}

    def test_whitespace_string_returns_empty(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        result = resolver.resolve("   ", customer_meta)
        assert result == {}


class TestMultipleExpand:
    def test_multiple_valid_would_fail_for_order(
        self, resolver: ExpandResolver, order_meta: dict
    ) -> None:
        # order has no navigation properties
        with pytest.raises(ValueError, match="Unknown navigation property"):
            resolver.resolve("Orders", order_meta)

    def test_unknown_property_raises(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        with pytest.raises(ValueError, match="Unknown navigation property"):
            resolver.resolve("NonExistent", customer_meta)


class TestNestedOptions:
    def test_nested_select(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($select=id,amount)", customer_meta)
        opts = result["Orders"]
        assert opts.select == ["id", "amount"]

    def test_nested_filter(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($filter=amount gt 100)", customer_meta)
        opts = result["Orders"]
        assert opts.filter_expr == "amount gt 100"

    def test_nested_top(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($top=5)", customer_meta)
        opts = result["Orders"]
        assert opts.top == 5

    def test_nested_skip(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($skip=10)", customer_meta)
        opts = result["Orders"]
        assert opts.skip == 10

    def test_nested_count(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($count=true)", customer_meta)
        opts = result["Orders"]
        assert opts.count is True

    def test_nested_orderby_asc(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($orderby=amount asc)", customer_meta)
        opts = result["Orders"]
        assert opts.order_by == [("amount", "asc")]

    def test_nested_orderby_desc(self, resolver: ExpandResolver, customer_meta: dict) -> None:
        result = resolver.resolve("Orders($orderby=amount desc)", customer_meta)
        opts = result["Orders"]
        assert opts.order_by == [("amount", "desc")]

    def test_nested_orderby_default_asc(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        result = resolver.resolve("Orders($orderby=id)", customer_meta)
        opts = result["Orders"]
        assert opts.order_by == [("id", "asc")]

    def test_multiple_nested_options(
        self, resolver: ExpandResolver, customer_meta: dict
    ) -> None:
        result = resolver.resolve("Orders($select=id,amount;$top=3;$skip=0)", customer_meta)
        opts = result["Orders"]
        assert opts.select == ["id", "amount"]
        assert opts.top == 3
        assert opts.skip == 0
