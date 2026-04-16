# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""GraphQL read-only protocol layer for genro-data-api."""

from __future__ import annotations

from genro_data_api.graphql.request_handler import GraphQLRequestHandler
from genro_data_api.graphql.schema_generator import GraphQLSchemaGenerator

__all__ = ["GraphQLRequestHandler", "GraphQLSchemaGenerator"]
