"""Scalable synthetic v2 city map orchestrator.

Chains the four S2 pipeline stages into a single authority that
``sim.init`` can consume in the same slot as ``generate_city_map``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from metroflow.city.generated_map import PreviewCityTopology
from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_authority import (
    ScalableStaticAuthority,
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
from metroflow.city.zones import ZoningPlacementResult, generate_zones_and_pois
from metroflow.city.graph import RoadNetworkCSR

__all__ = [
    "ScalableCityMap",
    "build_scalable_city_map",
]


class _ScalableCityConfigLike(Protocol):
    topology_mode: str
    morphology_style_id: str
    zone_poi_coupling_mode: str
    scale_spec: CityScaleSpec | None


@dataclass(frozen=True, slots=True)
class ScalableCityMap:
    """End-to-end scalable synthetic v2 city map result.

    Provides ``topology``, ``zoning``, and ``road_csr`` in the same
    shape that ``sim.init._InitialCityAuthority`` expects so the
    simulation runtime can consume it without special-casing.
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
        object.__setattr__(
            self,
            "fingerprint",
            self.static_authority.fingerprint,
        )


def build_scalable_city_map(
    config: _ScalableCityConfigLike,
    scenario_id: str,
    seed: int,
    *,
    population_target: int | None = None,
) -> ScalableCityMap:
    """Build an end-to-end scalable synthetic v2 city map.

    This is the single public orchestrator that ``sim.init`` and
    gallery renderers should call.  It chains:

    1. ``build_scalable_street_network``
    2. ``build_scalable_block_authority``
    3. ``compile_scalable_topology``
    4. ``build_scalable_static_authority``
    5. ``generate_zones_and_pois``

    Parameters
    ----------
    config : _ScalableCityConfigLike
        Must have ``topology_mode == "scalable_synthetic_v2"`` and a
        non-None ``scale_spec``.
    scenario_id : str
        Scenario identifier for downstream metadata.
    seed : int
        Deterministic generation seed.
    population_target : int | None
        If supplied, forwarded to zone/POI generation for demand
        allocation.  Defaults to ``scale_spec.target_population``.
    """

    if str(config.topology_mode) != "scalable_synthetic_v2":
        raise ValueError(
            "build_scalable_city_map requires topology_mode='scalable_synthetic_v2'"
        )
    if config.scale_spec is None:
        raise ValueError("build_scalable_city_map requires a non-None scale_spec")

    scale_spec: CityScaleSpec = config.scale_spec
    style_id = str(config.morphology_style_id)
    seed = int(seed)

    # Stage 1: S2 physical topology
    network = build_scalable_street_network(scale_spec, style_id, seed)

    # Stage 2: DCEL / block authority
    blocks = build_scalable_block_authority(network)

    # Stage 3: compiled topology (PreviewCityTopology + RoadNetworkCSR)
    compiled = compile_scalable_topology(network, block_authority=blocks)

    # Stage 4: static authority
    static_authority = build_scalable_static_authority(
        scale_spec, style_id, seed, network, blocks, compiled,
    )

    # Stage 5: zones / POIs from compiled topology
    effective_population = (
        population_target
        if population_target is not None
        else scale_spec.target_population
    )
    zoning = generate_zones_and_pois(
        compiled.topology,
        config=None,
        seed=seed,
        population_target=effective_population,
        validate=True,
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
