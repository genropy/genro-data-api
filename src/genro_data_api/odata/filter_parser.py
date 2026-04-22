# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 $filter expression parser.

Parses OData filter strings into a FilterNode tree.

Supported comparison operators: eq, ne, gt, ge, lt, le, in.
Supported logical operators: and, or, not.
Supported boolean functions: contains(), startswith(), endswith().
Supported scalar (value-returning) functions:
    tolower, toupper, trim, length, indexof, substring, concat,
    year, month, day, hour, minute, second, date, now,
    round, floor, ceiling,
    cast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FilterNode:
    """Base class for filter tree nodes."""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Expression nodes — values and function calls used as operands
# ---------------------------------------------------------------------------


@dataclass
class FunctionCallNode:
    """A scalar function call used as an expression operand.

    e.g. year(data), tolower(name), substring(name, 0, 3).
    Distinguished from FunctionNode which models boolean string predicates.
    """

    name: str
    args: list[Expression] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "fncall",
            "name": self.name,
            "args": [_expr_to_dict(a) for a in self.args],
        }


Expression = str | int | float | bool | None | FunctionCallNode


def _expr_to_dict(expr: Expression) -> Any:
    if isinstance(expr, FunctionCallNode):
        return expr.to_dict()
    return expr


# ---------------------------------------------------------------------------
# Predicate nodes — boolean conditions
# ---------------------------------------------------------------------------


@dataclass
class ComparisonNode(FilterNode):
    """A left op value comparison (e.g. name eq 'Alice', year(data) eq 2024).

    ``field`` accepts a bare column name for backward compatibility, or a
    ``FunctionCallNode`` when the left side is a scalar function expression.
    ``value`` accepts a literal or a ``FunctionCallNode`` such as ``now()``.
    """

    field: str | FunctionCallNode
    op: str
    value: str | int | float | bool | None | FunctionCallNode

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "comparison",
            "field": _expr_to_dict(self.field),
            "op": self.op,
            "value": _expr_to_dict(self.value),
        }


@dataclass
class InNode(FilterNode):
    """Membership test: field in (v1, v2, ...)."""

    field: str | FunctionCallNode
    values: list[str | int | float | bool | None] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "in",
            "field": _expr_to_dict(self.field),
            "values": list(self.values),
        }


