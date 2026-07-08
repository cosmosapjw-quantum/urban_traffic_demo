"""Deterministic district-first backbone planning for synthetic city generation."""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["BackbonePlan", "plan_city_backbone"]

_MORPHOLOGY_FAMILIES: tuple[str, ...] = (
    "grid_spine",
    "offset_spine",
    "curved_spine",
)


@dataclass(slots=True, frozen=True)
class BackbonePlan:
    """Deterministic geometry plan consumed by topology/zoning builders."""

    population_target: int
    corridor_count: int
    x_positions: tuple[float, ...]
    bridge_indices: tuple[int, ...]
    ramp_indices: tuple[int, ...]
    corridor_family_by_index: tuple[str, ...]
    corridor_district_ids: tuple[int, ...]
    district_centers: tuple[tuple[float, float], ...]
    subcenter_points: tuple[tuple[float, float], ...]


def plan_city_backbone(
    *,
    population_target: int,
    seed: int,
    radial_corridor_count: int = 96,
    bridge_count: int = 5,
    interchange_density_profile: str = "high",
) -> BackbonePlan:
    """Plan a bounded-aspect, district-first city backbone."""

    resolved_population = max(1, int(population_target))
    seed = int(seed)
    corridor_count = _scaled_corridor_count(
        base_corridor_count=max(int(radial_corridor_count), int(bridge_count)),
        population_target=resolved_population,
    )

    family_by_index = _assign_morphology_families(corridor_count=corridor_count, seed=seed)
    spacing_x = _bounded_aspect_spacing(corridor_count=corridor_count)
    raw_x = tuple(
        (idx * spacing_x)
        + _corridor_x_offset(
            family=family_by_index[idx],
            index=idx,
            seed=seed,
            spacing=spacing_x,
        )
        for idx in range(corridor_count)
    )
    if raw_x:
        center = (raw_x[0] + raw_x[-1]) * 0.5
        x_positions = tuple(value - center for value in raw_x)
    else:
        x_positions = ()

    bridge_indices = _rotated_indices(corridor_count, count=int(bridge_count), seed=seed + 3)
    ramp_target = _ramp_corridor_count(
        corridor_count=corridor_count,
        interchange_density_profile=interchange_density_profile,
    )
    ramp_indices = _rotated_indices(corridor_count, count=ramp_target, seed=seed + 17)

    district_count = _district_count(population_target=resolved_population)
    district_anchor_indices = _rotated_indices(corridor_count, count=district_count, seed=seed + 7)
    district_x_scale = 0.42
    district_centers = tuple(
        (
            float(x_positions[idx]) * district_x_scale,
            _district_center_y(rank=rank, seed=seed),
        )
        for rank, idx in enumerate(district_anchor_indices)
    )

    corridor_district_ids = _corridor_district_ids(
        corridor_count=corridor_count,
        district_anchor_indices=district_anchor_indices,
    )
    subcenter_target = min(max(6, district_count), max(6, corridor_count))
    subcenter_indices = _rotated_indices(corridor_count, count=subcenter_target, seed=seed + 29)
    subcenter_points = tuple(
        (
            float(x_positions[idx]) * district_x_scale,
            _subcenter_y(rank=rank, seed=seed),
        )
        for rank, idx in enumerate(subcenter_indices)
    )

    return BackbonePlan(
        population_target=resolved_population,
        corridor_count=corridor_count,
        x_positions=x_positions,
        bridge_indices=bridge_indices,
        ramp_indices=ramp_indices,
        corridor_family_by_index=family_by_index,
        corridor_district_ids=corridor_district_ids,
        district_centers=district_centers,
        subcenter_points=subcenter_points,
    )


def _scaled_corridor_count(*, base_corridor_count: int, population_target: int) -> int:
    base = max(4, int(base_corridor_count))
    target = int(population_target)
    if target >= 100_000:
        return max(64, min(base, 64))
    if target >= 50_000:
        return max(40, min(base, 48))
    if target >= 20_000:
        return max(24, min(base, 32))
    return max(base, 8)


def _bounded_aspect_spacing(*, corridor_count: int) -> float:
    # Keep the horizontal span bounded so the rendered envelope stays non-strip-like.
    if corridor_count <= 1:
        return 130.0
    max_horizontal_span = 12_000.0
    spacing = max_horizontal_span / float(max(1, corridor_count - 1))
    return max(80.0, min(130.0, spacing))


def _assign_morphology_families(*, corridor_count: int, seed: int) -> tuple[str, ...]:
    if corridor_count <= 0:
        return ()
    rotation = int(seed) % len(_MORPHOLOGY_FAMILIES)
    return tuple(
        _MORPHOLOGY_FAMILIES[(idx + rotation) % len(_MORPHOLOGY_FAMILIES)]
        for idx in range(corridor_count)
    )


def _corridor_x_offset(*, family: str, index: int, seed: int, spacing: float) -> float:
    if family == "grid_spine":
        return 0.0
    if family == "offset_spine":
        return float(((seed + (index * 3)) % 5) - 2) * (spacing * 0.22)
    return math.sin((seed + index) * 0.55) * (spacing * 0.35)


def _rotated_indices(total: int, *, count: int, seed: int) -> tuple[int, ...]:
    if total <= 0 or count <= 0:
        return ()
    count = min(int(count), int(total))
    step = max(1, total // count)
    base = list(range(0, total, step))[:count]
    rotation = seed % total
    rotated = {(index + rotation) % total for index in base}
    return tuple(sorted(rotated))


def _ramp_corridor_count(*, corridor_count: int, interchange_density_profile: str) -> int:
    density = str(interchange_density_profile).lower()
    if density == "low":
        factor = 0.25
    elif density == "high":
        factor = 0.75
    else:
        factor = 0.5
    return max(1, min(corridor_count, int(round(corridor_count * factor))))


def _district_count(*, population_target: int) -> int:
    target = int(population_target)
    if target >= 100_000:
        return 8
    if target >= 50_000:
        return 6
    if target >= 20_000:
        return 4
    return 3


def _district_center_y(*, rank: int, seed: int) -> float:
    levels = (-760.0, -460.0, -140.0, 220.0, 560.0, 900.0)
    base = levels[(rank + seed) % len(levels)]
    jitter = ((seed + (rank * 5)) % 3 - 1) * 40.0
    return float(base + jitter)


def _subcenter_y(*, rank: int, seed: int) -> float:
    levels = (-520.0, -260.0, 20.0, 300.0, 620.0, 940.0)
    base = levels[(seed + rank) % len(levels)]
    jitter = ((seed + (rank * 7)) % 5 - 2) * 30.0
    return float(base + jitter)


def _corridor_district_ids(
    *,
    corridor_count: int,
    district_anchor_indices: tuple[int, ...],
) -> tuple[int, ...]:
    if corridor_count <= 0 or not district_anchor_indices:
        return ()
    districts = tuple(sorted(int(index) for index in district_anchor_indices))
    out: list[int] = []
    for idx in range(corridor_count):
        nearest_rank = min(
            range(len(districts)),
            key=lambda rank: (abs(idx - districts[rank]), rank),
        )
        out.append(int(nearest_rank) + 1)
    return tuple(out)
