"""Causal passage -> finite-response speed bounds -> future arrival bounds.

Research observer only. All physical clocks are seconds, lengths metres and
speeds m/s. The model is spatially homogeneous tau*v' = V-v with a known
positive invariant/forcing interval [a,b] throughout the prediction interval.
A probe is one matched exact passage, never an event-age or population mean.

The formulas are analytic enclosures in real arithmetic. Python float outputs
and bisection brackets are numerical approximations, NOT directed-rounding
interval certificates. Experiments supply separate high-precision checks and,
for the route decision, an exact rational dominance argument.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class CompletedPassage:
    context: str
    entry_s: float
    exit_s: float
    delivered_s: float
    length_m: float
    kind: str = "matched_entry_exit"

    def __post_init__(self) -> None:
        for key in ("entry_s", "exit_s", "delivered_s", "length_m"):
            object.__setattr__(self, key, _finite(getattr(self, key), key))
        if not self.context or self.kind != "matched_entry_exit":
            raise ValueError("explicit context and a matched boundary passage required")
        if not (0 <= self.entry_s < self.exit_s <= self.delivered_s):
            raise ValueError("positive passage duration and completed causal delivery required")
        if self.length_m <= 0:
            raise ValueError("positive observed length required")


@dataclass(frozen=True)
class NumericalDurationBounds:
    lower_s: float
    upper_s: float
    lower_root_bracket_s: tuple[float, float]
    upper_root_bracket_s: tuple[float, float]
    root_tolerance_s: float
    iterations: tuple[int, int]


@dataclass(frozen=True)
class ResponseProbeCertificate:
    """Conditional analytic certificate, with explicitly approximate evaluation.

    The caller certifies known tau and forcing/initial speed bounds, in the same
    fixed traffic context as the exact completed probe. Bounds must remain valid
    through every queried exit. This is not an estimator for tau, a queue model,
    or a guarantee after finite-demand rerouting changes the field.
    """
    context: str
    probe: CompletedPassage
    decision_s: float
    relaxation_s: float
    speed_lower_m_s: float
    speed_upper_m_s: float

    def __post_init__(self) -> None:
        for key in ("decision_s", "relaxation_s",
                    "speed_lower_m_s", "speed_upper_m_s"):
            object.__setattr__(self, key, _finite(getattr(self, key), key))
        if self.context != self.probe.context:
            raise ValueError("probe and prediction contexts differ")
        if self.decision_s < self.probe.delivered_s:
            raise ValueError("probe has not been delivered at this decision")
        if not (self.relaxation_s > 0
                and 0 < self.speed_lower_m_s <= self.speed_upper_m_s):
            raise ValueError("positive relaxation and positive ordered speed bounds required")
        if not self.speed_lower_m_s <= self.mean_speed_m_s <= self.speed_upper_m_s:
            raise ValueError("observed distance/duration contradict invariant speed bounds")
        if not math.isfinite(self.duration_s / self.relaxation_s):
            raise ValueError("duration/relaxation is outside floating evaluation range")

    @property
    def duration_s(self) -> float:
        return self.probe.exit_s - self.probe.entry_s

    @property
    def mean_speed_m_s(self) -> float:
        return self.probe.length_m / self.duration_s

    @property
    def memory_weight(self) -> float:
        """alpha = z/expm1(z); stable for both short and long observations."""
        z = self.duration_s / self.relaxation_s
        if z == 0:  # ratio underflow: the continuous alpha -> 1 limit
            return 1.0
        alpha = (z / math.expm1(z) if z < 50
                 else z * math.exp(-z) / -math.expm1(-z))
        return min(1.0, max(0.0, alpha))

    @property
    def exit_speed_bounds_m_s(self) -> tuple[float, float]:
        alpha = self.memory_weight
        mean = self.mean_speed_m_s
        a, b = self.speed_lower_m_s, self.speed_upper_m_s
        return (max(a, alpha * mean + (1 - alpha) * a),
                min(b, alpha * mean + (1 - alpha) * b))

    @staticmethod
    def _relax(value: float, forcing: float, elapsed: float, tau: float) -> float:
        z = elapsed / tau
        # Positive convex terms avoid b - (b-v)*exp(-z) cancellation.
        result = value * math.exp(-z) + forcing * -math.expm1(-z)
        return min(max(value, forcing), max(min(value, forcing), result))

    @property
    def decision_speed_bounds_m_s(self) -> tuple[float, float]:
        lo, hi = self.exit_speed_bounds_m_s
        delay = self.decision_s - self.probe.exit_s
        return (self._relax(lo, self.speed_lower_m_s, delay, self.relaxation_s),
                self._relax(hi, self.speed_upper_m_s, delay, self.relaxation_s))

    def speed_bounds_at(self, entry_s: float) -> tuple[float, float]:
        entry = _finite(entry_s, "entry_s")
        if entry < self.decision_s:
            raise ValueError("future prediction cannot precede its decision")
        lo, hi = self.decision_speed_bounds_m_s
        elapsed = entry - self.decision_s
        return (self._relax(lo, self.speed_lower_m_s, elapsed, self.relaxation_s),
                self._relax(hi, self.speed_upper_m_s, elapsed, self.relaxation_s))

    @staticmethod
    def _distance(initial: float, forcing: float, duration: float, tau: float) -> float:
        if duration == 0:
            return 0.0
        z = duration / tau
        weight = 1.0 if z == 0 else -math.expm1(-z) / z
        weight = min(1.0, max(0.0, weight))
        # Integral = h * [v_entry*w + forcing*(1-w)], both terms nonnegative.
        return duration * (initial * weight + forcing * (1 - weight))

    def distance_bounds(self, entry_s: float, duration_s: float) -> tuple[float, float]:
        duration = _finite(duration_s, "duration_s")
        if duration < 0:
            raise ValueError("negative future duration")
        lo, hi = self.speed_bounds_at(entry_s)
        return (self._distance(lo, self.speed_lower_m_s, duration, self.relaxation_s),
                self._distance(hi, self.speed_upper_m_s, duration, self.relaxation_s))

    def duration_bounds(self, entry_s: float, length_m: float, *,
                        tolerance_s: float = 1e-11, max_iterations: int = 200
                        ) -> NumericalDurationBounds:
        self.speed_bounds_at(entry_s)
        length = _finite(length_m, "length_m")
        tolerance = _finite(tolerance_s, "tolerance_s")
        if length <= 0 or tolerance <= 0 or max_iterations < 1:
            raise ValueError("positive length, root tolerance and iteration budget required")
        start = length / self.speed_upper_m_s
        end = length / self.speed_lower_m_s
        if not math.isfinite(end):
            raise ValueError("passage time outside floating evaluation range")

        def bisect(side: int) -> tuple[tuple[float, float], int]:
            lo, hi = start, end
            for iteration in range(max_iterations + 1):
                if hi - lo <= tolerance:
                    return (lo, hi), iteration
                if iteration == max_iterations:
                    break
                middle = lo + (hi - lo) / 2
                if middle == lo or middle == hi:
                    break
                distance = self.distance_bounds(entry_s, middle)[side]
                if distance < length:
                    lo = middle
                else:
                    hi = middle
            raise ArithmeticError("root tolerance not resolved within floating/iteration budget")

        lower, count_lower = bisect(1)  # faster admissible field -> earlier exit
        upper, count_upper = bisect(0)  # slower admissible field -> later exit
        return NumericalDurationBounds(lower[0], upper[1], lower, upper,
                                       tolerance, (count_lower, count_upper))
