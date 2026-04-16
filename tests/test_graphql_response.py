# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for GraphQLResponseFormatter."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from graphql import ExecutionResult, GraphQLError

from genro_data_api.graphql.response import GraphQLResponseFormatter


def test_format_success():
    formatter = GraphQLResponseFormatter()
    result = ExecutionResult(data={"customer": [{"id": 1}]})
    body = formatter.format(result)
    payload = json.loads(body)
    assert payload["data"] == {"customer": [{"id": 1}]}
    assert "errors" not in payload


def test_format_null_data_no_errors():
    formatter = GraphQLResponseFormatter()
    result = ExecutionResult(data=None)
    body = formatter.format(result)
    payload = json.loads(body)
    assert payload["data"] is None
    assert "errors" not in payload


def test_format_with_errors():
    formatter = GraphQLResponseFormatter()
    error = GraphQLError("Something went wrong")
    result = ExecutionResult(data=None, errors=[error])
    body = formatter.format(result)
    payload = json.loads(body)
    assert payload["data"] is None
    assert len(payload["errors"]) == 1
    assert "Something went wrong" in payload["errors"][0]["message"]


def test_format_error_message():
    formatter = GraphQLResponseFormatter()
    body = formatter.format_error("Not Found")
    payload = json.loads(body)
    assert payload["data"] is None
    assert payload["errors"][0]["message"] == "Not Found"


def test_format_error_message_arbitrary():
    formatter = GraphQLResponseFormatter()
    body = formatter.format_error("Method Not Allowed")
    payload = json.loads(body)
    assert payload["errors"][0]["message"] == "Method Not Allowed"


def test_format_datetime_serialization():
    formatter = GraphQLResponseFormatter()
    dt = datetime.datetime(2025, 6, 15, 10, 30, 0)
    result = ExecutionResult(data={"ts": dt})
    body = formatter.format(result)
    payload = json.loads(body)
    assert "2025-06-15" in payload["data"]["ts"]


def test_format_date_serialization():
    formatter = GraphQLResponseFormatter()
    d = datetime.date(2025, 1, 1)
    result = ExecutionResult(data={"date": d})
    body = formatter.format(result)
    payload = json.loads(body)
    assert "2025-01-01" in payload["data"]["date"]


def test_format_decimal_serialization():
    formatter = GraphQLResponseFormatter()
    result = ExecutionResult(data={"amount": Decimal("3.14")})
    body = formatter.format(result)
    payload = json.loads(body)
    assert abs(payload["data"]["amount"] - 3.14) < 0.001


def test_format_multiple_errors():
    formatter = GraphQLResponseFormatter()
    errors = [GraphQLError("Error one"), GraphQLError("Error two")]
    result = ExecutionResult(data=None, errors=errors)
    body = formatter.format(result)
    payload = json.loads(body)
    assert len(payload["errors"]) == 2


def test_format_returns_valid_json():
    formatter = GraphQLResponseFormatter()
    result = ExecutionResult(data={"x": "hello"})
    body = formatter.format(result)
    # Must be parseable JSON
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
