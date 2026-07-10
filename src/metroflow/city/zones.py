"""Zoning and POI placement generation for synthetic city topologies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Iterator, Mapping, Protocol

from metroflow.city.graph import Node
from metroflow.city.morphology_quality import (
    compute_morphology_quality_metrics,
    evaluate_morphology_quality_gate,
    morphology_placement_anchor_digest,
)
from metroflow.sim.config import CityGenerationConfig, ZoneType

__all__ = [
    "POIType",
    "Zone",
    "POI",
    "ZoningPlacementResult",
    "generate_zones_and_pois",
    "build_zones_and_pois",
    "zoning_placement_fingerprint",
]

_MORPHOLOGY_COUPLING_GATE_VERSION = "morphology_quality_v2"
_MORPHOLOGY_COUPLING_GATE_SCOPE = (
    "weak_connectivity_block_density_intersection_mix_"
    "global_local_cell_presence_junction_proximity"
)


class SyntheticCityTopologyLike(Protocol):
    """Topology surface required by zoning without depending on a generator module."""

    nodes: tuple[Node, ...]
    road_geometry: Any
    metadata: Mapping[str, Any]


class StrEnum(str, Enum):
    """Local string enum base."""


class POIType(StrEnum):
    HOME = "home"
    WORKPLACE = "workplace"
    LEISURE = "leisure"


@dataclass(slots=True)
class Zone:
    """Land-use zone with aggregate capacities used by demand generation."""

    zone_id: int
    zone_type: ZoneType | str
    centroid_x: float
    centroid_y: float
    population_capacity: int = 0
    job_capacity: int = 0
    leisure_capacity: int = 0

    def __post_init__(self) -> None:
        self.zone_id = int(self.zone_id)
        self.zone_type = ZoneType(self.zone_type)
        self.centroid_x = float(self.centroid_x)
        self.centroid_y = float(self.centroid_y)
        self.population_capacity = int(self.population_capacity)
        self.job_capacity = int(self.job_capacity)
        self.leisure_capacity = int(self.leisure_capacity)
        if self.population_capacity < 0:
            raise ValueError("Zone population_capacity must be >= 0")
        if self.job_capacity < 0:
            raise ValueError("Zone job_capacity must be >= 0")
        if self.leisure_capacity < 0:
            raise ValueError("Zone leisure_capacity must be >= 0")


@dataclass(slots=True)
class POI:
    """Point of interest anchored to a zone and nearest access node."""

    poi_id: int
    zone_id: int
    poi_type: POIType | str
    node_id: int
    capacity_hint: int = 0

    def __post_init__(self) -> None:
        self.poi_id = int(self.poi_id)
        self.zone_id = int(self.zone_id)
        self.poi_type = POIType(self.poi_type)
        self.node_id = int(self.node_id)
        self.capacity_hint = int(self.capacity_hint)
        if self.capacity_hint < 0:
            raise ValueError("POI capacity_hint must be >= 0")


@dataclass(slots=True)
class ZoningPlacementResult:
    """Output container for zone and POI generation from a static topology."""

    zones: tuple[Zone, ...]
    pois: tuple[POI, ...]
    node_zone_by_id: dict[int, int] = field(default_factory=dict)
    zone_node_ids: dict[int, tuple[int, ...]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.zones = tuple(self.zones)
        self.pois = tuple(self.pois)
        self.node_zone_by_id = {int(k): int(v) for k, v in dict(self.node_zone_by_id).items()}
        self.zone_node_ids = {
            int(zone_id): tuple(int(node_id) for node_id in node_ids)
            for zone_id, node_ids in dict(self.zone_node_ids).items()
        }
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

    def validate(
        self,
        *,
        topology: SyntheticCityTopologyLike | None = None,
    ) -> tuple[str, ...]:
        """Return validation issues (empty tuple means valid)."""

        issues: list[str] = []
        zone_ids = [zone.zone_id for zone in self.zones]
        if len(set(zone_ids)) != len(zone_ids):
            issues.append("duplicate zone_id values")
        if set(zone.zone_type for zone in self.zones) != set(ZoneType):
            issues.append("zones must include all four zone types")

        zone_id_set = set(zone_ids)
        node_id_set = None
        if topology is not None:
            node_id_set = {node.node_id for node in topology.nodes}

        if set(self.zone_node_ids) != zone_id_set:
            issues.append("zone_node_ids keys must match zone ids")
        inverse_from_zone_nodes: dict[int, int] = {}
        duplicate_zone_node_refs = 0
        for zone_id, node_ids in self.zone_node_ids.items():
            if len(node_ids) != len(set(node_ids)):
                issues.append(f"zone_node_ids[{zone_id}] contains duplicate node ids")
            for node_id in node_ids:
                previous_zone = inverse_from_zone_nodes.get(node_id)
                if previous_zone is not None and previous_zone != zone_id:
                    duplicate_zone_node_refs += 1
                inverse_from_zone_nodes[node_id] = zone_id
        if duplicate_zone_node_refs:
            issues.append("zone_node_ids contains nodes assigned to multiple zones")

        for poi in self.pois:
            if poi.zone_id not in zone_id_set:
                issues.append(f"poi {poi.poi_id} references missing zone_id {poi.zone_id}")
            if node_id_set is not None and poi.node_id not in node_id_set:
                issues.append(f"poi {poi.poi_id} references missing node_id {poi.node_id}")

        for node_id, zone_id in self.node_zone_by_id.items():
            if zone_id not in zone_id_set:
                issues.append(f"node_zone_by_id maps node {node_id} to missing zone_id {zone_id}")
                continue
            if inverse_from_zone_nodes.get(node_id) != zone_id:
                issues.append(
                    f"node_zone_by_id / zone_node_ids mismatch for node {node_id} (zone {zone_id})"
                )

        for node_id, zone_id in inverse_from_zone_nodes.items():
            if self.node_zone_by_id.get(node_id) != zone_id:
                issues.append(
                    f"zone_node_ids / node_zone_by_id mismatch for node {node_id} (zone {zone_id})"
                )

        if node_id_set is not None:
            missing_nodes = sorted(node_id_set - set(self.node_zone_by_id))
            if missing_nodes:
                issues.append(f"node_zone_by_id missing {len(missing_nodes)} topology nodes")
        return tuple(issues)


def generate_zones_and_pois(
    topology: SyntheticCityTopologyLike,
    config: CityGenerationConfig | None = None,
    *,
    seed: int = 0,
    population_target: int | None = None,
    validate: bool = True,
) -> ZoningPlacementResult:
    """Generate a deterministic zoning layout and POI anchors for a city topology."""

    cfg = config if config is not None else CityGenerationConfig()
    nodes = tuple(topology.nodes)
    if not nodes:
        raise ValueError("topology.nodes must not be empty")
    if len(nodes) < 4:
        raise ValueError("topology.nodes must contain at least 4 nodes for zone placement")

    seed = int(seed)
    coupling = _resolve_zone_poi_coupling(topology=topology, config=cfg)
    layout_plan = _plan_zoning_layout(
        nodes=nodes,
        cfg=cfg,
        seed=seed,
        population_target=population_target,
        topology=topology,
        coupling_mode=coupling.resolved_mode,
    )
    node_by_id = {node.node_id: node for node in nodes}
    centers = tuple(node_by_id[node_id] for node_id in layout_plan.center_node_ids)
    zone_types = layout_plan.zone_types
    zone_type_plan_counts = Counter(zone_types)
    zones: list[Zone] = []
    for zone_id, (zone_type, center_node) in enumerate(zip(zone_types, centers, strict=True), start=1):
        type_count = max(1, int(zone_type_plan_counts.get(zone_type, 1)))
        per_zone_share = float(cfg.zone_mix_targets[zone_type]) / float(type_count)
        population_capacity, job_capacity, leisure_capacity = _zone_capacities_for_type(
            zone_type=zone_type,
            share=per_zone_share,
            population_target=layout_plan.population_target,
        )
        zones.append(
            Zone(
                zone_id=zone_id,
                zone_type=zone_type,
                centroid_x=center_node.x,
                centroid_y=center_node.y,
                population_capacity=population_capacity,
                job_capacity=job_capacity,
                leisure_capacity=leisure_capacity,
            )
        )

    center_by_zone_id = {
        zone.zone_id: (zone.centroid_x, zone.centroid_y)
        for zone in zones
    }
    center_node_id_by_zone = {
        zone.zone_id: center.node_id
        for zone, center in zip(zones, centers, strict=True)
    }

    node_zone_by_id: dict[int, int] = {}
    zone_node_lists: dict[int, list[int]] = {zone.zone_id: [] for zone in zones}
    for node in nodes:
        zone_id = _nearest_zone_id(node, center_by_zone_id)
        node_zone_by_id[node.node_id] = zone_id
        zone_node_lists[zone_id].append(node.node_id)

    # Ensure each zone has at least one node anchor by assigning its center node.
    center_node_ids = [center.node_id for center in centers]
    for zone, center_node_id in zip(zones, center_node_ids, strict=True):
        if center_node_id not in zone_node_lists[zone.zone_id]:
            previous_zone = node_zone_by_id.get(center_node_id)
            if previous_zone is not None and center_node_id in zone_node_lists[previous_zone]:
                zone_node_lists[previous_zone].remove(center_node_id)
            zone_node_lists[zone.zone_id].append(center_node_id)
            node_zone_by_id[center_node_id] = zone.zone_id

    zone_node_ids = {
        zone_id: tuple(sorted(node_ids)) if node_ids else ()
        for zone_id, node_ids in zone_node_lists.items()
    }

    pois = _generate_pois(
        zones=tuple(zones),
        zone_node_ids=zone_node_ids,
        center_node_id_by_zone=center_node_id_by_zone,
        poi_density_profile=cfg.poi_density_profile,
        seed=seed,
        population_target=layout_plan.population_target,
        node_by_id=node_by_id,
        coupling_mode=coupling.resolved_mode,
    )
    zone_type_counts = Counter(str(zone.zone_type.value) for zone in zones)
    zone_density_tiers = {
        zone.zone_id: _zone_density_tier_for_type(zone.zone_type)
        for zone in zones
    }
    district_archetypes = {
        zone.zone_id: _district_archetype_for_type(zone.zone_type)
        for zone in zones
    }
    topology_metadata = topology.metadata if isinstance(topology.metadata, Mapping) else {}
    district_centers = _coerce_xy_points(topology_metadata.get("district_centers"))
    subcenter_points = _coerce_xy_points(topology_metadata.get("subcenter_points"))
    district_id_by_zone_id = _district_ids_for_zones(
        zones=tuple(zones),
        district_centers=district_centers,
    )
    subcenter_zone_ids = _subcenter_zone_ids(
        zones=tuple(zones),
        points=subcenter_points,
    )
    poi_type_counts = Counter(str(poi.poi_type.value) for poi in pois)

    result = ZoningPlacementResult(
        zones=tuple(zones),
        pois=pois,
        node_zone_by_id=node_zone_by_id,
        zone_node_ids=zone_node_ids,
        metadata={
            "seed": seed,
            "zone_count": len(zones),
            "poi_count": len(pois),
            "poi_density_profile": cfg.poi_density_profile,
            "population_target": layout_plan.population_target,
            "zone_type_counts": dict(sorted(zone_type_counts.items())),
            "zoning_policy": (
                "morphology_anchor_centroid_capacity"
                if coupling.resolved_mode == "morphology_gated"
                else "hybrid_centroid_capacity"
            ),
            "zoning_center_selection_policy": layout_plan.selection_policy,
            "poi_placement_policy": (
                "morphology_spatial_cycle_and_center"
                if coupling.resolved_mode == "morphology_gated"
                else "hybrid_center_and_distributed"
            ),
            "zone_poi_coupling_requested_mode": coupling.requested_mode,
            "zone_poi_coupling_resolved_mode": coupling.resolved_mode,
            "zone_poi_coupling_fallback_reason": coupling.fallback_reason,
            "zone_poi_coupling_gate_version": coupling.gate_version,
            "zone_poi_coupling_gate_digest": coupling.gate_digest,
            "zone_poi_coupling_anchor_digest": coupling.anchor_digest,
            "morphology_style_id": str(topology_metadata.get("style_id", "")),
            "zone_density_tiers": zone_density_tiers,
            "district_archetype_by_zone_id": district_archetypes,
            "district_id_by_zone_id": district_id_by_zone_id,
            "subcenter_zone_ids": subcenter_zone_ids,
            "poi_type_counts": dict(sorted(poi_type_counts.items())),
        },
    )
    result.metadata["zoning_placement_fingerprint"] = zoning_placement_fingerprint(
        result
    )
    if validate:
        issues = result.validate(topology=topology)
        if issues:
            raise ValueError("Invalid zoning/POI placement: " + "; ".join(issues))
    return result


def build_zones_and_pois(
    topology: SyntheticCityTopologyLike,
    config: CityGenerationConfig | None = None,
    *,
    seed: int = 0,
    population_target: int | None = None,
    validate: bool = True,
) -> ZoningPlacementResult:
    """Alias for `generate_zones_and_pois`."""

    return generate_zones_and_pois(
        topology,
        config=config,
        seed=seed,
        population_target=population_target,
        validate=validate,
    )


def zoning_placement_fingerprint(result: ZoningPlacementResult) -> str:
    """Hash the effective zoning/POI placement, not its requested configuration."""

    payload = {
        "zones": [
            {
                "zone_id": zone.zone_id,
                "zone_type": zone.zone_type.value,
                "centroid_x": zone.centroid_x,
                "centroid_y": zone.centroid_y,
                "population_capacity": zone.population_capacity,
                "job_capacity": zone.job_capacity,
                "leisure_capacity": zone.leisure_capacity,
            }
            for zone in sorted(result.zones, key=lambda item: item.zone_id)
        ],
        "pois": [
            {
                "poi_id": poi.poi_id,
                "zone_id": poi.zone_id,
                "poi_type": poi.poi_type.value,
                "node_id": poi.node_id,
                "capacity_hint": poi.capacity_hint,
            }
            for poi in sorted(result.pois, key=lambda item: item.poi_id)
        ],
        "node_zone_by_id": sorted(result.node_zone_by_id.items()),
        "zone_node_ids": [
            (int(zone_id), tuple(sorted(int(node_id) for node_id in node_ids)))
            for zone_id, node_ids in sorted(result.zone_node_ids.items())
        ],
        "resolved_mode": result.metadata.get(
            "zone_poi_coupling_resolved_mode", "legacy"
        ),
        "zoning_policy": result.metadata.get("zoning_policy", ""),
        "poi_placement_policy": result.metadata.get("poi_placement_policy", ""),
    }
    stable_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def _resolve_zone_poi_coupling(
    *,
    topology: SyntheticCityTopologyLike,
    config: CityGenerationConfig,
) -> _ZonePoiCouplingDecision:
    requested = str(config.zone_poi_coupling_mode)
    if requested == "legacy":
        return _ZonePoiCouplingDecision(
            requested_mode=requested,
            resolved_mode="legacy",
            fallback_reason="",
            gate_version="",
            gate_digest="",
            anchor_digest="",
        )

    metadata = topology.metadata if isinstance(topology.metadata, Mapping) else {}
    raw_gate = metadata.get("morphology_quality_gate")
    if not isinstance(raw_gate, Mapping):
        return _legacy_coupling_fallback(requested, "gate_missing")

    gate_version = str(raw_gate.get("gate_version", ""))
    gate_digest = str(raw_gate.get("metrics_digest", ""))
    if raw_gate.get("accepted") is not True:
        return _legacy_coupling_fallback(
            requested,
            "gate_rejected",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    raw_failures = raw_gate.get("failures", ())
    if (
        not isinstance(raw_failures, (tuple, list))
        or any(not isinstance(item, str) for item in raw_failures)
        or raw_failures
    ):
        return _legacy_coupling_fallback(
            requested,
            "gate_rejected",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if gate_version != _MORPHOLOGY_COUPLING_GATE_VERSION:
        return _legacy_coupling_fallback(
            requested,
            "gate_version_mismatch",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if str(raw_gate.get("gate_scope", "")) != _MORPHOLOGY_COUPLING_GATE_SCOPE:
        return _legacy_coupling_fallback(
            requested,
            "gate_scope_mismatch",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )

    geometry = getattr(topology, "road_geometry", None)
    actual_fingerprint = str(getattr(geometry, "fingerprint", ""))
    gate_fingerprint = str(raw_gate.get("geometry_fingerprint", ""))
    metadata_fingerprint = str(metadata.get("road_geometry_fingerprint", ""))
    if (
        not actual_fingerprint
        or gate_fingerprint != actual_fingerprint
        or metadata_fingerprint != actual_fingerprint
    ):
        return _legacy_coupling_fallback(
            requested,
            "gate_geometry_mismatch",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if str(raw_gate.get("style_id", "")) != str(metadata.get("style_id", "")):
        return _legacy_coupling_fallback(
            requested,
            "gate_style_mismatch",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    raw_anchor_digest = str(raw_gate.get("placement_anchor_digest", ""))
    if not _is_sha256_digest(gate_digest) or not _is_sha256_digest(
        raw_anchor_digest
    ):
        return _legacy_coupling_fallback(
            requested,
            "gate_metadata_invalid",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    try:
        current_anchor_digest = morphology_placement_anchor_digest(
            metadata=metadata,
            nodes=tuple(topology.nodes),
            require_nonempty=True,
        )
    except (TypeError, ValueError, OverflowError):
        return _legacy_coupling_fallback(
            requested,
            "anchor_metadata_invalid",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if current_anchor_digest != raw_anchor_digest:
        return _legacy_coupling_fallback(
            requested,
            "anchor_digest_mismatch",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    try:
        current_metrics = compute_morphology_quality_metrics(topology)
        current_gate = evaluate_morphology_quality_gate(
            style_id=str(metadata.get("style_id", "")),
            geometry_fingerprint=actual_fingerprint,
            metrics=current_metrics,
            placement_anchor_digest=current_anchor_digest,
        )
    except (TypeError, ValueError, OverflowError):
        return _legacy_coupling_fallback(
            requested,
            "gate_recompute_failed",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if not current_gate.accepted:
        return _legacy_coupling_fallback(
            requested,
            "gate_rejected",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if current_gate.metrics_digest != gate_digest:
        return _legacy_coupling_fallback(
            requested,
            "gate_metrics_mismatch",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    if dict(current_gate.as_dict()) != dict(raw_gate):
        return _legacy_coupling_fallback(
            requested,
            "gate_metadata_invalid",
            gate_version=gate_version,
            gate_digest=gate_digest,
        )
    return _ZonePoiCouplingDecision(
        requested_mode=requested,
        resolved_mode="morphology_gated",
        fallback_reason="",
        gate_version=gate_version,
        gate_digest=gate_digest,
        anchor_digest=current_anchor_digest,
    )


def _legacy_coupling_fallback(
    requested_mode: str,
    fallback_reason: str,
    *,
    gate_version: str = "",
    gate_digest: str = "",
    anchor_digest: str = "",
) -> _ZonePoiCouplingDecision:
    return _ZonePoiCouplingDecision(
        requested_mode=requested_mode,
        resolved_mode="legacy",
        fallback_reason=fallback_reason,
        gate_version=gate_version,
        gate_digest=gate_digest,
        anchor_digest=anchor_digest,
    )


def _is_sha256_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(slots=True)
class _ZoningLayoutPlan:
    center_node_ids: tuple[int, ...]
    zone_types: tuple[ZoneType, ...]
    population_target: int
    selection_policy: str = "legacy_coordinate_stride"


@dataclass(frozen=True, slots=True)
class _ZonePoiCouplingDecision:
    requested_mode: str
    resolved_mode: str
    fallback_reason: str
    gate_version: str
    gate_digest: str
    anchor_digest: str


def _plan_zoning_layout(
    *,
    nodes: tuple[Node, ...],
    cfg: CityGenerationConfig,
    seed: int,
    population_target: int | None,
    topology: SyntheticCityTopologyLike,
    coupling_mode: str = "legacy",
) -> _ZoningLayoutPlan:
    """Plan zoning IDs/types before object materialization (JAX-portable boundary)."""

    resolved_population_target = _resolve_population_target(
        population_target=population_target,
        topology=topology,
    )
    zone_count_target = _target_zone_count(
        population_target=resolved_population_target,
        node_count=len(nodes),
    )
    zone_types = _zone_types_for_count(
        zone_count=zone_count_target,
        population_target=resolved_population_target,
    )
    if coupling_mode == "morphology_gated":
        centers = _choose_morphology_zone_centers(
            nodes,
            topology=topology,
            zone_types=zone_types,
        )
        selection_policy = "morphology_anchor_farthest_point_v1"
    else:
        centers = _choose_zone_centers(nodes, seed=seed, count=zone_count_target)
        selection_policy = "legacy_coordinate_stride"
    return _ZoningLayoutPlan(
        center_node_ids=tuple(node.node_id for node in centers),  # type: ignore[arg-type]
        zone_types=zone_types,
        population_target=resolved_population_target,
        selection_policy=selection_policy,
    )


def _choose_zone_centers(
    nodes: tuple[Node, ...],
    *,
    seed: int,
    count: int,
) -> tuple[Node, ...]:
    requested = max(4, int(count))
    ordered = tuple(sorted(nodes, key=lambda node: (node.x, node.y, node.node_id)))
    if requested >= len(ordered):
        return ordered
    stride = float(len(ordered)) / float(requested)
    selected: list[Node] = []
    selected_ids: set[int] = set()
    for idx in range(requested):
        pos = int((idx + 0.5) * stride)
        pos = max(0, min(len(ordered) - 1, pos))
        node = ordered[pos]
        if node.node_id in selected_ids:
            continue
        selected.append(node)
        selected_ids.add(node.node_id)
    if len(selected) < requested:
        rotation = int(seed) % len(ordered)
        rotated = ordered[rotation:] + ordered[:rotation]
        for node in rotated:
            if node.node_id in selected_ids:
                continue
            selected.append(node)
            selected_ids.add(node.node_id)
            if len(selected) >= requested:
                break
    return tuple(selected[:requested])


def _choose_morphology_zone_centers(
    nodes: tuple[Node, ...],
    *,
    topology: SyntheticCityTopologyLike,
    zone_types: tuple[ZoneType, ...],
) -> tuple[Node, ...]:
    """Choose diverse centers, then align their roles to the morphology anchors."""

    count = len(zone_types)
    metadata = topology.metadata if isinstance(topology.metadata, Mapping) else {}
    district_points = _coerce_xy_points(metadata.get("district_centers"))
    subcenter_points = _coerce_xy_points(metadata.get("subcenter_points"))
    downtown_points = _coerce_xy_points((metadata.get("downtown_anchor"),))
    if downtown_points:
        downtown = downtown_points[0]
    elif district_points:
        downtown = district_points[0]
    else:
        downtown = _mean_node_position(nodes)

    anchor_points = _unique_xy_points(
        (downtown,) + subcenter_points + district_points
    )
    selected: list[Node] = []
    selected_ids: set[int] = set()
    for point in anchor_points:
        node = _nearest_unused_node(nodes, point=point, used_ids=selected_ids)
        if node is None:
            break
        selected.append(node)
        selected_ids.add(node.node_id)
        if len(selected) >= count:
            break

    if not selected:
        node = _nearest_unused_node(nodes, point=downtown, used_ids=set())
        if node is not None:
            selected.append(node)
            selected_ids.add(node.node_id)
    while len(selected) < count:
        candidates = tuple(node for node in nodes if node.node_id not in selected_ids)
        if not candidates:
            break
        node = max(
            candidates,
            key=lambda candidate: (
                min(_distance_sq_nodes(candidate, other) for other in selected),
                -candidate.node_id,
            ),
        )
        selected.append(node)
        selected_ids.add(node.node_id)

    if len(selected) != count:
        raise ValueError("morphology zone center selection could not satisfy zone count")
    return _align_centers_to_zone_types(
        centers=tuple(selected),
        zone_types=zone_types,
        downtown=downtown,
        subcenter_points=subcenter_points,
    )


def _align_centers_to_zone_types(
    *,
    centers: tuple[Node, ...],
    zone_types: tuple[ZoneType, ...],
    downtown: tuple[float, float],
    subcenter_points: tuple[tuple[float, float], ...],
) -> tuple[Node, ...]:
    remaining = list(centers)
    assigned: dict[ZoneType, list[Node]] = {zone_type: [] for zone_type in ZoneType}
    requested_counts = Counter(zone_types)

    for _ in range(requested_counts[ZoneType.CBD_COMMERCIAL]):
        assigned[ZoneType.CBD_COMMERCIAL].append(
            _pop_best_node(remaining, key=lambda node: _distance_sq_point(node, downtown))
        )
    activity_points = subcenter_points or (downtown,)
    for idx in range(requested_counts[ZoneType.MIXED_USE]):
        point = activity_points[idx % len(activity_points)]
        assigned[ZoneType.MIXED_USE].append(
            _pop_best_node(remaining, key=lambda node: _distance_sq_point(node, point))
        )
    for _ in range(requested_counts[ZoneType.INDUSTRIAL]):
        assigned[ZoneType.INDUSTRIAL].append(
            _pop_best_node(
                remaining,
                key=lambda node: -_distance_sq_point(node, downtown),
            )
        )
    assigned[ZoneType.RESIDENTIAL].extend(
        sorted(
            remaining,
            key=lambda node: (
                math.atan2(node.y - downtown[1], node.x - downtown[0]),
                _distance_sq_point(node, downtown),
                node.node_id,
            ),
        )
    )

    output: list[Node] = []
    offsets = {zone_type: 0 for zone_type in ZoneType}
    for zone_type in zone_types:
        offset = offsets[zone_type]
        candidates = assigned[zone_type]
        if offset >= len(candidates):
            raise ValueError(f"missing morphology center for zone type {zone_type.value}")
        output.append(candidates[offset])
        offsets[zone_type] += 1
    return tuple(output)


def _pop_best_node(nodes: list[Node], *, key: Any) -> Node:
    if not nodes:
        raise ValueError("morphology zone center pool exhausted")
    best_index = min(range(len(nodes)), key=lambda idx: (key(nodes[idx]), nodes[idx].node_id))
    return nodes.pop(best_index)


def _nearest_unused_node(
    nodes: tuple[Node, ...],
    *,
    point: tuple[float, float],
    used_ids: set[int],
) -> Node | None:
    candidates = tuple(node for node in nodes if node.node_id not in used_ids)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda node: (_distance_sq_point(node, point), node.node_id),
    )


def _mean_node_position(nodes: tuple[Node, ...]) -> tuple[float, float]:
    return (
        sum(float(node.x) for node in nodes) / len(nodes),
        sum(float(node.y) for node in nodes) / len(nodes),
    )


def _unique_xy_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    output: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for x, y in points:
        point = (float(x), float(y))
        if point in seen:
            continue
        seen.add(point)
        output.append(point)
    return tuple(output)


def _distance_sq_point(node: Node, point: tuple[float, float]) -> float:
    return (float(node.x) - point[0]) ** 2 + (float(node.y) - point[1]) ** 2


def _distance_sq_nodes(left: Node, right: Node) -> float:
    return (float(left.x) - float(right.x)) ** 2 + (
        float(left.y) - float(right.y)
    ) ** 2


def _resolve_population_target(
    *,
    population_target: int | None,
    topology: SyntheticCityTopologyLike,
) -> int:
    if population_target is not None:
        resolved = int(population_target)
    else:
        resolved = int(topology.metadata.get("population_target", 100_000))
    if resolved < 1:
        raise ValueError("population_target must be >= 1")
    return resolved


def _target_zone_count(*, population_target: int, node_count: int) -> int:
    if population_target >= 100_000:
        target = 24
    elif population_target >= 50_000:
        target = 12
    elif population_target >= 20_000:
        target = 8
    else:
        target = 4
    return max(4, min(int(target), max(4, int(node_count))))


def _zone_types_for_count(*, zone_count: int, population_target: int) -> tuple[ZoneType, ...]:
    count = max(4, int(zone_count))
    if population_target >= 100_000:
        residential = max(8, int(round(count * 0.40)))
        industrial = max(2, int(round(count * 0.15)))
        mixed_use = max(4, int(round(count * 0.20)))
        cbd = count - residential - industrial - mixed_use
        if cbd < 4:
            deficit = 4 - cbd
            shiftable = max(0, residential - 8)
            take = min(deficit, shiftable)
            residential -= take
            deficit -= take
            if deficit > 0:
                mixed_take = min(deficit, max(0, mixed_use - 4))
                mixed_use -= mixed_take
                deficit -= mixed_take
            cbd = count - residential - industrial - mixed_use
    else:
        residential = count // 2
        industrial = max(1, count // 8)
        cbd = max(1, count // 6)
        mixed_use = count - residential - industrial - cbd
        if mixed_use < 1:
            mixed_use = 1
            residential = max(1, residential - 1)
    sequence = (
        [ZoneType.RESIDENTIAL] * residential
        + [ZoneType.CBD_COMMERCIAL] * cbd
        + [ZoneType.INDUSTRIAL] * industrial
        + [ZoneType.MIXED_USE] * mixed_use
    )
    if len(sequence) < count:
        sequence.extend([ZoneType.RESIDENTIAL] * (count - len(sequence)))
    return tuple(sequence[:count])


def _zone_capacities_for_type(
    *,
    zone_type: ZoneType,
    share: float,
    population_target: int,
) -> tuple[int, int, int]:
    base = max(1, int(round(population_target * share)))
    if zone_type == ZoneType.RESIDENTIAL:
        return (base, max(1, base // 5), max(1, base // 4))
    if zone_type == ZoneType.CBD_COMMERCIAL:
        return (max(1, base // 5), int(base * 2.0), max(1, base // 2))
    if zone_type == ZoneType.INDUSTRIAL:
        return (max(1, base // 8), int(base * 3.0 // 2), max(1, base // 6))
    return (max(1, int(base * 0.8)), max(1, int(base * 0.9)), max(1, int(base * 0.8)))


def _nearest_zone_id(
    node: Node,
    centers_by_zone_id: dict[int, tuple[float, float]],
) -> int:
    return min(
        centers_by_zone_id,
        key=lambda zone_id: (
            (node.x - centers_by_zone_id[zone_id][0]) ** 2
            + (node.y - centers_by_zone_id[zone_id][1]) ** 2,
            zone_id,
        ),
    )


def _generate_pois(
    *,
    zones: tuple[Zone, ...],
    zone_node_ids: dict[int, tuple[int, ...]],
    center_node_id_by_zone: dict[int, int],
    poi_density_profile: str,
    seed: int,
    population_target: int,
    node_by_id: Mapping[int, Node],
    coupling_mode: str,
) -> tuple[POI, ...]:
    density = str(poi_density_profile).lower()
    poi_multiplier = {"sparse": 1, "baseline": 2, "dense": 3}.get(density, 2)
    target_poi_count = _target_poi_count_by_population(
        population_target=population_target,
        density_profile=density,
    )
    base_mix_total = 0
    for zone in zones:
        for _, count in _poi_mix_for_zone(zone.zone_type, multiplier=poi_multiplier):
            base_mix_total += int(count)
    scaling = max(1, int(round(float(target_poi_count) / float(max(1, base_mix_total)))))

    poi_id = 1
    pois: list[POI] = []
    seed_offset = seed % 7

    for zone in zones:
        anchor_nodes = zone_node_ids.get(zone.zone_id, ())
        if not anchor_nodes:
            continue
        if coupling_mode == "morphology_gated":
            anchor_nodes = _spatially_order_zone_nodes(
                anchor_nodes,
                node_by_id=node_by_id,
                zone=zone,
            )
        mix = _poi_mix_for_zone(zone.zone_type, multiplier=poi_multiplier)
        node_cycle = _cycle_nodes(anchor_nodes, offset=seed_offset + zone.zone_id)
        center_node_id = center_node_id_by_zone.get(zone.zone_id)
        for poi_type, count in mix:
            scaled_count = max(1, int(count) * scaling)
            for idx in range(scaled_count):
                # Hybrid placement: keep core anchors near district center while
                # still distributing destinations across zone nodes.
                if center_node_id is not None and idx % 3 == 0:
                    node_id = int(center_node_id)
                else:
                    node_id = next(node_cycle)
                capacity_hint = _poi_capacity_hint(zone, poi_type=poi_type)
                pois.append(
                    POI(
                        poi_id=poi_id,
                        zone_id=zone.zone_id,
                        poi_type=poi_type,
                        node_id=node_id,
                        capacity_hint=capacity_hint,
                    )
                )
                poi_id += 1
    return tuple(pois)


def _spatially_order_zone_nodes(
    node_ids: tuple[int, ...],
    *,
    node_by_id: Mapping[int, Node],
    zone: Zone,
) -> tuple[int, ...]:
    return tuple(
        sorted(
            node_ids,
            key=lambda node_id: (
                math.atan2(
                    float(node_by_id[node_id].y) - zone.centroid_y,
                    float(node_by_id[node_id].x) - zone.centroid_x,
                ),
                (float(node_by_id[node_id].x) - zone.centroid_x) ** 2
                + (float(node_by_id[node_id].y) - zone.centroid_y) ** 2,
                node_id,
            ),
        )
    )


def _poi_mix_for_zone(zone_type: ZoneType, *, multiplier: int) -> tuple[tuple[POIType, int], ...]:
    if zone_type == ZoneType.RESIDENTIAL:
        return (
            (POIType.HOME, 3 * multiplier),
            (POIType.LEISURE, 1 * multiplier),
            (POIType.WORKPLACE, 1),
        )
    if zone_type == ZoneType.CBD_COMMERCIAL:
        return (
            (POIType.WORKPLACE, 4 * multiplier),
            (POIType.LEISURE, 2 * multiplier),
            (POIType.HOME, 1),
        )
    if zone_type == ZoneType.INDUSTRIAL:
        return (
            (POIType.WORKPLACE, 3 * multiplier),
            (POIType.LEISURE, 1),
            (POIType.HOME, 1),
        )
    return (
        (POIType.HOME, 2 * multiplier),
        (POIType.WORKPLACE, 2 * multiplier),
        (POIType.LEISURE, 2 * multiplier),
    )


def _poi_capacity_hint(zone: Zone, *, poi_type: POIType) -> int:
    if poi_type == POIType.HOME:
        return max(1, zone.population_capacity // 10)
    if poi_type == POIType.WORKPLACE:
        return max(1, zone.job_capacity // 10)
    return max(1, zone.leisure_capacity // 10)


def _target_poi_count_by_population(*, population_target: int, density_profile: str) -> int:
    base = max(24, int(population_target) // 20)
    if density_profile == "dense":
        factor = 1.0
    elif density_profile == "sparse":
        factor = 0.45
    else:
        factor = 0.7
    return max(24, int(round(float(base) * factor)))


def _zone_density_tier_for_type(zone_type: ZoneType) -> str:
    if zone_type == ZoneType.CBD_COMMERCIAL:
        return "high"
    if zone_type == ZoneType.MIXED_USE:
        return "low"
    return "medium"


def _district_archetype_for_type(zone_type: ZoneType) -> str:
    if zone_type == ZoneType.RESIDENTIAL:
        return "residential_neighborhood"
    if zone_type == ZoneType.CBD_COMMERCIAL:
        return "central_business_core"
    if zone_type == ZoneType.INDUSTRIAL:
        return "industrial_belt"
    return "mixed_activity_hub"


def _coerce_xy_points(raw: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return ()
    out: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, Iterable) or isinstance(item, (str, bytes)):
            continue
        pair = tuple(item)
        if len(pair) < 2:
            continue
        try:
            out.append((float(pair[0]), float(pair[1])))
        except (TypeError, ValueError):
            continue
    return tuple(out)


def _district_ids_for_zones(
    *,
    zones: tuple[Zone, ...],
    district_centers: tuple[tuple[float, float], ...],
) -> dict[int, int]:
    if not zones:
        return {}
    if not district_centers:
        return {zone.zone_id: ((idx % 4) + 1) for idx, zone in enumerate(zones)}
    out: dict[int, int] = {}
    for zone in zones:
        district_idx = min(
            range(len(district_centers)),
            key=lambda idx: (
                (zone.centroid_x - district_centers[idx][0]) ** 2
                + (zone.centroid_y - district_centers[idx][1]) ** 2,
                idx,
            ),
        )
        out[zone.zone_id] = int(district_idx) + 1
    return out


def _subcenter_zone_ids(
    *,
    zones: tuple[Zone, ...],
    points: tuple[tuple[float, float], ...],
) -> tuple[int, ...]:
    if not zones:
        return ()
    zone_positions = {zone.zone_id: (zone.centroid_x, zone.centroid_y) for zone in zones}
    selected: list[int] = []
    seen: set[int] = set()
    for x, y in points:
        zone_id = min(
            zone_positions,
            key=lambda candidate: (
                (x - zone_positions[candidate][0]) ** 2
                + (y - zone_positions[candidate][1]) ** 2,
                candidate,
            ),
        )
        if zone_id in seen:
            continue
        seen.add(zone_id)
        selected.append(int(zone_id))
    if len(selected) < 6:
        ranked = sorted(
            zones,
            key=lambda zone: (zone.job_capacity + zone.leisure_capacity, zone.zone_id),
            reverse=True,
        )
        for zone in ranked:
            if zone.zone_id in seen:
                continue
            seen.add(zone.zone_id)
            selected.append(zone.zone_id)
            if len(selected) >= min(6, len(zones)):
                break
    return tuple(int(zone_id) for zone_id in selected)


def _cycle_nodes(node_ids: Iterable[int], *, offset: int = 0) -> Iterator[int]:
    ordered = tuple(int(node_id) for node_id in node_ids)
    if not ordered:
        raise ValueError("node_ids must not be empty")
    start = offset % len(ordered)
    idx = start
    while True:
        yield ordered[idx]
        idx = (idx + 1) % len(ordered)
