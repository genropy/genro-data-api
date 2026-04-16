# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Type mapping from GenroPy dtype codes to standard type systems.

Single source of truth for translating GenroPy column types to:
- OData Edm types (for CSDL metadata and response serialization)
- GraphQL scalar types (future)
- Python native types (for validation and testing)

GenroPy dtype codes are single letters (or short codes) defined in
the ORM model. This module maps them to their equivalents in each
target type system.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TypeMapping:
    """Mapping for a single GenroPy dtype to target type systems."""

    gnr_dtype: str
    """GenroPy dtype code (e.g. 'A', 'N', 'I', 'D')."""

    edm_type: str
    """OData Edm type (e.g. 'Edm.String', 'Edm.Int32')."""

    python_type: type
    """Python native type for validation."""

    description: str
    """Human-readable description of the GenroPy type."""

    graphql_type: str = "String"
    """GraphQL scalar type (future use)."""


# Master type mapping table
_TYPE_MAP: dict[str, TypeMapping] = {}


def _register(gnr_dtype: str, edm_type: str, python_type: type,
              description: str, graphql_type: str = "String") -> None:
    _TYPE_MAP[gnr_dtype] = TypeMapping(
        gnr_dtype=gnr_dtype,
        edm_type=edm_type,
        python_type=python_type,
        description=description,
        graphql_type=graphql_type,
    )


# Text types
_register("A", "Edm.String", str, "Text (varchar)")
_register("T", "Edm.String", str, "Text (long)")
_register("C", "Edm.String", str, "Character (fixed length)")
_register("P", "Edm.String", str, "Pickle (serialized)")
_register("X", "Edm.String", str, "XML / Bag")
_register("Z", "Edm.String", str, "Compressed text")
_register("NU", "Edm.String", str, "Unformatted number (stored as text)")

# Numeric types
_register("N", "Edm.Decimal", float, "Numeric (decimal)", "Float")
_register("I", "Edm.Int32", int, "Integer (32-bit)", "Int")
_register("L", "Edm.Int64", int, "Long integer (64-bit)", "Int")
_register("R", "Edm.Double", float, "Real (double precision)", "Float")
_register("SERIAL", "Edm.Int64", int, "Auto-increment serial", "Int")

# Boolean
_register("B", "Edm.Boolean", bool, "Boolean", "Boolean")

# Date/Time types
_register("D", "Edm.Date", str, "Date (YYYY-MM-DD)", "String")
_register("DH", "Edm.DateTimeOffset", str, "Datetime with time", "String")
_register("DHZ", "Edm.DateTimeOffset", str, "Datetime with timezone", "String")
_register("H", "Edm.TimeOfDay", str, "Time (HH:MM:SS)", "String")

# Binary
_register("O", "Edm.Binary", bytes, "Binary / Blob", "String")


def get_type_mapping(gnr_dtype: str) -> TypeMapping:
    """Get the type mapping for a GenroPy dtype code.

    Args:
        gnr_dtype: GenroPy dtype code (e.g. 'A', 'N', 'I').

    Returns:
        TypeMapping with all target type equivalents.

    Raises:
        KeyError: If the dtype code is unknown.
    """
    return _TYPE_MAP[gnr_dtype]


def get_edm_type(gnr_dtype: str, fallback: str = "Edm.String") -> str:
    """Get the OData Edm type for a GenroPy dtype code.

    Args:
        gnr_dtype: GenroPy dtype code.
        fallback: Edm type to return if dtype is unknown.

    Returns:
        OData Edm type string (e.g. 'Edm.String', 'Edm.Int32').
    """
    mapping = _TYPE_MAP.get(gnr_dtype)
    if mapping is None:
        return fallback
    return mapping.edm_type


def get_graphql_type(gnr_dtype: str, fallback: str = "String") -> str:
    """Get the GraphQL scalar type for a GenroPy dtype code.

    Args:
        gnr_dtype: GenroPy dtype code.
        fallback: GraphQL type to return if dtype is unknown.

    Returns:
        GraphQL scalar type string (e.g. 'String', 'Int', 'Float').
    """
    mapping = _TYPE_MAP.get(gnr_dtype)
    if mapping is None:
        return fallback
    return mapping.graphql_type


def all_mappings() -> dict[str, TypeMapping]:
    """Return all registered type mappings.

    Returns:
        Dict of gnr_dtype -> TypeMapping.
    """
    return dict(_TYPE_MAP)
