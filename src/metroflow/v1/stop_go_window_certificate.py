"""Conditional stop-go arrival bounds from clipped motion and FIFO service.

SI units: seconds, metres, metres/second, metres/second**2 and vehicle-equivalent
mass. This is a research observer. It does not change native transport/routing.
A caller supplies ex ante window guarantees; an authority string records that
assumption and does not prove it for an endogenous traffic network.

The theorem is in real arithmetic. Transcendental evaluation uses Python float
with an explicit engineering margin, NOT directed-rounding interval arithmetic.
Exact Fraction arithmetic is used only for grid phase, mass-window counts and
feasibility checks on the supplied binary-float inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import math


class NumericalEvaluationError(ArithmeticError):
    """Valid mathematical inputs exceed this numerical evaluator's range."""


class WindowPhase(str, Enum):
    SLIDING = "sliding"
    ALIGNED = "aligned"


class BoundStatus(str, Enum):
    BOUND_EVALUATED = "BOUND_EVALUATED"
    HORIZON_UNCERTIFIED = "HORIZON_UNCERTIFIED"


def _finite(value: float, name: str, *, positive: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def _fraction(value: float) -> Fraction:
    return Fraction.from_float(value)


def _ceil_fraction(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _float_rational(value: Fraction, *, upward: bool) -> float:
    try:
        result = float(value)
    except OverflowError as error:
        raise NumericalEvaluationError("rational result exceeds finite float range") from error
    if not math.isfinite(result):
        raise NumericalEvaluationError("rational result exceeds finite float range")
    if upward and _fraction(result) < value:
        result = math.nextafter(result, math.inf)
    if not upward and _fraction(result) > value:
        result = math.nextafter(result, -math.inf)
    if not math.isfinite(result):
        raise NumericalEvaluationError("rounding exceeds finite float range")
    return result


def _phase(phase: WindowPhase, origin: float | None) -> tuple[WindowPhase, float | None]:
    phase = WindowPhase(phase)
    if phase is WindowPhase.SLIDING:
        if origin is not None:
            raise ValueError("sliding windows do not have an alignment origin")
    elif origin is None:
        raise ValueError("aligned windows require alignment_origin_s")
    else:
        origin = _finite(origin, "alignment_origin_s")
    return phase, origin


def _window_start(entry: float, window: float, phase: WindowPhase,
                  origin: float | None) -> Fraction:
    start = _fraction(entry)
    if phase is WindowPhase.ALIGNED:
        assert origin is not None
        base, width = _fraction(origin), _fraction(window)
        index = _ceil_fraction((start - base) / width)
        start = base + index * width
    return start


@dataclass(frozen=True)
class ExAnteBasis:
    context: str
    authority: str
    available_at_s: float
    valid_from_s: float
    valid_until_s: float

    def __post_init__(self) -> None:
        if not self.context.strip() or not self.authority.strip():
            raise ValueError("explicit context and caller authority are required")
        for name in ("available_at_s", "valid_from_s", "valid_until_s"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.valid_until_s < self.valid_from_s:
            raise ValueError("validity interval is reversed")


@dataclass(frozen=True)
class ClippedMotionLaw:
    relaxation_s: float
    speed_cap_m_s: float
    acceleration_m_s2: float
    braking_m_s2: float

    def __post_init__(self) -> None:
        for name in ("relaxation_s", "speed_cap_m_s", "acceleration_m_s2"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(self, "braking_m_s2", _finite(self.braking_m_s2, "braking_m_s2"))

    @property
    def eta(self) -> float:
        ratio = (_fraction(self.acceleration_m_s2) * _fraction(self.relaxation_s)
                 / _fraction(self.speed_cap_m_s))
        eta = _float_rational(min(Fraction(1), ratio), upward=False)
        if eta == 0:
            raise NumericalEvaluationError("positive eta underflows float")
        return eta


@dataclass(frozen=True)
class ForcingWindow:
    basis: ExAnteBasis
    window_s: float
    forcing_integral_lower_m: float
    phase: WindowPhase = WindowPhase.SLIDING
    alignment_origin_s: float | None = None

    def __post_init__(self) -> None:
        for name in ("window_s", "forcing_integral_lower_m"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        phase, origin = _phase(self.phase, self.alignment_origin_s)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "alignment_origin_s", origin)


@dataclass(frozen=True)
class JointServiceWindow:
    basis: ExAnteBasis
    window_s: float
    capacity_veh_s: float
    service_integral_lower_veh: float
    phase: WindowPhase = WindowPhase.SLIDING
    alignment_origin_s: float | None = None
    derivation: str = "direct_joint"
    marginal_integrals_veh: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        for name in ("window_s", "capacity_veh_s"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        object.__setattr__(self, "service_integral_lower_veh",
                           _finite(self.service_integral_lower_veh, "service_integral_lower_veh"))
        maximum = _fraction(self.window_s) * _fraction(self.capacity_veh_s)
        if _fraction(self.service_integral_lower_veh) > maximum:
            raise ValueError("joint service exceeds capacity times window")
        phase, origin = _phase(self.phase, self.alignment_origin_s)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "alignment_origin_s", origin)
        if self.derivation not in ("direct_joint", "marginal_overlap"):
            raise ValueError("unknown joint-service derivation")
        if self.derivation == "direct_joint":
            if self.marginal_integrals_veh is not None:
                raise ValueError("direct joint service must not carry marginal inputs")
        else:
            if self.marginal_integrals_veh is None or len(self.marginal_integrals_veh) != 2:
                raise ValueError("marginal overlap requires two marginal integrals")
            green, receiving = (_finite(x, "marginal_integral_veh")
                                for x in self.marginal_integrals_veh)
            if max(_fraction(green), _fraction(receiving)) > maximum:
                raise ValueError("a marginal exceeds capacity times window")
            joint = max(Fraction(0), _fraction(green) + _fraction(receiving) - maximum)
            if _fraction(self.service_integral_lower_veh) > joint:
                raise ValueError("declared joint lower exceeds guaranteed overlap")
            object.__setattr__(self, "marginal_integrals_veh", (green, receiving))

    @classmethod
    def from_marginals(cls, *, basis: ExAnteBasis, window_s: float,
                       capacity_veh_s: float, green_integral_lower_veh: float,
                       receiving_integral_lower_veh: float,
                       phase: WindowPhase = WindowPhase.SLIDING,
                       alignment_origin_s: float | None = None) -> JointServiceWindow:
        window = _finite(window_s, "window_s", positive=True)
        capacity = _finite(capacity_veh_s, "capacity_veh_s", positive=True)
        green = _finite(green_integral_lower_veh, "green_integral_lower_veh")
        receiving = _finite(receiving_integral_lower_veh, "receiving_integral_lower_veh")
        joint = max(Fraction(0), _fraction(green) + _fraction(receiving)
                    - _fraction(window) * _fraction(capacity))
        return cls(basis, window, capacity, _float_rational(joint, upward=False),
                   phase, alignment_origin_s, "marginal_overlap", (green, receiving))


@dataclass(frozen=True)
class QueueRankBound:
    basis: ExAnteBasis
    ahead_and_tagged_mass_veh: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "ahead_and_tagged_mass_veh",
                           _finite(self.ahead_and_tagged_mass_veh,
                                   "ahead_and_tagged_mass_veh", positive=True))


@dataclass(frozen=True)
class NumericalGuard:
    absolute_distance_m: float = 1e-10
    relative_distance: float = 1e-12

    def __post_init__(self) -> None:
        for name in ("absolute_distance_m", "relative_distance"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))


@dataclass(frozen=True)
class DistanceEvaluation:
    lower_m: float
    guard_m: float
    eta: float
    windows: int


@dataclass(frozen=True)
class MotionBound:
    status: BoundStatus
    reason: str
    window_start_s: float
    available_windows: int
    windows_used: int | None
    upper_time_s: float | None
    lower_distance_m: float
    distance_guard_m: float
    ignored_phase_delay_s: float
    initial_speed_lower_used_m_s: float


@dataclass(frozen=True)
class ServiceBound:
    status: BoundStatus
    reason: str
    ready_upper_s: float
    window_start_s: float
    windows_needed: int | None
    upper_time_s: float | None
    service_mass_lower_veh: float
    rank_mass_veh: float


@dataclass(frozen=True)
class LinkBound:
    status: BoundStatus
    reason: str
    context: str
    decision_s: float
    entry_s: float
    motion: MotionBound
    service: ServiceBound | None
    exit_upper_s: float | None
    numerical_semantics: str = "analytic conditional bound; guarded float evaluation, not interval-certified"


def motion_distance_lower(law: ClippedMotionLaw, forcing: ForcingWindow,
                          windows: int, *, initial_speed_lower_m_s: float = 0.0,
                          guard: NumericalGuard = NumericalGuard()) -> DistanceEvaluation:
    """Evaluate the real-arithmetic lower at full windows; not a causal check."""
    if isinstance(windows, bool) or not isinstance(windows, int) or windows < 1:
        raise ValueError("windows must be a positive integer")
    v0 = _finite(initial_speed_lower_m_s, "initial_speed_lower_m_s")
    if v0 > law.speed_cap_m_s:
        raise ValueError("initial speed lower exceeds invariant cap")
    if (_fraction(forcing.forcing_integral_lower_m)
            > _fraction(law.speed_cap_m_s) * _fraction(forcing.window_s)):
        raise ValueError("forcing integral exceeds speed cap times window")
    tau, J, H = law.relaxation_s, forcing.forcing_integral_lower_m, forcing.window_s
    eta = law.eta
    h = _float_rational(windows * _fraction(H), upward=False)
    x, y = H / tau, h / tau
    if x == 0 or y == 0:
        raise NumericalEvaluationError("window/relaxation underflows numerical kernel")
    denominator = -math.expm1(-x)
    memory = -math.expm1(-y)
    z = (J / law.speed_cap_m_s) / tau
    # phi(z)=(1-exp(-z))/z, with its continuous value at zero.
    phi = 1.0 if z == 0 else (0.0 if math.isinf(z) else -math.expm1(-z) / z)
    sum_forcing = _float_rational(windows * _fraction(J), upward=False)
    tail = J * phi * (memory / denominator)
    initial = v0 * (tau * memory)
    lower = initial + eta * (sum_forcing - tail)
    scale = abs(initial) + eta * (abs(sum_forcing) + abs(tail))
    margin = guard.absolute_distance_m + guard.relative_distance * scale
    if not all(math.isfinite(x) for x in (lower, scale, margin)):
        raise NumericalEvaluationError("distance or margin is not representable")
    if lower < -margin:
        raise NumericalEvaluationError("kernel cancellation violates nonnegative lower")
    return DistanceEvaluation(max(0.0, lower), margin, eta, windows)


def _validate_basis(basis: ExAnteBasis, context: str, decision: float, entry: float) -> None:
    if basis.context != context:
        raise ValueError("guarantee context does not match query")
    if basis.available_at_s > decision:
        raise ValueError("guarantee was not available at decision time")
    if basis.valid_from_s > entry:
        raise ValueError("guarantee validity begins after query entry")


def _motion_bound(law: ClippedMotionLaw, forcing: ForcingWindow, entry: float,
                  length: float, v0: float, guard: NumericalGuard) -> MotionBound:
    start = _window_start(entry, forcing.window_s, forcing.phase, forcing.alignment_origin_s)
    delay = start - _fraction(entry)
    initial = v0 if delay == 0 else 0.0
    available = max(0, int((_fraction(forcing.basis.valid_until_s) - start)
                           // _fraction(forcing.window_s)))
    start_float = _float_rational(start, upward=True)
    delay_float = _float_rational(delay, upward=True)
    if available == 0:
        return MotionBound(BoundStatus.HORIZON_UNCERTIFIED, "no complete valid forcing window",
                           start_float, 0, None, None, 0.0, 0.0, delay_float, initial)

    def evaluate(n: int) -> DistanceEvaluation:
        return motion_distance_lower(law, forcing, n, initial_speed_lower_m_s=initial, guard=guard)

    def sufficient(value: DistanceEvaluation) -> bool:
        return value.lower_m - value.guard_m >= length

    # Exponential bracketing avoids evaluating unnecessarily enormous horizons.
    lo, hi = 0, 1
    value = evaluate(hi)
    while not sufficient(value) and hi < available:
        lo, hi = hi, min(2 * hi, available)
        value = evaluate(hi)
    if not sufficient(value):
        return MotionBound(BoundStatus.HORIZON_UNCERTIFIED,
                           "valid horizon does not establish guarded distance threshold",
                           start_float, available, None, None, value.lower_m, value.guard_m,
                           delay_float, initial)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        middle = evaluate(mid)
        if sufficient(middle):
            hi, value = mid, middle
        else:
            lo = mid
    value = evaluate(hi)
    upper = _float_rational(start + hi * _fraction(forcing.window_s), upward=True)
    return MotionBound(BoundStatus.BOUND_EVALUATED, "conditional motion bound evaluated",
                       start_float, available, hi, upper, value.lower_m, value.guard_m,
                       delay_float, initial)


def _service_bound(service: JointServiceWindow, rank: QueueRankBound,
                   ready_upper: float) -> ServiceBound:
    start = _window_start(ready_upper, service.window_s, service.phase,
                          service.alignment_origin_s)
    start_float = _float_rational(start, upward=True)
    joint, mass = service.service_integral_lower_veh, rank.ahead_and_tagged_mass_veh
    if rank.basis.valid_until_s < ready_upper:
        return ServiceBound(BoundStatus.HORIZON_UNCERTIFIED,
                            "rank bound does not cover every possible ready time",
                            ready_upper, start_float, None, None, joint, mass)
    if joint == 0:
        return ServiceBound(BoundStatus.HORIZON_UNCERTIFIED,
                            "no positive joint service follows from this guarantee",
                            ready_upper, start_float, None, None, joint, mass)
    count = _ceil_fraction(_fraction(mass) / _fraction(joint))
    finish = start + count * _fraction(service.window_s)
    if finish > _fraction(service.basis.valid_until_s):
        return ServiceBound(BoundStatus.HORIZON_UNCERTIFIED,
                            "required service windows exceed validity horizon",
                            ready_upper, start_float, count, None, joint, mass)
    return ServiceBound(BoundStatus.BOUND_EVALUATED, "conditional FIFO service bound evaluated",
                        ready_upper, start_float, count, _float_rational(finish, upward=True),
                        joint, mass)


def evaluate_link_bound(*, context: str, decision_s: float, entry_s: float,
                        length_m: float, law: ClippedMotionLaw,
                        forcing: ForcingWindow, service: JointServiceWindow,
                        rank: QueueRankBound, initial_speed_lower_m_s: float = 0.0,
                        guard: NumericalGuard = NumericalGuard()) -> LinkBound:
    """Bound last tagged-rank outlet under the documented physical assumptions.

    HORIZON_UNCERTIFIED means this promise/evaluation cannot establish a finite
    bound; it does not mean physical unreachability. Invalid or noncausal input
    raises ValueError; unrepresentable numeric evaluation raises
    NumericalEvaluationError. Production/native routing is not invoked.
    """
    if not context.strip():
        raise ValueError("explicit query context required")
    decision = _finite(decision_s, "decision_s")
    entry = _finite(entry_s, "entry_s")
    length = _finite(length_m, "length_m", positive=True)
    v0 = _finite(initial_speed_lower_m_s, "initial_speed_lower_m_s")
    if decision > entry:
        raise ValueError("prediction entry precedes decision")
    if v0 > law.speed_cap_m_s:
        raise ValueError("initial speed lower exceeds invariant cap")
    if (_fraction(forcing.forcing_integral_lower_m)
            > _fraction(law.speed_cap_m_s) * _fraction(forcing.window_s)):
        raise ValueError("forcing integral exceeds speed cap times window")
    for basis in (forcing.basis, service.basis, rank.basis):
        _validate_basis(basis, context, decision, entry)
    motion = _motion_bound(law, forcing, entry, length, v0, guard)
    if motion.status is BoundStatus.HORIZON_UNCERTIFIED:
        return LinkBound(motion.status, motion.reason, context, decision, entry,
                         motion, None, None)
    assert motion.upper_time_s is not None
    node = _service_bound(service, rank, motion.upper_time_s)
    return LinkBound(node.status, node.reason, context, decision, entry,
                     motion, node, node.upper_time_s)
