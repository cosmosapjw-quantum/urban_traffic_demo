from dataclasses import dataclass
from numbers import Integral

__all__ = ["CityScaleSpec"]


@dataclass(frozen=True, slots=True)
class CityScaleSpec:
    target_population: int
    urbanized_area_km2: float

    def __post_init__(self) -> None:
        if isinstance(self.target_population, bool) or not isinstance(
            self.target_population, Integral
        ):
            raise TypeError("population must be a non-bool integral value")
        object.__setattr__(self, "target_population", int(self.target_population))
        object.__setattr__(self, "urbanized_area_km2", float(self.urbanized_area_km2))
