"""Public configuration contract for opt-in scalable synthetic v2 cities."""

from __future__ import annotations

import math
from enum import IntEnum

import pytest

from metroflow.sim.config import (
    CITY_TOPOLOGY_MODES,
    CityGenerationConfig,
    CityScaleSpec,
)


class _PopulationTarget(IntEnum):
    MINIMUM = 100_000


def test_city_scale_spec_is_city_owned_and_reexported_by_sim_config() -> None:
    """Catches a second scale authority being defined in the simulator layer."""
    from metroflow.city.scale import CityScaleSpec as CityOwnedScaleSpec

    assert CityScaleSpec is CityOwnedScaleSpec


def test_city_scale_spec_normalizes_supported_numeric_boundary_inputs() -> None:
    """Catches rejection or lossy conversion of authoritative numeric inputs."""
    minimum_density = CityScaleSpec(
        target_population=_PopulationTarget.MINIMUM,
        urbanized_area_km2=40,
    )
    maximum_density = CityScaleSpec(target_population=1_000_000, urbanized_area_km2=150)

    assert minimum_density.target_population == 100_000
    assert isinstance(minimum_density.target_population, int)
    assert minimum_density.urbanized_area_km2 == 40.0
    assert isinstance(minimum_density.urbanized_area_km2, float)
    assert maximum_density.target_population / maximum_density.urbanized_area_km2 == pytest.approx(
        6_666.666666666667
    )


@pytest.mark.parametrize(
    "target_population", [True, 100_000.0, 100_000.5, "100000", math.nan, math.inf]
)
def test_city_scale_spec_rejects_non_integral_population_authority(
    target_population: object,
) -> None:
    """Catches bool, float, string, or nonfinite population aliasing through int()."""
    with pytest.raises((TypeError, ValueError), match="population"):
        CityScaleSpec(target_population=target_population, urbanized_area_km2=40)


@pytest.mark.parametrize("urbanized_area_km2", [True, "40", math.nan, math.inf])
def test_city_scale_spec_rejects_non_numeric_or_nonfinite_area_authority(
    urbanized_area_km2: object,
) -> None:
    """Catches string/bool coercion and nonfinite area admission through float()."""
    with pytest.raises((TypeError, ValueError), match="area"):
        CityScaleSpec(target_population=100_000, urbanized_area_km2=urbanized_area_km2)


@pytest.mark.parametrize(
    ("target_population", "urbanized_area_km2", "dimension"),
    [
        (99_999, 40, "population"),
        (1_000_001, 200, "population"),
        (100_000, True, "area"),
        (True, 40, "population"),
        (100_000, math.inf, "area"),
        (100_000, 0, "area"),
        (100_000, 401, "area"),
        (100_000, 14, "density"),
        (1_000_000, 149, "density"),
    ],
)
def test_city_scale_spec_names_the_violated_dimension(
    target_population: object,
    urbanized_area_km2: object,
    dimension: str,
) -> None:
    """Rejects a change that accepts an unsupported scale dimension."""
    with pytest.raises((TypeError, ValueError), match=dimension):
        CityScaleSpec(
            target_population=target_population,
            urbanized_area_km2=urbanized_area_km2,
        )


def test_scalable_v2_requires_its_scale_and_block_coupling_contract() -> None:
    """Rejects a change that makes v2 selection implicit or under-specified."""
    config = CityGenerationConfig(
        topology_mode="scalable_synthetic_v2",
        morphology_style_id="grid_core",
        zone_poi_coupling_mode="block_based_v1",
        scale_spec=CityScaleSpec(100_000, 40),
    )

    assert "scalable_synthetic_v2" in CITY_TOPOLOGY_MODES
    assert isinstance(config.scale_spec, CityScaleSpec)
    assert config.scale_spec == CityScaleSpec(100_000, 40.0)

    with pytest.raises(ValueError, match="mode.*scale_spec|scale_spec.*mode"):
        CityGenerationConfig(
            topology_mode="scalable_synthetic_v2",
            morphology_style_id="grid_core",
            zone_poi_coupling_mode="block_based_v1",
        )
    with pytest.raises(ValueError, match="mode.*scale_spec|scale_spec.*mode"):
        CityGenerationConfig(
            topology_mode="scalable_synthetic_v2",
            morphology_style_id="grid_core",
            scale_spec=CityScaleSpec(100_000, 40.0),
        )
    with pytest.raises(ValueError, match="mode.*scale_spec|scale_spec.*mode"):
        CityGenerationConfig(scale_spec=CityScaleSpec(100_000, 40.0))


