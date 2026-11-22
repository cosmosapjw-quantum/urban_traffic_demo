"""Exact pathwise, route-labelled nonstationary occupation-age balance.

Scientific reference implementation, not the native f64 traffic engine.
Mass units are persons/vehicles; time in seconds; birth moment in mass*seconds.
The event stream is external boundary only; internal route-preserving transfers
cancel in the network-wide first-moment budget.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Literal, Mapping, Sequence


@dataclass(frozen=True)
class BoundaryEvent:
    clock: F
    route: int
    direction: Literal["in", "out"]
    mass: F
    birth_moment: F


@dataclass(frozen=True)
class RouteResidence:
    initial_age: F
    entry_age: F
    output_delay: F
    terminal_age: F
    area: F
    final_mass: F
    final_birth_moment: F


def finite_residence_balance(
    t0: F,
    horizon: F,
    initial: Mapping[int, tuple[F, F]],
    events: Sequence[BoundaryEvent],
) -> dict[int, RouteResidence]:
    """Compute D_out = ∫N dt + D_in + A(t0) - A(T) exactly.

    Group boundary actions at each identical clock so their exact net mass and
    birth moment are tested together, even if the caller lists exits first.
    This is not a FIFO enforcement theorem; it is a labelled conservation law.
    The finite event stream is source-time ordered, with no reordering at
    distinct times and no stochastic/roundoff approximations.
    """
    t0, horizon = F(t0), F(horizon)
    if horizon < t0:
        raise ValueError("negative finite physical observation horizon")
    states: dict[int, tuple[F, F]] = {}
    for route, (m, b) in initial.items():
        m, b = F(m), F(b)
        if m < 0 or (m == 0 and b != 0) or b > m * t0:
            raise ValueError("initial route stock or birth-time moment is invalid")
        states[route] = (m, b)
    route_set = set(states)
    for evt in events:
        route_set.add(evt.route)
    mass = {r: states.get(r, (F(0), F(0)))[0] for r in route_set}
    birth = {r: states.get(r, (F(0), F(0)))[1] for r in route_set}
    area = {r: F(0) for r in route_set}
    entry_age = {r: F(0) for r in route_set}
    output_delay = {r: F(0) for r in route_set}
    initial_age = {r: t0 * mass[r] - birth[r] for r in route_set}
    last = t0
    i = 0
    while i < len(events):
        clock = F(events[i].clock)
        if clock < last or clock > horizon:
            raise ValueError("boundary events must be chronological and within horizon")
        width = clock - last
        for r in route_set:
            area[r] += mass[r] * width
        # Simultaneous boundary actions form one signed physical source
        # measure, not an arbitrary sequence of intermediate route states.
        delta_m: dict[int, F] = {}
        delta_b: dict[int, F] = {}
        while i < len(events) and F(events[i].clock) == clock:
            event = events[i]
            m, b = F(event.mass), F(event.birth_moment)
            if m < 0 or (m == 0 and b != 0) or b > clock * m:
                raise ValueError("negative event mass or future birth-time moment")
            if event.direction not in ("in", "out"):
                raise ValueError("unrecognized original boundary direction")
            sign = 1 if event.direction == "in" else -1
            delta_m[event.route] = delta_m.get(event.route, F(0)) + sign * m
            delta_b[event.route] = delta_b.get(event.route, F(0)) + sign * b
            if sign == 1:
                entry_age[event.route] += clock * m - b
            else:
                output_delay[event.route] += clock * m - b
            i += 1
        for r in delta_m:
            mass[r] += delta_m[r]
            birth[r] += delta_b[r]
            if mass[r] < 0 or (mass[r] == 0 and birth[r] != 0) or birth[r] > mass[r] * clock:
                raise ValueError("route source/birth conservation violated")
        last = clock
    for r in route_set:
        area[r] += mass[r] * (horizon - last)
    result: dict[int, RouteResidence] = {}
    for r in sorted(route_set):
        term = horizon * mass[r] - birth[r]
        value = RouteResidence(initial_age[r],entry_age[r],output_delay[r],
                               term,area[r],mass[r],birth[r])
        if value.output_delay != value.area + value.entry_age + value.initial_age - value.terminal_age:
            raise ArithmeticError("exact route age stock balance violated")
        result[r] = value
    return result
