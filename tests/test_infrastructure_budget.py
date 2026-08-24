from dataclasses import FrozenInstanceError

import pytest


@pytest.mark.parametrize(
    ("area_km2", "expected_centers", "expected_bridges"),
    (
        (25.0, 2, 3),
        (40.0, 2, 3),
        (100.0, 2, 3),
        (250.0, 3, 4),
    ),
)
def test_river_budget_is_bounded_monotone_and_uses_explicit_units(
    area_km2: float, expected_centers: int, expected_bridges: int
) -> None:
    from metroflow.city.infrastructure_budget import InfrastructureBudget

    budget = InfrastructureBudget.for_city("river_constrained", area_km2)

    assert budget.urbanized_area_km2 == area_km2
    assert budget.perimeter_gateway_count == 8
    assert budget.center_count == expected_centers
    assert budget.river_bridge_count == expected_bridges
    assert budget.arterial_lattice_stride == 9
    assert budget.collector_lattice_stride == 3
    assert budget.macroblock_lattice_stride == 9
    assert budget.superblock_district_span_mm == 2_000_000
    assert budget.macroblock_retained_period == 3
    with pytest.raises(FrozenInstanceError):
        budget.river_bridge_count = 99


def test_style_budget_exposes_scale_dependent_centres_and_ring_geometry() -> None:
    from metroflow.city.infrastructure_budget import InfrastructureBudget

    small = InfrastructureBudget.for_city("polycentric_tod", 25.0)
    large = InfrastructureBudget.for_city("polycentric_tod", 250.0)
    ring = InfrastructureBudget.for_city("ring_radial", 100.0)

    assert small.center_count == 3
    assert large.center_count == 5
    assert small.center_count <= large.center_count <= 8
    assert ring.radial_ring_geometry(3_000_000, 250_000) == (8, 64)
    assert ring.radial_ring_geometry(9_000_000, 250_000) == (23, 176)


@pytest.mark.parametrize("style_id", ("unknown", "", None))
def test_budget_rejects_unknown_style_authority(style_id: object) -> None:
    from metroflow.city.infrastructure_budget import InfrastructureBudget

    with pytest.raises(ValueError, match="style_id"):
        InfrastructureBudget.for_city(style_id, 40.0)
