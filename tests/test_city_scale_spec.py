from dataclasses import FrozenInstanceError
from enum import IntEnum

import pytest

from metroflow.city.scale import CityScaleSpec, __all__


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
