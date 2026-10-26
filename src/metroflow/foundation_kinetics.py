"""Continuous-speed conditional kinetic reference, in metres and seconds.

Each bin is a quadrature mass, not a vehicle. Its gap is frozen during a local
characteristic. This module does NOT close the evolution of leader correlations,
prove collision avoidance, or replace the network solver's transport physics.
"""

from dataclasses import dataclass, replace
import math


@dataclass(frozen=True, slots=True)
class VehicleClass:
    name: str = "car"
    preferred_mps: float = 20.0
    response_s: float = 2.0
    accel_mps2: float = 2.0
    brake_mps2: float = 4.0
    min_gap_m: float = 2.0
    headway_s: float = 1.0
    length_m: float = 5.0

    def __post_init__(self):
        positive = (
            self.preferred_mps,
            self.response_s,
            self.accel_mps2,
            self.brake_mps2,
            self.headway_s,
            self.length_m,
        )
        if not self.name or any(not math.isfinite(x) or x <= 0 for x in positive):
            raise ValueError("invalid physical vehicle class")
        if not math.isfinite(self.min_gap_m) or self.min_gap_m < 0:
            raise ValueError("invalid minimum gap")


@dataclass(frozen=True, slots=True)
class PhaseBin:
    mass: float
    gap_m: float
    speed_mps: float
    position_m: float = 0.0

    def __post_init__(self):
        if any(not math.isfinite(x) or x < 0 for x in (self.mass, self.gap_m, self.speed_mps)):
            raise ValueError("invalid quadrature mass, gap or speed")
        if not math.isfinite(self.position_m):
            raise ValueError("nonfinite position")


def target_speed(vehicle, gap, cap):
    if any(not math.isfinite(x) or x < 0 for x in (gap, cap)):
        raise ValueError("invalid local gap or road speed cap")
    return min(vehicle.preferred_mps, cap, max(0.0, (gap - vehicle.min_gap_m) / vehicle.headway_s))


def characteristic(vehicle, v0, target, dt):
    """Exact frozen-target flow of dv/dt=clip((target-v)/tau,-b,a).

    Displacement is integrated from the same continuous speed law. A changed
    road cap does not instantaneously clip an existing speed to that cap.
    """
    if any(not math.isfinite(x) or x < 0 for x in (v0, target, dt)):
        raise ValueError("speed, target and duration must be finite nonnegative")
    tau = vehicle.response_s
    difference = target - v0
    limit = vehicle.accel_mps2 if difference >= 0 else vehicle.brake_mps2
    acceleration = limit if difference >= 0 else -limit
    saturated = max(0.0, (abs(difference) - limit * tau) / limit)
    first = min(dt, saturated)
    distance = v0 * first + 0.5 * acceleration * first * first
    speed = v0 + acceleration * first
    remaining = dt - first
    if remaining > 0:
        change = -math.expm1(-remaining / tau)
        distance += target * remaining + (speed - target) * tau * change
        speed += (target - speed) * change
    return distance, max(0.0, speed)


def evolve(vehicle, bins, dt, cap):
    """Push forward fixed weighted nodes; neither mass nor bin count changes."""
    result = []
    for point in bins:
        dx, v = characteristic(
            vehicle, point.speed_mps, target_speed(vehicle, point.gap_m, cap), dt
        )
        result.append(replace(point, speed_mps=v, position_m=point.position_m + dx))
    return tuple(result)


def passage(vehicle, v0, target, length):
    """First passage from the SAME characteristic, including asymptotic stopping.

    Returns (+infinity,0) if a positive target cannot be reached. The exact
    frozen-target trajectory is monotone in distance; bisection solves its root.
    """
    characteristic(vehicle, v0, target, 0.0)
    if not math.isfinite(length) or length < 0:
        raise ValueError("invalid travel length")
    if length == 0:
        return 0.0, v0
    if target == 0:
        saturated = max(0.0, (v0 - vehicle.brake_mps2 * vehicle.response_s) / vehicle.brake_mps2)
        dx, v = characteristic(vehicle, v0, 0.0, saturated)
        limit = dx + v * vehicle.response_s
        if length >= limit:
            return math.inf, 0.0
    hi = max(1.0, length / max(v0, target, 1e-12))
    for _ in range(256):
        if characteristic(vehicle, v0, target, hi)[0] >= length:
            break
        hi *= 2.0
        if not math.isfinite(hi):
            raise ArithmeticError("passage bracket overflow")
    else:
        raise ArithmeticError("passage bracket exhausted")
    lo = 0.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if characteristic(vehicle, v0, target, mid)[0] >= length:
            hi = mid
        else:
            lo = mid
    return hi, characteristic(vehicle, v0, target, hi)[1]


def moments(bins):
    """Mass, mean speed, speed variance; explicit zero-mass vacuum convention."""
    bins = tuple(bins)
    mass = math.fsum(b.mass for b in bins)
    if mass == 0:
        return 0.0, 0.0, 0.0
    speed = math.fsum(b.mass * b.speed_mps for b in bins) / mass
    return mass, speed, math.fsum(b.mass * (b.speed_mps - speed) ** 2 for b in bins) / mass


def mean_passage(vehicle, bins, cap, length):
    """Conditional E_G[T], NOT length/E_G[v]; unreachable positive mass => inf."""
    bins = tuple(bins)
    mass = math.fsum(b.mass for b in bins)
    if mass <= 0:
        raise ValueError("mean passage is undefined for vacuum")
    return math.fsum(
        (b.mass / mass)
        * passage(vehicle, b.speed_mps, target_speed(vehicle, b.gap_m, cap), length)[0]
        for b in bins
        if b.mass > 0
    )
