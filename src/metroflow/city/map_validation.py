"""Fail-closed validation report for accepted generated-city map contracts."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from metroflow.map.road_geometry import (
    RoadGeometryCatalog,
    count_interior_centerline_intersections,
    validate_geometry_endpoint_anchors,
)
from metroflow.map.section_compiler import RoadSectionCatalog, compile_road_sections

from .connectivity import analyze_directed_reachability, analyze_weak_connectivity
from .graph import Node, RoadLink, validate_road_network_topology

__all__ = [
    "CityMapValidationReport",
    "require_valid_city_map_contract",
    "validate_city_map_contract",
]


class _TopologyLike(Protocol):
    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    turns: tuple[Any, ...]
    bridge_crossings: tuple[Any, ...]
    road_geometry: RoadGeometryCatalog | None
    road_sections: RoadSectionCatalog | None
    node_interfaces: Any
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CityMapValidationReport:
    failure_codes: tuple[str, ...] = ()
    metrics: Mapping[str, int | float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "failure_codes",
            tuple(sorted({str(code) for code in self.failure_codes})),
        )
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @property
    def ok(self) -> bool:
        return not self.failure_codes

    def summary(self) -> str:
        return "ok" if self.ok else ", ".join(self.failure_codes)


def validate_city_map_contract(
    topology: _TopologyLike,
    *,
    od_sample_count: int = 64,
    seed: int = 0,
) -> CityMapValidationReport:
    """Validate topology, geometry, section, provenance, and sampled OD gates."""

    sample_count = int(od_sample_count)
    if sample_count < 0:
        raise ValueError("od_sample_count must be >= 0")
    nodes = tuple(topology.nodes)
    links = tuple(topology.links)
    metadata = dict(topology.metadata)
    failures: list[str] = []

    topology_report = validate_road_network_topology(
        nodes=nodes,
        links=links,
        turns=tuple(topology.turns),
        bridge_crossings=tuple(topology.bridge_crossings),
        require_weak_connectivity=True,
    )
    if not topology_report.ok:
        failures.append("topology_validation")
    connectivity = analyze_weak_connectivity(nodes=nodes, links=links)
    if connectivity.component_count != 1:
        failures.append("weak_connectivity")

    geometry = topology.road_geometry
    intersection_count = -1
    geometry_assignment_count = 0
    if not isinstance(geometry, RoadGeometryCatalog):
        failures.append("road_geometry_missing")
    else:
        geometry_assignment_count = len(geometry.assignments)
        if geometry_assignment_count != len(links):
            failures.append("geometry_assignment_coverage")
        try:
            validate_geometry_endpoint_anchors(
                catalog=geometry,
                nodes=nodes,
                links=links,
            )
        except (KeyError, TypeError, ValueError):
            failures.append("geometry_endpoint_anchors")
        intersection_count = count_interior_centerline_intersections(geometry)
        if intersection_count:
            failures.append("proper_centerline_intersections")
        if metadata.get("road_geometry_fingerprint") != geometry.fingerprint:
            failures.append("road_geometry_fingerprint")

    sections = topology.road_sections
    section_assignment_count = 0
    if not isinstance(sections, RoadSectionCatalog):
        failures.append("road_sections_missing")
    else:
        section_assignment_count = len(sections.assignments)
        if section_assignment_count != len(links):
            failures.append("section_assignment_coverage")
        for link in links:
            try:
                assignment = sections.assignment_for_link(link.link_id)
            except KeyError:
                failures.append("section_assignment_coverage")
                break
            if assignment.lane_count != link.lanes:
                failures.append("section_lane_authority")
                break
            if assignment.capacity_veh_per_tick != link.capacity_veh_per_tick:
                failures.append("section_capacity_authority")
                break
        if metadata.get("road_section_fingerprint") != sections.fingerprint:
            failures.append("road_section_fingerprint")
        if isinstance(geometry, RoadGeometryCatalog):
            try:
                expected_sections = compile_road_sections(
                    links=links,
                    road_geometry=geometry,
                )
            except (KeyError, TypeError, ValueError):
                failures.append("section_semantic_catalog")
            else:
                if expected_sections != sections:
                    failures.append("section_semantic_catalog")

    node_interfaces = topology.node_interfaces
    node_interface_count = 0
    if node_interfaces is None:
        failures.append("node_interfaces_missing")
    else:
        node_interface_count = len(tuple(node_interfaces.interfaces))
        if node_interface_count != len(nodes):
            failures.append("node_interface_coverage")
        if metadata.get("node_interface_fingerprint") != node_interfaces.fingerprint:
            failures.append("node_interface_fingerprint")

    sampled_od_count, reachable_od_count = _sample_reachable_od_pairs(
        nodes=nodes,
        links=links,
        sample_count=sample_count,
        seed=int(seed),
    )
    if reachable_od_count != sampled_od_count:
        failures.append("sampled_od_reachability")

    return CityMapValidationReport(
        failure_codes=tuple(failures),
        metrics={
            "node_count": len(nodes),
            "link_count": len(links),
            "weak_component_count": connectivity.component_count,
            "proper_intersection_count": intersection_count,
            "geometry_assignment_count": geometry_assignment_count,
            "section_assignment_count": section_assignment_count,
            "node_interface_count": node_interface_count,
            "sampled_od_count": sampled_od_count,
            "reachable_od_count": reachable_od_count,
            "validation_seed": int(seed),
        },
    )


def require_valid_city_map_contract(
    topology: _TopologyLike,
    *,
    od_sample_count: int = 64,
    seed: int = 0,
) -> CityMapValidationReport:
    report = validate_city_map_contract(
        topology,
        od_sample_count=od_sample_count,
        seed=seed,
    )
    if not report.ok:
        raise ValueError(
            f"city map validation failed: {report.summary()}; "
            f"metrics={dict(report.metrics)}"
        )
    return report


def _sample_reachable_od_pairs(
    *,
    nodes: tuple[Node, ...],
    links: tuple[RoadLink, ...],
    sample_count: int,
    seed: int,
) -> tuple[int, int]:
    node_ids = tuple(sorted(node.node_id for node in nodes))
    if sample_count == 0:
        return 0, 0
    if len(node_ids) < 2:
        return sample_count, 0
    rng = random.Random(seed)
    pairs: list[tuple[int, int]] = []
    for _ in range(sample_count):
        origin_index = rng.randrange(len(node_ids))
        destination_index = rng.randrange(len(node_ids) - 1)
        if destination_index >= origin_index:
            destination_index += 1
        pairs.append((node_ids[origin_index], node_ids[destination_index]))

    report = analyze_directed_reachability(
        nodes=nodes,
        links=links,
        pairs=pairs,
    )
    return report.pair_count, report.reachable_pair_count