def test_scalable_v2_rejects_mapping_scale_spec() -> None:
    """Catches a mapping or duck type becoming a second unvalidated scale authority."""
    with pytest.raises(TypeError, match="scale_spec"):
        CityGenerationConfig(
            topology_mode="scalable_synthetic_v2",
            morphology_style_id="grid_core",
            zone_poi_coupling_mode="block_based_v1",
            scale_spec={"target_population": 100_000, "urbanized_area_km2": 40},
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
def test_scalable_v2_requires_one_of_six_explicit_styles(style_id: str) -> None:
    """Catches v2 style admission drifting away from its closed six-style contract."""
    config = CityGenerationConfig(
        topology_mode="scalable_synthetic_v2",
        morphology_style_id=style_id,
        zone_poi_coupling_mode="block_based_v1",
        scale_spec=CityScaleSpec(100_000, 40),
    )

    assert config.morphology_style_id == style_id


def test_scalable_v2_rejects_legacy_auto_style() -> None:
    """Catches legacy scenario-dependent style fallback leaking into v2."""
    with pytest.raises(ValueError, match="style|auto"):
        CityGenerationConfig(
            topology_mode="scalable_synthetic_v2",
            morphology_style_id="auto",
            zone_poi_coupling_mode="block_based_v1",
            scale_spec=CityScaleSpec(100_000, 40),
        )


@pytest.mark.parametrize(
    "population_target", [True, 100_000.0, 100_000.5, "100000", math.nan, math.inf]
)
def test_simulation_population_target_rejects_non_integral_authority(
    population_target: object,
) -> None:
    """Catches silent runtime population aliases and unstable conversion errors."""
    from metroflow.sim.config import SimulationConfig

    with pytest.raises((TypeError, ValueError), match="population_target"):
        SimulationConfig(population_target=population_target)


def test_simulation_population_target_preserves_exact_int() -> None:
    """Catches valid runtime population integers being changed by validation."""
    from metroflow.sim.config import SimulationConfig

    config = SimulationConfig(population_target=123_456)

    assert config.population_target == 123_456
    assert type(config.population_target) is int


@pytest.mark.parametrize(
    ("topology_mode", "zone_poi_coupling_mode"),
    (
        ("standard", "legacy"),
        ("sidecar_local_fabric", "legacy"),
        ("sidecar_local_fabric_planar", "legacy"),
        ("realistic_synthetic_v1", "block_based_v1"),
    ),
)
def test_existing_topology_modes_keep_scale_free_results(
    topology_mode: str,
    zone_poi_coupling_mode: str,
) -> None:
    """Catches v2 scale/style validation leaking into existing topology modes."""
    config = CityGenerationConfig(
        topology_mode=topology_mode,
        zone_poi_coupling_mode=zone_poi_coupling_mode,
    )

    assert config.topology_mode == topology_mode
    assert config.morphology_style_id == "auto"
    assert config.zone_poi_coupling_mode == zone_poi_coupling_mode
    assert config.scale_spec is None


def test_standard_default_remains_legacy_and_has_no_scale_spec() -> None:
    """Rejects a change that silently promotes v2 or changes legacy defaults."""
    config = CityGenerationConfig()

    assert config.topology_mode == "standard"
    assert config.zone_poi_coupling_mode == "legacy"
    assert config.scale_spec is None


@pytest.mark.parametrize(
    ("kwarg", "value", "match_str"),
    [
        ({"ring_road_count": 5}, 5, "ring_road_count"),
        ({"radial_corridor_count": 8}, 8, "radial_corridor_count"),
        ({"barrier_count": 2}, 2, "barrier_count"),
        ({"bridge_count": 5}, 5, "bridge_count"),
        ({"interchange_density_profile": "high"}, "high", "interchange_density_profile"),
        ({"poi_density_profile": "dense"}, "dense", "poi_density_profile"),
    ],
)
def test_scalable_v2_rejects_unsupported_knobs(
    kwarg: dict[str, object],
    value: object,
    match_str: str,
) -> None:
    """Catches unsupported configuration knobs being silently ignored in v2."""
    base_kwargs = {
        "topology_mode": "scalable_synthetic_v2",
        "morphology_style_id": "grid_core",
        "zone_poi_coupling_mode": "block_based_v1",
        "scale_spec": CityScaleSpec(100_000, 40),
    }
    base_kwargs.update(kwarg)
    with pytest.raises(ValueError, match=match_str):
        CityGenerationConfig(**base_kwargs)

