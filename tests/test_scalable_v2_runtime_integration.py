"""PR102 regression: scalable_synthetic_v2 end-to-end simulation init."""

from __future__ import annotations

import pytest

from metroflow.city.scale import CityScaleSpec
from metroflow.sim.config import CityGenerationConfig, SimulationConfig


def test_scalable_v2_simulation_init_succeeds() -> None:
    """P0-1 regression: scalable_synthetic_v2 must reach sim init without ValueError."""
    from metroflow.sim.init import build_initial_simulation_state

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=100_000),
        scenario_seed=42,
        city_config=CityGenerationConfig(
            topology_mode="scalable_synthetic_v2",
            morphology_style_id="grid_core",
            zone_poi_coupling_mode="block_based_v1",
            scale_spec=CityScaleSpec(100_000, 25.0),
        ),
    )
    assert bundle.state is not None
    assert bundle.city_topology is not None
    assert len(bundle.city_topology.nodes) > 0
    assert len(bundle.city_topology.links) > 0
    assert bundle.zoning is not None
    assert len(bundle.zoning.zones) > 0


def test_scalable_v2_orchestrator_returns_valid_map() -> None:
    """Standalone orchestrator produces consistent topology/CSR/zoning."""
    from metroflow.city.scalable_city import build_scalable_city_map

    cfg = CityGenerationConfig(
        topology_mode="scalable_synthetic_v2",
        morphology_style_id="grid_core",
        zone_poi_coupling_mode="block_based_v1",
        scale_spec=CityScaleSpec(100_000, 25.0),
    )
    city = build_scalable_city_map(cfg, scenario_id="test", seed=17)
    assert city.topology is not None
    assert city.road_csr is not None
    assert city.road_csr.node_count == len(city.topology.nodes)
    assert city.road_csr.link_count == len(city.topology.links)
    assert city.fingerprint == city.static_authority.fingerprint
    assert len(city.zoning.zones) > 0


def test_scalable_v2_deterministic_replay() -> None:
    """Two runs with same (config, seed) produce identical fingerprints."""
    from metroflow.city.scalable_city import build_scalable_city_map

    cfg = CityGenerationConfig(
        topology_mode="scalable_synthetic_v2",
        morphology_style_id="ring_radial",
        zone_poi_coupling_mode="block_based_v1",
        scale_spec=CityScaleSpec(100_000, 25.0),
    )
    a = build_scalable_city_map(cfg, scenario_id="replay", seed=29)
    b = build_scalable_city_map(cfg, scenario_id="replay", seed=29)
    assert a.fingerprint == b.fingerprint
    assert a.network.fingerprint == b.network.fingerprint
    assert a.blocks.fingerprint == b.blocks.fingerprint
    assert a.compiled.fingerprint == b.compiled.fingerprint


def test_scalable_v2_rejects_wrong_topology_mode() -> None:
    """Orchestrator rejects non-v2 topology modes."""
    from metroflow.city.scalable_city import build_scalable_city_map

    cfg = CityGenerationConfig(
        topology_mode="realistic_synthetic_v1",
        morphology_style_id="grid_core",
        zone_poi_coupling_mode="block_based_v1",
    )
    with pytest.raises(ValueError, match="scalable_synthetic_v2"):
        build_scalable_city_map(cfg, scenario_id="test", seed=17)
