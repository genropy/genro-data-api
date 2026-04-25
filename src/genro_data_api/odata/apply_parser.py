# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 $apply expression parser.

Parses OData $apply strings into an ApplyPipeline AST. Supported
transformations: ``filter``, ``groupby``, ``aggregate``. The pipeline
is applied left-to-right, separated by ``/``.

Aggregation methods: ``sum``, ``average``, ``min``, ``max``,
``countdistinct``, and the special ``$count`` form used without a
column name.

Example strings accepted::

    aggregate(total with sum as Revenue)
    aggregate($count as N)
    groupby((state))
    groupby((state), aggregate(total with sum as GrandTotal))
    filter(year(date) eq 2024)/groupby((customer_id), aggregate($count as N))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


@dataclass
class AggregateItem:
    """One aggregation entry inside an aggregate(...) step."""

    column: str | None  # None when method == 'count' ($count form)
    method: str         # 'sum' | 'average' | 'min' | 'max' | 'countdistinct' | 'count'
    alias: str

    def to_dict(self) -> dict[str, Any]:
        return {"column": self.column, "method": self.method, "alias": self.alias}


@dataclass
class AggregateStep:
    """An ``aggregate(...)`` transformation."""

    items: list[AggregateItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "aggregate", "items": [i.to_dict() for i in self.items]}


@dataclass
class GroupByStep:
    """A ``groupby((keys), aggregate(...))`` transformation.

    When no aggregate is nested, the inner ``aggregate`` field is None and
    the result is just the distinct tuples of the grouping keys.
    """

    keys: list[str] = field(default_factory=list)
    aggregate: AggregateStep | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "groupby",
            "keys": list(self.keys),
            "aggregate": self.aggregate.to_dict() if self.aggregate else None,
        }


@dataclass
class FilterStep:
    """A ``filter(<$filter expression>)`` transformation.

    The body is kept as a raw string; the backend re-parses it with the
    regular ODataFilterParser so the full filter grammar is available.
    """

    filter_expr: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "filter", "filter_expr": self.filter_expr}


ApplyStep = AggregateStep | GroupByStep | FilterStep


@dataclass
class ApplyPipeline:
    """An ordered list of $apply transformations."""

    steps: list[ApplyStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [s.to_dict() for s in self.steps]}

    def result_columns(self) -> list[str]:
        """Names of the columns appearing in the final result.

        Used by the response formatter to build the ``@odata.context``
        projection clause ``#EntitySet(col1,col2,...)``.

        The shape is dictated by the **last** shape-producing step in
        the pipeline (``groupby`` or ``aggregate``); any earlier
        shape-producing step is rolled up by the later one, matching
        OData ``$apply`` semantics:

        - ``aggregate(...)`` collapses the input to a single row whose
          columns are the aliases; any prior grouping is dropped.
        - ``groupby((keys), aggregate(...))`` emits one row per group,
          columns = keys plus the inner aggregate aliases.
        - ``groupby((keys))`` with no inner aggregate emits distinct
          tuples of the keys.

        Pipelines made only of ``filter`` steps produce no new shape
        and return an empty list; callers should keep the input
        entity's native columns in that case.
        """
        for step in reversed(self.steps):
            if isinstance(step, AggregateStep):
                return [i.alias for i in step.items]
            if isinstance(step, GroupByStep):
                cols = list(step.keys)
                if step.aggregate:
                    cols.extend(i.alias for i in step.aggregate.items)
                return cols
        return []


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


_AGGREGATION_METHODS: frozenset[str] = frozenset(
    {"sum", "average", "min", "max", "countdistinct"}
)


