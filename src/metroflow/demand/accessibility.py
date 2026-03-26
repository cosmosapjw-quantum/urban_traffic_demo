from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class AccessibilitySnapshot:
    computed_at_step: int
    zonal_costs: Tuple[Tuple[float, ...], ...] = tuple()


def compute_accessibility_placeholder() -> AccessibilitySnapshot:
    return AccessibilitySnapshot(computed_at_step=0, zonal_costs=tuple())
