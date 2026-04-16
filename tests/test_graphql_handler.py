# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for GraphQLRequestHandler."""

from __future__ import annotations

import json

from genro_data_api.graphql.request_handler import GraphQLRequestHandler


def test_post_simple_query(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": "{ customer { id name } }"})
    status, headers, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    assert "errors" not in data
    assert "customer" in data["data"]
    assert len(data["data"]["customer"]) == 3


def test_post_query_with_top(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": "{ customer(top: 2) { id name } }"})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    assert len(data["data"]["customer"]) == 2


def test_post_query_with_skip(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": "{ customer(skip: 1) { id } }"})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    assert len(data["data"]["customer"]) == 2


def test_post_bykey_query(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": '{ customer_byKey(key: "1") { id name } }'})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    assert data["data"]["customer_byKey"]["id"] == 1
    assert data["data"]["customer_byKey"]["name"] == "Alice Corp"


def test_post_bykey_not_found(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": '{ customer_byKey(key: "999") { id } }'})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    assert data["data"]["customer_byKey"] is None


def test_post_order_query(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": "{ order { id status amount } }"})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    assert len(data["data"]["order"]) == 3


def test_get_query(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, body_out = handler.handle("GET", "/", {"query": "{ order { id status } }"})
    assert status == 200
    data = json.loads(body_out)
    assert "order" in data["data"]


def test_get_schema(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, headers, body_out = handler.handle("GET", "/schema", {})
    assert status == 200
    assert "Customer" in body_out
    assert "Order" in body_out
    assert "customer" in body_out
    assert "customer_byKey" in body_out


def test_get_schema_wrong_method(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, _ = handler.handle("POST", "/schema", {}, "{}")
    assert status == 405


def test_delete_root_method_not_allowed(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, _ = handler.handle("DELETE", "/", {})
    assert status == 405


def test_put_method_not_allowed(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, _ = handler.handle("PUT", "/", {})
    assert status == 405


def test_unknown_path_returns_404(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, _ = handler.handle("GET", "/unknown", {})
    assert status == 404


def test_post_invalid_json_body(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, body_out = handler.handle("POST", "/", {}, "not-json")
    assert status == 400
    data = json.loads(body_out)
    assert data["data"] is None
    assert len(data["errors"]) > 0


def test_post_missing_query(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"variables": {}})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 400


def test_get_missing_query_param(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    status, _, body_out = handler.handle("GET", "/", {})
    assert status == 400


def test_post_invalid_graphql_syntax(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": "{ invalid syntax {{{"})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200  # GraphQL returns 200 even with parse errors
    data = json.loads(body_out)
    assert "errors" in data


def test_response_content_type_json(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": "{ customer { id } }"})
    _, headers, _ = handler.handle("POST", "/", {}, body)
    assert headers["Content-Type"] == "application/json;charset=UTF-8"


def test_schema_content_type_text(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    _, headers, _ = handler.handle("GET", "/schema", {})
    assert "text/plain" in headers["Content-Type"]


def test_post_with_filter(mock_backend):
    handler = GraphQLRequestHandler(mock_backend)
    body = json.dumps({"query": '{ customer(filter: "country eq \'IT\'") { id country } }'})
    status, _, body_out = handler.handle("POST", "/", {}, body)
    assert status == 200
    data = json.loads(body_out)
    customers = data["data"]["customer"]
    assert all(c["country"] == "IT" for c in customers)
