"""Declared common-speed closure, finite response, metres/seconds/vehicles.

No network solver: T03/T04 will consume this local motion surface. Latent p is
not actual speed. Frozen bulk density supplies a mean-gap hazard approximation;
it does not imply pair safety, a closed pair PDE, or an empirical calibration.
"""

from dataclasses import dataclass, replace
import math

from ..foundation_kinetics import VehicleClass, characteristic, passage, target_speed
from .city import reject


@dataclass(frozen=True, slots=True)
class ClassMass:
    vehicle: VehicleClass
    mass_veh: float
    latent: float = 1.0
    restart_s_inv: float = 0.2
    hazard_s_inv: float = 0.3
    gap_scale_m: float = 10.0

    def __post_init__(self):
        if not isinstance(self.vehicle, VehicleClass):
            reject("registered physical vehicle class required")
        if (
            not math.isfinite(self.mass_veh)
            or self.mass_veh <= 0
            or not math.isfinite(self.latent)
            or not 0 <= self.latent <= 1
        ):
            reject("positive class mass and latent probability in [0,1] required")
        if any(
            not math.isfinite(x) or x < 0
            for x in (self.restart_s_inv, self.hazard_s_inv, self.gap_scale_m)
        ):
            reject("finite nonnegative rates and gap scale required")


@dataclass(frozen=True, slots=True)
class BulkState:
    time_s: float
    speed_mps: float
    classes: tuple[ClassMass, ...]

    def __post_init__(self):
        if not isinstance(self.classes, tuple) or any(
            not math.isfinite(x) or x < 0 for x in (self.time_s, self.speed_mps)
        ):
            reject("immutable class tuple and finite nonnegative clock/speed required")
        if len(self.classes) > 3 or len({c.vehicle.name for c in self.classes}) != len(
            self.classes
        ):
            reject("at most three distinct physical classes required")
        if not self.classes and self.speed_mps != 0:
            reject("vacuum speed convention is zero")

    @property
    def mass_veh(self):
        return math.fsum(c.mass_veh for c in self.classes)


@dataclass(frozen=True, slots=True)
class KineticEnvironment:
    lane_length_m: float  # sum of physical lane lengths, NOT centerline length
    cap_mps: float
    stamp_s: float

    def __post_init__(self):
        if (
            not math.isfinite(self.lane_length_m)
            or self.lane_length_m <= 0
            or any(not math.isfinite(x) or x < 0 for x in (self.cap_mps, self.stamp_s))
        ):
            reject("positive lane space, nonnegative cap and observation stamp required")


@dataclass(frozen=True, slots=True)
class BulkCoefficients:
    target_mps: float
    admissible_mps: float
    response_s: float
    accel_mps2: float
    brake_mps2: float
    mean_gap_m: float
    hazards_s_inv: tuple[float, ...]

    @property
    def characteristic_class(self):
        return VehicleClass(
            "bulk", max(1.0, self.admissible_mps), self.response_s, self.accel_mps2, self.brake_mps2
        )


@dataclass(frozen=True, slots=True)
class BulkStep:
    state: BulkState
    distance_m: float
    coefficients: BulkCoefficients | None


@dataclass(frozen=True, slots=True)
class PassagePrediction:
    status: str
    elapsed_s: float | None
    speed_mps: float
    assumed_environment_stamp_s: float


def compile_bulk(classes, *, speed_mps=0.0, time_s=0.0):
    """Quotient only fragments of the SAME class and rates, retaining weighted p."""
    groups = {}
    for c in classes:
        groups.setdefault(c.vehicle.name, []).append(c)
    result = []
    for _, parts in sorted(groups.items()):
        first = parts[0]
        if any(
            (c.vehicle, c.restart_s_inv, c.hazard_s_inv, c.gap_scale_m)
            != (first.vehicle, first.restart_s_inv, first.hazard_s_inv, first.gap_scale_m)
            for c in parts
        ):
            reject("same class label has incompatible physical laws")
        mass = math.fsum(c.mass_veh for c in parts)
        result.append(
            replace(
                first, mass_veh=mass, latent=math.fsum(c.mass_veh * c.latent for c in parts) / mass
            )
        )
    return BulkState(time_s, speed_mps, tuple(result))


