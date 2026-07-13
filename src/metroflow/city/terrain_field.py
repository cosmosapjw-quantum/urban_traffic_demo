"""Bounded deterministic terrain fields for realistic synthetic cities."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np

from .morphology_reference import get_morphology_archetype

__all__ = ["TerrainField", "build_terrain_field"]

Array = np.ndarray


@dataclass(frozen=True, slots=True)
class TerrainField:
    """Read-only meter-space terrain raster with an explicit finite extent."""

    width_m: float
    height_m: float
    cell_size_x_m: float
    cell_size_y_m: float
    seed: int
    style_id: str
    elevation_m: Array = field(repr=False, compare=False)
    slope_rise_per_m: Array = field(repr=False, compare=False)
    water_mask: Array = field(repr=False, compare=False)
    buildable_mask: Array = field(repr=False, compare=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        width_m = float(self.width_m)
        height_m = float(self.height_m)
        cell_x = float(self.cell_size_x_m)
        cell_y = float(self.cell_size_y_m)
        if not all(math.isfinite(value) and value > 0.0 for value in (width_m, height_m, cell_x, cell_y)):
            raise ValueError("terrain extents and cell sizes must be finite and > 0")
        elevation = _readonly_array(self.elevation_m, np.float32)
        slope = _readonly_array(self.slope_rise_per_m, np.float32)
        water = _readonly_array(self.water_mask, np.bool_)
        buildable = _readonly_array(self.buildable_mask, np.bool_)
        if elevation.ndim != 2 or elevation.shape[0] < 2 or elevation.shape[1] < 2:
            raise ValueError("terrain arrays must be 2-D with at least two cells per axis")
        if not (elevation.shape == slope.shape == water.shape == buildable.shape):
            raise ValueError("terrain arrays must have identical shapes")
        if not bool(np.all(np.isfinite(elevation))) or not bool(np.all(np.isfinite(slope))):
            raise ValueError("terrain numeric arrays must be finite")
        if bool(np.any(slope < 0.0)):
            raise ValueError("slope_rise_per_m must be >= 0")
        if bool(np.any(water & buildable)):
            raise ValueError("water cells cannot be buildable")
        object.__setattr__(self, "width_m", width_m)
        object.__setattr__(self, "height_m", height_m)
        object.__setattr__(self, "cell_size_x_m", cell_x)
        object.__setattr__(self, "cell_size_y_m", cell_y)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "style_id", str(self.style_id))
        object.__setattr__(self, "elevation_m", elevation)
        object.__setattr__(self, "slope_rise_per_m", slope)
        object.__setattr__(self, "water_mask", water)
        object.__setattr__(self, "buildable_mask", buildable)
        object.__setattr__(self, "fingerprint", _terrain_fingerprint(self))

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.elevation_m.shape)

    @property
    def x_coordinates_m(self) -> Array:
        values = np.linspace(
            -self.width_m * 0.5,
            self.width_m * 0.5,
            self.shape[1],
            dtype=np.float32,
        )
        values.flags.writeable = False
        return values

    @property
    def y_coordinates_m(self) -> Array:
        values = np.linspace(
            -self.height_m * 0.5,
            self.height_m * 0.5,
            self.shape[0],
            dtype=np.float32,
        )
        values.flags.writeable = False
        return values


def build_terrain_field(
    *,
    width: int | float,
    height: int | float,
    seed: int,
    style_id: str = "polycentric_tod",
    max_grid_size: int = 256,
) -> TerrainField:
    """Build a bounded field; ``width`` and ``height`` are meters."""

    resolved_style_id = get_morphology_archetype(style_id).style_id
    width_m = float(width)
    height_m = float(height)
    grid_limit = int(max_grid_size)
    if not math.isfinite(width_m) or width_m <= 0.0:
        raise ValueError("width must be finite and > 0 meters")
    if not math.isfinite(height_m) or height_m <= 0.0:
        raise ValueError("height must be finite and > 0 meters")
    if not 16 <= grid_limit <= 256:
        raise ValueError("max_grid_size must be in [16, 256]")
    longest = max(width_m, height_m)
    cols = max(16, min(grid_limit, int(round(grid_limit * width_m / longest))))
    rows = max(16, min(grid_limit, int(round(grid_limit * height_m / longest))))
    x = np.linspace(-width_m * 0.5, width_m * 0.5, cols, dtype=np.float64)
    y = np.linspace(-height_m * 0.5, height_m * 0.5, rows, dtype=np.float64)
    grid_x, grid_y = np.meshgrid(x, y)
    phase = (int(seed) % 10_007) * 0.0137
    normalized_x = grid_x / width_m
    normalized_y = grid_y / height_m
    raw = (
        0.52
        + 0.18 * np.sin(normalized_x * math.tau * 2.1 + phase)
        + 0.13 * np.cos(normalized_y * math.tau * 1.7 - phase * 0.7)
        + 0.08 * np.sin((normalized_x + normalized_y) * math.tau * 3.2 + phase * 0.3)
    )
    raw -= float(np.min(raw))
    raw /= max(float(np.max(raw)), 1e-12)
    elevation = 18.0 + raw * 96.0
    cell_x = width_m / max(cols - 1, 1)
    cell_y = height_m / max(rows - 1, 1)
    grad_y, grad_x = np.gradient(elevation, cell_y, cell_x)
    slope = np.hypot(grad_x, grad_y)
    water = _water_mask(
        style_id=resolved_style_id,
        seed=int(seed),
        grid_x=grid_x,
        grid_y=grid_y,
        width_m=width_m,
        height_m=height_m,
        phase=phase,
    )
    buildable = (~water) & (slope <= 0.16)
    return TerrainField(
        width_m=width_m,
        height_m=height_m,
        cell_size_x_m=cell_x,
        cell_size_y_m=cell_y,
        seed=int(seed),
        style_id=resolved_style_id,
        elevation_m=elevation,
        slope_rise_per_m=slope,
        water_mask=water,
        buildable_mask=buildable,
    )


def _water_mask(
    *,
    style_id: str,
    seed: int,
    grid_x: Array,
    grid_y: Array,
    width_m: float,
    height_m: float,
    phase: float,
) -> Array:
    if style_id == "river_constrained":
        center_x = width_m * 0.055 * np.sin(grid_y / height_m * math.tau * 1.4 + phase)
        return np.abs(grid_x - center_x) <= width_m * 0.032
    if style_id in {"organic", "polycentric_tod"} and seed % 5 == 0:
        center_y = height_m * 0.16 + height_m * 0.035 * np.sin(
            grid_x / width_m * math.tau * 1.8 + phase
        )
        return np.abs(grid_y - center_y) <= height_m * 0.018
    return np.zeros(grid_x.shape, dtype=np.bool_)


def _readonly_array(value: Array, dtype: np.dtype[object]) -> Array:
    out = np.ascontiguousarray(value, dtype=dtype).copy()
    out.flags.writeable = False
    return out


def _terrain_fingerprint(field_value: TerrainField) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "schema": "terrain_field_v1",
                "width_m": field_value.width_m,
                "height_m": field_value.height_m,
                "cell_size_x_m": field_value.cell_size_x_m,
                "cell_size_y_m": field_value.cell_size_y_m,
                "seed": field_value.seed,
                "style_id": field_value.style_id,
                "shape": field_value.shape,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    for array in (
        field_value.elevation_m,
        field_value.slope_rise_per_m,
        field_value.water_mask,
        field_value.buildable_mask,
    ):
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()
