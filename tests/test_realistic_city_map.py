from __future__ import annotations

from dataclasses import replace
import subprocess
import sys

import numpy as np
import pytest


def _config(style_id: str):
    from metroflow.sim.config import CityGenerationConfig

    return CityGenerationConfig(
        topology_mode="realistic_synthetic_v1",
        morphology_style_id=style_id,
        zone_poi_coupling_mode="block_based_v1",
    )


@pytest.mark.parametrize(
    "style_id",
    (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
@pytest.mark.parametrize("seed", (17, 29, 41, 44))
def test_generate_realistic_city_map_passes_runtime_authority_gates(
    style_id: str,
    seed: int,
) -> None:
    from metroflow.city.realistic_city import generate_city_map

    generated = generate_city_map(
        _config(style_id),
        scenario_id="synthetic_smoke",
        seed=seed,
    )

    assert generated.quality.passed
    assert generated.quality.metrics["weak_component_count"] == 1
    assert generated.quality.metrics["connectivity_repair_link_count"] == 0
    assert generated.quality.metrics["proper_intersection_count"] == 0
    assert generated.quality.metrics["sampled_od_count"] == 512
    assert generated.quality.metrics["reachable_od_count"] == 512
    assert generated.quality.metrics["geometry_coverage"] == 1.0
    assert generated.quality.metrics["section_coverage"] == 1.0
    assert generated.quality.metrics["node_interface_coverage"] == 1.0
    assert generated.quality.metrics["turn_pair_coverage"] == 1.0
    assert generated.topology.metadata["city_blueprint_fingerprint"] == (
        generated.blueprint.fingerprint
    )
    assert generated.topology.metadata["connectivity_repair_link_count"] == 0
    assert generated.road_csr.node_count == len(generated.topology.nodes)
    assert generated.road_csr.link_count == len(generated.topology.links)
    assert not generated.zoning.validate(topology=generated.topology)


def test_realistic_city_config_is_explicit_and_cross_mode_fail_closed() -> None:
    from metroflow.sim.config import CityGenerationConfig

    assert CityGenerationConfig().topology_mode == "standard"
    assert CityGenerationConfig().zone_poi_coupling_mode == "legacy"
    with pytest.raises(ValueError, match="block_based_v1"):
        CityGenerationConfig(
            topology_mode="realistic_synthetic_v1",
            zone_poi_coupling_mode="legacy",
        )
    with pytest.raises(ValueError, match="realistic_synthetic_v1"):
        CityGenerationConfig(zone_poi_coupling_mode="block_based_v1")


def test_realistic_city_generation_and_facade_are_deterministic() -> None:
    from metroflow.city import generate_city_map as public_generate_city_map
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.realistic_city import generate_city_map

    config = _config("polycentric_tod")
    first = generate_city_map(config, scenario_id="synthetic_smoke", seed=41)
    second = generate_city_map(_config("polycentric_tod"), scenario_id="synthetic_smoke", seed=41)
    facade = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 41,
            "style_id": "polycentric_tod",
            "preview_mode": "realistic_synthetic_v1",
        }
    )

    assert first.fingerprint == second.fingerprint
    assert public_generate_city_map is generate_city_map
    assert first.blueprint.fingerprint == second.blueprint.fingerprint
    assert first.topology.road_geometry.fingerprint == facade.road_geometry.fingerprint


def test_realistic_city_initialization_replay_and_static_map_are_integrated() -> None:
    from metroflow.sim.config import SimulationConfig
    from metroflow.sim.control import SimulationControl
    from metroflow.sim.init import build_initial_simulation_state
    from metroflow.sim.replay import (
        RuntimeReplayRequest,
        make_runtime_replay_boundary,
        replay_simulation_sequence,
    )
    from metroflow.sim.rng import key_from_seed
    from metroflow.ui.static_map import build_static_city_map_artifact

    bundle = build_initial_simulation_state(
        config=SimulationConfig(population_target=500, active_agent_capacity=32),
        city_config=_config("organic"),
        scenario_seed=17,
        eager_trip_generation=True,
    )
    assert bundle.generated_city_map is not None
    assert bundle.state.static.metadata["city_blueprint_fingerprint"] == (
        bundle.generated_city_map.blueprint.fingerprint
    )
    artifact = build_static_city_map_artifact(bundle.state)
    assert artifact.metadata["city_blueprint_fingerprint"] == (
        bundle.generated_city_map.blueprint.fingerprint
    )
    assert any("polygon" in zone for zone in artifact.zones)
    assert "<polygon" in artifact.to_html()

    controls = (SimulationControl(),)
    rng_key = key_from_seed(17)
    boundary = make_runtime_replay_boundary(
        bundle.state,
        controls=controls,
        rng_key=rng_key,
        num_steps=1,
    )
    result = replay_simulation_sequence(
        RuntimeReplayRequest(
            name="replay_realistic_city",
            initial_state=bundle.state,
            declared_boundary=boundary,
            controls=controls,
            rng_key=rng_key,
            num_steps=1,
        )
    )
    assert result.initial_boundary == boundary
    assert np.array_equal(result.final_rng_key, result.final_rng_key.copy())
    changed_static = replace(
        bundle.state.static,
        metadata={
            **bundle.state.static.metadata,
            "city_blueprint_fingerprint": "0" * 64,
        },
    )
    changed_state = replace(bundle.state, static=changed_static)
    assert make_runtime_replay_boundary(
        changed_state,
        controls=controls,
        rng_key=rng_key,
        num_steps=1,
    ) != boundary


def test_realistic_city_generation_never_calls_connectivity_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.city import connectivity
    from metroflow.city.realistic_city import generate_city_map

    def forbidden_repair(**_kwargs):
        raise AssertionError("realistic generation must not call connectivity repair")

    monkeypatch.setattr(connectivity, "repair_weak_connectivity", forbidden_repair)
    generated = generate_city_map(
        _config("grid_core"),
        scenario_id="synthetic_smoke",
        seed=17,
    )

    assert generated.topology.metadata["connectivity_repair_link_count"] == 0


def test_realistic_city_import_does_not_load_optional_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.realistic_city; "
                "assert 'jax' not in sys.modules; "
                "assert 'torch' not in sys.modules; "
                "assert '_metroflow_rust' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr

    config_import = subprocess.run(
        [
            sys.executable,
            "-c",
            "import metroflow.sim.config; import metroflow.city.block_land_use",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert config_import.returncode == 0, config_import.stderr
