from dataclasses import FrozenInstanceError

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
