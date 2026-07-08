"""Zoning and POI placement generation for synthetic city topologies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator, Mapping, Protocol

from metroflow.city.graph import Node
from metroflow.sim.config import CityGenerationConfig, ZoneType

__all__ = [
    "POIType",
    "Zone",
    "POI",
    "ZoningPlacementResult",
    "generate_zones_and_pois",
    "build_zones_and_pois",
]


class SyntheticCityTopologyLike(Protocol):
    """Topology surface required by zoning without depending on a generator module."""

    nodes: tuple[Node, ...]
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
    layout_plan = _plan_zoning_layout(
        nodes=nodes,
        cfg=cfg,
        seed=seed,
        population_target=population_target,
        topology=topology,
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
            "zoning_policy": "hybrid_centroid_capacity",
            "poi_placement_policy": "hybrid_center_and_distributed",
            "zone_density_tiers": zone_density_tiers,
            "district_archetype_by_zone_id": district_archetypes,
            "district_id_by_zone_id": district_id_by_zone_id,
            "subcenter_zone_ids": subcenter_zone_ids,
            "poi_type_counts": dict(sorted(poi_type_counts.items())),
        },
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


@dataclass(slots=True)
class _ZoningLayoutPlan:
    center_node_ids: tuple[int, ...]
    zone_types: tuple[ZoneType, ...]
    population_target: int


def _plan_zoning_layout(
    *,
    nodes: tuple[Node, ...],
    cfg: CityGenerationConfig,
    seed: int,
    population_target: int | None,
    topology: SyntheticCityTopologyLike,
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
    centers = _choose_zone_centers(nodes, seed=seed, count=zone_count_target)
    zone_types = _zone_types_for_count(
        zone_count=zone_count_target,
        population_target=resolved_population_target,
    )
    return _ZoningLayoutPlan(
        center_node_ids=tuple(node.node_id for node in centers),  # type: ignore[arg-type]
        zone_types=zone_types,
        population_target=resolved_population_target,
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
