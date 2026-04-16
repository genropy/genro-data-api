# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""Tests for CsdlRenderer."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from genro_data_api.core.backend import DataApiBackend
from genro_data_api.odata.csdl_renderer import CsdlRenderer

_EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"


@pytest.fixture
def renderer() -> CsdlRenderer:
    return CsdlRenderer()


class TestRenderOutput:
    def test_returns_string(self, renderer: CsdlRenderer, mock_backend: DataApiBackend) -> None:
        result = renderer.render(mock_backend)
        assert isinstance(result, str)

    def test_xml_declaration(self, renderer: CsdlRenderer, mock_backend: DataApiBackend) -> None:
        result = renderer.render(mock_backend)
        assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_is_parseable_xml(self, renderer: CsdlRenderer, mock_backend: DataApiBackend) -> None:
        result = renderer.render(mock_backend)
        root = ET.fromstring(result.split("\n", 1)[1].strip())
        assert root is not None

    def test_root_element_is_edmx(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        root = ET.fromstring(result.split("\n", 1)[1].strip())
        assert root.tag == f"{{{_EDMX_NS}}}Edmx"
        assert root.get("Version") == "4.0"

    def test_contains_schema(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "Schema" in result
        assert 'Namespace="Default"' in result

    def test_entity_type_customer(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert 'Name="customer"' in result

    def test_entity_type_order(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert 'Name="order"' in result

    def test_primary_key(self, renderer: CsdlRenderer, mock_backend: DataApiBackend) -> None:
        result = renderer.render(mock_backend)
        assert "PropertyRef" in result
        assert 'Name="id"' in result

    def test_properties_present(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "Edm.Int32" in result
        assert "Edm.String" in result
        assert "Edm.Boolean" in result
        assert "Edm.Decimal" in result

    def test_nullable_false_on_key(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert 'Nullable="false"' in result

    def test_max_length_attribute(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "MaxLength" in result

    def test_precision_and_scale(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "Precision" in result
        assert "Scale" in result

    def test_navigation_property(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "NavigationProperty" in result
        assert 'Name="Orders"' in result
        assert "Collection(" in result

    def test_entity_container(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "EntityContainer" in result
        assert "DefaultContainer" in result

    def test_entity_set_elements(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "EntitySet" in result

    def test_navigation_property_binding(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert "NavigationPropertyBinding" in result

    def test_custom_namespace(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend, namespace="MyService")
        assert 'Namespace="MyService"' in result
        assert "MyService." in result
        assert "MyServiceContainer" in result

    def test_entity_set_has_entity_type(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend, namespace="Default")
        assert 'EntityType="Default.customer"' in result
