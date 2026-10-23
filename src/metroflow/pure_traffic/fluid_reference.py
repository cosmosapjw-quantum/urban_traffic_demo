"""Stdlib finite-volume oracle; NOT the integer vehicle network solver.

Densities are veh/m (all lanes aggregated), speeds m/s, times s, fluxes veh/s.
A fixed pair of boundary reservoir states defines the finite-domain problem.
Exact comparisons require its Riemann waves not to reach the outer boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True, slots=True)
class FundamentalDiagram:
    free_speed_mps: float
    wave_speed_mps: float
    jam_density_veh_m: float
    capacity_veh_s: float | None = None

    def __post_init__(self) -> None:
        for value in (self.free_speed_mps, self.wave_speed_mps, self.jam_density_veh_m):
            if not math.isfinite(value) or value <= 0:
                raise ValueError('FD speeds and jam density must be finite and positive')
        if self.capacity_veh_s is not None and (
            not math.isfinite(self.capacity_veh_s)
            or not 0 < self.capacity_veh_s <= self.triangular_capacity
        ):
            raise ValueError('capacity must lie in (0, triangular capacity]')

    @property
    def critical_density(self) -> float:
        """Apex of the uncapped triangle, not a unique critical density if capped."""
        return self.wave_speed_mps * self.jam_density_veh_m / (self.free_speed_mps + self.wave_speed_mps)

    @property
    def triangular_capacity(self) -> float:
        return self.free_speed_mps * self.critical_density

    @property
    def capacity(self) -> float:
        return self.triangular_capacity if self.capacity_veh_s is None else self.capacity_veh_s

    def demand(self, density: float) -> float:
        return min(self.free_speed_mps * density, self.capacity)

    def supply(self, density: float) -> float:
        return min(self.capacity, self.wave_speed_mps * (self.jam_density_veh_m - density))

    def flow(self, density: float) -> float:
        return min(self.demand(density), self.supply(density))


def _check_density(fd: FundamentalDiagram, *values: float) -> None:
    if any(not math.isfinite(k) or not 0 <= k <= fd.jam_density_veh_m for k in values):
        raise ValueError('density must lie in [0, jam density]')


def exact_riemann_averages(
    fd: FundamentalDiagram, left: float, right: float,
    cell_edges_m: Sequence[float], time_s: float,
) -> tuple[float, ...]:
    """Exact cell integrals of a strict triangular-FD entropy solution at x0=0.

    Expansion across the apex consists of two contact discontinuities bounding
    a critical-density plateau, NOT the smooth fan of a quadratic LWR flux.
    """
    _check_density(fd, left, right)
    edges=tuple(cell_edges_m)
    if len(edges)<2 or any(not math.isfinite(x) for x in edges) or any(b<=a for a,b in zip(edges,edges[1:])):
        raise ValueError('cell edges must be finite and strictly increasing')
    if not math.isfinite(time_s) or time_s<0:
        raise ValueError('time must be finite and non-negative')
    if not math.isclose(fd.capacity,fd.triangular_capacity,rel_tol=1e-14):
        raise ValueError('exact oracle supports strict triangular FD only')
    kc=fd.critical_density
    if left == right:
        return (left,) * (len(edges)-1)
    if time_s == 0:
        cuts=(0.,); values=(left,right)
    elif left < right:
        shock=(fd.flow(right)-fd.flow(left))/(right-left)
        cuts=(shock*time_s,); values=(left,right)
    elif right < kc < left:
        cuts=(-fd.wave_speed_mps*time_s,fd.free_speed_mps*time_s)
        values=(left,kc,right)
    else:
        speed=fd.free_speed_mps if left<=kc else -fd.wave_speed_mps
        cuts=(speed*time_s,); values=(left,right)
    limits=(-math.inf,)+cuts+(math.inf,)
    return tuple(
        math.fsum(max(0.,min(b,hi)-max(a,lo))*value
                  for lo,hi,value in zip(limits,limits[1:],values)) / (b-a)
        for a,b in zip(edges,edges[1:])
    )


def exact_profile_l1(
    fd: FundamentalDiagram, left: float, right: float,
    cell_edges_m: Sequence[float], density_veh_m: Sequence[float], time_s: float,
) -> float:
    """Integral of |piecewise-constant numerical reconstruction - exact field|.

    Unlike comparing cell averages alone, this norm includes unavoidable
    subcell representation error when a discontinuity lies inside a cell.
    """
    if len(density_veh_m)+1 != len(cell_edges_m):
        raise ValueError('density/cell-edge shape mismatch')
    _check_density(fd, *density_veh_m)
    candidate_cuts=[-fd.wave_speed_mps*time_s, fd.free_speed_mps*time_s, 0.]
    if left != right:
        candidate_cuts.append((fd.flow(right)-fd.flow(left))/(right-left)*time_s)
    terms=[]
    for a,b,k in zip(cell_edges_m,cell_edges_m[1:],density_veh_m):
        subedges=(a,*sorted(set(x for x in candidate_cuts if a<x<b)),b)
        exact=exact_riemann_averages(fd,left,right,subedges,time_s)
        terms.extend(abs(k-e)*(hi-lo) for lo,hi,e in zip(subedges,subedges[1:],exact))
    return math.fsum(terms)


def solve_riemann(
    fd: FundamentalDiagram, left: float, right: float, time_s: float,
    *, n_cells: int=200, x_min_m: float=-2000., x_max_m: float=2000., cfl: float=.8,
) -> dict[str, object]:
    """First-order Godunov finite volume with a conservative boundary ledger."""
    _check_density(fd,left,right)
    if not math.isfinite(cfl) or not 0<cfl<=1:
        raise ValueError('CFL number must lie in (0,1]')
    if not isinstance(n_cells,int) or isinstance(n_cells,bool) or n_cells<2:
        raise ValueError('n_cells must be an integer >= 2')
    if not all(math.isfinite(x) for x in (x_min_m,x_max_m,time_s)) or not x_min_m<0<x_max_m or time_s<0:
        raise ValueError('finite domain must straddle zero and time must be non-negative')
    if x_min_m > -fd.wave_speed_mps*time_s or x_max_m < fd.free_speed_mps*time_s:
        raise ValueError('Riemann comparison waves must remain inside the domain')
    dx=(x_max_m-x_min_m)/n_cells
    edges=tuple(x_min_m+i*dx for i in range(n_cells+1))
    density=list(exact_riemann_averages(fd,left,right,edges,0.))
    mass0=math.fsum(density)*dx
    incoming=[]; outgoing=[]
    max_dt=cfl*dx/max(fd.free_speed_mps,fd.wave_speed_mps)
    time=0.; steps=0
    while time < time_s:
        dt=min(max_dt,time_s-time)
        extended=(left,*density,right)
        flux=[min(fd.demand(a),fd.supply(b)) for a,b in zip(extended,extended[1:])]
        density=[k+dt/dx*(flux[i]-flux[i+1]) for i,k in enumerate(density)]
        # Never silently clip a density or repair its mass.
        if any(not -1e-14<=k<=fd.jam_density_veh_m+1e-14 for k in density):
            raise RuntimeError('Godunov density bound failed')
        incoming.append(dt*flux[0]); outgoing.append(dt*flux[-1])
        time+=dt; steps+=1
    exact=exact_riemann_averages(fd,left,right,edges,time_s)
    return {
        'n_cells':n_cells,'dx_m':dx,'time_s':time_s,'steps':steps,
        'cell_centres_m':tuple((a+b)/2 for a,b in zip(edges,edges[1:])),
        'density_veh_m':tuple(density),'exact_density_veh_m':exact,
        'l1_error_vehicles':math.fsum(abs(a-b) for a,b in zip(density,exact))*dx,
        'l1_profile_error_vehicles':exact_profile_l1(fd,left,right,edges,density,time_s),
        'mass_balance_error_vehicles':math.fsum(density)*dx-mass0-math.fsum(incoming)+math.fsum(outgoing),
        'cumulative_inflow_vehicles':math.fsum(incoming),
        'cumulative_outflow_vehicles':math.fsum(outgoing),
    }
