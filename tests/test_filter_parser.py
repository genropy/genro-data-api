# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for ODataFilterParser."""

from __future__ import annotations

import pytest

from genro_data_api.odata.filter_parser import (
    ComparisonNode,
    FunctionNode,
    LogicalNode,
    ODataFilterParser,
)


@pytest.fixture
def parser() -> ODataFilterParser:
    return ODataFilterParser()


class TestSimpleComparisons:
    def test_string_eq(self, parser: ODataFilterParser) -> None:
        node = parser.parse("name eq 'Alice'")
        assert isinstance(node, ComparisonNode)
        assert node.field == "name"
        assert node.op == "eq"
        assert node.value == "Alice"

    def test_string_ne(self, parser: ODataFilterParser) -> None:
        node = parser.parse("status ne 'inactive'")
        assert isinstance(node, ComparisonNode)
        assert node.op == "ne"
        assert node.value == "inactive"

    def test_int_gt(self, parser: ODataFilterParser) -> None:
        node = parser.parse("age gt 18")
        assert isinstance(node, ComparisonNode)
        assert node.op == "gt"
        assert node.value == 18

    def test_int_ge(self, parser: ODataFilterParser) -> None:
        node = parser.parse("count ge 0")
        assert isinstance(node, ComparisonNode)
        assert node.op == "ge"
        assert node.value == 0

    def test_int_lt(self, parser: ODataFilterParser) -> None:
        node = parser.parse("price lt 100")
        assert isinstance(node, ComparisonNode)
        assert node.op == "lt"

    def test_int_le(self, parser: ODataFilterParser) -> None:
        node = parser.parse("stock le 50")
        assert isinstance(node, ComparisonNode)
        assert node.op == "le"

    def test_float_value(self, parser: ODataFilterParser) -> None:
        node = parser.parse("price gt 3.14")
        assert isinstance(node, ComparisonNode)
        assert node.value == pytest.approx(3.14)

    def test_negative_int(self, parser: ODataFilterParser) -> None:
        node = parser.parse("balance lt -10")
        assert isinstance(node, ComparisonNode)
        assert node.value == -10

    def test_bool_true(self, parser: ODataFilterParser) -> None:
        node = parser.parse("active eq true")
        assert isinstance(node, ComparisonNode)
        assert node.value is True

    def test_bool_false(self, parser: ODataFilterParser) -> None:
        node = parser.parse("active eq false")
        assert isinstance(node, ComparisonNode)
        assert node.value is False

    def test_null_value(self, parser: ODataFilterParser) -> None:
        node = parser.parse("name eq null")
        assert isinstance(node, ComparisonNode)
        assert node.value is None

    def test_escaped_quote_in_string(self, parser: ODataFilterParser) -> None:
        node = parser.parse("name eq 'O''Brien'")
        assert isinstance(node, ComparisonNode)
        assert node.value == "O'Brien"

    def test_navigation_path_field(self, parser: ODataFilterParser) -> None:
        node = parser.parse("Category/Name eq 'Tools'")
        assert isinstance(node, ComparisonNode)
        assert node.field == "Category/Name"


class TestFunctions:
    def test_contains(self, parser: ODataFilterParser) -> None:
        node = parser.parse("contains(name, 'Ali')")
        assert isinstance(node, FunctionNode)
        assert node.name == "contains"
        assert node.field == "name"
        assert node.value == "Ali"

    def test_startswith(self, parser: ODataFilterParser) -> None:
        node = parser.parse("startswith(email, 'admin')")
        assert isinstance(node, FunctionNode)
        assert node.name == "startswith"
        assert node.field == "email"
        assert node.value == "admin"

    def test_endswith(self, parser: ODataFilterParser) -> None:
        node = parser.parse("endswith(email, '.com')")
        assert isinstance(node, FunctionNode)
        assert node.name == "endswith"
        assert node.value == ".com"


class TestLogical:
    def test_and(self, parser: ODataFilterParser) -> None:
        node = parser.parse("age gt 18 and age lt 65")
        assert isinstance(node, LogicalNode)
        assert node.op == "and"
        assert len(node.children) == 2
        assert all(isinstance(c, ComparisonNode) for c in node.children)

    def test_or(self, parser: ODataFilterParser) -> None:
        node = parser.parse("country eq 'IT' or country eq 'US'")
        assert isinstance(node, LogicalNode)
        assert node.op == "or"
        assert len(node.children) == 2

    def test_not(self, parser: ODataFilterParser) -> None:
        node = parser.parse("not (active eq true)")
        assert isinstance(node, LogicalNode)
        assert node.op == "not"
        assert len(node.children) == 1
        child = node.children[0]
        assert isinstance(child, ComparisonNode)
        assert child.value is True

    def test_and_three_terms(self, parser: ODataFilterParser) -> None:
        node = parser.parse("a eq 1 and b eq 2 and c eq 3")
        assert isinstance(node, LogicalNode)
        assert node.op == "and"
        assert len(node.children) == 3

    def test_or_takes_multiple(self, parser: ODataFilterParser) -> None:
        node = parser.parse("x eq 1 or x eq 2 or x eq 3")
        assert isinstance(node, LogicalNode)
        assert node.op == "or"
        assert len(node.children) == 3

    def test_precedence_and_over_or(self, parser: ODataFilterParser) -> None:
        # 'a and b or c' should parse as '(a and b) or c'
        node = parser.parse("a eq 1 and b eq 2 or c eq 3")
        assert isinstance(node, LogicalNode)
        assert node.op == "or"
        left = node.children[0]
        assert isinstance(left, LogicalNode)
        assert left.op == "and"

    def test_parentheses_override_precedence(self, parser: ODataFilterParser) -> None:
        node = parser.parse("a eq 1 and (b eq 2 or c eq 3)")
        assert isinstance(node, LogicalNode)
        assert node.op == "and"
        right = node.children[1]
        assert isinstance(right, LogicalNode)
        assert right.op == "or"

    def test_nested_complex(self, parser: ODataFilterParser) -> None:
        expr = "(age gt 18 and active eq true) or country eq 'IT'"
        node = parser.parse(expr)
        assert isinstance(node, LogicalNode)
        assert node.op == "or"


class TestToDict:
    def test_comparison_to_dict(self, parser: ODataFilterParser) -> None:
        node = parser.parse("name eq 'Alice'")
        d = node.to_dict()
        assert d == {"type": "comparison", "field": "name", "op": "eq", "value": "Alice"}

    def test_logical_to_dict(self, parser: ODataFilterParser) -> None:
        node = parser.parse("a eq 1 and b eq 2")
        d = node.to_dict()
        assert d["type"] == "logical"
        assert d["op"] == "and"
        assert len(d["children"]) == 2

    def test_function_to_dict(self, parser: ODataFilterParser) -> None:
        node = parser.parse("contains(name, 'foo')")
        d = node.to_dict()
        assert d == {"type": "function", "name": "contains", "field": "name", "value": "foo"}


class TestErrors:
    def test_empty_string(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError, match="Empty"):
            parser.parse("")

    def test_whitespace_only(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError, match="Empty"):
            parser.parse("   ")

    def test_unknown_operator(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError, match="operator"):
            parser.parse("name like 'Alice'")

    def test_unexpected_token(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError):
            parser.parse("name eq 'Alice' garbage")

    def test_unclosed_paren(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError):
            parser.parse("(name eq 'Alice'")

    def test_function_non_string_arg(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError, match="string"):
            parser.parse("contains(name, 42)")

    def test_invalid_char(self, parser: ODataFilterParser) -> None:
        with pytest.raises(ValueError, match="Unexpected character"):
            parser.parse("name eq @value")
