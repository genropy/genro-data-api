# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0

"""OData v4 CSDL XML metadata renderer.

Generates the $metadata XML document from a DataApiBackend.
The output conforms to the OData Common Schema Definition Language (CSDL) v4.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from genro_data_api.core.backend import DataApiBackend
from genro_data_api.core.type_map import get_edm_type

_EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"
_EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"


class CsdlRenderer:
    """Renders OData v4 CSDL XML from a DataApiBackend."""

    def render(self, backend: DataApiBackend, namespace: str = "Default") -> str:
        """Generate CSDL XML for all entity types in the backend.

        Args:
            backend: Data backend providing entity sets and metadata.
            namespace: OData namespace prefix for EntityTypes (default: "Default").

        Returns:
            Valid OData v4 CSDL XML string with XML declaration.
        """
        ET.register_namespace("edmx", _EDMX_NS)
        ET.register_namespace("", _EDM_NS)

        root = ET.Element(f"{{{_EDMX_NS}}}Edmx", {"Version": "4.0"})
        data_services = ET.SubElement(root, f"{{{_EDMX_NS}}}DataServices")
        schema = ET.SubElement(data_services, f"{{{_EDM_NS}}}Schema", {"Namespace": namespace})

        entity_sets_info = backend.entity_sets()
        metadata_list: list[dict[str, Any]] = []

        for entity_set in entity_sets_info:
            name = entity_set["name"]
            meta = backend.entity_metadata(name)
            metadata_list.append(meta)
            type_name = self._type_name(name)
            self._add_entity_type(schema, meta, type_name, namespace)

        container = ET.SubElement(
            schema,
            f"{{{_EDM_NS}}}EntityContainer",
            {"Name": f"{namespace}Container"},
        )
        for entity_set, meta in zip(entity_sets_info, metadata_list, strict=True):
            es_name = entity_set["name"]
            type_name = self._type_name(es_name)
            es_elem = ET.SubElement(
                container,
                f"{{{_EDM_NS}}}EntitySet",
                {
                    "Name": es_name,
                    "EntityType": f"{namespace}.{type_name}",
                },
            )
            for nav in meta.get("navigation", []):
                ET.SubElement(
                    es_elem,
                    f"{{{_EDM_NS}}}NavigationPropertyBinding",
                    {"Path": nav["name"], "Target": nav["target"]},
                )

        ET.indent(root, space="  ")
        xml_body = ET.tostring(root, encoding="unicode", xml_declaration=False)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body

    def _add_entity_type(
        self,
        schema: ET.Element,
        meta: dict[str, Any],
        type_name: str,
        namespace: str,
    ) -> None:
        entity_type = ET.SubElement(schema, f"{{{_EDM_NS}}}EntityType", {"Name": type_name})

        keys = meta.get("key", [])
        if keys:
            key_elem = ET.SubElement(entity_type, f"{{{_EDM_NS}}}Key")
            for key_name in keys:
                ET.SubElement(key_elem, f"{{{_EDM_NS}}}PropertyRef", {"Name": key_name})

        for prop in meta.get("properties", []):
            attrs: dict[str, str] = {
                "Name": prop["name"],
                "Type": get_edm_type(prop.get("type", "A")),
                "Nullable": "true" if prop.get("nullable", True) else "false",
            }
            if "maxLength" in prop:
                attrs["MaxLength"] = str(prop["maxLength"])
            if "precision" in prop:
                attrs["Precision"] = str(prop["precision"])
            if "scale" in prop:
                attrs["Scale"] = str(prop["scale"])
            ET.SubElement(entity_type, f"{{{_EDM_NS}}}Property", attrs)

        for nav in meta.get("navigation", []):
            target_type = f"{namespace}.{self._type_name(nav['target'])}"
            nav_type = f"Collection({target_type})" if nav.get("collection", False) else target_type
            ET.SubElement(
                entity_type,
                f"{{{_EDM_NS}}}NavigationProperty",
                {"Name": nav["name"], "Type": nav_type},
            )

    def _type_name(self, entity_name: str) -> str:
        """Derive a valid XML NCName from a GenroPy entity name."""
        return entity_name.replace(".", "_").replace("-", "_")
