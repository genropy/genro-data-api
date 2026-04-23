# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for ODataResponseFormatter."""

from __future__ import annotations

import pytest

from genro_data_api.core.backend import DataApiBackend, QueryResult
from genro_data_api.odata.response import ODataResponseFormatter


@pytest.fixture
def formatter() -> ODataResponseFormatter:
    return ODataResponseFormatter()


@pytest.fixture
def result_3() -> QueryResult:
    return QueryResult(
        records=[
            {"id": 1, "name": "Alice Corp"},
            {"id": 2, "name": "Bob Ltd"},
            {"id": 3, "name": "Charlie GmbH"},
        ]
    )


@pytest.fixture
def result_with_count() -> QueryResult:
    return QueryResult(
        records=[{"id": 1, "name": "Alice Corp"}, {"id": 2, "name": "Bob Ltd"}],
        total_count=10,
    )


class TestFormatCollection:
    def test_basic_structure(
        self, formatter: ODataResponseFormatter, result_3: QueryResult
    ) -> None:
        payload = formatter.format_collection("customer", result_3, "/odata")
        assert "@odata.context" in payload
        assert "value" in payload

    def test_context_url(
        self, formatter: ODataResponseFormatter, result_3: QueryResult
    ) -> None:
        payload = formatter.format_collection("customer", result_3, "/odata")
        assert payload["@odata.context"] == "/odata/$metadata#customer"

    def test_records_in_value(
        self, formatter: ODataResponseFormatter, result_3: QueryResult
    ) -> None:
        payload = formatter.format_collection("customer", result_3, "/odata")
        assert len(payload["value"]) == 3
        assert payload["value"][0]["name"] == "Alice Corp"

    def test_no_count_when_not_requested(
        self, formatter: ODataResponseFormatter, result_3: QueryResult
    ) -> None:
        payload = formatter.format_collection("customer", result_3, "/odata")
        assert "@odata.count" not in payload

    def test_count_included_when_present(
        self, formatter: ODataResponseFormatter, result_with_count: QueryResult
    ) -> None:
        payload = formatter.format_collection("customer", result_with_count, "/odata")
        assert payload["@odata.count"] == 10

    def test_no_next_link_without_top(
        self, formatter: ODataResponseFormatter, result_with_count: QueryResult
    ) -> None:
        payload = formatter.format_collection("customer", result_with_count, "/odata")
        assert "@odata.nextLink" not in payload

    def test_next_link_when_more_pages(
        self, formatter: ODataResponseFormatter, result_with_count: QueryResult
    ) -> None:
        # top=2, skip=0, total=10 → nextLink points to the next page via
        # an opaque $skiptoken (offset-based under the hood).
        payload = formatter.format_collection(
            "customer", result_with_count, "/odata", skip=0, top=2
        )
        assert "@odata.nextLink" in payload
        assert "$skiptoken=" in payload["@odata.nextLink"]
        # The token encodes skip=2, top=2 so the client round-trips the
        # right offset on the next request.
        from genro_data_api.odata.skiptoken import decode
        token = payload["@odata.nextLink"].split("$skiptoken=", 1)[1]
        state = decode(token)
        assert state["skip"] == 2
        assert state["top"] == 2

    def test_no_next_link_on_last_page(
        self, formatter: ODataResponseFormatter, result_with_count: QueryResult
    ) -> None:
        # top=2, skip=8, total=10 → no nextLink (8+2=10, not < 10)
        result = QueryResult(records=[{"id": 9}, {"id": 10}], total_count=10)
        payload = formatter.format_collection("customer", result, "/odata", skip=8, top=2)
        assert "@odata.nextLink" not in payload

    def test_next_link_includes_entity_name(
        self, formatter: ODataResponseFormatter, result_with_count: QueryResult
    ) -> None:
        payload = formatter.format_collection(
            "customer", result_with_count, "/odata", skip=0, top=2
        )
        assert "customer" in payload["@odata.nextLink"]

    def test_no_next_link_without_total_count(
        self, formatter: ODataResponseFormatter
    ) -> None:
        result = QueryResult(records=[{"id": 1}])
        payload = formatter.format_collection("customer", result, "/odata", skip=0, top=5)
        assert "@odata.nextLink" not in payload


class TestFormatEntity:
    def test_context_url(self, formatter: ODataResponseFormatter) -> None:
        record = {"id": 1, "name": "Alice Corp"}
        payload = formatter.format_entity("customer", record, "/odata")
        assert payload["@odata.context"] == "/odata/$metadata#customer/$entity"

    def test_record_fields_present(self, formatter: ODataResponseFormatter) -> None:
        record = {"id": 1, "name": "Alice Corp", "country": "IT"}
        payload = formatter.format_entity("customer", record, "/odata")
        assert payload["id"] == 1
        assert payload["name"] == "Alice Corp"
        assert payload["country"] == "IT"

    def test_no_extra_fields(self, formatter: ODataResponseFormatter) -> None:
        record = {"id": 42}
        payload = formatter.format_entity("order", record, "/odata")
        assert set(payload.keys()) == {"@odata.context", "id"}


class TestFormatMetadataJson:
    def test_returns_dict(
        self, formatter: ODataResponseFormatter, mock_backend: DataApiBackend
    ) -> None:
        result = formatter.format_metadata_json(mock_backend)
        assert isinstance(result, dict)

    def test_version_present(
        self, formatter: ODataResponseFormatter, mock_backend: DataApiBackend
    ) -> None:
        result = formatter.format_metadata_json(mock_backend)
        assert result.get("$Version") == "4.0"

    def test_entity_container_present(
        self, formatter: ODataResponseFormatter, mock_backend: DataApiBackend
    ) -> None:
        result = formatter.format_metadata_json(mock_backend)
        assert "$EntityContainer" in result

    def test_entity_types_present(
        self, formatter: ODataResponseFormatter, mock_backend: DataApiBackend
    ) -> None:
        result = formatter.format_metadata_json(mock_backend)
        assert "Default.customer" in result
        assert "Default.order" in result
