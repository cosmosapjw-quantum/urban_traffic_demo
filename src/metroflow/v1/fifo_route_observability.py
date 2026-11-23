"""Causal FIFO arrival-map enclosures and a finite-response reference experiment.

Research observer only: this module does not mutate V1 routing or native traffic.
Pointwise passage probes are not completed-population means or birth moments.
All calculations use exact rational arithmetic; None is an unbounded upper clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
import heapq
from itertools import count
from typing import Iterable


@dataclass(frozen=True)
class ArrivalBand:
    lower: F
    upper: F | None

    @property
    def width(self) -> F | None:
        return None if self.upper is None else self.upper - self.lower


@dataclass(frozen=True)
class PassageProbe:
    """Matched entry/exit clock of one ordered boundary label, in SI seconds."""

    context: str
    entry_s: F
    exit_lower_s: F
    exit_upper_s: F
    stamp_s: F
    delivered_s: F
    kind: str = "matched_entry_exit"

    def __post_init__(self):
        for key in ("entry_s", "exit_lower_s", "exit_upper_s",
                    "stamp_s", "delivered_s"):
            object.__setattr__(self, key, F(getattr(self, key)))
        if not self.context or self.kind != "matched_entry_exit":
            raise ValueError("matched boundary passage and explicit context required")
        if not (0 <= self.entry_s <= self.exit_lower_s <= self.exit_upper_s
                <= self.stamp_s <= self.delivered_s):
            raise ValueError("entry, completed exit, stamp and delivery must be causal")


class FIFOArrivalEnvelope:
    """Sharp enclosure in the declared monotone gamma-Lipschitz function class.

    gamma=None retains FIFO alone. A finite gamma is an input certificate,
    not something fitted from a finite sample. In particular stop/spillback
    dynamics do not inherit a finite gamma from the finite-response example.
    Queries are limited to the declared finite entry-time domain [0, horizon].
    """

    def __init__(self, probes: Iterable[PassageProbe], *, context: str,
                 decision_s: F, entry_horizon_s: F, tau_min_s: F,
                 gamma: F | None = None):
        self.probes = tuple(probes)
        self.context = context
        self.decision_s = F(decision_s)
        self.entry_horizon_s = F(entry_horizon_s)
        self.tau_min_s = F(tau_min_s)
        self.gamma = None if gamma is None else F(gamma)
        if (not context or not 0 <= self.decision_s <= self.entry_horizon_s
                or self.tau_min_s < 0 or
                (self.gamma is not None and self.gamma < 1)):
            raise ValueError("finite domain, causal decision, nonnegative floor and gamma>=1 required")
        for p in self.probes:
            if (p.context != context or p.delivered_s > self.decision_s
                    or p.entry_s > self.entry_horizon_s):
                raise ValueError("probe context/domain mismatch or information not delivered")
            if p.exit_upper_s < p.entry_s + self.tau_min_s:
                raise ValueError("probe incompatible with minimum physical travel time")
        for p in self.probes:
            for q in self.probes:
                if self.gamma is None:
                    incompatible = p.entry_s <= q.entry_s and p.exit_lower_s > q.exit_upper_s
                else:
                    incompatible = p.exit_lower_s > (
                        q.exit_upper_s + self.gamma * max(p.entry_s - q.entry_s, F(0)))
                if incompatible:
                    raise ValueError("passage intervals have no admissible FIFO arrival map")

    def at(self, entry_s: F) -> ArrivalBand:
        t = F(entry_s)
        if not 0 <= t <= self.entry_horizon_s:
            raise ValueError("query outside certified entry-time domain")
        lower = t + self.tau_min_s
        upper = None
        for p in self.probes:
            if self.gamma is None:
                if p.entry_s <= t:
                    lower = max(lower, p.exit_lower_s)
                if t <= p.entry_s:
                    upper = p.exit_upper_s if upper is None else min(upper, p.exit_upper_s)
            else:
                lower = max(lower, p.exit_lower_s - self.gamma * max(p.entry_s - t, F(0)))
                cap = p.exit_upper_s + self.gamma * max(t - p.entry_s, F(0))
                upper = cap if upper is None else min(upper, cap)
        return ArrivalBand(lower, upper)


def compose_route(route: Iterable[FIFOArrivalEnvelope], departure_s: F) -> ArrivalBand:
    """Enclose a fixed route in a fixed traffic field by monotone composition."""
    maps = tuple(route)
    start = F(departure_s)
    if any(m.decision_s > start for m in maps):
        raise ValueError("route cannot consume information delivered after departure")
    lower = upper = start
    for m in maps:
        lower = m.at(lower).lower
        upper = None if upper is None else m.at(upper).upper
    return ArrivalBand(lower, upper)


@dataclass(frozen=True)
class RouteEdge:
    """One arc of a caller-supplied LEGAL turn-expanded directed graph."""

    key: str
    tail: str
    head: str
    arrival: FIFOArrivalEnvelope


@dataclass(frozen=True)
class RouteCertificate:
    lower_optimum_s: F | None
    upper_selected_s: F | None
    selected_edges: tuple[str, ...]

    @property
    def regret_bound_s(self) -> F | None:
        if self.lower_optimum_s is None or self.upper_selected_s is None:
            return None
        return self.upper_selected_s - self.lower_optimum_s


def _earliest(edges, origin, destination, departure, side):
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge.tail, []).append(edge)
    serial = count()
    queue = [(departure, next(serial), origin, ())]
    best = {origin: departure}
    while queue:
        clock, _, node, path = heapq.heappop(queue)
        if best[node] != clock:
            continue
        if node == destination:
            return clock, path
        for edge in adjacency.get(node, ()):
            band = edge.arrival.at(clock)
            reached = band.lower if side == "lower" else band.upper
            if reached is None:
                continue
            if edge.head not in best or reached < best[edge.head]:
                best[edge.head] = reached
                heapq.heappush(queue, (reached, next(serial), edge.head, path + (edge.key,)))
    return None, ()


def route_certificate(edges: Iterable[RouteEdge], origin: str, destination: str,
                      departure_s: F) -> RouteCertificate:
    """Lower optimum and upper-optimal feasible route, with regret certificate.

    This does not allocate demand or implement production K/path-size choice.
    Equal upper labels may select any minimizer; no tie-dependent probability
    is assigned. Missing upper coverage means unknown, not physical blockage.
    """
    edges = tuple(edges)
    departure = F(departure_s)
    if origin == destination:
        raise ValueError("same-location activity is outside the routing certificate")
    if len({e.key for e in edges}) != len(edges):
        raise ValueError("unique graph arc identities required")
    if any(not e.key or not e.tail or not e.head or e.arrival.decision_s > departure
           for e in edges):
        raise ValueError("invalid graph arc or future information")
    lower, _ = _earliest(edges, origin, destination, departure, "lower")
    upper, path = _earliest(edges, origin, destination, departure, "upper")
    return RouteCertificate(lower, upper, path)


@dataclass(frozen=True)
class FiniteResponseField:
    """Manufactured exact spatially homogeneous finite-response velocity.

    Piecewise-affine v(t) solves tau_r*v'=V(t)-v(t) a.e. for the declared
    forcing V=v+tau_r*v'. Target jumps at knots are allowed; v is continuous.
    Positive initial/target bounds establish invariant speed bounds. This is
    a reference scientific experiment, not a native city/spillback solver.
    """

    knots: tuple[tuple[F, F], ...]
    relaxation_s: F

    def __post_init__(self):
        object.__setattr__(self, "knots", tuple((F(t), F(v)) for t, v in self.knots))
        object.__setattr__(self, "relaxation_s", F(self.relaxation_s))
        if len(self.knots) < 2 or self.knots[0][0] != 0 or self.relaxation_s <= 0:
            raise ValueError("positive relaxation and finite clock domain starting at zero required")
        if any(v <= 0 for _, v in self.knots):
            raise ValueError("positive velocity required")
        if any(b[0] <= a[0] for a, b in zip(self.knots, self.knots[1:])):
            raise ValueError("strictly increasing velocity knots required")
        if self.speed_bounds[0] <= 0:
            raise ValueError("forcing does not certify a positive invariant speed floor")

    @property
    def horizon_s(self):
        return self.knots[-1][0]

    @property
    def speed_bounds(self):
        values = [self.knots[0][1]]
        for (ta, va), (tb, vb) in zip(self.knots, self.knots[1:]):
            slope = (vb - va) / (tb - ta)
            values.extend((va + self.relaxation_s * slope,
                           vb + self.relaxation_s * slope))
        return min(values), max(values)

    @property
    def gamma(self):
        lo, hi = self.speed_bounds
        return hi / lo

    def distance(self, start_s: F, end_s: F) -> F:
        """Exact integral of v [m/s] over [start,end] [s], returning metres."""
        start, end = F(start_s), F(end_s)
        if not 0 <= start <= end <= self.horizon_s:
            raise ValueError("integration outside velocity domain")
        result = F(0)
        for (ta, va), (tb, vb) in zip(self.knots, self.knots[1:]):
            a, b = max(start, ta), min(end, tb)
            if a < b:
                slope = (vb - va) / (tb - ta)
                result += va * (b - a) + slope * ((b - ta)**2 - (a - ta)**2) / 2
        return result

    def exit_band(self, entry_s: F, length_m: F,
                  width_s: F = F(1, 10**9)) -> ArrivalBand:
        """Exact-rational bracket for the root integral(entry,exit) v dt=length."""
        entry, length, width = F(entry_s), F(length_m), F(width_s)
        if not 0 <= entry < self.horizon_s or length <= 0 or width <= 0:
            raise ValueError("positive distance/width and valid entry clock required")
        low, high = entry, self.horizon_s
        if self.distance(entry, high) < length:
            raise ValueError("passage unresolved within declared velocity horizon")
        while high - low > width:
            mid = (low + high) / 2
            if self.distance(entry, mid) < length:
                low = mid
            else:
                high = mid
        return ArrivalBand(low, high)
