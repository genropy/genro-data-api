# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for ODataApplyParser."""

from __future__ import annotations

import pytest

from genro_data_api.odata.apply_parser import (
    AggregateItem,
    AggregateStep,
    ApplyPipeline,
    FilterStep,
    GroupByStep,
    ODataApplyParser,
)


@pytest.fixture
def parser() -> ODataApplyParser:
    return ODataApplyParser()


class TestAggregate:
    def test_single_sum(self, parser: ODataApplyParser) -> None:
        result = parser.parse("aggregate(total with sum as Revenue)")
        assert result == ApplyPipeline(
            steps=[
                AggregateStep(
                    items=[AggregateItem(column="total", method="sum", alias="Revenue")]
                )
            ]
        )

    def test_multiple_aggregations(self, parser: ODataApplyParser) -> None:
        result = parser.parse(
            "aggregate(total with sum as Revenue, total with max as BiggestInvoice)"
        )
        step = result.steps[0]
        assert isinstance(step, AggregateStep)
        assert [i.alias for i in step.items] == ["Revenue", "BiggestInvoice"]
        assert [i.method for i in step.items] == ["sum", "max"]

    def test_count_form(self, parser: ODataApplyParser) -> None:
        result = parser.parse("aggregate($count as NumInvoices)")
        step = result.steps[0]
        assert isinstance(step, AggregateStep)
        assert step.items == [
            AggregateItem(column=None, method="count", alias="NumInvoices")
        ]

    def test_countdistinct(self, parser: ODataApplyParser) -> None:
        result = parser.parse("aggregate(customer_id with countdistinct as Uniques)")
        step = result.steps[0]
        assert isinstance(step, AggregateStep)
        assert step.items[0].method == "countdistinct"

    def test_unsupported_method_rejected(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Unsupported aggregation method"):
            parser.parse("aggregate(total with median as X)")

    def test_empty_body_rejected(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty aggregate"):
            parser.parse("aggregate()")


class TestGroupBy:
    def test_single_key_no_aggregate(self, parser: ODataApplyParser) -> None:
        result = parser.parse("groupby((state))")
        step = result.steps[0]
        assert isinstance(step, GroupByStep)
        assert step.keys == ["state"]
        assert step.aggregate is None

    def test_multiple_keys(self, parser: ODataApplyParser) -> None:
        result = parser.parse("groupby((state, customer_type_code))")
        step = result.steps[0]
        assert isinstance(step, GroupByStep)
        assert step.keys == ["state", "customer_type_code"]

    def test_with_aggregate(self, parser: ODataApplyParser) -> None:
        result = parser.parse(
            "groupby((state), aggregate(total with sum as GrandTotal))"
        )
        step = result.steps[0]
        assert isinstance(step, GroupByStep)
        assert step.keys == ["state"]
        assert step.aggregate is not None
        assert step.aggregate.items[0].alias == "GrandTotal"

    def test_missing_parens_around_keys_rejected(
        self, parser: ODataApplyParser
    ) -> None:
        with pytest.raises(ValueError, match="enclosed in parentheses"):
            parser.parse("groupby(state, aggregate($count as N))")

    def test_extra_args_rejected(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="at most two arguments"):
            parser.parse("groupby((state), aggregate($count as N), extra)")


class TestFilter:
    def test_filter_passthrough(self, parser: ODataApplyParser) -> None:
        result = parser.parse("filter(year(date) eq 2024)")
        step = result.steps[0]
        assert isinstance(step, FilterStep)
        assert step.filter_expr == "year(date) eq 2024"


class TestPipeline:
    def test_filter_groupby_aggregate(self, parser: ODataApplyParser) -> None:
        result = parser.parse(
            "filter(year(date) eq 2024)/"
            "groupby((customer_id), aggregate(total with sum as Total))"
        )
        assert len(result.steps) == 2
        assert isinstance(result.steps[0], FilterStep)
        assert isinstance(result.steps[1], GroupByStep)

    def test_result_columns_on_aggregate_only(
        self, parser: ODataApplyParser
    ) -> None:
        result = parser.parse(
            "aggregate(total with sum as Revenue, $count as NumRows)"
        )
        assert result.result_columns() == ["Revenue", "NumRows"]

    def test_result_columns_on_groupby_with_aggregate(
        self, parser: ODataApplyParser
    ) -> None:
        result = parser.parse(
            "groupby((state), aggregate(total with sum as Total))"
        )
        assert result.result_columns() == ["state", "Total"]

    def test_result_columns_on_groupby_no_aggregate(
        self, parser: ODataApplyParser
    ) -> None:
        result = parser.parse("groupby((state, customer_type_code))")
        assert result.result_columns() == ["state", "customer_type_code"]


class TestErrors:
    def test_empty_string(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty"):
            parser.parse("")

    def test_unknown_transformation(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            parser.parse("sort((state))")

    def test_unbalanced_parens(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Unbalanced"):
            parser.parse("aggregate(total with sum as Revenue")

    def test_trailing_garbage(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError):
            parser.parse("aggregate($count as N) garbage")
