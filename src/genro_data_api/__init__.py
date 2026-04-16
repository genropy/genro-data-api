# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""genro-data-api: standardized data API protocols for Genropy.

Exposes database data through industry-standard protocols
(OData v4, GraphQL) via a server-agnostic request handler.

Core exports:
    DataApiBackend         - Protocol that any data source must implement
    QueryOptions           - Structured query parameters
    QueryResult            - Query result container
    GraphQLRequestHandler  - GraphQL HTTP request handler
    GraphQLSchemaGenerator - Builds GraphQL schema from a backend
"""

from genro_data_api.core.backend import DataApiBackend, QueryOptions, QueryResult
from genro_data_api.graphql.request_handler import GraphQLRequestHandler
from genro_data_api.graphql.schema_generator import GraphQLSchemaGenerator

__all__ = [
    "DataApiBackend",
    "GraphQLRequestHandler",
    "GraphQLSchemaGenerator",
    "QueryOptions",
    "QueryResult",
]

__version__ = "0.1.0.dev1"
