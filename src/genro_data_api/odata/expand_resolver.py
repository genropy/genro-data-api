# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 $expand expression resolver.

Parses and validates $expand expressions, returning a dict of navigation
property names to their nested QueryOptions.

Supported formats:
  Simple:   Orders
  Multiple: Orders,Category
  Nested:   Orders($select=id,total;$filter=amount gt 100;$top=5)
"""

from __future__ import annotations

from genro_data_api.core.backend import QueryOptions


class ExpandResolver:
    """Parses OData $expand strings and validates against entity metadata."""

    def resolve(self, expand_string: str, entity_metadata: dict) -> dict[str, QueryOptions]:
        """Parse a $expand string and return per-navigation QueryOptions.

        Args:
            expand_string: OData $expand value (e.g. "Orders,Category($select=id)").
            entity_metadata: Metadata dict for the parent entity (from backend).
                Must contain a 'navigation' list with 'name' keys.

        Returns:
            Mapping of navigation property name to QueryOptions.

        Raises:
            ValueError: If a referenced navigation property does not exist.
        """
        if not expand_string.strip():
            return {}

        nav_names: set[str] = {
            nav["name"] for nav in entity_metadata.get("navigation", [])
        }
        items = self._split_top_level(expand_string)
        result: dict[str, QueryOptions] = {}

        for item in items:
            item = item.strip()
            if not item:
                continue
            name, nested_str = self._split_name_options(item)
            if name not in nav_names:
                raise ValueError(
                    f"Unknown navigation property: {name!r}. "
                    f"Available: {sorted(nav_names)}"
                )
            result[name] = self._parse_nested_options(nested_str) if nested_str else QueryOptions()

        return result

    def _split_top_level(self, s: str) -> list[str]:
        """Split by comma, ignoring commas inside nested parentheses."""
        parts: list[str] = []
        depth = 0
        start = 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(s[start:i])
                start = i + 1
        parts.append(s[start:])
        return parts

    def _split_name_options(self, item: str) -> tuple[str, str]:
        """Split 'NavName(options)' into ('NavName', 'options')."""
        paren_pos = item.find("(")
        if paren_pos == -1:
            return item.strip(), ""
        name = item[:paren_pos].strip()
        # Remove outer parens: item[paren_pos] == '(' and item[-1] == ')'
        options_str = item[paren_pos + 1 : -1]
        return name, options_str

    def _parse_nested_options(self, options_str: str) -> QueryOptions:
        """Parse semicolon-separated OData system query options from $expand."""
        opts = QueryOptions()
        for part in options_str.split(";"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("$select="):
                opts.select = [f.strip() for f in part[len("$select=") :].split(",")]
            elif part.startswith("$filter="):
                opts.filter_expr = part[len("$filter=") :]
            elif part.startswith("$orderby="):
                opts.order_by = self._parse_orderby(part[len("$orderby=") :])
            elif part.startswith("$top="):
                opts.top = int(part[len("$top=") :])
            elif part.startswith("$skip="):
                opts.skip = int(part[len("$skip=") :])
            elif part.startswith("$count="):
                opts.count = part[len("$count=") :].lower() == "true"
        return opts

    def _parse_orderby(self, orderby_str: str) -> list[tuple[str, str]]:
        """Parse '$orderby' value into list of (field, direction) tuples."""
        result: list[tuple[str, str]] = []
        for item in orderby_str.split(","):
            parts = item.strip().split()
            if len(parts) == 1:
                result.append((parts[0], "asc"))
            elif len(parts) == 2:
                direction = parts[1].lower()
                if direction not in ("asc", "desc"):
                    raise ValueError(f"Invalid orderby direction: {parts[1]!r}")
                result.append((parts[0], direction))
            else:
                raise ValueError(f"Invalid orderby clause: {item!r}")
        return result
