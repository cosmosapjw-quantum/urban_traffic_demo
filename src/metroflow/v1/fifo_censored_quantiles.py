"""Finite-horizon FIFO route travel-time law with explicit right censoring.

Independent exact rational research oracle, NOT the original Rust road engine.
The input z coordinate is cumulative mass, NOT calendar time. Each cohort
span carries a fixed original birth-clock and route mark. A continuous
nondecreasing cumulative physical service curve supplies its exit clock.
Every source mass not exited by observation H is explicitly at age +infinity.
No steady-state assumption or stochastic route-reassignment is made.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from typing import Iterable


@dataclass(frozen=True)
class FIFOBlock:
    route: int
    z0: F
    z1: F
    birth: F

    def __post_init__(self) -> None:
        if not isinstance(self.route, int) or self.route < 0:
            raise ValueError("source route identifier must be a nonnegative int")
        if F(self.z0) < 0 or F(self.z1) <= F(self.z0):
            raise ValueError("source mass interval must have strictly positive size")


@dataclass(frozen=True)
class ServiceCurve:
    """Continuous piecewise-affine cumulative ACTUAL service, not free capacity.

    Knot clock values strictly increase; mass values are nondecreasing.
    It starts at physical clock0, serviced mass0; beyond the last knot
    actual served mass remains constant (no fictitious late output).
    """

    points: tuple[tuple[F, F], ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("need at least two exact cumulative service knots")
        if self.points[0] != (F(0), F(0)):
            raise ValueError("physical cumulative service must start at (0,0)")
        for (t0, s0), (t1, s1) in zip(self.points, self.points[1:]):
            if F(t1) <= F(t0) or F(s1) < F(s0):
                raise ValueError("service clock must increase; service mass cannot decrease")

    def value(self, clock: F) -> F:
        clock = F(clock)
        if clock <= F(self.points[0][0]):
            return F(self.points[0][1])
        for (ta, sa), (tb, sb) in zip(self.points, self.points[1:]):
            if clock <= F(tb):
                return F(sa) + (F(sb) - F(sa)) * (clock - F(ta)) / (F(tb) - F(ta))
        return F(self.points[-1][1])


def service_dominates(fast: ServiceCurve, slow: ServiceCurve) -> bool:
    """Pointwise S_fast >= S_slow, certified on all linear knot intervals."""
    boundaries={F(0)}
    boundaries.update(F(t) for t, _ in fast.points)
    boundaries.update(F(t) for t, _ in slow.points)
    return all(fast.value(t) >= slow.value(t) for t in boundaries)


def _clip_mass(value: F, start: F, stop: F) -> F:
    return max(F(0), min(F(stop), F(value)) - F(start))


class FiniteFIFOQuantiles:
    """Full fixed-input route denominator with unfinished source at +infinity.

    source ordered pure route cohort spans. Each span is uniform in mass
    coordinate z; routing weights of nonpure mixtures can be expanded into
    disjoint ordered mass spans before constructing this reference oracle.
    """

    def __init__(self, source: Iterable[FIFOBlock], service: ServiceCurve,
                 horizon: F) -> None:
        self.source = tuple(source)
        self.service = service
        self.horizon = F(horizon)
        if not self.source or self.horizon < 0:
            raise ValueError("empty source or invalid finite horizon")
        last = F(0)
        route_masses: dict[int, F] = {}
        for cohort in self.source:
            lo, hi, birth = F(cohort.z0), F(cohort.z1), F(cohort.birth)
            if lo != last:
                raise ValueError("source intervals must be contiguous and FIFO ordered")
            if service.value(birth) > lo:
                raise ValueError("source physically serviced before original birth")
            route_masses[cohort.route] = (
                route_masses.get(cohort.route, F(0)) + (hi - lo))
            last = hi
        if service.value(F(service.points[-1][0])) > last:
            raise ValueError("actual output mass exceeds supplied physical source")
        self.route_masses = route_masses

    def route_mass(self, route: int) -> F:
        try:
            return self.route_masses[route]
        except KeyError as exc:
            raise ValueError("source has no mass for route") from exc

    def _served_route_mass(self, route: int, extra_max_age: F | None) -> F:
        self.route_mass(route)
        out = F(0)
        for cohort in self.source:
            if cohort.route != route:
                continue
            deadline = self.horizon
            if extra_max_age is not None:
                deadline = min(deadline, F(cohort.birth) + F(extra_max_age))
            out += _clip_mass(self.service.value(deadline), cohort.z0, cohort.z1)
        return out

    def completion(self, route: int) -> F:
        return self._served_route_mass(route, None) / self.route_mass(route)

    def cdf(self, route: int, delay: F) -> F:
        """Exact full-source P(exit by H and experienced delay <= delay)."""
        if F(delay) < 0:
            return F(0)
        return self._served_route_mass(route, F(delay)) / self.route_mass(route)

    def _finite_delay_breakpoints(self, route: int) -> tuple[F, ...]:
        """Original piecewise-affine inverse on each strictly served segment.

        The right-hand boundary of a service plateau is taken from the
        following advancing segment: a zero-mass endpoint has no mass, while
        quantiles at its right limit must still be exact.
        """
        self.route_mass(route)
        cap = self.service.value(self.horizon)
        breaks: set[F] = {F(0)}
        for cohort in self.source:
            if cohort.route != route:
                continue
            lo, hi, birth = F(cohort.z0), F(cohort.z1), F(cohort.birth)
            for (ta, sa), (tb, sb) in zip(
                    self.service.points, self.service.points[1:]):
                ta, sa, tb, sb = F(ta), F(sa), F(tb), F(sb)
                if sb <= sa:
                    continue
                left = max(lo, sa)
                right = min(hi, sb, cap)
                if right <= left:
                    continue
                for z in (left, right):
                    time = ta + (z - sa) * (tb - ta) / (sb - sa)
                    age = time - birth
                    if age < 0:
                        raise ArithmeticError("source FIFO service before birth")
                    breaks.add(age)
        return tuple(sorted(breaks))

    def quantile(self, route: int, probability: F) -> F | None:
        """Generalized inverse of full-source CDF, None means +infinity."""
        q = F(probability)
        if not F(0) < q <= F(1):
            raise ValueError("quantile probability must lie in (0,1]")
        if q > self.completion(route):
            return None
        delays = self._finite_delay_breakpoints(route)
        last_t = delays[0]
        last_F = self.cdf(route, last_t)
        if last_F >= q:
            return last_t
        for next_t in delays[1:]:
            next_F = self.cdf(route, next_t)
            if next_F >= q:
                if next_F == last_F:
                    return next_t
                # Physical route CDF is affine between actual service-mass
                # and source-birth breakpoints, exact rational interpolation.
                return last_t + (q - last_F) * (next_t - last_t) / (next_F - last_F)
            last_t, last_F = next_t, next_F
        raise ArithmeticError("completed mass reached but quantile not bracketed")
