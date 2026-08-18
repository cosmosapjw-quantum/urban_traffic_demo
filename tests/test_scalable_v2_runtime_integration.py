"""PR102/PR108 regression: scalable_synthetic_v2 end-to-end simulation init & single authority."""

from __future__ import annotations

import pytest

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_city import build_scalable_city_map
from metroflow.sim.config import CityGenerationConfig, SimulationConfig
from metroflow.sim.init import build_initial_simulation_state


def test_scalable_v2_simulation_init_succeeds() -> None:
    """P0-1 regression: scalable_synthetic_v2 must reach sim init without ValueError."""
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
    assert bundle.scalable_city_map is not None


def test_scalable_v2_orchestrator_returns_valid_map() -> None:
    """Standalone orchestrator produces consistent topology/CSR/zoning/fingerprint."""
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
    assert len(city.fingerprint) == 64
    assert len(city.zoning.zones) > 0


def test_scalable_v2_deterministic_replay() -> None:
    """Two runs with same (config, seed) produce identical fingerprints."""
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
    assert a.static_authority.fingerprint == b.static_authority.fingerprint


def test_scalable_v2_rejects_wrong_topology_mode() -> None:
    """Orchestrator rejects non-v2 topology modes."""
    cfg = CityGenerationConfig(
        topology_mode="realistic_synthetic_v1",
        morphology_style_id="grid_core",
        zone_poi_coupling_mode="block_based_v1",
    )
    with pytest.raises(ValueError, match="scalable_synthetic_v2"):
        build_scalable_city_map(cfg, scenario_id="test", seed=17)


def test_scalable_runtime_uses_single_landuse_authority() -> None:
    """P0 audit: simulation init must use ScalableStaticAuthority as the single land-use authority."""
    scale_spec = CityScaleSpec(100_000, 25.0)
    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=100_000),
        scenario_seed=17,
        city_config=CityGenerationConfig(
            topology_mode="scalable_synthetic_v2",
            morphology_style_id="grid_core",
            zone_poi_coupling_mode="block_based_v1",
            scale_spec=scale_spec,
        ),
    )

    assert bundle.scalable_city_map is not None
    static_auth = bundle.scalable_city_map.static_authority

    # 1. Zoning metadata binds directly to static authority
    assert bundle.zoning.metadata["zone_poi_coupling_resolved_mode"] == "block_based_v1"
    assert bundle.zoning.metadata["static_authority_fingerprint"] == static_auth.fingerprint
    assert bundle.zoning.metadata["taz_catalog_fingerprint"] == static_auth.taz_catalog.fingerprint
    assert bundle.zoning.metadata["poi_catalog_fingerprint"] == static_auth.poi_catalog.fingerprint

    # 2. Total population capacity in zoning matches capacity certificate
    zoning_pop_capacity = sum(z.population_capacity for z in bundle.zoning.zones)
    assert zoning_pop_capacity == static_auth.capacity_certificate.resident_capacity_total

    # 3. Total POIs match authoritative catalog
    assert len(bundle.zoning.pois) == len(static_auth.poi_catalog.pois)

    # 4. SimulationState metadata contains static authority fingerprints
    state_meta = bundle.state.static.metadata
    assert state_meta["static_authority_fingerprint"] == static_auth.fingerprint
    assert state_meta["taz_catalog_fingerprint"] == static_auth.taz_catalog.fingerprint


def test_population_authorities_must_match() -> None:
    """P0 audit: differing population authorities between sim and city must fail closed."""
    # 1. In sim.init: SimulationConfig vs CityGenerationConfig mismatch
    with pytest.raises(ValueError, match="population authorities disagree"):
        build_initial_simulation_state(
            config=SimulationConfig(population_target=100_000),
            scenario_seed=17,
            city_config=CityGenerationConfig(
                topology_mode="scalable_synthetic_v2",
                morphology_style_id="grid_core",
                zone_poi_coupling_mode="block_based_v1",
                scale_spec=CityScaleSpec(150_000, 25.0),
            ),
        )

    # 2. In build_scalable_city_map: population_target override mismatch
    cfg = CityGenerationConfig(
        topology_mode="scalable_synthetic_v2",
        morphology_style_id="grid_core",
        zone_poi_coupling_mode="block_based_v1",
        scale_spec=CityScaleSpec(100_000, 25.0),
    )
    with pytest.raises(ValueError, match="population authorities disagree"):
        build_scalable_city_map(cfg, "test", 17, population_target=150_000)


def test_scalable_v2_cross_process_hashseed_replay() -> None:
    """PR112 audit: ScalableCityMap fingerprint must be byte-identical across PYTHONHASHSEED values."""
    import os
    import subprocess
    import sys

    hashseeds = ["0", "1", "42", "1337"]
    fingerprints: list[str] = []

    code = (
        "from metroflow.city.scale import CityScaleSpec; "
        "from metroflow.sim.config import CityGenerationConfig; "
        "from metroflow.city.scalable_city import build_scalable_city_map; "
        "cfg = CityGenerationConfig(topology_mode='scalable_synthetic_v2', "
        "morphology_style_id='ring_radial', zone_poi_coupling_mode='block_based_v1', "
        "scale_spec=CityScaleSpec(100_000, 25.0)); "
        "city = build_scalable_city_map(cfg, 'test', 17); "
        "print(city.fingerprint)"
    )

    for seed in hashseeds:
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = ".:src"
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        fingerprints.append(result.stdout.strip())

    assert len(set(fingerprints)) == 1, f"Fingerprints diverged across hashseeds: {fingerprints}"


def test_scalable_city_map_rejects_tampered_zoning_metadata() -> None:
    """PR112 audit: ScalableCityMap.__post_init__ must reject tampered zoning fingerprint."""
    from metroflow.city.scalable_city import ScalableCityMap

    cfg = CityGenerationConfig(
        topology_mode="scalable_synthetic_v2",
        morphology_style_id="grid_core",
        zone_poi_coupling_mode="block_based_v1",
        scale_spec=CityScaleSpec(100_000, 25.0),
    )
    city = build_scalable_city_map(cfg, "test", 17)

    # Tamper with recorded zoning fingerprint
    tampered_zoning = city.zoning
    tampered_zoning.metadata["zoning_placement_fingerprint"] = "0" * 64

    with pytest.raises(ValueError, match="zoning metadata fingerprint .* does not match actual"):
        ScalableCityMap(
            topology=city.topology,
            zoning=tampered_zoning,
            road_csr=city.road_csr,
            network=city.network,
            blocks=city.blocks,
            compiled=city.compiled,
            static_authority=city.static_authority,
        )

