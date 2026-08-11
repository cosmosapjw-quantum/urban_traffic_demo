from dataclasses import FrozenInstanceError
from enum import IntEnum

import pytest

from metroflow.city.scale import CityScaleSpec, __all__


class _AreaInt(int):
    pass


def test_city_scale_spec_is_a_frozen_slotted_two_field_value_object() -> None:
    """Deleting the scale value object's dataclass contract breaks city callers."""
    assert __all__ == ["CityScaleSpec"]
    assert tuple(CityScaleSpec.__dataclass_fields__) == (
        "target_population",
        "urbanized_area_km2",
    )

    scale = CityScaleSpec(target_population=100_000, urbanized_area_km2=40.0)

    assert not hasattr(scale, "__dict__")
    with pytest.raises(FrozenInstanceError):
        scale.target_population = 200_000


def test_city_scale_spec_normalizes_integer_inputs_to_builtin_value_types() -> None:
    """Retaining accepted numeric subclasses would leak unstable value types."""

    class Population(IntEnum):
        TARGET = 100_000

    scale = CityScaleSpec(target_population=Population.TARGET, urbanized_area_km2=40)
    upper_density = CityScaleSpec(target_population=1_000_000, urbanized_area_km2=150)

    assert type(scale.target_population) is int
    assert type(scale.urbanized_area_km2) is float
    assert (scale.target_population, scale.urbanized_area_km2) == (100_000, 40.0)
    assert (upper_density.target_population, upper_density.urbanized_area_km2) == (
        1_000_000,
        150.0,
    )


@pytest.mark.parametrize(
    "population",
    [True, 100_000.0, 100_000.5, "100000", float("nan"), float("inf")],
)
def test_city_scale_spec_rejects_non_integral_population_authority(population: object) -> None:
    """Coercing non-integral population inputs would bypass the city authority boundary."""
    with pytest.raises(TypeError, match="population"):
        CityScaleSpec(target_population=population, urbanized_area_km2=40.0)


@pytest.mark.parametrize(
    ("area", "error"),
    [
        (True, TypeError),
        ("40", TypeError),
        (_AreaInt(40), TypeError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
    ],
)
def test_city_scale_spec_rejects_non_authoritative_or_nonfinite_area(
    area: object, error: type[Exception]
) -> None:
    """Coercing area inputs would erase the city boundary's unit authority."""
    with pytest.raises(error, match="area"):
        CityScaleSpec(target_population=100_000, urbanized_area_km2=area)


@pytest.mark.parametrize(
    ("population", "area", "dimension"),
    [
        (99_999, 40.0, "population"),
        (1_000_001, 150.0, "population"),
        (100_000, 0.0, "area"),
        (100_000, 400.1, "area"),
        (100_000, 40.1, "density"),
        (1_000_000, 149.0, "density"),
    ],
)
def test_city_scale_spec_enforces_population_area_and_density_bounds(
    population: int, area: float, dimension: str
) -> None:
    """Removing any scale bound would admit an invalid city specification."""
    with pytest.raises(ValueError, match=dimension):
        CityScaleSpec(target_population=population, urbanized_area_km2=area)
