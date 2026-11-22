"""Route-labelled finite-horizon age-excess transport with exact original clocks.

This independent Fraction oracle is NOT the native Rust FIFO solver.
The output stop-loss curve reconstructs completed-sojourn tail masses, while
unfinished end stock remains explicitly censored and is not counted as output.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction as F
from collections import defaultdict
from typing import Iterable, Mapping


@dataclass(frozen=True)
class AgeCohort:
    route: int
    mass: F
    birth: F


@dataclass(frozen=True)
class AgeBoundary:
    """External arrival/final exit, or an explicitly paired internal transfer."""
    time: F
    route: int
    direction: str
    mass: F
    birth: F
    kind: str = "external"


@dataclass(frozen=True)
class RouteAgeExcess:
    output_loss: F
    tail_stock_time: F
    entry_loss: F
    initial_loss: F
    terminal_loss: F
    output_mass: F
    route_source_mass: F
    completed_cdf: F | None
    fixed_source_cdf: F | None
    strict_output_tail_mass: F
    weak_output_tail_mass: F
    output_delay_square: F

    def censored_tail_upper_bound(self, delta: F) -> F:
        """Rigorous full-source P(unfinished OR completed age >= u+delta).

        This RouteAgeExcess instance was evaluated at threshold u, and
        output_loss stores the completed stop-loss K(u). Any completed
        sojourn w >= u+delta contributes >=delta to K(u). Unfinished
        original source mass is at +infinity and must remain counted.
        The estimate needs no fitted distribution or microscopic tail.
        """
        gap=F(delta)
        if gap<=0 or self.route_source_mass<=0:
            raise ValueError("positive threshold gap and original route mass required")
        if self.output_mass<0 or self.output_mass>self.route_source_mass:
            raise ValueError("nonphysical route completed/source mass")
        unfinished=self.route_source_mass-self.output_mass
        completed_upper=min(self.output_mass,self.output_loss/gap)
        return (unfinished+completed_upper)/self.route_source_mass


def finite_age_excess_transport(
    t0:F, T:F, initial:Iterable[AgeCohort],
    boundaries:Iterable[AgeBoundary],
    thresholds:Iterable[F],
    *, assigned_source_mass:Mapping[int,F] | None = None,
) -> dict[tuple[int,F],RouteAgeExcess]:
    """Exact route age-excess identity for atomic source events.

    Initial state is at t0 AFTER all events at t0. Ordered boundaries
    occur in (t0,T], including events at T. Every resident ages at speed1.
    External boundaries denote original arrivals and final completions.
    Explicit internal annotations must cancel at equal time/route/birth;
    they are excluded from the arrival and completion distributions.
    The caller supplies physically legitimate transfers and preserves the
    original route/birth labels; this observer cannot establish unique IDs.

    Without assigned_source_mass the source denominator is initial stock
    plus external entry mass in this window. A declared nonnegative source
    population can additionally include assigned but not-yet-entered mass,
    which remains censored at +infinity. Unique-vehicle interpretation
    requires each original mass to enter/complete at most once; otherwise
    external records describe entry episodes. Adjacent windows share their
    endpoint stock, so their source denominators must not be added directly.
    Inputs are finite atomic cohorts/events with finite rational ages.
    """
    t0,T=F(t0),F(T)
    if T<t0:
        raise ValueError("terminal clock precedes source initial clock")
    src=tuple(initial)
    all_events=tuple(boundaries)
    us=tuple(dict.fromkeys(F(u) for u in thresholds))
    if any(u<0 for u in us):
        raise ValueError("negative age-excess threshold")
    route_mass:dict[int,F]=defaultdict(F)
    active:dict[tuple[int,F],F]=defaultdict(F)
    for x in src:
        m,b=F(x.mass),F(x.birth)
        if x.route<0 or m<=0 or b>t0:
            raise ValueError("nonphysical original resident source cohort")
        active[(x.route,b)]+=m
        route_mass[x.route]+=m
    last=t0
    internal_balance:dict[tuple[F,int,F],F]=defaultdict(F)
    for event in all_events:
        t,m,b=F(event.time),F(event.mass),F(event.birth)
        if t<=t0 or t>T or t<last or m<=0 or event.route<0 or b>t:
            raise ValueError("out of order or nonphysical source boundary")
        if event.direction not in ("in","out"):
            raise ValueError("invalid boundary source direction")
        if event.kind not in ("external","internal"):
            raise ValueError("invalid boundary kind")
        if event.kind=="internal":
            internal_balance[(t,event.route,b)]+=(m if event.direction=="in" else -m)
        elif event.direction=="in":
            route_mass[event.route]+=m
        last=t
    if any(internal_balance.values()):
        raise ValueError("internal transfers must cancel at equal time/route/birth")
    events=tuple(event for event in all_events if event.kind=="external")
    if assigned_source_mass is not None:
        declared={route:F(mass) for route,mass in assigned_source_mass.items()}
        observed_routes=set(route_mass)|{event.route for event in events}
        if (any(route<0 or mass<0 for route,mass in declared.items())
            or not observed_routes.issubset(declared)
            or any(declared[route]<mass for route,mass in route_mass.items())):
            raise ValueError("declared source must include all admitted route mass")
        route_mass=declared
    # An invalid output-only route must still be checked and rejected by
    # the active-stock conservation guard, not raise an unrelated KeyError.
    routes=set(route_mass)|{event.route for event in events}
    observed:dict[tuple[int,F],dict[str,F]]={
        (r,u):{
            "area":F(0), "input":F(0), "output":F(0),
            "cdf_mass":F(0), "tail_gt":F(0), "tail_ge":F(0),
            "initial":F(0),
        }
        for r in routes for u in us
    }
    for (r,b),m in active.items():
        for u in us:
            observed[(r,u)]["initial"]+=m*max(F(0),t0-b-u)
    out_mass:dict[int,F]=defaultdict(F)
    out_square:dict[int,F]=defaultdict(F)
    departure_ages:dict[int,list[tuple[F,F]]]=defaultdict(list)
    last=t0
    cursor=0
    while cursor<len(events):
        time=F(events[cursor].time)
        for (r,b),m in active.items():
            for u in us:
                a=max(last,b+u)
                if time>a:
                    observed[(r,u)]["area"]+=m*(time-a)
        grouped:dict[tuple[int,F],F]=defaultdict(F)
        while cursor<len(events) and F(events[cursor].time)==time:
            ev=events[cursor]
            m,b=F(ev.mass),F(ev.birth)
            age=time-b
            key=(ev.route,b)
            if ev.direction=="in":
                grouped[key]+=m
            else:
                grouped[key]-=m
                out_mass[ev.route]+=m
                out_square[ev.route]+=m*age*age
                departure_ages[ev.route].append((age,m))
            for u in us:
                g=m*max(F(0),age-u)
                if ev.direction=="in":
                    observed[(ev.route,u)]["input"]+=g
                else:
                    observed[(ev.route,u)]["output"]+=g
            cursor+=1
        for key,delta in grouped.items():
            if active[key]+delta<0:
                raise ValueError("output mass exceeds physically active route-birth cohort")
            active[key]+=delta
            if active[key]==0:
                del active[key]
        last=time
    for (r,b),m in active.items():
        for u in us:
            a=max(last,b+u)
            if T>a:
                observed[(r,u)]["area"]+=m*(T-a)
    result={}
    for r in routes:
        for u in us:
            v=observed[(r,u)]
            terminal=sum((m*max(F(0),T-b-u)
                          for (route,b),m in active.items() if route==r),F(0))
            if v["output"]!=v["area"]+v["input"]+v["initial"]-terminal:
                raise ArithmeticError("finite age-excess transport conservation violated")
            gt=sum((m for age,m in departure_ages[r] if age>u),F(0))
            ge=sum((m for age,m in departure_ages[r] if age>=u),F(0))
            cdf_mass=out_mass[r]-gt
            total=route_mass[r]
            result[(r,u)]=RouteAgeExcess(
                v["output"],v["area"],v["input"],v["initial"],terminal,
                out_mass[r],total,
                (cdf_mass/out_mass[r] if out_mass[r] else None),
                (cdf_mass/total if total else None),
                gt,ge,out_square[r],
            )
    return result
