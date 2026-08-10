"""Authoritative public scale contract for scalable synthetic cities."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral

__all__ = ["CityScaleSpec"]


@dataclass(frozen=True, slots=True)
class CityScaleSpec:
    """Validated v2 scale using non-bool ``Integral`` population authority.

    Area authority is deliberately narrower: only built-in ``int`` and
    ``float`` values are admitted, then normalized to ``float``.
    """

    target_population: int
    urbanized_area_km2: float

    def __post_init__(self) -> None:
        if isinstance(self.target_population, bool) or not isinstance(
            self.target_population, Integral
        ):
            raise TypeError("population must be a non-bool integer")
        if type(self.urbanized_area_km2) not in {int, float}:
            raise TypeError("area must be a non-bool finite int or float")

        target_population = int(self.target_population)
        urbanized_area_km2 = float(self.urbanized_area_km2)
        if not 100_000 <= target_population <= 1_000_000:
            raise ValueError("population must be in [100000, 1000000]")
        if not isfinite(urbanized_area_km2) or not 0 < urbanized_area_km2 <= 400:
            raise ValueError("area must be finite and in (0, 400]")

        density = target_population / urbanized_area_km2
        if not 2_500 <= density <= 6_667:
            raise ValueError("density must be in [2500, 6667] persons/km2")

        object.__setattr__(self, "target_population", target_population)
        object.__setattr__(self, "urbanized_area_km2", urbanized_area_km2)
