from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ZoneDevelopmentDelta:
    housing_delta: Tuple[float, ...]
    jobs_delta: Tuple[float, ...]


def reduce_zonal_costs_to_lagged_accessibility(
    zonal_costs: Tuple[Tuple[float, ...], ...],
    eps: float = 1e-6,
) -> Tuple[float, ...]:
    zone_count = len(zonal_costs)
    if any(len(row) != zone_count for row in zonal_costs):
        raise ValueError("zonal_costs rows must match zonal_costs dimension.")
    if any(cost < 0.0 for row in zonal_costs for cost in row):
        raise ValueError("zonal_costs must be non-negative.")
    if eps <= 0.0:
        raise ValueError("eps must be positive.")

    reduced = []
    for row in zonal_costs:
        mean_cost = sum(row) / len(row)
        reduced.append(1.0 / max(mean_cost, eps))
    return tuple(reduced)


def apply_lagged_landuse_feedback(
    lagged_accessibility: Tuple[float, ...],
    current_housing: Tuple[float, ...],
    current_jobs: Tuple[float, ...],
    gain: float = 0.01,
) -> ZoneDevelopmentDelta:
    if len(lagged_accessibility) != len(current_housing) or len(lagged_accessibility) != len(current_jobs):
        raise ValueError("lagged_accessibility, current_housing, and current_jobs must align.")
    if gain < 0.0:
        raise ValueError("gain must be non-negative.")
    if any(value < 0.0 for value in current_housing):
        raise ValueError("current_housing must be non-negative.")
    if any(value < 0.0 for value in current_jobs):
        raise ValueError("current_jobs must be non-negative.")

    # Same-tick closure remains forbidden: only lagged accessibility is consumed here.
    h = tuple(gain * max(accessibility, 0.0) for accessibility in lagged_accessibility)
    j = tuple(gain * max(accessibility, 0.0) for accessibility in lagged_accessibility)
    return ZoneDevelopmentDelta(housing_delta=h, jobs_delta=j)


def apply_landuse_delta(
    current_housing: Tuple[float, ...],
    current_jobs: Tuple[float, ...],
    delta: ZoneDevelopmentDelta,
) -> Tuple[Tuple[float, ...], Tuple[float, ...]]:
    next_housing = tuple(max(housing + change, 0.0) for housing, change in zip(current_housing, delta.housing_delta))
    next_jobs = tuple(max(jobs + change, 0.0) for jobs, change in zip(current_jobs, delta.jobs_delta))
    return next_housing, next_jobs
