# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""genro-data-api: standardized data API protocols for Genropy.

Exposes database data through industry-standard protocols
(OData v4, GraphQL) via a server-agnostic request handler.

Core exports:
    DataApiBackend - Protocol that any data source must implement
    QueryOptions   - Structured query parameters
    QueryResult    - Query result container
"""

from genro_data_api.core.backend import DataApiBackend, QueryOptions, QueryResult

__all__ = [
    "DataApiBackend",
    "QueryOptions",
    "QueryResult",
]

__version__ = "0.1.0.dev1"
