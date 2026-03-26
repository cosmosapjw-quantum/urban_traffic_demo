from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ZoneDevelopmentDelta:
    housing_delta: Tuple[float, ...]
    jobs_delta: Tuple[float, ...]


def apply_lagged_landuse_feedback(
    lagged_accessibility: Tuple[float, ...],
    current_housing: Tuple[float, ...],
    current_jobs: Tuple[float, ...],
    gain: float = 0.01,
) -> ZoneDevelopmentDelta:
    # Placeholder: same-tick closure 금지. 반드시 lagged_accessibility만 입력으로 받는다.
    h = tuple(gain * a for a in lagged_accessibility)
    j = tuple(gain * a for a in lagged_accessibility)
    return ZoneDevelopmentDelta(housing_delta=h, jobs_delta=j)
