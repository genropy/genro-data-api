# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for GraphQLSchemaGenerator."""

from __future__ import annotations

from graphql import GraphQLList, GraphQLNonNull, GraphQLObjectType, GraphQLSchema

from genro_data_api.graphql.schema_generator import GraphQLSchemaGenerator


def test_generate_returns_schema(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    assert isinstance(schema, GraphQLSchema)


def test_schema_has_query_type(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    assert schema.query_type is not None
    assert schema.query_type.name == "Query"


def test_query_has_collection_fields(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    fields = schema.query_type.fields
    assert "customer" in fields
    assert "order" in fields


def test_query_has_bykey_fields(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    fields = schema.query_type.fields
    assert "customer_byKey" in fields
    assert "order_byKey" in fields


def test_customer_collection_field_type(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    field = schema.query_type.fields["customer"]
    assert isinstance(field.type, GraphQLList)
    assert isinstance(field.type.of_type, GraphQLNonNull)
    inner = field.type.of_type.of_type
    assert isinstance(inner, GraphQLObjectType)
    assert inner.name == "Customer"


def test_customer_bykey_field_type(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    field = schema.query_type.fields["customer_byKey"]
    assert isinstance(field.type, GraphQLObjectType)
    assert field.type.name == "Customer"


def test_customer_type_properties(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    customer_type = schema.type_map.get("Customer")
    assert isinstance(customer_type, GraphQLObjectType)
    fields = customer_type.fields
    assert "id" in fields
    assert "name" in fields
    assert "country" in fields
    assert "active" in fields


def test_order_type_properties(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    order_type = schema.type_map.get("Order")
    assert isinstance(order_type, GraphQLObjectType)
    fields = order_type.fields
    assert "id" in fields
    assert "customer_id" in fields
    assert "amount" in fields
    assert "status" in fields


def test_customer_navigation_property(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    customer_type = schema.type_map.get("Customer")
    assert isinstance(customer_type, GraphQLObjectType)
    assert "Orders" in customer_type.fields


def test_collection_field_args(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    field = schema.query_type.fields["customer"]
    arg_names = set(field.args.keys())
    assert arg_names == {"top", "skip", "filter", "orderby", "count"}


def test_bykey_field_has_key_arg(mock_backend):
    gen = GraphQLSchemaGenerator()
    schema = gen.generate(mock_backend)
    field = schema.query_type.fields["customer_byKey"]
    assert "key" in field.args
    assert isinstance(field.args["key"].type, GraphQLNonNull)


def test_type_name_with_dots():
    gen = GraphQLSchemaGenerator()
    assert gen._type_name("pkg.customer") == "PkgCustomer"
    assert gen._type_name("customer") == "Customer"


def test_field_name_with_dots():
    gen = GraphQLSchemaGenerator()
    assert gen._field_name("pkg.customer") == "pkg_customer"
    assert gen._field_name("customer") == "customer"
