"""Deterministic diagnostic accessibility checks for generated land use."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from metroflow.city.connectivity import analyze_directed_reachability
from metroflow.city.graph import Node, RoadLink
from metroflow.city.zones import POI, Zone, ZoningPlacementResult

__all__ = [
    "LandUseAccessibilityAudit",
    "LandUsePlacementComparison",
    "audit_landuse_accessibility",
    "compare_landuse_placements",
]


@dataclass(frozen=True, slots=True)
class LandUseAccessibilityAudit:
    coupling_mode: str
    zoning_fingerprint: str
    zone_count: int
    poi_count: int
    zone_access_covered_count: int
    poi_access_valid_count: int
    unique_poi_access_node_count: int
    directed_zone_pair_count: int
    directed_zone_pair_reachable_count: int
    mean_poi_distance_from_zone_centroid_m: float
    max_poi_distance_from_zone_centroid_m: float
    uncovered_zone_ids: tuple[int, ...]
    invalid_poi_ids: tuple[int, ...]
    unreachable_zone_pairs: tuple[tuple[int, int], ...]
    evidence_status: str = "diagnostic_not_validation"

    @property
    def zone_access_coverage_share(self) -> float:
        return _share(self.zone_access_covered_count, self.zone_count)

    @property
    def poi_access_valid_share(self) -> float:
        return _share(self.poi_access_valid_count, self.poi_count)

    @property
    def unique_poi_access_node_share(self) -> float:
        return _share(self.unique_poi_access_node_count, self.poi_count)

    @property
    def directed_zone_pair_reachability_share(self) -> float:
        return _share(
            self.directed_zone_pair_reachable_count,
            self.directed_zone_pair_count,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "coupling_mode": self.coupling_mode,
            "zoning_fingerprint": self.zoning_fingerprint,
            "zone_count": self.zone_count,
            "poi_count": self.poi_count,
            "zone_access_covered_count": self.zone_access_covered_count,
            "zone_access_coverage_share": self.zone_access_coverage_share,
            "poi_access_valid_count": self.poi_access_valid_count,
            "poi_access_valid_share": self.poi_access_valid_share,
            "unique_poi_access_node_count": self.unique_poi_access_node_count,
            "unique_poi_access_node_share": self.unique_poi_access_node_share,
            "directed_zone_pair_count": self.directed_zone_pair_count,
            "directed_zone_pair_reachable_count": (
                self.directed_zone_pair_reachable_count
            ),
            "directed_zone_pair_reachability_share": (
                self.directed_zone_pair_reachability_share
            ),
            "mean_poi_distance_from_zone_centroid_m": (
                self.mean_poi_distance_from_zone_centroid_m
            ),
            "max_poi_distance_from_zone_centroid_m": (
                self.max_poi_distance_from_zone_centroid_m
            ),
            "uncovered_zone_ids": self.uncovered_zone_ids,
            "invalid_poi_ids": self.invalid_poi_ids,
            "unreachable_zone_pairs": self.unreachable_zone_pairs,
            "evidence_status": self.evidence_status,
        }


@dataclass(frozen=True, slots=True)
class LandUsePlacementComparison:
    aggregate_contract_preserved: bool
    zone_center_changed_count: int
    zone_center_changed_share: float
    poi_access_node_changed_count: int
    poi_access_node_changed_share: float
    accessibility_retention_ratio: float
    directed_reachability_retention_ratio: float

    @property
    def placement_changed(self) -> bool:
        return bool(
            self.zone_center_changed_count or self.poi_access_node_changed_count
        )

    @property
    def accessibility_preserved(self) -> bool:
        return self.accessibility_retention_ratio >= 1.0

    @property
    def directed_reachability_preserved(self) -> bool:
        return self.directed_reachability_retention_ratio >= 1.0

    def as_dict(self) -> dict[str, int | float | bool]:
        return {
            "aggregate_contract_preserved": self.aggregate_contract_preserved,
            "zone_center_changed_count": self.zone_center_changed_count,
            "zone_center_changed_share": self.zone_center_changed_share,
            "poi_access_node_changed_count": self.poi_access_node_changed_count,
            "poi_access_node_changed_share": self.poi_access_node_changed_share,
            "accessibility_retention_ratio": self.accessibility_retention_ratio,
            "directed_reachability_retention_ratio": (
                self.directed_reachability_retention_ratio
            ),
            "accessibility_preserved": self.accessibility_preserved,
            "directed_reachability_preserved": (
                self.directed_reachability_preserved
            ),
            "placement_changed": self.placement_changed,
        }


def audit_landuse_accessibility(
    *,
    nodes: Sequence[Node],
    links: Sequence[RoadLink],
    zones: Sequence[Zone],
    pois: Sequence[POI],
    node_zone_by_id: Mapping[int, int],
    zone_node_ids: Mapping[int, Sequence[int]],
    coupling_mode: str,
    zoning_fingerprint: str,
) -> LandUseAccessibilityAudit:
    """Audit access-node integrity and directed representative-zone reachability."""

    nodes_t = tuple(nodes)
    links_t = tuple(links)
    zones_t = tuple(zones)
    pois_t = tuple(pois)
    node_by_id = {int(node.node_id): node for node in nodes_t}
    if len(node_by_id) != len(nodes_t):
        raise ValueError("nodes must have unique node_id values")
    zone_by_id = {int(zone.zone_id): zone for zone in zones_t}
    if len(zone_by_id) != len(zones_t):
        raise ValueError("zones must have unique zone_id values")
    if len({int(poi.poi_id) for poi in pois_t}) != len(pois_t):
        raise ValueError("pois must have unique poi_id values")
    normalized_node_zone = {
        int(node_id): int(zone_id) for node_id, zone_id in node_zone_by_id.items()
    }
    normalized_zone_nodes = {
        int(zone_id): tuple(int(node_id) for node_id in node_ids)
        for zone_id, node_ids in zone_node_ids.items()
    }

    representative_by_zone: dict[int, int] = {}
    uncovered_zone_ids: list[int] = []
    for zone_id, zone in sorted(zone_by_id.items()):
        candidate_ids = tuple(
            node_id
            for node_id in normalized_zone_nodes.get(zone_id, ())
            if node_id in node_by_id and normalized_node_zone.get(node_id) == zone_id
        )
        if not candidate_ids:
            uncovered_zone_ids.append(zone_id)
            continue
        representative_by_zone[zone_id] = min(
            candidate_ids,
            key=lambda node_id: (
                _distance_from_zone(node_by_id[node_id], zone),
                node_id,
            ),
        )

    invalid_poi_ids: list[int] = []
    valid_poi_node_ids: list[int] = []
    poi_distances: list[float] = []
    for poi in pois_t:
        zone = zone_by_id.get(int(poi.zone_id))
        zone_nodes = normalized_zone_nodes.get(int(poi.zone_id), ())
        valid = (
            zone is not None
            and int(poi.node_id) in node_by_id
            and normalized_node_zone.get(int(poi.node_id)) == int(poi.zone_id)
            and int(poi.node_id) in zone_nodes
        )
        if not valid:
            invalid_poi_ids.append(int(poi.poi_id))
            continue
        valid_poi_node_ids.append(int(poi.node_id))
        poi_distances.append(_distance_from_zone(node_by_id[int(poi.node_id)], zone))

    ordered_zone_pairs = tuple(
        (origin_zone_id, destination_zone_id)
        for origin_zone_id in sorted(zone_by_id)
        for destination_zone_id in sorted(zone_by_id)
        if origin_zone_id != destination_zone_id
    )
    valid_zone_pairs = tuple(
        pair
        for pair in ordered_zone_pairs
        if pair[0] in representative_by_zone and pair[1] in representative_by_zone
    )
    node_pairs = tuple(
        (representative_by_zone[origin], representative_by_zone[destination])
        for origin, destination in valid_zone_pairs
    )
    reachability = analyze_directed_reachability(
        nodes=nodes_t,
        links=links_t,
        pairs=node_pairs,
    )
    unreachable_node_pairs = set(reachability.unreachable_pairs)
    reachable_zone_pairs = {
        zone_pair
        for zone_pair, node_pair in zip(valid_zone_pairs, node_pairs, strict=True)
        if node_pair not in unreachable_node_pairs
    }
    unreachable_zone_pairs = tuple(
        pair for pair in ordered_zone_pairs if pair not in reachable_zone_pairs
    )
    return LandUseAccessibilityAudit(
        coupling_mode=str(coupling_mode),
        zoning_fingerprint=str(zoning_fingerprint),
        zone_count=len(zones_t),
        poi_count=len(pois_t),
        zone_access_covered_count=len(representative_by_zone),
        poi_access_valid_count=len(valid_poi_node_ids),
        unique_poi_access_node_count=len(set(valid_poi_node_ids)),
        directed_zone_pair_count=len(ordered_zone_pairs),
        directed_zone_pair_reachable_count=(
            len(ordered_zone_pairs) - len(unreachable_zone_pairs)
        ),
        mean_poi_distance_from_zone_centroid_m=(
            sum(poi_distances) / len(poi_distances) if poi_distances else 0.0
        ),
        max_poi_distance_from_zone_centroid_m=max(poi_distances, default=0.0),
        uncovered_zone_ids=tuple(uncovered_zone_ids),
        invalid_poi_ids=tuple(invalid_poi_ids),
        unreachable_zone_pairs=unreachable_zone_pairs,
    )


def compare_landuse_placements(
    *,
    legacy: ZoningPlacementResult,
    morphology: ZoningPlacementResult,
    legacy_audit: LandUseAccessibilityAudit,
    morphology_audit: LandUseAccessibilityAudit,
) -> LandUsePlacementComparison:
    """Compare placement-only changes while checking aggregate contract parity."""

    legacy_zones = {zone.zone_id: zone for zone in legacy.zones}
    morphology_zones = {zone.zone_id: zone for zone in morphology.zones}
    legacy_pois = {poi.poi_id: poi for poi in legacy.pois}
    morphology_pois = {poi.poi_id: poi for poi in morphology.pois}
    if len(legacy_zones) != len(legacy.zones) or len(morphology_zones) != len(
        morphology.zones
    ):
        raise ValueError("land-use comparison requires unique zone ids")
    if len(legacy_pois) != len(legacy.pois) or len(morphology_pois) != len(
        morphology.pois
    ):
        raise ValueError("land-use comparison requires unique POI ids")
    aggregate_preserved = (
        legacy_zones.keys() == morphology_zones.keys()
        and legacy_pois.keys() == morphology_pois.keys()
        and all(
            _zone_aggregate_signature(legacy_zones[zone_id])
            == _zone_aggregate_signature(morphology_zones[zone_id])
            for zone_id in legacy_zones
        )
        and all(
            _poi_aggregate_signature(legacy_pois[poi_id])
            == _poi_aggregate_signature(morphology_pois[poi_id])
            for poi_id in legacy_pois
        )
    )
    changed_zones = sum(
        (
            legacy_zones[zone_id].centroid_x,
            legacy_zones[zone_id].centroid_y,
        )
        != (
            morphology_zones[zone_id].centroid_x,
            morphology_zones[zone_id].centroid_y,
        )
        for zone_id in legacy_zones.keys() & morphology_zones.keys()
    )
    changed_pois = sum(
        legacy_pois[poi_id].node_id != morphology_pois[poi_id].node_id
        for poi_id in legacy_pois.keys() & morphology_pois.keys()
    )
    return LandUsePlacementComparison(
        aggregate_contract_preserved=aggregate_preserved,
        zone_center_changed_count=int(changed_zones),
        zone_center_changed_share=_share(changed_zones, len(legacy_zones)),
        poi_access_node_changed_count=int(changed_pois),
        poi_access_node_changed_share=_share(changed_pois, len(legacy_pois)),
        accessibility_retention_ratio=_retention_ratio(
            morphology_audit.poi_access_valid_share,
            legacy_audit.poi_access_valid_share,
        ),
        directed_reachability_retention_ratio=_retention_ratio(
            morphology_audit.directed_zone_pair_reachability_share,
            legacy_audit.directed_zone_pair_reachability_share,
        ),
    )


def _share(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else float(numerator / denominator)


def _retention_ratio(value: float, baseline: float) -> float:
    if baseline <= 0.0:
        return 1.0
    return float(max(0.0, min(value / baseline, 1.0)))


def _distance_from_zone(node: Node, zone: Zone) -> float:
    return math.hypot(
        float(node.x) - float(zone.centroid_x),
        float(node.y) - float(zone.centroid_y),
    )


def _zone_aggregate_signature(zone: Zone) -> tuple[Any, ...]:
    return (
        zone.zone_type,
        zone.population_capacity,
        zone.job_capacity,
        zone.leisure_capacity,
    )


def _poi_aggregate_signature(poi: POI) -> tuple[Any, ...]:
    return (poi.zone_id, poi.poi_type, poi.capacity_hint)
