# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 $filter expression parser.

Parses OData filter strings into a FilterNode tree.
Supports: eq, ne, gt, ge, lt, le, and, or, not,
contains(), startswith(), endswith().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FilterNode:
    """Base class for filter tree nodes."""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class ComparisonNode(FilterNode):
    """A field op value comparison (e.g. name eq 'Alice')."""

    field: str
    op: str
    value: str | int | float | bool | None

    def to_dict(self) -> dict[str, Any]:
        return {"type": "comparison", "field": self.field, "op": self.op, "value": self.value}


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
    """A string function call: contains(), startswith(), endswith()."""

    name: str
    field: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "function", "name": self.name, "field": self.field, "value": self.value}


class ODataFilterParser:
    """Parses OData v4 $filter expressions into a FilterNode tree."""

    _COMPARISON_OPS: frozenset[str] = frozenset({"eq", "ne", "gt", "ge", "lt", "le"})
    _FUNCTION_NAMES: frozenset[str] = frozenset({"contains", "startswith", "endswith"})

    def __init__(self) -> None:
        self._tokens: list[str] = []
        self._pos: int = 0

    def parse(self, filter_string: str) -> FilterNode:
        """Parse an OData $filter string into a FilterNode tree.

        Args:
            filter_string: OData filter expression (e.g. "name eq 'Alice'").

        Returns:
            Root FilterNode of the parsed tree.

        Raises:
            ValueError: If the expression is empty, invalid, or malformed.
        """
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

    def _peek(self) -> str | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
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
        if tok in self._FUNCTION_NAMES:
            return self._parse_function()
        return self._parse_comparison()

    def _parse_function(self) -> FunctionNode:
        name = self._consume()
        self._expect("(")
        field_name = self._consume()
        self._expect(",")
        val = self._parse_value()
        if not isinstance(val, str):
            raise ValueError(f"Function {name!r} requires a string argument, got {val!r}")
        self._expect(")")
        return FunctionNode(name=name, field=field_name, value=val)

    def _parse_comparison(self) -> ComparisonNode:
        field_name = self._consume()
        op = self._consume()
        if op not in self._COMPARISON_OPS:
            raise ValueError(f"Unknown comparison operator: {op!r}")
        val = self._parse_value()
        return ComparisonNode(field=field_name, op=op, value=val)

    def _parse_value(self) -> str | int | float | bool | None:
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
