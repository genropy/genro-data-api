# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for the opaque $skiptoken encoder/decoder."""

from __future__ import annotations

import pytest

from genro_data_api.odata.skiptoken import decode, encode, filter_hash


class TestEncodeDecode:
    def test_round_trip_minimal(self) -> None:
        token = encode({"skip": 100, "top": 50, "filter_hash": "abc"})
        state = decode(token)
        assert state["skip"] == 100
        assert state["top"] == 50
        assert state["filter_hash"] == "abc"
        assert state["v"] == 1

    def test_round_trip_preserves_extra_keys(self) -> None:
        token = encode({"skip": 0, "top": 10, "filter_hash": "x", "extra": [1, 2, 3]})
        state = decode(token)
        assert state["extra"] == [1, 2, 3]

    def test_token_is_urlsafe(self) -> None:
        # No + or / characters that would need URL-encoding as query string.
        token = encode({"skip": 999999, "top": 10, "filter_hash": "abcdef" * 3})
        assert "+" not in token
        assert "/" not in token

    def test_empty_token_rejected(self) -> None:
        with pytest.raises(ValueError, match="Empty"):
            decode("")

    def test_malformed_base64_rejected(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            decode("not!valid!base64!!!!!!")

    def test_malformed_json_rejected(self) -> None:
        import base64
        token = base64.urlsafe_b64encode(b"not a json").decode().rstrip("=")
        with pytest.raises(ValueError, match="Malformed"):
            decode(token)

    def test_wrong_version_rejected(self) -> None:
        import base64
        import json
        payload = json.dumps({"v": 999, "skip": 0, "top": 10}).encode()
        token = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        with pytest.raises(ValueError, match="Unsupported"):
            decode(token)

    def test_non_utf8_bytes_rejected(self) -> None:
        import base64
        token = base64.urlsafe_b64encode(b"\xff\xfe\xfd").decode().rstrip("=")
        with pytest.raises(ValueError, match="Malformed"):
            decode(token)

    def test_json_array_rejected(self) -> None:
        import base64
        token = base64.urlsafe_b64encode(b"[1, 2, 3]").decode().rstrip("=")
        with pytest.raises(ValueError, match="not a JSON object"):
            decode(token)


class TestFilterHash:
    def test_ignores_pagination_params(self) -> None:
        a = filter_hash({"$filter": "x eq 1", "$top": "10"})
        b = filter_hash({"$filter": "x eq 1", "$top": "500", "$skip": "200"})
        assert a == b

    def test_same_for_equal_filter(self) -> None:
        a = filter_hash({"$filter": "country eq 'IT'"})
        b = filter_hash({"$filter": "country eq 'IT'"})
        assert a == b

    def test_different_for_different_filter(self) -> None:
        a = filter_hash({"$filter": "country eq 'IT'"})
        b = filter_hash({"$filter": "country eq 'US'"})
        assert a != b

    def test_includes_apply(self) -> None:
        a = filter_hash({"$apply": "groupby((state))"})
        b = filter_hash({"$apply": "groupby((country))"})
        assert a != b

    def test_empty_params_stable(self) -> None:
        assert filter_hash({}) == filter_hash({})
        # No filter/orderby/apply at all: still produces a valid short hash.
        h = filter_hash({})
        assert len(h) == 16