@dataclass
class LogicalNode(FilterNode):
    """A logical AND / OR / NOT node."""

    op: str
    children: list[FilterNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "logical",
            "op": self.op,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class FunctionNode(FilterNode):
    """A boolean string predicate: contains(), startswith(), endswith()."""

    name: str
    field: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "field": self.field,
            "value": self.value,
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class ODataFilterParser:
    """Parses OData v4 $filter expressions into a FilterNode tree."""

    _COMPARISON_OPS: frozenset[str] = frozenset({"eq", "ne", "gt", "ge", "lt", "le"})

    # Functions that appear as boolean predicates (standalone).
    _BOOLEAN_FUNCTIONS: frozenset[str] = frozenset(
        {"contains", "startswith", "endswith"}
    )

    # Functions that return a value and appear as operands in comparisons.
    _SCALAR_FUNCTIONS: frozenset[str] = frozenset(
        {
            # string
            "tolower", "toupper", "trim", "length", "indexof", "substring", "concat",
            # date/time
            "year", "month", "day", "hour", "minute", "second", "date", "now",
            # math
            "round", "floor", "ceiling",
            # type
            "cast",
        }
    )

    def __init__(self) -> None:
        self._tokens: list[str] = []
        self._pos: int = 0

    def parse(self, filter_string: str) -> FilterNode:
        """Parse an OData $filter string into a FilterNode tree."""
        stripped = filter_string.strip()
        if not stripped:
            raise ValueError("Empty filter expression")
        self._tokens = self._tokenize(stripped)
        self._pos = 0
        result = self._parse_or()
        if self._pos < len(self._tokens):
            tok = self._tokens[self._pos]
            raise ValueError(f"Unexpected token: {tok!r}")
        return result

    # ------------------------------------------------------------------
    # Tokenizer
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        i = 0
        length = len(text)
        while i < length:
            ch = text[i]
            if ch.isspace():
                i += 1
                continue
            if ch == "'":
                # single-quoted string literal; '' is an escaped single quote
                j = i + 1
                while j < length:
                    if text[j] == "'":
                        if j + 1 < length and text[j + 1] == "'":
                            j += 2
                        else:
                            j += 1
                            break
                    else:
                        j += 1
                tokens.append(text[i:j])
                i = j
            elif ch in "(),":
                tokens.append(ch)
                i += 1
            elif ch.isdigit() or (ch == "-" and i + 1 < length and text[i + 1].isdigit()):
                j = i + 1
                while j < length and (text[j].isdigit() or text[j] == "."):
                    j += 1
                tokens.append(text[i:j])
                i = j
            elif ch.isalpha() or ch == "_":
                j = i + 1
                while j < length and (text[j].isalnum() or text[j] in "_./"):
                    j += 1
                tokens.append(text[i:j])
                i = j
            else:
                raise ValueError(f"Unexpected character {ch!r} at position {i}")
        return tokens

    # ------------------------------------------------------------------
    # Recursive descent entry points
    # ------------------------------------------------------------------

    def _peek(self, offset: int = 0) -> str | None:
        idx = self._pos + offset
        if idx < len(self._tokens):
            return self._tokens[idx]
        return None

    def _consume(self) -> str:
        if self._pos >= len(self._tokens):
            raise ValueError("Unexpected end of filter expression")
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, expected: str) -> str:
        tok = self._consume()
        if tok != expected:
            raise ValueError(f"Expected {expected!r}, got {tok!r}")
        return tok

    @staticmethod
    def _field_ref(token: str) -> str:
        """Convert a raw identifier token into a GenroPy field reference.

        A plain column name ``name`` becomes ``$name``; a navigation path
        such as ``cliente_id/descr`` becomes ``@cliente_id.descr`` to match
        GenroPy's query syntax for following relationships.
        """
        if "/" in token:
            return "@" + token.replace("/", ".")
        return "$" + token

    def _parse_or(self) -> FilterNode:
        nodes: list[FilterNode] = [self._parse_and()]
        while self._peek() == "or":
            self._consume()
            nodes.append(self._parse_and())
        if len(nodes) == 1:
            return nodes[0]
        return LogicalNode(op="or", children=nodes)

    def _parse_and(self) -> FilterNode:
        nodes: list[FilterNode] = [self._parse_not()]
        while self._peek() == "and":
            self._consume()
            nodes.append(self._parse_not())
        if len(nodes) == 1:
            return nodes[0]
        return LogicalNode(op="and", children=nodes)

    def _parse_not(self) -> FilterNode:
        if self._peek() == "not":
            self._consume()
            child = self._parse_primary()
            return LogicalNode(op="not", children=[child])
        return self._parse_primary()

    def _parse_primary(self) -> FilterNode:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok == "(":
            self._consume()
            node = self._parse_or()
            self._expect(")")
            return node
        if tok in self._BOOLEAN_FUNCTIONS:
            return self._parse_boolean_function()
        return self._parse_predicate()

    # ------------------------------------------------------------------
    # Predicates: comparisons, in-membership, boolean functions
    # ------------------------------------------------------------------

    def _parse_boolean_function(self) -> FunctionNode:
        name = self._consume()
        self._expect("(")
        field_name = self._field_ref(self._consume())
        self._expect(",")
        val = self._parse_literal()
        if not isinstance(val, str):
            raise ValueError(
                f"Function {name!r} requires a string argument, got {val!r}"
            )
        self._expect(")")
        return FunctionNode(name=name, field=field_name, value=val)

    def _parse_predicate(self) -> FilterNode:
        """Parse a single predicate: <expr> (eq|ne|...|in) <value-or-list>."""
        left = self._parse_expression()
        op_tok = self._consume()
        if op_tok == "in":
            return self._parse_in(left)
        if op_tok not in self._COMPARISON_OPS:
            raise ValueError(f"Unknown comparison operator: {op_tok!r}")
        value = self._parse_value_or_call()
        return ComparisonNode(field=left, op=op_tok, value=value)

    def _parse_value_or_call(self) -> str | int | float | bool | None | FunctionCallNode:
        tok = self._peek()
        if tok is not None and tok in self._SCALAR_FUNCTIONS and self._peek(1) == "(":
            return self._parse_function_call()
        return self._parse_literal()

    def _parse_in(self, left: str | FunctionCallNode) -> InNode:
        self._expect("(")
        values: list[str | int | float | bool | None] = []
        if self._peek() != ")":
            values.append(self._parse_literal())
            while self._peek() == ",":
                self._consume()
                values.append(self._parse_literal())
        self._expect(")")
        if not values:
            raise ValueError("'in' operator requires at least one value")
        return InNode(field=left, values=values)

    # ------------------------------------------------------------------
    # Expressions: field refs and scalar function calls
    # ------------------------------------------------------------------

    def _parse_expression(self) -> str | FunctionCallNode:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok in self._SCALAR_FUNCTIONS and self._peek(1) == "(":
            return self._parse_function_call()
        return self._field_ref(self._consume())

    def _parse_function_call(self) -> FunctionCallNode:
        name = self._consume()
        self._expect("(")
        args: list[Expression] = []
        if self._peek() != ")":
            args.append(self._parse_argument())
            while self._peek() == ",":
                self._consume()
                args.append(self._parse_argument())
        self._expect(")")
        return FunctionCallNode(name=name, args=args)

    def _parse_argument(self) -> Expression:
        """A function argument may be a literal, a field ref, or a nested call."""
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok in self._SCALAR_FUNCTIONS and self._peek(1) == "(":
            return self._parse_function_call()
        if tok[0] == "'" or tok in ("true", "false", "null") or tok[0].isdigit() or tok[0] == "-":
            return self._parse_literal()
        # bare identifier — treat as field reference
        return self._field_ref(self._consume())

    # ------------------------------------------------------------------
    # Literals
    # ------------------------------------------------------------------

    def _parse_literal(self) -> str | int | float | bool | None:
        tok = self._consume()
        if tok.startswith("'"):
            return tok[1:-1].replace("''", "'")
        if tok == "true":
            return True
        if tok == "false":
            return False
        if tok == "null":
            return None
        try:
            if "." in tok:
                return float(tok)
            return int(tok)
        except ValueError:
            raise ValueError(f"Cannot parse literal value: {tok!r}") from None
