"""Exact finite-horizon route-labelled second age-moment transport.

This is a *diagnostic* reference for raw original birth times b. The native
MetroFlow road checkpoint tracks mass and first birth-time moment only.
No physical variance can be inferred from those two variables alone.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Literal, Mapping, Sequence


@dataclass(frozen=True)
class QuadraticBoundaryEvent:
    clock: F
    route: int
    direction: Literal["in", "out"]
    mass: F
    first_birth_moment: F
    second_birth_moment: F


@dataclass(frozen=True)
class QuadraticRouteBalance:
    initial_age2: F
    entry_age2: F
    output_age2: F
    terminal_age2: F
    area_age: F
    final_mass: F
    final_birth1: F
    final_birth2: F
    output_age1: F
    output_mass: F
    output_mean: F | None
    output_variance: F | None
    age_variance: F | None
    realizability_gap: F


def _source_moment_valid(clock: F, mass: F, b1: F, b2: F) -> bool:
    """Necessary finite positive-mass birth-moment realizability conditions."""
    return (
        mass >= 0
        and (mass != 0 or (b1 == 0 and b2 == 0))
        and (mass == 0 or (b1 <= clock * mass and mass * b2 >= b1 * b1))
    )


def finite_second_residence_balance(
    t0: F,
    horizon: F,
    initial: Mapping[int, tuple[F, F, F]],
    events: Sequence[QuadraticBoundaryEvent],
) -> dict[int, QuadraticRouteBalance]:
    """Compute D2_out=2∫A dt+D2_in+Q(t0)−Q(T) by exact Fraction arithmetic.

    Source events are ordered by time. Simultaneous events are grouped so no
    fictitious negative intermediate stock is induced by arbitrary list order.
    All units of second-moment quantities are mass*second**2.
    """
    t0, horizon = F(t0), F(horizon)
    if horizon < t0:
        raise ValueError("negative finite physical horizon")
    route_set=set(initial)|{event.route for event in events}
    N={r:F(initial.get(r,(0,0,0))[0]) for r in route_set}
    H={r:F(initial.get(r,(0,0,0))[1]) for r in route_set}
    J={r:F(initial.get(r,(0,0,0))[2]) for r in route_set}
    for r in route_set:
        if not _source_moment_valid(t0,N[r],H[r],J[r]):
            raise ValueError("initial route mass/birth quadratic moments not realizable")
    initial_q={r:t0*t0*N[r]-2*t0*H[r]+J[r] for r in route_set}
    area={r:F(0) for r in route_set}
    in2={r:F(0) for r in route_set}
    out2={r:F(0) for r in route_set}
    out1={r:F(0) for r in route_set}
    out_m={r:F(0) for r in route_set}
    last=t0
    i=0
    while i<len(events):
        t=F(events[i].clock)
        if t<last or t>horizon:
            raise ValueError("quadratic source boundary events out of order/time")
        # Exact integral of t N - H on [last,t] with constant N,H.
        for r in route_set:
            area[r]+=N[r]*(t*t-last*last)/2-H[r]*(t-last)
        delta_n:dict[int,F]={}
        delta_h:dict[int,F]={}
        delta_j:dict[int,F]={}
        while i<len(events) and F(events[i].clock)==t:
            event=events[i]
            mass,b1,b2=(F(event.mass),F(event.first_birth_moment),
                          F(event.second_birth_moment))
            if not _source_moment_valid(t,mass,b1,b2):
                raise ValueError("invalid original birth quadratic boundary measure")
            if event.direction not in ("in","out"):
                raise ValueError("invalid route boundary direction")
            sign=F(1) if event.direction=="in" else F(-1)
            delta_n[event.route]=delta_n.get(event.route,F(0))+sign*mass
            delta_h[event.route]=delta_h.get(event.route,F(0))+sign*b1
            delta_j[event.route]=delta_j.get(event.route,F(0))+sign*b2
            age2=t*t*mass-2*t*b1+b2
            if sign>0:
                in2[event.route]+=age2
            else:
                out2[event.route]+=age2
                out1[event.route]+=t*mass-b1
                out_m[event.route]+=mass
            i+=1
        for r in delta_n:
            N[r]+=delta_n[r]
            H[r]+=delta_h[r]
            J[r]+=delta_j[r]
            if not _source_moment_valid(t,N[r],H[r],J[r]):
                raise ValueError("post-boundary quadratic source stock invalid")
        last=t
    result={}
    for r in sorted(route_set):
        area[r]+=N[r]*(horizon*horizon-last*last)/2-H[r]*(horizon-last)
        q=horizon*horizon*N[r]-2*horizon*H[r]+J[r]
        if out2[r]!=2*area[r]+in2[r]+initial_q[r]-q:
            raise ArithmeticError("route quadratic transport conservation failed")
        if out_m[r]>0:
            mu=out1[r]/out_m[r]
            sigma2=out2[r]/out_m[r]-mu*mu
            if sigma2<0:
                raise ArithmeticError("negative departed duration variance")
        else:
            mu=sigma2=None
        if N[r]>0:
            age_mean=horizon-H[r]/N[r]
            age_sigma2=q/N[r]-age_mean*age_mean
            gap=N[r]*q-(horizon*N[r]-H[r])**2
            if gap<0 or age_sigma2<0:
                raise ArithmeticError("negative resident age variance")
        else:
            age_sigma2=None
            gap=F(0)
        result[r]=QuadraticRouteBalance(
            initial_q[r],in2[r],out2[r],q,area[r],
            N[r],H[r],J[r],out1[r],out_m[r],mu,sigma2,age_sigma2,gap,
        )
    return result