class ODataApplyParser:
    """Parses an OData v4 ``$apply`` pipeline string into an ApplyPipeline."""

    def __init__(self) -> None:
        self._text: str = ""
        self._pos: int = 0

    def parse(self, apply_string: str) -> ApplyPipeline:
        """Parse an OData ``$apply`` string."""
        stripped = apply_string.strip()
        if not stripped:
            raise ValueError("Empty $apply expression")
        self._text = stripped
        self._pos = 0
        steps: list[ApplyStep] = []
        steps.append(self._parse_step())
        while self._peek() == "/":
            self._advance()  # consume '/'
            steps.append(self._parse_step())
        if self._pos < len(self._text):
            raise ValueError(
                f"Unexpected trailing input in $apply: {self._text[self._pos:]!r}"
            )
        return ApplyPipeline(steps=steps)

    # ------------------------------------------------------------------
    # Cursor helpers
    # ------------------------------------------------------------------

    def _peek(self) -> str | None:
        self._skip_whitespace()
        if self._pos < len(self._text):
            return self._text[self._pos]
        return None

    def _advance(self) -> str:
        ch = self._text[self._pos]
        self._pos += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self._pos < len(self._text) and self._text[self._pos].isspace():
            self._pos += 1

    def _read_identifier(self) -> str:
        self._skip_whitespace()
        start = self._pos
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch.isalnum() or ch in "_$":
                self._pos += 1
            else:
                break
        if start == self._pos:
            raise ValueError(
                f"Expected identifier at position {start} of $apply"
            )
        return self._text[start:self._pos]

    def _read_balanced_parens(self) -> str:
        """Read content between matching outer parens, consuming both.

        Respects nested parentheses and single-quoted strings (with OData
        escape ``''`` for embedded quotes).
        """
        self._skip_whitespace()
        if self._pos >= len(self._text) or self._text[self._pos] != "(":
            raise ValueError(
                f"Expected '(' at position {self._pos} of $apply"
            )
        self._pos += 1
        start = self._pos
        depth = 1
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch == "'":
                # skip over quoted literal, honouring '' escape
                self._pos += 1
                while self._pos < len(self._text):
                    if self._text[self._pos] == "'":
                        if (
                            self._pos + 1 < len(self._text)
                            and self._text[self._pos + 1] == "'"
                        ):
                            self._pos += 2
                        else:
                            self._pos += 1
                            break
                    else:
                        self._pos += 1
            elif ch == "(":
                depth += 1
                self._pos += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    body = self._text[start:self._pos]
                    self._pos += 1
                    return body
                self._pos += 1
            else:
                self._pos += 1
        raise ValueError("Unbalanced '(' in $apply")

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _parse_step(self) -> ApplyStep:
        name = self._read_identifier()
        if name == "filter":
            return self._parse_filter_step()
        if name == "aggregate":
            return self._parse_aggregate_step()
        if name == "groupby":
            return self._parse_groupby_step()
        raise ValueError(f"Unsupported $apply transformation: {name!r}")

    def _parse_filter_step(self) -> FilterStep:
        body = self._read_balanced_parens().strip()
        if not body:
            raise ValueError("Empty filter() body")
        return FilterStep(filter_expr=body)

    def _parse_aggregate_step(self) -> AggregateStep:
        body = self._read_balanced_parens().strip()
        if not body:
            raise ValueError("Empty aggregate() body")
        items = [self._parse_aggregate_item(part) for part in _split_top_level(body, ",")]
        return AggregateStep(items=items)

    def _parse_aggregate_item(self, raw: str) -> AggregateItem:
        raw = raw.strip()
        if not raw:
            raise ValueError("Empty aggregate entry")
        # Two forms:
        #   '$count as Alias'
        #   'column with method as Alias'
        if raw.startswith("$count"):
            rest = raw[len("$count"):].strip()
            alias = _parse_as_alias(rest)
            return AggregateItem(column=None, method="count", alias=alias)
        # column with method as Alias
        parts = raw.split()
        # Expected shape: [column, 'with', method, 'as', alias]
        if len(parts) < 5 or parts[1] != "with" or parts[3] != "as":
            raise ValueError(
                f"Invalid aggregate entry {raw!r}; expected "
                "'column with method as alias' or '$count as alias'"
            )
        column, _with, method, _as, *alias_parts = parts
        alias = " ".join(alias_parts)
        if method not in _AGGREGATION_METHODS:
            raise ValueError(
                f"Unsupported aggregation method {method!r}. "
                f"Supported: {sorted(_AGGREGATION_METHODS)} or $count"
            )
        if not _is_identifier(column):
            raise ValueError(
                f"Invalid column name in aggregate(): {column!r}"
            )
        if not _is_identifier(alias):
            raise ValueError(f"Invalid alias in aggregate(): {alias!r}")
        return AggregateItem(column=column, method=method, alias=alias)

    def _parse_groupby_step(self) -> GroupByStep:
        body = self._read_balanced_parens().strip()
        if not body:
            raise ValueError("Empty groupby() body")
        parts = _split_top_level(body, ",")
        # First part is '(key1, key2, ...)'; the optional second part is
        # an aggregate(...) transformation.
        keys_raw = parts[0].strip()
        if not (keys_raw.startswith("(") and keys_raw.endswith(")")):
            raise ValueError(
                f"groupby keys must be enclosed in parentheses, got {keys_raw!r}"
            )
        inner = keys_raw[1:-1].strip()
        if not inner:
            raise ValueError("Empty groupby key list")
        keys = [k.strip() for k in _split_top_level(inner, ",")]
        for k in keys:
            if not _is_identifier(k):
                raise ValueError(f"Invalid groupby key: {k!r}")
        aggregate: AggregateStep | None = None
        if len(parts) == 2:
            second = parts[1].strip()
            if not second.startswith("aggregate("):
                raise ValueError(
                    "Second argument of groupby() must be aggregate(...), "
                    f"got {second!r}"
                )
            inner_body = second[len("aggregate("): -1].strip()
            if not inner_body:
                raise ValueError("Empty aggregate() inside groupby")
            items = [
                self._parse_aggregate_item(part)
                for part in _split_top_level(inner_body, ",")
            ]
            aggregate = AggregateStep(items=items)
        elif len(parts) > 2:
            raise ValueError(
                "groupby() accepts at most two arguments: keys and an optional aggregate"
            )
        return GroupByStep(keys=keys, aggregate=aggregate)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_identifier(token: str) -> bool:
    if not token:
        return False
    first = token[0]
    if not (first.isalpha() or first == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in token)


def _parse_as_alias(rest: str) -> str:
    parts = rest.strip().split()
    if len(parts) != 2 or parts[0] != "as":
        raise ValueError(
            f"Expected 'as <alias>' after $count, got {rest!r}"
        )
    alias = parts[1]
    if not _is_identifier(alias):
        raise ValueError(f"Invalid alias {alias!r}")
    return alias


def _split_top_level(text: str, separator: str) -> list[str]:
    """Split ``text`` on ``separator``, ignoring occurrences inside parentheses or quotes."""
    result: list[str] = []
    depth = 0
    start = 0
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "'":
            i += 1
            while i < length:
                if text[i] == "'":
                    if i + 1 < length and text[i + 1] == "'":
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                raise ValueError("Unbalanced ')' while splitting $apply body")
            depth -= 1
        elif ch == separator and depth == 0:
            result.append(text[start:i])
            start = i + 1
        i += 1
    if depth != 0:
        raise ValueError("Unbalanced '(' while splitting $apply body")
    result.append(text[start:])
    return result
