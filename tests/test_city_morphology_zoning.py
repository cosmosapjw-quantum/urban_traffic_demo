from __future__ import annotations

from collections import Counter
from dataclasses import replace
from types import MappingProxyType

import pytest


def _generated_topology(seed: int = 17):
    from metroflow.city.generator_v2 import GeneratorV2

    return GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": seed,
            "preview_mode": "sidecar_local_fabric_planar",
            "style_id": "polycentric_tod",
        }
    )


def test_zone_poi_coupling_config_defaults_legacy_and_rejects_unknown() -> None:
    from metroflow.sim.config import CityGenerationConfig

    assert CityGenerationConfig().zone_poi_coupling_mode == "legacy"
    with pytest.raises(ValueError, match="zone_poi_coupling_mode"):
        CityGenerationConfig(zone_poi_coupling_mode="learned")


def test_explicit_legacy_zoning_preserves_default_result() -> None:
    from metroflow.city.zones import generate_zones_and_pois
    from metroflow.sim.config import CityGenerationConfig

    topology = _generated_topology()
    default = generate_zones_and_pois(
        topology,
        CityGenerationConfig(),
        seed=17,
        population_target=20_000,
    )
    explicit = generate_zones_and_pois(
        topology,
        CityGenerationConfig(zone_poi_coupling_mode="legacy"),
        seed=17,
        population_target=20_000,
    )

    assert default == explicit
    assert default.metadata["zone_poi_coupling_resolved_mode"] == "legacy"
    assert (
        default.metadata["zoning_placement_fingerprint"]
        == "daf2fa8a40248208499a5533db0fbe28914f4a0dd25dadd869066ae1486dabd3"
    )


def test_new_config_and_replay_fields_preserve_positional_compatibility() -> None:
    from metroflow.city.morphology_quality import MorphologyQualityGate
    from metroflow.sim.config import CityGenerationConfig
    from metroflow.sim.replay import RuntimeReplayBoundary

    hierarchy = dict(CityGenerationConfig().road_hierarchy_profile)
    config = CityGenerationConfig("standard", "auto", hierarchy)
    assert config.road_hierarchy_profile == hierarchy
    boundary = RuntimeReplayBoundary(
        "scenario",
        7,
        3,
        "config",
        "cache",
        "rust_cpu",
        "auto",
        "baseline",
        "rust_cpu",
    )
    assert boundary.edge_backend == "rust_cpu"
    assert boundary.agent_backend == "rust_cpu"
    assert boundary.static_input_fingerprint == ""
    gate = MorphologyQualityGate(True, "v", "scope", "style", "geometry", "digest", ())
    assert gate.placement_anchor_digest == ""


def test_admitted_morphology_zoning_is_deterministic_and_preserves_aggregates() -> None:
    from metroflow.city.zones import generate_zones_and_pois
    from metroflow.sim.config import CityGenerationConfig

    topology = _generated_topology()
    legacy = generate_zones_and_pois(
        topology,
        CityGenerationConfig(),
        seed=17,
        population_target=20_000,
    )
    config = CityGenerationConfig(zone_poi_coupling_mode="morphology_gated")
    first = generate_zones_and_pois(
        topology,
        config,
        seed=17,
        population_target=20_000,
    )
    second = generate_zones_and_pois(
        topology,
        config,
        seed=17,
        population_target=20_000,
    )

    assert first == second
    assert first.metadata["zone_poi_coupling_resolved_mode"] == "morphology_gated"
    assert first.metadata["zone_poi_coupling_gate_version"] == "morphology_quality_v2"
    assert len(first.metadata["zone_poi_coupling_anchor_digest"]) == 64
    assert len(first.metadata["zoning_placement_fingerprint"]) == 64
    assert [zone.zone_type for zone in first.zones] == [zone.zone_type for zone in legacy.zones]
    assert sorted(
        (zone.zone_type.value, zone.population_capacity, zone.job_capacity, zone.leisure_capacity)
        for zone in first.zones
    ) == sorted(
        (zone.zone_type.value, zone.population_capacity, zone.job_capacity, zone.leisure_capacity)
        for zone in legacy.zones
    )
    assert tuple((zone.centroid_x, zone.centroid_y) for zone in first.zones) != tuple(
        (zone.centroid_x, zone.centroid_y) for zone in legacy.zones
    )
    assert tuple(poi.node_id for poi in first.pois) != tuple(
        poi.node_id for poi in legacy.pois
    )
    assert len(first.pois) == len(legacy.pois)
    assert [zone.zone_id for zone in first.zones] == [zone.zone_id for zone in legacy.zones]
    assert [poi.poi_id for poi in first.pois] == [poi.poi_id for poi in legacy.pois]
    assert Counter(
        (poi.poi_type, poi.capacity_hint) for poi in first.pois
    ) == Counter((poi.poi_type, poi.capacity_hint) for poi in legacy.pois)


