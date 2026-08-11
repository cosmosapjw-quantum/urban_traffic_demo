from dataclasses import dataclass

__all__ = ["CityScaleSpec"]


@dataclass(frozen=True, slots=True)
class CityScaleSpec:
    target_population: int
    urbanized_area_km2: float
