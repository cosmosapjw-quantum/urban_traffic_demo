"""Exact stop-loss envelopes from mass, first age moment, and known support.

This observer does not modify the native FIFO dynamics. Inputs are exact
numbers; passing native floats preserves their represented values but does not
certify their accumulated rounding error or establish missing support facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from typing import Iterable


@dataclass(frozen=True)
class AgeMomentBlock:
    """One nonnegative age measure specified by mass, moment and support."""

    mass: F
    age_moment: F
    lower_age: F
    upper_age: F

    def __post_init__(self) -> None:
        for name in ("mass", "age_moment", "lower_age", "upper_age"):
            object.__setattr__(self, name, F(getattr(self, name)))
        m, a, lo, hi = (self.mass, self.age_moment,
                        self.lower_age, self.upper_age)
        if m < 0 or lo < 0 or hi < lo:
            raise ValueError("nonnegative mass and ordered nonnegative support required")
        if not m * lo <= a <= m * hi:
            raise ValueError("age moment is incompatible with mass and support")

    @property
    def uniform_gap_bound(self) -> F:
        """Exact maximum single-block envelope gap over all thresholds."""
        m, a, lo, hi = (self.mass, self.age_moment,
                        self.lower_age, self.upper_age)
        if m == 0 or lo == hi:
            return F(0)
        return (a - m * lo) * (m * hi - a) / (m * (hi - lo))


@dataclass(frozen=True)
class StopLossEnvelope:
    threshold: F
    mass: F
    age_moment: F
    lower: F
    upper: F
    uniform_gap_bound: F


@dataclass(frozen=True)
class CdfEnvelope:
    threshold: F
    source_mass: F
    observed_mass: F
    lower: F
    upper: F
    strict_tail_lower: F
    strict_tail_upper: F


def from_birth_moment(
    mass: F, birth_moment: F, observation_time: F,
    birth_lower: F, birth_upper: F,
) -> AgeMomentBlock:
    """Translate a proven birth support to age at one common observation time.

    The caller supplies genuine birth support; a mean is not such a support.
    Negative birth clocks are allowed under a translation of the time origin.
    Every admitted birth must precede the common observation time.
    """
    m, b, t, lo, hi = map(F, (mass, birth_moment, observation_time,
                              birth_lower, birth_upper))
    if hi < lo or hi > t:
        raise ValueError("ordered birth support must precede observation time")
    return AgeMomentBlock(m, m * t - b, t - hi, t - lo)


def stop_loss_envelope(
    blocks: Iterable[AgeMomentBlock], threshold: F,
) -> StopLossEnvelope:
    """Sharp per-block Jensen/chord bounds, added over disjoint measure parts.

    Thresholds may be real, including negative values used by CDF secants.
    Physical age-excess queries normally use threshold >= 0. Blocks must
    represent disjoint parts of the same observation measure. Combining
    snapshot stocks from different times is not a disjoint partition.
    """
    u = F(threshold)
    mass = moment = lower = upper = gap = F(0)
    for block in blocks:
        m, a, lo, hi = (block.mass, block.age_moment,
                        block.lower_age, block.upper_age)
        mass += m
        moment += a
        lower += max(a - m * u, F(0))
        if lo == hi:
            upper += m * max(lo - u, F(0))
        else:
            upper += ((m * hi - a) * max(lo - u, F(0))
                      + (a - m * lo) * max(hi - u, F(0))) / (hi - lo)
        gap += block.uniform_gap_bound
    return StopLossEnvelope(u, mass, moment, lower, upper, gap)


def _source_mass(observed: F, assigned: F | None) -> F:
    source = observed if assigned is None else F(assigned)
    if source <= 0 or source < observed:
        raise ValueError("positive assigned source must include all observed mass")
    return source


def censored_tail_upper_bound(
    envelope: StopLossEnvelope, delta: F,
    assigned_source_mass: F | None = None,
) -> F:
    """Bound P(W_H >= threshold+delta), counting unobserved source at infinity.

    A completed-journey interpretation requires final external exits of
    once-only source mass. Internal passage rows describe passage incidences;
    their probability law is not a unique-vehicle completion law.
    """
    gap = F(delta)
    if gap <= 0:
        raise ValueError("positive delay gap required")
    source = _source_mass(envelope.mass, assigned_source_mass)
    censored = source - envelope.mass
    return (censored + min(envelope.mass, envelope.upper / gap)) / source


def cdf_envelope(
    blocks: Iterable[AgeMomentBlock], threshold: F, step: F,
    assigned_source_mass: F | None = None,
) -> CdfEnvelope:
    """Certified CDF interval from secants, not derivatives of ordered bounds.

    Bounds apply to the strict observed tail {age > threshold}; at atoms the
    upper backward secant also includes equality mass and may be conservative.
    Support facts tighten degenerate and fully classified blocks. Assigned
    mass absent from these observations is censored at +infinity.
    """
    items = tuple(blocks)
    u, h = F(threshold), F(step)
    if h <= 0:
        raise ValueError("positive secant step required")
    mid = stop_loss_envelope(items, u)
    left = stop_loss_envelope(items, u - h)
    right = stop_loss_envelope(items, u + h)
    source = _source_mass(mid.mass, assigned_source_mass)
    definite_gt = sum((b.mass for b in items if b.lower_age > u), F(0))
    definite_le = sum((b.mass for b in items if b.upper_age <= u), F(0))
    tail_lower = max(F(0), definite_gt, (mid.lower - right.upper) / h)
    tail_upper = min(mid.mass - definite_le,
                     (left.upper - mid.lower) / h)
    if not F(0) <= tail_lower <= tail_upper <= mid.mass:
        raise ArithmeticError("inconsistent stop-loss secant bounds")
    return CdfEnvelope(
        u, source, mid.mass, (mid.mass - tail_upper) / source,
        (mid.mass - tail_lower) / source, tail_lower, tail_upper,
    )
