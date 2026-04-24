# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Opaque ``$skiptoken`` encoder/decoder for server-driven pagination.

OData v4 lets the server emit ``@odata.nextLink`` values that carry an
opaque ``$skiptoken`` parameter instead of exposing ``$skip``/``$top``
directly. The client is required to round-trip the token verbatim on
the next request; the server is free to change the payload format
between versions without breaking clients.

This module implements token v1: offset-based pagination encoded as
``base64url(json({v:1, skip, top, filter_hash}))``. The ``filter_hash``
is a short digest of the original ``$filter``/``$orderby``/``$apply``
query arguments; if the client tampers with those between pages, the
server refuses the stale token rather than returning inconsistent rows.

Future versions can switch to keyset pagination (storing the last-seen
primary key) or to a GenroPy frozen-result-set id + row index, all
without changing the public contract — clients just keep passing the
``$skiptoken`` string they receive.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

_TOKEN_VERSION = 1


def encode(state: dict[str, Any]) -> str:
    """Serialise a pagination state dict into an opaque token string.

    The input must at minimum carry ``skip`` and ``top`` ints. A
    ``filter_hash`` computed with :func:`filter_hash` should be included
    so the decoder can detect clients that tampered with the outer query.
    """
    payload = {"v": _TOKEN_VERSION, **state}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(token: str) -> dict[str, Any]:
    """Parse an opaque token back to its state dict.

    Raises ValueError on invalid encoding, bad JSON, or unknown token
    version. The caller is expected to validate ``filter_hash`` against
    the current request after decoding.
    """
    if not token:
        raise ValueError("Empty $skiptoken")
    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode((token + padding).encode("ascii"))
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        raise ValueError(f"Malformed $skiptoken: {exc!s}") from None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Malformed $skiptoken payload: {exc!s}") from None
    if not isinstance(payload, dict):
        raise ValueError("$skiptoken payload is not a JSON object")
    version = payload.get("v")
    if version != _TOKEN_VERSION:
        raise ValueError(
            f"Unsupported $skiptoken version: {version!r}; "
            f"expected {_TOKEN_VERSION}"
        )
    return payload


def filter_hash(params: dict[str, str]) -> str:
    """Return a short stable digest of the query options that fix the row set.

    Hashes the subset of parameters that affect **which rows** a query
    returns (``$filter``, ``$orderby``, ``$apply``) — deliberately
    ignoring pagination parameters (``$top``, ``$skip``, ``$skiptoken``)
    and rendering hints (``$select``, ``$expand``, ``$format``).

    Two requests with identical filter/orderby/apply produce the same
    hash regardless of insertion order in the dict.
    """
    relevant = {
        key: params[key]
        for key in ("$filter", "$orderby", "$apply")
        if key in params
    }
    digest = hashlib.sha256(
        json.dumps(relevant, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest[:16]
