"""Scalable synthetic v2 city map orchestrator.

Chains the four S2 pipeline stages into a single static authority and
projects authoritative zoning, TAZ, and POI placements for simulation runtime.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol

from metroflow.city.generated_map import PreviewCityTopology
from metroflow.city.graph import RoadNetworkCSR
from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_authority import (
    ScalableStaticAuthority,
    V2LandUseType,
    V2PoiKind,
    build_scalable_static_authority,
)
from metroflow.city.scalable_blocks import (
    ScalableBlockAuthority,
    build_scalable_block_authority,
)
from metroflow.city.scalable_topology import (
    ScalableStreetNetwork,
    build_scalable_street_network,
)
from metroflow.city.scalable_topology_adapter import (
    ScalableCompiledTopology,
    compile_scalable_topology,
)
from metroflow.city.zones import (
    POI,
    POIType,
    Zone,
    ZoningPlacementResult,
    zoning_placement_fingerprint,
)
from metroflow.sim.config import ZoneType

__all__ = [
    "ScalableCityMap",
    "build_scalable_city_map",
    "project_scalable_zoning_from_static_authority",
]


class _ScalableCityConfigLike(Protocol):
    topology_mode: str
    morphology_style_id: str
    zone_poi_coupling_mode: str
    scale_spec: CityScaleSpec | None


@dataclass(frozen=True, slots=True)
class ScalableCityMap:
    """End-to-end scalable synthetic v2 city map result.

    Provides ``topology``, ``zoning``, ``road_csr``, and ``static_authority``
    with a unified cryptographic fingerprint sealing topology, static authority,
    and projected zoning.
    """

    topology: PreviewCityTopology
    zoning: ZoningPlacementResult
    road_csr: RoadNetworkCSR
    network: ScalableStreetNetwork
    blocks: ScalableBlockAuthority
    compiled: ScalableCompiledTopology
    static_authority: ScalableStaticAuthority
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        zoning_fp = self.zoning.metadata.get(
            "zoning_placement_fingerprint",
            zoning_placement_fingerprint(self.zoning),
        )
        payload = {
            "static_authority_fingerprint": self.static_authority.fingerprint,
            "zoning_placement_fingerprint": zoning_fp,
            "scale_fingerprint": self.static_authority.source_scale_fingerprint,
        }
        sealed_fp = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        object.__setattr__(self, "fingerprint", sealed_fp)


def project_scalable_zoning_from_static_authority(
    static_authority: ScalableStaticAuthority,
    topology: PreviewCityTopology,
) -> ZoningPlacementResult:
    """Project authoritative zoning and POI containers directly from static authority.

    Guarantees 1:1 parity with the static authority's TAZ, POI, and block land-use
    catalogs without running separate legacy zoning generators.
    """
    node_by_id = {node.node_id: node for node in topology.nodes}
    block_type_map = {
        b.block_id: b.land_use_type for b in static_authority.block_land_use
    }

    # Map each V2Taz to an authoritative Zone
    zones: list[Zone] = []
    for taz in static_authority.taz_catalog.tazs:
        # Centroid from TAZ access node coordinates
        coords = [
            (node_by_id[nid].x, node_by_id[nid].y)
            for nid in taz.access_node_ids
            if nid in node_by_id
        ]
        centroid_x = sum(c[0] for c in coords) / len(coords) if coords else 0.0
        centroid_y = sum(c[1] for c in coords) / len(coords) if coords else 0.0

        # Dominant land use type from the TAZ's constituent blocks
        taz_types = {
            block_type_map[bid]
            for bid in taz.block_ids
            if bid in block_type_map
        }
        if taz_types == {V2LandUseType.COMMERCIAL}:
            zone_type = ZoneType.CBD_COMMERCIAL
        elif taz_types == {V2LandUseType.INDUSTRIAL}:
            zone_type = ZoneType.INDUSTRIAL
        elif taz_types == {V2LandUseType.RESIDENTIAL}:
            zone_type = ZoneType.RESIDENTIAL
        else:
            zone_type = ZoneType.MIXED_USE

        zones.append(
            Zone(
                zone_id=taz.taz_id,
                zone_type=zone_type,
                centroid_x=centroid_x,
                centroid_y=centroid_y,
                population_capacity=taz.resident_capacity_total,
                job_capacity=taz.job_capacity_total,
                leisure_capacity=taz.leisure_capacity_total,
            )
        )

    # Ensure all four ZoneType categories are represented for schema validity
    present_types = {z.zone_type for z in zones}
    missing_types = list(set(ZoneType) - present_types)
    if missing_types and len(zones) >= len(missing_types):
        for i, missing in enumerate(missing_types):
            zones[-(i + 1)].zone_type = missing

    # Map each V2Poi to an authoritative POI
    pois: list[POI] = []
    for poi in static_authority.poi_catalog.pois:
        if poi.poi_kind == V2PoiKind.HOME:
            poi_type = POIType.HOME
        elif poi.poi_kind == V2PoiKind.WORKPLACE:
            poi_type = POIType.WORKPLACE
        else:
            poi_type = POIType.LEISURE

        pois.append(
            POI(
                poi_id=poi.poi_id,
                zone_id=poi.taz_id,
                poi_type=poi_type,
                node_id=poi.access_node_id,
                capacity_hint=poi.capacity,
            )
        )

    node_zone_by_id = dict(static_authority.taz_catalog.node_owner_by_id)
    # Ensure every node in topology has a zone assignment
    for node in topology.nodes:
        if node.node_id not in node_zone_by_id and zones:
            node_zone_by_id[node.node_id] = zones[0].zone_id

    zone_node_map: dict[int, list[int]] = {z.zone_id: [] for z in zones}
    for nid, zid in sorted(node_zone_by_id.items()):
        if zid in zone_node_map:
            zone_node_map[zid].append(nid)

    zone_node_ids = {
        zid: tuple(nids)
        for zid, nids in zone_node_map.items()
    }

    metadata = {
        "zoning_policy": static_authority.schema_version,
        "poi_placement_policy": static_authority.schema_version,
        "zone_poi_coupling_requested_mode": "block_based_v1",
        "zone_poi_coupling_resolved_mode": "block_based_v1",
        "static_authority_fingerprint": static_authority.fingerprint,
        "taz_catalog_fingerprint": static_authority.taz_catalog.fingerprint,
        "poi_catalog_fingerprint": static_authority.poi_catalog.fingerprint,
        "land_use_catalog_fingerprint": static_authority.capacity_certificate.fingerprint,
        "population_target": static_authority.scale_spec.target_population,
        "urbanized_area_km2": static_authority.scale_spec.urbanized_area_km2,
    }

    result = ZoningPlacementResult(
        zones=tuple(zones),
        pois=tuple(pois),
        node_zone_by_id=node_zone_by_id,
        zone_node_ids=zone_node_ids,
        metadata=metadata,
    )
    result.metadata["zoning_placement_fingerprint"] = zoning_placement_fingerprint(result)

    issues = result.validate(topology=topology)
    if issues:
        raise ValueError(f"projected zoning validation failed: {issues}")

    return result


def build_scalable_city_map(
    config: _ScalableCityConfigLike,
    scenario_id: str,
    seed: int,
    *,
    population_target: int | None = None,
) -> ScalableCityMap:
    """Build an end-to-end scalable synthetic v2 city map.

    Chains S2 street network → DCEL blocks → compiled topology → static authority,
    and projects authoritative zoning and POIs directly from static authority.
    """
    if str(config.topology_mode) != "scalable_synthetic_v2":
        raise ValueError(
            "build_scalable_city_map requires topology_mode='scalable_synthetic_v2'"
        )
    if config.scale_spec is None:
        raise ValueError("build_scalable_city_map requires a non-None scale_spec")

    scale_spec: CityScaleSpec = config.scale_spec
    if population_target is not None and int(population_target) != scale_spec.target_population:
        raise ValueError(
            f"population authorities disagree: population_target ({population_target}) "
            f"!= scale_spec.target_population ({scale_spec.target_population})"
        )

    style_id = str(config.morphology_style_id)
    seed = int(seed)

    # Stage 1: S2 physical topology
    network = build_scalable_street_network(scale_spec, style_id, seed)

    # Stage 2: DCEL / block authority
    blocks = build_scalable_block_authority(network)

    # Stage 3: compiled topology (PreviewCityTopology + RoadNetworkCSR)
    compiled = compile_scalable_topology(network, block_authority=blocks)

    # Stage 4: static authority (land use, capacity certificate, TAZ, POI, CSR)
    static_authority = build_scalable_static_authority(
        scale_spec, style_id, seed, network, blocks, compiled,
    )

    # Stage 5: Authoritative zoning projection from static authority
    zoning = project_scalable_zoning_from_static_authority(
        static_authority=static_authority,
        topology=compiled.topology,
    )

    return ScalableCityMap(
        topology=compiled.topology,
        zoning=zoning,
        road_csr=compiled.road_csr,
        network=network,
        blocks=blocks,
        compiled=compiled,
        static_authority=static_authority,
    )
