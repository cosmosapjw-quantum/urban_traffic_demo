"""Population stocks -> entropy-balanced person trips -> vehicle demand."""
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class Balance:
    matrix: tuple[tuple[float,...],...]
    iterations: int
    max_margin_error: float

class DemandInfeasible(ValueError): pass

import math
import heapq
from .landuse import City
from ..active_suffix.node import allocate
from ..active_suffix.common import Demand


def balance_od(origins,destinations,costs_s,tau_s=900.,tolerance=1e-9,max_iter=1000):
    """IPF with an independent support-feasibility max-flow before iteration.

    Minimize sum T_ij(log(T_ij/K_ij)-1), K=exp(-cost/tau), under BOTH
    margins and structural zeros. Costs are frozen planning skims, not a dynamic
    user equilibrium or a claim of independent drivers' physical entropy.
    """
    nr,nc=len(origins),len(destinations)
    if (not nr or not nc or len(costs_s)!=nr or any(len(r)!=nc for r in costs_s)
        or not math.isfinite(tau_s) or tau_s<=0 or not math.isfinite(tolerance)
        or tolerance<=0 or not isinstance(max_iter,int) or isinstance(max_iter,bool) or max_iter<1):
        raise ValueError('invalid balancing dimensions/scales')
    if any(not math.isfinite(v) or v<0 for v in tuple(origins)+tuple(destinations)):
        raise ValueError('invalid nonnegative person margins')
    if any(math.isnan(v) or v<0 for row in costs_s for v in row):
        raise ValueError('costs must be nonnegative seconds; infinity is unreachable')
    total=math.fsum(origins);other=math.fsum(destinations)
    if abs(total-other)>1e-12*max(1.,total,other):
        raise DemandInfeasible('workers and assigned jobs do not balance')
    if total==0:return Balance(tuple((0.,)*nc for _ in range(nr)),0,0.)
    rows=[v/total for v in origins];cols=[v/total for v in destinations]
    support={(i,j):1. for i in range(nr) for j in range(nc)
             if rows[i]>0 and cols[j]>0 and math.isfinite(costs_s[i][j])}
    feasible=allocate(support,dict(enumerate(rows)),dict(enumerate(cols)))
    if math.fsum(feasible.values()) < 1.-1e-10:
        raise DemandInfeasible('unreachable or capacity-infeasible worker/job support')
    matrix=[[0.]*nc for _ in range(nr)]
    for i in range(nr):
        js=[j for j in range(nc) if (i,j) in support]
        if not js:continue
        offset=min(costs_s[i][j] for j in js)
        for j in js:
            exponent=(costs_s[i][j]-offset)/tau_s
            if exponent>700:raise ValueError('kernel dynamic range requires log-domain balancing')
            matrix[i][j]=math.exp(-exponent)
    for iteration in range(1,max_iter+1):
        for i in range(nr):
            value=math.fsum(matrix[i])
            if rows[i]>0 and value<=0:raise ArithmeticError('lost row support')
            scale=rows[i]/value if value else 0.
            matrix[i]=[v*scale for v in matrix[i]]
        for j in range(nc):
            value=math.fsum(matrix[i][j] for i in range(nr))
            if cols[j]>0 and value<=0:raise ArithmeticError('lost column support')
            scale=cols[j]/value if value else 0.
            for i in range(nr):matrix[i][j]*=scale
        error=max([abs(math.fsum(matrix[i])-rows[i]) for i in range(nr)]+
                  [abs(math.fsum(matrix[i][j] for i in range(nr))-cols[j]) for j in range(nc)])
        if error<=tolerance:
            return Balance(tuple(tuple(v*total for v in row) for row in matrix),iteration,error*total)
    raise RuntimeError(f'IPF did not converge in {max_iter} iterations; normalized residual={error}')


@dataclass(frozen=True,slots=True)
class District:
    id: str
    access_node: str
    residents: int
    jobs: int
    service_places: int
    zone_ids: tuple[str,...]


def districts(city: City, divisions=4) -> tuple[District,...]:
    """Spatial AND bank/component grouping. No cross-river centroid teleportation.

    The representative is an existing access node nearest a weighted centre.
    Within-district access distances remain unresolved and are not called zero.
    """
    if not isinstance(divisions,int) or isinstance(divisions,bool) or divisions<1:
        raise ValueError('invalid district divisions')
    extent=city.terrain.n*city.terrain.spacing_m
    coords={n.id:(n.x_m,n.y_m) for n in city.network.nodes}
    components=dict(city.network.components);groups={}
    for z in city.zones:
        if z.access_node is None or z.residents+z.jobs==0:continue
        bank=tuple(-1 if z.x_m<r.xmin else 1 if z.x_m>r.xmax else 0 for r in city.terrain.water)
        key=(int(z.x_m/extent*divisions),int(z.y_m/extent*divisions),components[z.access_node],bank)
        groups.setdefault(key,[]).append(z)
    result=[]
    for k,zs in sorted(groups.items()):
        weight=sum(z.residents+z.jobs for z in zs)
        x=sum(z.x_m*(z.residents+z.jobs) for z in zs)/weight
        y=sum(z.y_m*(z.residents+z.jobs) for z in zs)/weight
        access=min({z.access_node for z in zs},key=lambda v:(math.dist(coords[v],(x,y)),v))
        result.append(District(str(k),access,sum(z.residents for z in zs),sum(z.jobs for z in zs),
                               sum(z.service_capacity for z in zs),tuple(z.id for z in zs)))
    if sum(d.residents for d in result)!=city.population or sum(d.jobs for d in result)!=city.jobs:
        raise ArithmeticError('district aggregation lost urban stock')
    return tuple(result)


