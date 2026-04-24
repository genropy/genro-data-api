# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for core type mapping."""

from genro_data_api.core.type_map import (
    all_mappings,
    get_edm_type,
    get_graphql_type,
    get_type_mapping,
)


class TestTypeMap:
    """Type mapping from GenroPy dtype to Edm and GraphQL types."""

    def test_text_types_map_to_edm_string(self):
        for dtype in ("A", "T", "C", "X", "Z", "P"):
            assert get_edm_type(dtype) == "Edm.String"

    def test_integer_maps_to_edm_int32(self):
        assert get_edm_type("I") == "Edm.Int32"

    def test_long_maps_to_edm_int64(self):
        assert get_edm_type("L") == "Edm.Int64"

    def test_numeric_maps_to_edm_decimal(self):
        assert get_edm_type("N") == "Edm.Decimal"

    def test_real_maps_to_edm_double(self):
        assert get_edm_type("R") == "Edm.Double"

    def test_boolean_maps_to_edm_boolean(self):
        assert get_edm_type("B") == "Edm.Boolean"

    def test_date_maps_to_edm_date(self):
        assert get_edm_type("D") == "Edm.Date"

    def test_datetime_maps_to_edm_datetimeoffset(self):
        assert get_edm_type("DH") == "Edm.DateTimeOffset"

    def test_time_maps_to_edm_timeofday(self):
        assert get_edm_type("H") == "Edm.TimeOfDay"

    def test_unknown_dtype_returns_fallback(self):
        assert get_edm_type("UNKNOWN") == "Edm.String"
        assert get_edm_type("UNKNOWN", fallback="Edm.Int32") == "Edm.Int32"

    def test_graphql_integer(self):
        assert get_graphql_type("I") == "Int"

    def test_graphql_numeric(self):
        assert get_graphql_type("N") == "Float"

    def test_graphql_boolean(self):
        assert get_graphql_type("B") == "Boolean"

    def test_graphql_unknown_fallback(self):
        assert get_graphql_type("UNKNOWN") == "String"

    def test_get_type_mapping_returns_dataclass(self):
        m = get_type_mapping("A")
        assert m.gnr_dtype == "A"
        assert m.edm_type == "Edm.String"
        assert m.python_type is str

    def test_get_type_mapping_unknown_raises(self):
        import pytest
        with pytest.raises(KeyError):
            get_type_mapping("NONEXISTENT")

    def test_all_mappings_not_empty(self):
        mappings = all_mappings()
        assert len(mappings) > 10
        assert "A" in mappings
        assert "I" in mappings