@pytest.mark.parametrize(
    ("gate_patch", "expected_reason"),
    (
        ({"accepted": False}, "gate_rejected"),
        ({"accepted": True, "failures": ("forged",)}, "gate_rejected"),
        ({"gate_version": "morphology_quality_v1"}, "gate_version_mismatch"),
        ({"geometry_fingerprint": "stale"}, "gate_geometry_mismatch"),
        ({"metrics_digest": "0" * 64}, "gate_metrics_mismatch"),
        ({"placement_anchor_digest": "0" * 64}, "anchor_digest_mismatch"),
    ),
)
def test_morphology_zoning_falls_back_exactly_when_gate_is_not_admissible(
    gate_patch: dict[str, object],
    expected_reason: str,
) -> None:
    from metroflow.city.zones import generate_zones_and_pois
    from metroflow.sim.config import CityGenerationConfig

    topology = _generated_topology()
    metadata = dict(topology.metadata)
    gate = dict(metadata["morphology_quality_gate"])
    gate.update(gate_patch)
    metadata["morphology_quality_gate"] = gate
    stale = replace(topology, metadata=metadata)
    legacy = generate_zones_and_pois(
        stale,
        CityGenerationConfig(),
        seed=17,
        population_target=20_000,
    )
    fallback = generate_zones_and_pois(
        stale,
        CityGenerationConfig(zone_poi_coupling_mode="morphology_gated"),
        seed=17,
        population_target=20_000,
    )

    assert fallback.zones == legacy.zones
    assert fallback.pois == legacy.pois
    assert fallback.node_zone_by_id == legacy.node_zone_by_id
    assert fallback.zone_node_ids == legacy.zone_node_ids
    assert fallback.metadata["zone_poi_coupling_resolved_mode"] == "legacy"
    assert fallback.metadata["zone_poi_coupling_fallback_reason"] == expected_reason


@pytest.mark.parametrize(
    ("metadata_patch", "expected_reason"),
    (
        (
            {"district_centers": (), "subcenter_points": (), "downtown_anchor": None},
            "anchor_metadata_invalid",
        ),
        ({"district_centers": ((1.0e12, 1.0e12),)}, "anchor_metadata_invalid"),
        ({"district_centers": ((0.0, 0.0),)}, "anchor_digest_mismatch"),
    ),
)
def test_morphology_zoning_rejects_unbound_or_invalid_anchor_metadata(
    metadata_patch: dict[str, object],
    expected_reason: str,
) -> None:
    from metroflow.city.zones import generate_zones_and_pois
    from metroflow.sim.config import CityGenerationConfig

    topology = _generated_topology()
    metadata = dict(topology.metadata)
    metadata.update(metadata_patch)
    stale = replace(topology, metadata=metadata)
    result = generate_zones_and_pois(
        stale,
        CityGenerationConfig(zone_poi_coupling_mode="morphology_gated"),
        seed=17,
        population_target=20_000,
    )

    assert result.metadata["zone_poi_coupling_resolved_mode"] == "legacy"
    assert result.metadata["zone_poi_coupling_fallback_reason"] == expected_reason


def test_runtime_replay_boundary_fingerprints_static_zoning_input() -> None:
    from metroflow.sim.config import CityGenerationConfig, SimulationConfig
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed

    config = SimulationConfig(population_target=500, active_agent_capacity=16)
    legacy = build_initial_simulation_state(
        config=config,
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar",
            morphology_style_id="polycentric_tod",
        ),
        scenario_seed=17,
    ).state
    morphology = build_initial_simulation_state(
        config=config,
        city_config=CityGenerationConfig(
            topology_mode="sidecar_local_fabric_planar",
            morphology_style_id="polycentric_tod",
            zone_poi_coupling_mode="morphology_gated",
        ),
        scenario_seed=17,
    ).state

    legacy_boundary = make_runtime_replay_boundary(legacy)
    morphology_boundary = make_runtime_replay_boundary(morphology)
    assert legacy_boundary.config_fingerprint == morphology_boundary.config_fingerprint
    assert legacy_boundary.static_input_fingerprint != (
        morphology_boundary.static_input_fingerprint
    )
    assert legacy.static.metadata["zoning_placement_fingerprint"] != (
        morphology.static.metadata["zoning_placement_fingerprint"]
    )

    routing_static = dict(legacy.static.routing_static)
    routing_static["node_zone_by_id"] = {
        str(node_id): zone_id
        for node_id, zone_id in routing_static["node_zone_by_id"].items()
    }
    routing_static["zone_node_ids"] = {
        str(zone_id): tuple(reversed(node_ids))
        for zone_id, node_ids in routing_static["zone_node_ids"].items()
    }
    equivalent = replace(
        legacy,
        static=replace(
            legacy.static,
            routing_static=MappingProxyType(routing_static),
        ),
    )
    assert make_runtime_replay_boundary(equivalent) == legacy_boundary

    first_poi = legacy.static.pois[0]
    alternate_node = legacy.static.routing_static["zone_node_ids"][first_poi.zone_id][1]
    poi_only_change = replace(
        legacy,
        static=replace(
            legacy.static,
            pois=(replace(first_poi, node_id=alternate_node),) + legacy.static.pois[1:],
        ),
    )
    assert make_runtime_replay_boundary(poi_only_change) != legacy_boundary
    with pytest.raises(ValueError, match="declared runtime replay boundary"):
        replay_simulation_sequence(
            RuntimeReplayRequest(
                name="replay_static_mismatch",
                initial_state=poi_only_change,
                declared_boundary=legacy_boundary,
                controls=(),
                rng_key=key_from_seed(17),
                num_steps=0,
            )
        )

    changed_provenance = replace(
        legacy,
        static=replace(
            legacy.static,
            metadata={
                **legacy.static.metadata,
                "zone_poi_coupling_gate_digest": "f" * 64,
            },
        ),
    )
    assert make_runtime_replay_boundary(changed_provenance) != legacy_boundary
