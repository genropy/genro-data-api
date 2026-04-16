# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for ODataRequestHandler."""

from __future__ import annotations

import json

import pytest

from genro_data_api.core.backend import DataApiBackend
from genro_data_api.odata.request_handler import ODataRequestHandler


@pytest.fixture
def handler(mock_backend: DataApiBackend) -> ODataRequestHandler:
    return ODataRequestHandler(mock_backend, service_root="/odata")


class TestMethodRouting:
    def test_post_returns_405(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("POST", "/odata/customer", {})
        assert status == 405

    def test_patch_returns_405(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("PATCH", "/odata/customer", {})
        assert status == 405

    def test_delete_returns_405(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("DELETE", "/odata/customer", {})
        assert status == 405

    def test_405_includes_allow_header(self, handler: ODataRequestHandler) -> None:
        _, headers, _ = handler.handle("POST", "/odata/customer", {})
        assert "Allow" in headers


class TestPathRouting:
    def test_unknown_path_404(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/odata/nonexistent", {})
        assert status == 404

    def test_wrong_prefix_404(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/api/customer", {})
        assert status == 404

    def test_metadata_200(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/odata/$metadata", {})
        assert status == 200

    def test_metadata_content_type_xml(self, handler: ODataRequestHandler) -> None:
        _, headers, _ = handler.handle("GET", "/odata/$metadata", {})
        assert "xml" in headers.get("Content-Type", "")

    def test_metadata_body_is_xml(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/$metadata", {})
        assert body.startswith("<?xml")
        assert "EntityType" in body

    def test_service_document(self, handler: ODataRequestHandler) -> None:
        status, headers, body = handler.handle("GET", "/odata", {})
        assert status == 200
        assert "json" in headers.get("Content-Type", "")
        data = json.loads(body)
        assert "value" in data


class TestCollectionEndpoint:
    def test_collection_200(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/odata/customer", {})
        assert status == 200

    def test_collection_content_type_json(self, handler: ODataRequestHandler) -> None:
        _, headers, _ = handler.handle("GET", "/odata/customer", {})
        assert "json" in headers.get("Content-Type", "")

    def test_collection_returns_all_records(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {})
        data = json.loads(body)
        assert len(data["value"]) == 3

    def test_context_url_in_response(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {})
        data = json.loads(body)
        assert "@odata.context" in data
        assert "customer" in data["@odata.context"]

    def test_select_filters_fields(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$select": "id,name"})
        data = json.loads(body)
        record = data["value"][0]
        assert set(record.keys()) == {"id", "name"}

    def test_top_limits_results(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$top": "2"})
        data = json.loads(body)
        assert len(data["value"]) == 2

    def test_skip_offsets_results(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$skip": "1"})
        data = json.loads(body)
        assert len(data["value"]) == 2
        assert data["value"][0]["id"] == 2

    def test_count_included(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$count": "true"})
        data = json.loads(body)
        assert "@odata.count" in data
        assert data["@odata.count"] == 3

    def test_count_false_excluded(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$count": "false"})
        data = json.loads(body)
        assert "@odata.count" not in data

    def test_next_link_pagination(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle(
            "GET", "/odata/customer", {"$top": "2", "$count": "true"}
        )
        data = json.loads(body)
        assert "@odata.nextLink" in data

    def test_filter_eq(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle(
            "GET", "/odata/customer", {"$filter": "country eq 'IT'"}
        )
        data = json.loads(body)
        assert len(data["value"]) == 1
        assert data["value"][0]["country"] == "IT"

    def test_filter_boolean(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle(
            "GET", "/odata/customer", {"$filter": "active eq false"}
        )
        data = json.loads(body)
        assert len(data["value"]) == 1
        assert data["value"][0]["name"] == "Charlie GmbH"

    def test_filter_contains(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle(
            "GET", "/odata/customer", {"$filter": "contains(name, 'Corp')"}
        )
        data = json.loads(body)
        assert len(data["value"]) == 1
        assert "Corp" in data["value"][0]["name"]

    def test_orderby_asc(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$orderby": "name asc"})
        data = json.loads(body)
        names = [r["name"] for r in data["value"]]
        assert names == sorted(names)

    def test_orderby_desc(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer", {"$orderby": "id desc"})
        data = json.loads(body)
        ids = [r["id"] for r in data["value"]]
        assert ids == sorted(ids, reverse=True)

    def test_invalid_filter_400(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle(
            "GET", "/odata/customer", {"$filter": "name @@ 'bad'"}
        )
        assert status == 400

    def test_invalid_top_400(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/odata/customer", {"$top": "notanint"})
        assert status == 400

    def test_expand_sets_expand_options(self, handler: ODataRequestHandler) -> None:
        status, _, body = handler.handle(
            "GET", "/odata/customer", {"$expand": "Orders"}
        )
        assert status == 200
        data = json.loads(body)
        assert "value" in data


class TestSingleEntityEndpoint:
    def test_existing_entity_200(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/odata/customer(1)", {})
        assert status == 200

    def test_entity_content_type_json(self, handler: ODataRequestHandler) -> None:
        _, headers, _ = handler.handle("GET", "/odata/customer(1)", {})
        assert "json" in headers.get("Content-Type", "")

    def test_entity_fields_present(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer(1)", {})
        data = json.loads(body)
        assert data["id"] == 1
        assert data["name"] == "Alice Corp"

    def test_entity_context_url(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer(1)", {})
        data = json.loads(body)
        assert "@odata.context" in data
        assert "/$entity" in data["@odata.context"]

    def test_nonexistent_entity_404(self, handler: ODataRequestHandler) -> None:
        status, _, _ = handler.handle("GET", "/odata/customer(999)", {})
        assert status == 404

    def test_string_key(self, handler: ODataRequestHandler) -> None:
        # String key: customer('1') → tries to get customer with key '1'
        # MockBackend converts string to int, so this should work
        status, _, _ = handler.handle("GET", "/odata/customer('1')", {})
        assert status == 200


class TestCountEndpoint:
    def test_count_plain_text(self, handler: ODataRequestHandler) -> None:
        status, headers, body = handler.handle("GET", "/odata/customer/$count", {})
        assert status == 200
        assert "text/plain" in headers.get("Content-Type", "")
        assert body.isdigit()

    def test_count_value(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle("GET", "/odata/customer/$count", {})
        assert int(body) == 3

    def test_count_with_filter(self, handler: ODataRequestHandler) -> None:
        _, _, body = handler.handle(
            "GET", "/odata/customer/$count", {"$filter": "active eq true"}
        )
        assert int(body) == 2
