from dataclasses import dataclass
from math import isfinite
from numbers import Integral

__all__ = ["CityScaleSpec"]


@dataclass(frozen=True, slots=True)
class CityScaleSpec:
    """Scale specification for synthetic city generation.

    Contract:
    - ``urbanized_area_km2``: Governs the physical bounding box and
      street network spatial extent (width_mm x height_mm). Street topology
      generation depends on urbanized_area_km2 only.
    - ``target_population``: Governs downstream demographic generation,
      zoning placement, and trip demand allocation. It does not alter
      the static road network geometry.
    - Density constraint: ``target_population / urbanized_area_km2`` must
      fall within realistic urban density bounds [2500, 6667] people/km².
    """

    target_population: int
    urbanized_area_km2: float

    def __post_init__(self) -> None:
        if isinstance(self.target_population, bool) or not isinstance(
            self.target_population, Integral
        ):
            raise TypeError("population must be a non-bool integral value")
        if type(self.urbanized_area_km2) not in (int, float):
            raise TypeError("area must be an exact built-in int or float")
        try:
            area = float(self.urbanized_area_km2)
        except OverflowError as error:
            raise ValueError("area must be finite") from error
        if not isfinite(area):
            raise ValueError("area must be finite")
        population = int(self.target_population)
        if not 100_000 <= population <= 1_000_000:
            raise ValueError("population must be between 100000 and 1000000")
        if not 0 < area <= 400:
            raise ValueError("area must be in (0, 400]")
        density = population / area
        if not 2_500 <= density <= 6_667:
            raise ValueError("density must be between 2500 and 6667")
        object.__setattr__(self, "target_population", population)
        object.__setattr__(self, "urbanized_area_km2", area)
