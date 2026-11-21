"""Independent exact Fraction model for time-dependent FIFO departure age.

This is a scientific extension of cohort prefix N_r, H_r, not a modification
of original binary Rust packet work. API status: planned, not implemented.
"""
from dataclasses import dataclass
from fractions import Fraction
from metroflow.v1.fifo_cohort_moments import CohortPacket

@dataclass(frozen=True)
class AgeSnapshot:
    clock: Fraction
    served: Fraction
    route_mass: dict[int, Fraction]
    route_birth_moment: dict[int, Fraction]
    route_age_moment: dict[int, Fraction]
    mean_departed_age: dict[int, Fraction | None]

def departure_age_snapshot(
    cohorts: tuple[CohortPacket, ...], clock: Fraction, served: Fraction
) -> AgeSnapshot:
    raise NotImplementedError("dynamical route-age observable pending R5")