def coefficients(state, environment):
    if environment.stamp_s > state.time_s:
        reject("future environment observation is inadmissible")
    if not state.classes:
        reject("vacuum has no conditional motion law")
    occupied = math.fsum(c.mass_veh * c.vehicle.length_m for c in state.classes)
    if occupied > environment.lane_length_m:
        reject("class lengths exceed lane space", "PHYSICAL_INFEASIBLE")
    gap = (environment.lane_length_m - occupied) / state.mass_veh
    weights = tuple(c.mass_veh / state.mass_veh for c in state.classes)
    inverse_tau = math.fsum(w / c.vehicle.response_s for w, c in zip(weights, state.classes))
    admissible = min(target_speed(c.vehicle, gap, environment.cap_mps) for c in state.classes)
    target = (
        admissible
        * math.fsum(w * c.latent / c.vehicle.response_s for w, c in zip(weights, state.classes))
        / inverse_tau
    )
    hazards = tuple(
        c.hazard_s_inv * (c.gap_scale_m / (gap + c.vehicle.length_m)) ** 2 for c in state.classes
    )
    if any(not math.isfinite(x) for x in (target, inverse_tau, *hazards)):
        reject("nonfinite closure coefficients", "NUMERICAL_ERROR")
    return BulkCoefficients(
        target,
        admissible,
        1 / inverse_tau,
        min(c.vehicle.accel_mps2 for c in state.classes),
        min(c.vehicle.brake_mps2 for c in state.classes),
        gap,
        hazards,
    )


def _latent(classes, hazards, dt):
    out = []
    for c, nu in zip(classes, hazards):
        rate = c.restart_s_inv + nu
        if not math.isfinite(rate):
            reject("latent relaxation rate overflow", "NUMERICAL_ERROR")
        p = (
            c.latent
            if rate == 0
            else c.latent + (c.restart_s_inv / rate - c.latent) * (-math.expm1(-rate * dt))
        )
        out.append(replace(c, latent=p))
    return tuple(out)


def advance_bulk(state, environment, dt):
    """Symmetric p-half / exact frozen-speed / p-half splitting.

    p'_c=r_c(1-p_c)-nu_c p_c; v'=clip(sum w_c(U*p_c-v)/tau_c,
    -min b_c,min a_c). N, composition, lane space and observed cap are frozen
    over this local interval. Midpoint p is held for the characteristic. This
    numerical approximation requires dt refinement; distance uses that same v.
    """
    if not math.isfinite(dt) or dt < 0:
        reject("finite nonnegative step duration required")
    if environment.stamp_s > state.time_s:
        reject("future environment observation is inadmissible")
    if not state.classes:
        return BulkStep(replace(state, time_s=state.time_s + dt), 0.0, None)
    initial = coefficients(state, environment)
    mid = replace(state, classes=_latent(state.classes, initial.hazards_s_inv, dt / 2))
    held = coefficients(mid, environment)
    dx, v = characteristic(held.characteristic_class, state.speed_mps, held.target_mps, dt)
    final = BulkState(state.time_s + dt, v, _latent(mid.classes, held.hazards_s_inv, dt / 2))
    return BulkStep(final, dx, held)


def predict_passage(state, environment, length_m, *, step_s=0.5, horizon_s=3600.0, max_steps=10000):
    """First passage of the SAME split characteristic, frozen admitted environment.

    No future cap/density truth is consumed. Partial-bin roots retain the full
    bin's held coefficients so cost and motion agree on the same trajectory.
    """
    if (
        any(not math.isfinite(x) or x < 0 for x in (length_m, horizon_s))
        or not math.isfinite(step_s)
        or step_s <= 0
        or isinstance(max_steps, bool)
        or not isinstance(max_steps, int)
        or max_steps < 1
    ):
        reject("finite length/horizon and positive step/budget required")
    if environment.stamp_s > state.time_s:
        reject("future environment observation is inadmissible")
    if length_m == 0:
        return PassagePrediction("PASS", 0.0, state.speed_mps, environment.stamp_s)
    if not state.classes:
        return PassagePrediction("UNREACHABLE", None, 0.0, environment.stamp_s)
    current = state
    distance = 0.0
    for _ in range(max_steps):
        elapsed = current.time_s - state.time_s
        if elapsed >= horizon_s:
            return PassagePrediction(
                "HORIZON_REACHED", None, current.speed_mps, environment.stamp_s
            )
        dt = min(step_s, horizon_s - elapsed)
        step = advance_bulk(current, environment, dt)
        if distance + step.distance_m >= length_m:
            c = step.coefficients
            t, v = passage(
                c.characteristic_class, current.speed_mps, c.target_mps, length_m - distance
            )
            return PassagePrediction("PASS", elapsed + t, v, environment.stamp_s)
        # A permanently zero target has a finite asymptotic coast distance.
        if step.coefficients.admissible_mps == 0 or all(
            c.latent == 0 and c.restart_s_inv == 0 for c in current.classes
        ):
            c = step.coefficients
            t, v = passage(c.characteristic_class, current.speed_mps, 0.0, length_m - distance)
            if math.isinf(t):
                return PassagePrediction("UNREACHABLE", None, 0.0, environment.stamp_s)
        distance += step.distance_m
        current = step.state
    exc = RuntimeError("BLOCKED_RESOURCE: kinetic passage step budget exceeded")
    exc.checkpoint = current
    raise exc


