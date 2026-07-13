"""Stable generated-city topology contract shared by city pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metroflow.map.node_compiler import NodeInterfaceCatalog
from metroflow.map.road_geometry import RoadGeometryCatalog
from metroflow.map.section_compiler import RoadSectionCatalog

from .graph import (
    BridgeCrossing,
    Node,
    RoadLink,
    RoadNetworkCSR,
    TopologyValidationReport,
    TurnMovement,
    build_road_network_csr,
    validate_road_network_topology,
)

__all__ = ["PreviewCityTopology"]


@dataclass(slots=True)
class PreviewCityTopology:
    """Compiled static topology accepted by the simulation initializer."""

    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    turns: tuple[TurnMovement, ...] = ()
    bridge_crossings: tuple[BridgeCrossing, ...] = ()
    road_geometry: RoadGeometryCatalog | None = None
    road_sections: RoadSectionCatalog | None = None
    node_interfaces: NodeInterfaceCatalog | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _validated: bool = False

    def validate(
        self,
        *,
        require_weak_connectivity: bool = False,
    ) -> TopologyValidationReport:
        report = validate_road_network_topology(
            nodes=self.nodes,
            links=self.links,
            turns=self.turns,
            bridge_crossings=self.bridge_crossings,
            require_weak_connectivity=require_weak_connectivity,
        )
        self._validated = report.ok
        return report

    def build_csr(
        self,
        *,
        validate: bool | None = None,
        require_weak_connectivity: bool = False,
    ) -> RoadNetworkCSR:
        should_validate = (not self._validated) if validate is None else bool(validate)
        return build_road_network_csr(
            nodes=self.nodes,
            links=self.links,
            turns=self.turns,
            bridge_crossings=self.bridge_crossings,
            validate=should_validate,
            require_weak_connectivity=require_weak_connectivity,
        )
