"""Deterministic urban intensity and orientation fields."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np

from .morphology_reference import get_morphology_archetype
from .terrain_field import TerrainField

__all__ = ["UrbanCenter", "UrbanFormField", "build_urban_form_field"]

Array = np.ndarray


@dataclass(frozen=True, slots=True)
class UrbanCenter:
    center_id: int
    x_m: float
    y_m: float
    weight: float
    role: str

    def __post_init__(self) -> None:
        center_id = int(self.center_id)
        x_m = float(self.x_m)
        y_m = float(self.y_m)
        weight = float(self.weight)
        role = str(self.role).strip()
        if center_id < 0:
            raise ValueError("center_id must be >= 0")
        if not all(math.isfinite(value) for value in (x_m, y_m, weight)):
            raise ValueError("urban center coordinates and weight must be finite")
        if weight <= 0.0:
            raise ValueError("urban center weight must be > 0")
        if not role:
            raise ValueError("urban center role must not be empty")
        object.__setattr__(self, "center_id", center_id)
        object.__setattr__(self, "x_m", x_m)
        object.__setattr__(self, "y_m", y_m)
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "role", role)


@dataclass(frozen=True, slots=True)
class UrbanFormField:
    terrain_fingerprint: str
    style_id: str
    centers: tuple[UrbanCenter, ...]
    gateways_m: tuple[tuple[float, float], ...]
    development_intensity: Array = field(repr=False, compare=False)
    orientation_x: Array = field(repr=False, compare=False)
    orientation_y: Array = field(repr=False, compare=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        intensity = _readonly_array(self.development_intensity)
        orientation_x = _readonly_array(self.orientation_x)
        orientation_y = _readonly_array(self.orientation_y)
        if not (intensity.shape == orientation_x.shape == orientation_y.shape):
            raise ValueError("urban form arrays must have identical shapes")
        if intensity.ndim != 2:
            raise ValueError("urban form arrays must be 2-D")
        if bool(np.any(intensity < 0.0)) or bool(np.any(intensity > 1.0)):
            raise ValueError("development_intensity must be in [0, 1]")
        if not self.centers:
            raise ValueError("urban form requires at least one center")
        center_ids = tuple(center.center_id for center in self.centers)
        center_coordinates = tuple((center.x_m, center.y_m) for center in self.centers)
        if len(set(center_ids)) != len(center_ids):
            raise ValueError("urban center IDs must be unique")
        if len(set(center_coordinates)) != len(center_coordinates):
            raise ValueError("urban center coordinates must be unique")
        gateways = tuple((float(x), float(y)) for x, y in self.gateways_m)
        if not gateways or not all(
            math.isfinite(value) for point in gateways for value in point
        ):
            raise ValueError("urban gateways must be non-empty and finite")
        orientation_norm = np.hypot(orientation_x, orientation_y)
        if not bool(np.allclose(orientation_norm, 1.0, atol=1e-5)):
            raise ValueError("urban orientation vectors must have unit length")
        object.__setattr__(self, "terrain_fingerprint", str(self.terrain_fingerprint))
        object.__setattr__(self, "style_id", str(self.style_id))
        object.__setattr__(self, "centers", tuple(self.centers))
        object.__setattr__(
            self,
            "gateways_m",
            gateways,
        )
        object.__setattr__(self, "development_intensity", intensity)
        object.__setattr__(self, "orientation_x", orientation_x)
        object.__setattr__(self, "orientation_y", orientation_y)
        object.__setattr__(self, "fingerprint", _urban_form_fingerprint(self))


_CENTER_LAYOUTS: dict[str, tuple[tuple[float, float, float], ...]] = {
    "ring_radial": ((0.0, 0.0, 1.0), (-0.34, 0.02, 0.55), (0.32, -0.03, 0.55)),
    "grid_core": ((0.0, 0.0, 1.0), (-0.30, 0.24, 0.52), (0.31, -0.22, 0.50)),
    "polycentric_tod": ((-0.23, -0.20, 0.92), (0.24, -0.17, 0.88), (-0.18, 0.22, 0.86), (0.25, 0.21, 0.84)),
    "river_constrained": ((-0.25, -0.21, 0.90), (0.24, -0.16, 0.86), (-0.22, 0.23, 0.82), (0.26, 0.19, 0.80)),
    "superblock_mixed": ((-0.25, -0.22, 0.92), (0.25, -0.20, 0.88), (-0.23, 0.23, 0.84), (0.24, 0.22, 0.82)),
    "organic": ((-0.13, -0.08, 1.0), (0.27, 0.18, 0.67), (-0.29, 0.23, 0.61)),
}


def build_urban_form_field(
    *,
    terrain: TerrainField,
    style_id: str,
    seed: int,
) -> UrbanFormField:
    """Build development and street-orientation fields on accepted terrain."""

    style = get_morphology_archetype(style_id).style_id
    layout = _CENTER_LAYOUTS[style]
    x_values = terrain.x_coordinates_m.astype(np.float64)
    y_values = terrain.y_coordinates_m.astype(np.float64)
    grid_x, grid_y = np.meshgrid(x_values, y_values)
    centers: list[UrbanCenter] = []
    for index, (nx, ny, weight) in enumerate(layout):
        jitter_x = math.sin((int(seed) + 11) * (index + 3) * 0.173) * 0.025
        jitter_y = math.cos((int(seed) + 7) * (index + 5) * 0.191) * 0.025
        target_x = (nx + jitter_x) * terrain.width_m
        target_y = (ny + jitter_y) * terrain.height_m
        x_m, y_m = _nearest_buildable_coordinate(
            terrain=terrain,
            grid_x=grid_x,
            grid_y=grid_y,
            target_x=target_x,
            target_y=target_y,
        )
        centers.append(
            UrbanCenter(
                center_id=index,
                x_m=x_m,
                y_m=y_m,
                weight=weight,
                role="primary" if index == 0 else "subcenter",
            )
        )
    intensity = np.zeros(terrain.shape, dtype=np.float64)
    sigma_x = terrain.width_m * (0.20 if style == "organic" else 0.17)
    sigma_y = terrain.height_m * (0.19 if style == "river_constrained" else 0.16)
    for center in centers:
        intensity += center.weight * np.exp(
            -0.5
            * (
                ((grid_x - center.x_m) / sigma_x) ** 2
                + ((grid_y - center.y_m) / sigma_y) ** 2
            )
        )
    intensity *= np.clip(1.0 - terrain.slope_rise_per_m.astype(np.float64) * 3.0, 0.0, 1.0)
    intensity *= terrain.buildable_mask
    intensity /= max(float(np.max(intensity)), 1e-12)
    orientation_x, orientation_y = _orientation_field(
        style_id=style,
        seed=int(seed),
        grid_x=grid_x,
        grid_y=grid_y,
        centers=tuple(centers),
        width_m=terrain.width_m,
        height_m=terrain.height_m,
    )
    gateways = (
        (-terrain.width_m * 0.5, 0.0),
        (terrain.width_m * 0.5, 0.0),
        (0.0, -terrain.height_m * 0.5),
        (0.0, terrain.height_m * 0.5),
    )
    return UrbanFormField(
        terrain_fingerprint=terrain.fingerprint,
        style_id=style,
        centers=tuple(centers),
        gateways_m=gateways,
        development_intensity=intensity,
        orientation_x=orientation_x,
        orientation_y=orientation_y,
    )


def _nearest_buildable_coordinate(
    *,
    terrain: TerrainField,
    grid_x: Array,
    grid_y: Array,
    target_x: float,
    target_y: float,
) -> tuple[float, float]:
    distance = (grid_x - target_x) ** 2 + (grid_y - target_y) ** 2
    distance = np.where(terrain.buildable_mask, distance, np.inf)
    flat_index = int(np.argmin(distance))
    if not math.isfinite(float(distance.flat[flat_index])):
        raise ValueError("terrain contains no buildable center cell")
    row, column = np.unravel_index(flat_index, terrain.shape)
    return float(grid_x[row, column]), float(grid_y[row, column])


def _orientation_field(
    *,
    style_id: str,
    seed: int,
    grid_x: Array,
    grid_y: Array,
    centers: tuple[UrbanCenter, ...],
    width_m: float,
    height_m: float,
) -> tuple[Array, Array]:
    phase = (seed % 101) * 0.031
    if style_id == "ring_radial":
        angle = np.arctan2(grid_y, grid_x) + math.pi * 0.5
    elif style_id == "grid_core":
        angle = np.full(grid_x.shape, phase * 0.15)
    elif style_id == "river_constrained":
        angle = math.pi * 0.5 + 0.12 * np.sin(grid_y / height_m * math.tau + phase)
    elif style_id == "organic":
        angle = phase + 0.75 * np.sin(grid_x / width_m * math.tau * 1.3) * np.cos(
            grid_y / height_m * math.tau * 1.1
        )
    else:
        center_x = np.asarray([center.x_m for center in centers])[:, None, None]
        center_y = np.asarray([center.y_m for center in centers])[:, None, None]
        nearest = np.argmin(
            (grid_x[None, :, :] - center_x) ** 2
            + (grid_y[None, :, :] - center_y) ** 2,
            axis=0,
        )
        base_angles = np.asarray(
            [phase * 0.2 + index * (0.31 if style_id == "superblock_mixed" else 0.17) for index in range(len(centers))]
        )
        angle = base_angles[nearest]
    return np.cos(angle), np.sin(angle)


def _readonly_array(value: Array) -> Array:
    out = np.ascontiguousarray(value, dtype=np.float32).copy()
    if not bool(np.all(np.isfinite(out))):
        raise ValueError("urban form arrays must be finite")
    out.flags.writeable = False
    return out


def _urban_form_fingerprint(field_value: UrbanFormField) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "schema": "urban_form_field_v1",
                "terrain": field_value.terrain_fingerprint,
                "style_id": field_value.style_id,
                "centers": [
                    (center.center_id, center.x_m, center.y_m, center.weight, center.role)
                    for center in field_value.centers
                ],
                "gateways_m": field_value.gateways_m,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    for array in (
        field_value.development_intensity,
        field_value.orientation_x,
        field_value.orientation_y,
    ):
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()