def travel_skims(roads,areas,allowed_turns=None):
    """Frozen planning costs, with optional incoming-link turn authority.

    None retains the original node-Dijkstra path. An explicit turn set (including
    the empty set) uses exactly the legal link-state graph used by transport.
    The 120 s diagonal is an intrazonal deterrence prior, NOT a completed trip.
    """
    roads=tuple(roads)
    if allowed_turns is not None:
        from ..active_suffix.routing import Arc, destination_potential
        arcs=tuple(Arc(r.id,r.tail,r.head) for r in roads)
        costs={r.id:(r.length_m/r.free_speed_mps+
            (r.signal.cycle_s-r.signal.green_s)**2/(2*r.signal.cycle_s) if r.signal else
            r.length_m/r.free_speed_mps) for r in roads}
        for r in roads:
            if r.signal and r.signal.green_s==0:costs[r.id]=math.inf
        tables={d:destination_potential(arcs,costs,d,allowed_turns)
                for d in sorted({a.access_node for a in areas})}
        outgoing={a.access_node:tuple(r.id for r in roads if r.tail==a.access_node) for a in areas}
        return tuple(tuple(120. if i==j else 0. if a.access_node==b.access_node else
            min((tables[b.access_node][key] for key in outgoing[a.access_node]),default=math.inf)
            for j,b in enumerate(areas)) for i,a in enumerate(areas))
    adj={}
    for r in roads:
        red=(r.signal.cycle_s-r.signal.green_s)**2/(2*r.signal.cycle_s) if r.signal else 0.
        cost=r.length_m/r.free_speed_mps+red
        if r.signal and r.signal.green_s==0:continue
        adj.setdefault(r.tail,[]).append((r.head,cost))
    tables={}
    for origin in sorted({d.access_node for d in areas}):
        dist={origin:0.};queue=[(0.,origin)]
        while queue:
            v,u=heapq.heappop(queue)
            if v!=dist[u]:continue
            for dest,w in adj.get(u,()):
                value=v+w
                if value<dist.get(dest,math.inf):dist[dest]=value;heapq.heappush(queue,(value,dest))
        tables[origin]=dist
    # Finite intrazonal deterrence is a prior, NOT a simulated intrazonal time.
    return tuple(tuple(120. if i==j else tables[a.access_node].get(b.access_node,math.inf)
                       for j,b in enumerate(areas)) for i,a in enumerate(areas))


@dataclass(frozen=True,slots=True)
class TripPlan:
    areas: tuple[District,...]
    assignments: tuple[tuple[float,...],...]
    demands: tuple[Demand,...]
    ledger: tuple[tuple[str,float],...]
    balance_iterations: int
    max_margin_error: float


def plan_commute(city,roads,divisions=4,worker_fraction=.4,peak_fraction=.4,
                 car_person_share=.55,persons_per_car=1.25,profile=((0.,1800.,.5),(1800.,3600.,.5)),
                 tau_s=900.,max_od_groups=256,allowed_turns=None):
    """Person stocks -> one-way peak trips -> non-car/local/network ledgers.

    Profile weights integrate to one; no returns or service visits are invented.
    Intrazonal/same-access-node vehicle trips are unresolved local trips, NOT
    traffic completed with zero travel time. Non-car modes are not simulated.
    """
    for value in (worker_fraction,peak_fraction,car_person_share):
        if not math.isfinite(value) or not 0<=value<=1:raise ValueError('invalid participation/share')
    if not math.isfinite(persons_per_car) or persons_per_car<1:raise ValueError('invalid occupancy')
    if not profile or any(not all(map(math.isfinite,(a,b,w))) or a<0 or b<=a or w<0 for a,b,w in profile):
        raise ValueError('invalid departure profile')
    if abs(math.fsum(w for _,_,w in profile)-1)>1e-12:raise ValueError('profile weights must sum to one')
    ordered=sorted(profile)
    if any(b>c for (a,b,w),(c,d,v) in zip(ordered,ordered[1:])):raise ValueError('overlapping departure bins')
    areas=districts(city,divisions);costs=travel_skims(roads,areas,allowed_turns=allowed_turns)
    origins=tuple(d.residents*worker_fraction for d in areas);dest=tuple(float(d.jobs) for d in areas)
    result=balance_od(origins,dest,costs,tau_s=tau_s)
    factor=peak_fraction*car_person_share/persons_per_car;local=0.;od={}
    for i,a in enumerate(areas):
        for j,b in enumerate(areas):
            vehicles=result.matrix[i][j]*factor
            if i==j or a.access_node==b.access_node:local+=vehicles
            elif vehicles>0:
                key=(a.access_node,b.access_node);od[key]=od.get(key,0.)+vehicles
    if len(od)>max_od_groups:raise RuntimeError(f'OD budget {len(od)} > {max_od_groups}; no mass dropped')
    demands=tuple(Demand(a,b,start,end,amount*w/(end-start)) for (a,b),amount in sorted(od.items())
                  for start,end,w in ordered if w>0)
    workers=math.fsum(origins);persons=workers*peak_fraction
    network=math.fsum(od.values());vehicles=persons*car_person_share/persons_per_car
    ledger=dict(resident_stock=city.population,worker_stock=workers,job_stock=city.jobs,
        peak_person_trips=persons,noncar_person_trips=persons*(1-car_person_share),
        car_person_trips=persons*car_person_share,car_vehicle_trips=vehicles,
        unresolved_local_vehicle_trips=local,network_vehicle_trips=network,od_groups=len(od))
    if abs(network+local-vehicles)>1e-8*max(1.,vehicles):raise ArithmeticError('person/vehicle ledger')
    return TripPlan(areas,result.matrix,demands,tuple(sorted(ledger.items())),result.iterations,result.max_margin_error)
