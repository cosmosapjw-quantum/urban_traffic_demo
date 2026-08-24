"""Explicit, deterministic multiscale infrastructure budgets in physical units.

These formulas allocate synthetic topology only.  They deliberately consume
urbanized area, never target population: population remains demand authority.
They are not empirical calibrations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from math import isfinite

from metroflow.city.morphology_capabilities import STYLE_IDS

__all__ = ["InfrastructureBudget", "PERIMETER_GATEWAY_COUNT"]


PERIMETER_GATEWAY_COUNT = 8


def _ceil_sqrt(value: int) -> int:
    """Return the exact positive integer ceiling of a non-negative square root."""

    root = math.isqrt(value)
    return root if root * root == value else root + 1


@dataclass(frozen=True, slots=True)
class InfrastructureBudget:
    """Fixed-scale infrastructure allocation for one public morphology style.

    ``urbanized_area_km2`` is the only scale input.  Lattice strides count
    lattice intervals; radial inputs and returned radii are exact millimetres.
    The fixed eight-gateway budget deliberately represents the four corners
    and four cardinal perimeter anchors, independent of demand population.
    """

    style_id: str
    urbanized_area_km2: float
    perimeter_gateway_count: int
    center_count: int
    river_bridge_count: int
    arterial_lattice_stride: int
    collector_lattice_stride: int
    macroblock_lattice_stride: int
    superblock_district_span_mm: int
    macroblock_retained_period: int

    @classmethod
    def for_city(cls, style_id: object, urbanized_area_km2: object) -> "InfrastructureBudget":
        if type(style_id) is not str or style_id not in STYLE_IDS:
            raise ValueError("style_id must be a supported public morphology style")
        if type(urbanized_area_km2) not in (int, float):
            raise TypeError("urbanized_area_km2 must be an exact built-in number")
        area = float(urbanized_area_km2)
        if not isfinite(area) or area <= 0:
            raise ValueError("urbanized_area_km2 must be finite and positive")

        if style_id in {"polycentric_tod", "superblock_mixed"}:
            center_count = max(3, min(8, round(area / 50.0)))
        elif style_id == "river_constrained":
            center_count = max(2, min(5, round(area / 80.0)))
        else:
            center_count = 1

        # A river city always needs at least three registered failure groups.
        # The only growth term is a bounded square-root area allocation.
        bridge_count = (
            min(5, max(3, _ceil_sqrt(math.ceil(area / 25.0))))
            if style_id == "river_constrained"
            else 0
        )
        return cls(
            style_id=style_id,
            urbanized_area_km2=area,
            perimeter_gateway_count=PERIMETER_GATEWAY_COUNT,
            center_count=center_count,
            river_bridge_count=bridge_count,
            arterial_lattice_stride=9,
            collector_lattice_stride=3,
            macroblock_lattice_stride=9,
            superblock_district_span_mm=2_000_000,
            macroblock_retained_period=3,
        )

    def radial_ring_geometry(
        self, available_radius_mm: object, nominal_spacing_mm: object
    ) -> tuple[int, int]:
        """Return bounded concentric-ring and spoke counts from exact mm inputs."""

        available = _positive_int("available_radius_mm", available_radius_mm)
        spacing = _positive_int("nominal_spacing_mm", nominal_spacing_mm)
        outer = available * 3 // 4
        inner = max(2 * spacing, outer // 6)
        if inner >= outer:
            raise ValueError("radial geometry cannot fit two distinct radii")
        ring_count = max(8, 1 + (outer - inner) // spacing)
        estimated_spokes = max(32, round(math.tau * outer / spacing))
        spoke_count = max(32, ((estimated_spokes + 7) // 8) * 8)
        return (ring_count, spoke_count)

    def bridge_row_indices(self, row_count: object) -> tuple[int, ...]:
        """Return evenly spaced, interior river-bridge row indices."""

        count = _positive_int("row_count", row_count)
        if self.river_bridge_count == 0:
            return ()
        if count < self.river_bridge_count + 2:
            raise ValueError("river lattice cannot host the bridge budget")
        return tuple(
            count * (index + 1) // (self.river_bridge_count + 1)
            for index in range(self.river_bridge_count)
        )

    def perimeter_gateway_points(
        self, extent_mm: tuple[int, int, int, int]
    ) -> tuple[tuple[int, int], ...]:
        """Return the bounded corner/cardinal perimeter gateway authority."""

        if self.perimeter_gateway_count != PERIMETER_GATEWAY_COUNT:
            raise ValueError("perimeter gateway budget is not supported")
        min_x, max_x, min_y, max_y = extent_mm
        return (
            (min_x, min_y),
            (0, min_y),
            (max_x, min_y),
            (max_x, 0),
            (max_x, max_y),
            (0, max_y),
            (min_x, max_y),
            (min_x, 0),
        )


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return int(value)