def pair_compatibility(state, environment, pairs, leader_classes):
    """Necessary ring marginals/length ledger only, never sufficient safety proof.

    Each PairBin is follower quadrature mass; its leader mark is not counted
    twice. Different pair correlations can pass all these conditions.
    """
    coefficients(state, environment)
    pairs = tuple(pairs)
    leader_classes = tuple(leader_classes)
    if len(pairs) != len(leader_classes) or not pairs:
        reject("one declared leader class per nonempty pair bin required")
    total = math.fsum(p.mass for p in pairs)
    expected = {c.vehicle.name: c.mass_veh for c in state.classes}
    follower = {k: math.fsum(p.mass for p in pairs if p.vehicle.name == k) for k in expected}
    leader = {
        k: math.fsum(p.mass for p, k2 in zip(pairs, leader_classes) if k2 == k) for k in expected
    }
    registry = {c.vehicle.name: c.vehicle for c in state.classes}
    valid = all(
        p.vehicle.name in registry and p.vehicle == registry[p.vehicle.name] and k in registry
        for p, k in zip(pairs, leader_classes)
    )
    speeds = {p.v for p in pairs} | {p.w for p in pairs}
    speed_residual = max(
        (
            abs(
                math.fsum(p.mass for p in pairs if p.v == v)
                - math.fsum(p.mass for p in pairs if p.w == v)
            )
            for v in speeds
        ),
        default=0.0,
    )
    joint = {(p.vehicle.name, p.v) for p in pairs} | {
        (k, p.w) for p, k in zip(pairs, leader_classes)
    }
    joint_residual = max(
        (
            abs(
                math.fsum(p.mass for p in pairs if (p.vehicle.name, p.v) == key)
                - math.fsum(p.mass for p, k in zip(pairs, leader_classes) if (k, p.w) == key)
            )
            for key in joint
        ),
        default=0.0,
    )
    mean = math.fsum(p.mass * p.v for p in pairs) / total if total else 0.0
    length = math.fsum(p.mass * (p.h + p.vehicle.length_m) for p in pairs)
    mass_tol = 1e-9 * max(1.0, state.mass_veh)
    valid = (
        valid
        and abs(total - state.mass_veh) <= mass_tol
        and all(
            abs(follower[k] - expected[k]) <= mass_tol and abs(leader[k] - expected[k]) <= mass_tol
            for k in expected
        )
    )
    valid = (
        valid
        and speed_residual <= mass_tol
        and joint_residual <= mass_tol
        and abs(mean - state.speed_mps) <= 1e-9 * max(1.0, mean, state.speed_mps)
        and abs(length - environment.lane_length_m) <= 1e-9 * max(1.0, environment.lane_length_m)
    )
    return dict(
        status="PASS_NECESSARY_ONLY" if valid else "MODEL_ERROR",
        pair_mass_veh=total,
        lane_length_m=length,
        speed_marginal_residual_veh=speed_residual,
        follower_class_mass=follower,
        leader_class_mass=leader,
        joint_marginal_residual_veh=joint_residual,
        pair_mean_speed_mps=mean,
        safety="NOT_CERTIFIED",
        gap_closure="uniform mean gap is an approximation",
    )


def latent_reference(U, restart, stop, tau, p0, v0, t):
    """Exact UNCLIPPED homogeneous mean and stationary variance diagnostics.

    This is an independent continuous-speed latent-switching reference, not the
    common-speed closure's within-group variance (which is unresolved).
    """
    if (
        any(not math.isfinite(x) or x < 0 for x in (U, restart, stop, v0, t))
        or not math.isfinite(tau)
        or tau <= 0
        or not 0 <= p0 <= 1
        or restart + stop <= 0
    ):
        reject("valid positive-response latent reference parameters required")
    rate = restart + stop
    stationary = restart / rate
    p = stationary + (p0 - stationary) * math.exp(-rate * t)
    a = 1 / tau
    delta = a - rate
    convolution = (
        t * math.exp(-a * t)
        if delta == 0
        else math.exp(-min(a, rate) * t) * (-math.expm1(-abs(delta) * t)) / abs(delta)
    )
    mean = (
        U * stationary
        + (v0 - U * stationary) * math.exp(-a * t)
        + U * a * (p0 - stationary) * convolution
    )
    return dict(
        p=p,
        mean_mps=mean,
        latent_binary_mean_mps=U * p,
        stationary_variance_m2_s2=U * U * stationary * (1 - stationary) / (1 + rate * tau),
        binary_variance_m2_s2=U * U * stationary * (1 - stationary),
    )
