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


_EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"


def _parse(result: str) -> ET.Element:
    return ET.fromstring(result.split("\n", 1)[1].strip())


def _ns(tag: str) -> str:
    return f"{{{_EDM_NS}}}{tag}"


def _find_entity_type(root: ET.Element, name: str) -> ET.Element:
    for et in root.iter(_ns("EntityType")):
        if et.get("Name") == name:
            return et
    raise AssertionError(f"EntityType {name!r} not found")


def _find_entity_set(root: ET.Element, name: str) -> ET.Element:
    for es in root.iter(_ns("EntitySet")):
        if es.get("Name") == name:
            return es
    raise AssertionError(f"EntitySet {name!r} not found")


def _annotations(parent: ET.Element) -> list[ET.Element]:
    return [a for a in parent if a.tag == _ns("Annotation")]


def _terms(parent: ET.Element) -> list[str]:
    return [a.get("Term", "") for a in _annotations(parent)]


class TestVocabularyReferences:
    def test_core_vocabulary_imported(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert 'Namespace="Org.OData.Core.V1"' in result
        assert 'Alias="Core"' in result

    def test_capabilities_vocabulary_imported(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        result = renderer.render(mock_backend)
        assert 'Namespace="Org.OData.Capabilities.V1"' in result
        assert 'Alias="Capabilities"' in result


class TestCoreDescriptionAnnotations:
    def test_entity_type_description(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        et = _find_entity_type(root, "customer")
        terms = _terms(et)
        assert "Core.Description" in terms
        assert "Core.LongDescription" in terms

    def test_entity_set_description_from_title(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        descriptions = [
            a.get("String")
            for a in _annotations(es)
            if a.get("Term") == "Core.Description"
        ]
        assert "Customers" in descriptions

    def test_property_description(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        et = _find_entity_type(root, "customer")
        for prop in et.iter(_ns("Property")):
            if prop.get("Name") == "name":
                terms = _terms(prop)
                assert "Core.Description" in terms
                assert "Core.LongDescription" in terms
                return
        raise AssertionError("property 'name' not found")

    def test_property_without_label_has_no_description(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        et = _find_entity_type(root, "customer")
        for prop in et.iter(_ns("Property")):
            if prop.get("Name") == "country":
                assert "Core.Description" not in _terms(prop)
                return
        raise AssertionError("property 'country' not found")

    def test_navigation_property_description(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        et = _find_entity_type(root, "customer")
        for nav in et.iter(_ns("NavigationProperty")):
            if nav.get("Name") == "Orders":
                assert "Core.Description" in _terms(nav)
                return
        raise AssertionError("navigation 'Orders' not found")


class TestCoreComputed:
    def test_computed_marked_on_virtual_column(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        et = _find_entity_type(root, "customer")
        for prop in et.iter(_ns("Property")):
            if prop.get("Name") == "orders_count":
                annotations = _annotations(prop)
                computed = [a for a in annotations if a.get("Term") == "Core.Computed"]
                assert len(computed) == 1
                assert computed[0].get("Bool") == "true"
                return
        raise AssertionError("virtual column 'orders_count' not found")

    def test_computed_absent_on_regular_column(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        et = _find_entity_type(root, "customer")
        for prop in et.iter(_ns("Property")):
            if prop.get("Name") == "name":
                assert "Core.Computed" not in _terms(prop)
                return
        raise AssertionError("property 'name' not found")


class TestCapabilitiesAnnotations:
    def test_insert_restrictions_false(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        restriction = self._record_annotation(es, "Capabilities.InsertRestrictions")
        assert restriction["Insertable"] == "false"

    def test_update_restrictions_false(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        restriction = self._record_annotation(es, "Capabilities.UpdateRestrictions")
        assert restriction["Updatable"] == "false"

    def test_delete_restrictions_false(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        restriction = self._record_annotation(es, "Capabilities.DeleteRestrictions")
        assert restriction["Deletable"] == "false"

    def test_top_supported_true(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        for ann in _annotations(es):
            if ann.get("Term") == "Capabilities.TopSupported":
                assert ann.get("Bool") == "true"
                return
        raise AssertionError("TopSupported annotation missing")

    def test_skip_supported_true(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        for ann in _annotations(es):
            if ann.get("Term") == "Capabilities.SkipSupported":
                assert ann.get("Bool") == "true"
                return
        raise AssertionError("SkipSupported annotation missing")

    def test_count_restrictions_true(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        es = _find_entity_set(root, "customer")
        restriction = self._record_annotation(es, "Capabilities.CountRestrictions")
        assert restriction["Countable"] == "true"

    def test_every_entity_set_gets_write_restrictions(
        self, renderer: CsdlRenderer, mock_backend: DataApiBackend
    ) -> None:
        root = _parse(renderer.render(mock_backend))
        for es in root.iter(_ns("EntitySet")):
            terms = _terms(es)
            assert "Capabilities.InsertRestrictions" in terms
            assert "Capabilities.UpdateRestrictions" in terms
            assert "Capabilities.DeleteRestrictions" in terms

    @staticmethod
    def _record_annotation(parent: ET.Element, term: str) -> dict[str, str]:
        for ann in _annotations(parent):
            if ann.get("Term") != term:
                continue
            record = ann.find(_ns("Record"))
            assert record is not None, f"{term} has no Record child"
            return {
                pv.get("Property", ""): pv.get("Bool", "")
                for pv in record.iter(_ns("PropertyValue"))
            }
        raise AssertionError(f"annotation {term!r} missing")
