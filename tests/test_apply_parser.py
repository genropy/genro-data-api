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
    _is_identifier,
    _split_top_level,
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

    def test_missing_opening_paren(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Expected '\\('"):
            parser.parse("aggregate")

    def test_expected_identifier(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Expected identifier"):
            parser.parse("(foo)")

    def test_empty_filter_body(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty filter"):
            parser.parse("filter()")

    def test_empty_aggregate_body(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty aggregate"):
            parser.parse("aggregate()")

    def test_empty_groupby_body(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty groupby"):
            parser.parse("groupby()")

    def test_empty_aggregate_entry(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty aggregate entry"):
            parser.parse("aggregate(total with sum as Revenue, )")

    def test_malformed_aggregate_entry(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Invalid aggregate entry"):
            parser.parse("aggregate(total sum Revenue)")

    def test_unsupported_aggregate_method(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Unsupported aggregation method"):
            parser.parse("aggregate(total with median as M)")

    def test_invalid_column_in_aggregate(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Invalid column"):
            parser.parse("aggregate(1bad with sum as A)")

    def test_invalid_alias_in_aggregate(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Invalid alias"):
            parser.parse("aggregate(total with sum as 1bad)")

    def test_groupby_keys_without_parens(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="enclosed in parentheses"):
            parser.parse("groupby(state)")

    def test_groupby_empty_keys(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Empty groupby key"):
            parser.parse("groupby(())")

    def test_groupby_invalid_key(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Invalid groupby key"):
            parser.parse("groupby((1bad))")

    def test_groupby_second_arg_not_aggregate(
        self, parser: ODataApplyParser
    ) -> None:
        with pytest.raises(ValueError, match="must be aggregate"):
            parser.parse("groupby((state), filter(x eq 1))")

    def test_groupby_too_many_args(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="at most two arguments"):
            parser.parse(
                "groupby((state), aggregate($count as N), aggregate($count as M))"
            )

    def test_empty_aggregate_inside_groupby(
        self, parser: ODataApplyParser
    ) -> None:
        with pytest.raises(ValueError, match="Empty aggregate\\(\\) inside"):
            parser.parse("groupby((state), aggregate())")

    def test_count_without_as(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Expected 'as"):
            parser.parse("aggregate($count NumInvoices)")

    def test_count_invalid_alias(self, parser: ODataApplyParser) -> None:
        with pytest.raises(ValueError, match="Invalid alias"):
            parser.parse("aggregate($count as 1bad)")


class TestAggregateEscapedQuotes:
    def test_quote_escape_in_filter_body(
        self, parser: ODataApplyParser
    ) -> None:
        # The '' escape inside a single-quoted literal must not close the string.
        result = parser.parse("filter(name eq 'O''Brien')")
        step = result.steps[0]
        assert isinstance(step, FilterStep)
        assert step.filter_expr == "name eq 'O''Brien'"


class TestResultColumns:
    def test_empty_pipeline_returns_empty(self) -> None:
        assert ApplyPipeline().result_columns() == []

    def test_filter_only_returns_empty(
        self, parser: ODataApplyParser
    ) -> None:
        pipeline = parser.parse("filter(total gt 0)")
        assert pipeline.result_columns() == []


class TestToDict:
    def test_aggregate_step_roundtrip(self) -> None:
        step = AggregateStep(
            items=[AggregateItem(column="total", method="sum", alias="Rev")]
        )
        assert step.to_dict() == {
            "kind": "aggregate",
            "items": [{"column": "total", "method": "sum", "alias": "Rev"}],
        }

    def test_groupby_with_aggregate_roundtrip(self) -> None:
        step = GroupByStep(
            keys=["state"],
            aggregate=AggregateStep(
                items=[AggregateItem(column=None, method="count", alias="N")]
            ),
        )
        d = step.to_dict()
        assert d["kind"] == "groupby"
        assert d["keys"] == ["state"]
        assert d["aggregate"]["items"][0]["alias"] == "N"

    def test_groupby_without_aggregate_roundtrip(self) -> None:
        step = GroupByStep(keys=["a", "b"])
        d = step.to_dict()
        assert d["aggregate"] is None

    def test_filter_step_roundtrip(self) -> None:
        step = FilterStep(filter_expr="x eq 1")
        assert step.to_dict() == {"kind": "filter", "filter_expr": "x eq 1"}

    def test_pipeline_roundtrip(self) -> None:
        step = AggregateStep(
            items=[AggregateItem(column="t", method="sum", alias="R")]
        )
        p = ApplyPipeline(steps=[step])
        d = p.to_dict()
        assert d == {"steps": [step.to_dict()]}


class TestHelpers:
    def test_is_identifier_empty(self) -> None:
        assert not _is_identifier("")

    def test_is_identifier_starts_with_digit(self) -> None:
        assert not _is_identifier("1abc")

    def test_is_identifier_contains_dash(self) -> None:
        assert not _is_identifier("a-b")

    def test_is_identifier_underscore_start(self) -> None:
        assert _is_identifier("_foo")

    def test_split_top_level_closing_without_opening(self) -> None:
        with pytest.raises(ValueError, match="Unbalanced '\\)'"):
            _split_top_level("a),b", ",")

    def test_split_top_level_unclosed_opening(self) -> None:
        with pytest.raises(ValueError, match="Unbalanced '\\('"):
            _split_top_level("a(,b", ",")

    def test_split_top_level_respects_escaped_quote(self) -> None:
        parts = _split_top_level("'a''b',x", ",")
        assert parts == ["'a''b'", "x"]
