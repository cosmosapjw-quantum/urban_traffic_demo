"""Active, two-speed mesoscopic cohort transport without individual-car loops.

Scientific core: Python stdlib. Mass is a nonnegative real vehicle-equivalent
measure, NOT integer vehicle identities. Route/class/residence-stage count is
bounded independently of demand magnitude. This is a kinetic delayed-queue
closure with link storage, not a claim of spatial LWR/CTM wave convergence.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import deque
import hashlib
import json
import math
from .kinetic_routes import k_shortest_paths, destination_potential

@dataclass(frozen=True, slots=True)
class MesoLink:
    key: str
    tail: str
    head: str
    length_m: float
    speed_mps: float
    capacity_vps: float
    storage_veh: float

@dataclass(frozen=True, slots=True)
class DriverGroup:
    name: str
    origin: str
    destination: str
    desired_speed_mps: float = 15.
    acceleration_rate: float = .2  # stopped -> moving, s^-1
    braking_rate: float = .03     # encounter strength, s^-1

@dataclass(frozen=True, slots=True)
class MesoConfig:
    dt: float = 1.
    route_every: int = 10
    cost_tau_s: float = 30.
    choice_tau_s: float = 60.
    temperature_s: float = 10.
    max_paths: int = 3
    max_state_values: int = 100000

@dataclass(frozen=True, slots=True)
class MesoState:
    tick: int
    stopped: tuple[tuple[float, ...], ...]
    moving: tuple[tuple[float, ...], ...]
    ready: tuple[float, ...]
    pending: tuple[float, ...]
    completed: tuple[float, ...]
    released: tuple[float, ...]
    shares: tuple[float, ...]
    perceived_costs: tuple[float, ...]
    route_admissions: tuple[float, ...]
    vehicle_seconds: float = 0.
    routing_updates: int = 0
    candidate_regret_s: float = 0.


def collision_step(stopped, moving, alpha, beta, dt):
    """Exact frozen-density two-state gain/loss semigroup; mass conserved."""
    if not all(math.isfinite(x) and x>=0 for x in (stopped,moving,alpha,beta,dt)):
        raise ValueError('finite nonnegative masses, rates and time required')
    total=stopped+moving
    rate=alpha+beta
    if rate==0:return stopped,moving
    equilibrium=alpha*total/rate
    # Convex combination avoids subtracting two nearly equal large quantities.
    decay=math.exp(-rate*dt)
    new=moving*decay+equilibrium*(-math.expm1(-rate*dt))
    return max(0.,total-new),min(total,new)


def _proportional_allocate(requests, capacities):
    """Progressive proportional fill with shared sending/receiving constraints.

    Pareto-maximal (up to roundoff), NOT general maximum-total-throughput flow.
    All feasible nonempty movements receive a positive share; no ID tie priority.
    """
    left=list(capacities);flow=[0.]*len(requests)
    active={i for i,(d,res) in enumerate(requests) if d>1e-12 and all(left[r]>1e-12 for r in res)}
    for _ in range(len(requests)+len(capacities)+2):
        if not active:return flow,left
        use={}
        for i in active:
            d,res=requests[i]
            for r in res:use[r]=use.get(r,0.)+d
        delta=min([(requests[i][0]-flow[i])/requests[i][0] for i in active]+
                  [left[r]/weight for r,weight in use.items()])
        if delta<0:raise ArithmeticError('negative resource allocation')
        for i in active:flow[i]+=delta*requests[i][0]
        for r,weight in use.items():left[r]=max(0.,left[r]-delta*weight)
        active={i for i in active if requests[i][0]-flow[i]>1e-12 and all(left[r]>1e-12 for r in requests[i][1])}
    raise ArithmeticError('progressive filling failed to terminate')


def _allocate(requests, capacities, *, split=None):
    """Proportional warm start, then aggregate residual max-flow when coupled.

    Sending resources precede ``split``, receiving resources follow it. Every
    augment sends a real aggregate amount, never one vehicle/token at a time.
    Maximal throughput has priority; proportional fairness is not guaranteed
    when it conflicts with the maximum. No general starvation theorem is claimed.
    """
    flow,left=_proportional_allocate(requests,capacities)
    if split is None or all(d-f<=1e-12 for (d,_),f in zip(requests,flow)):
        return flow,left
    active=[i for i,(d,_) in enumerate(requests) if d>1e-12]
    used=sorted({r for i in active for r in requests[i][1]})
    if not any(r<split and left[r]>1e-12 for r in used):return flow,left
    n=len(capacities);source=n;sink=n+1;adj=[[] for _ in range(n+2)]
    def add(u,v,cap,current=0.):
        position=len(adj[u])
        adj[u].append([v,len(adj[v]),max(0.,cap-current)])
        adj[v].append([u,position,current])
        return u,position
    for r in used:
        consumed=capacities[r]-left[r]
        add(source,r,capacities[r],consumed) if r<split else add(r,sink,capacities[r],consumed)
    positions={}
    for i in active:
        d,res=requests[i]
        if len(res)==1 and res[0]<split:u,v=res[0],sink
        elif len(res)==2 and res[0]<split<=res[1]:u,v=res
        else:raise ValueError('node request is not sending/receiving bipartite')
        positions[i]=add(u,v,d,flow[i])
    # Edmonds-Karp: iteration count depends on graph dimensions, not car count.
    budget=(n+2)*max(1,sum(map(len,adj)))
    for _ in range(budget):
        prev={source:None};queue=deque([source])
        while queue and sink not in prev:
            u=queue.popleft()
            for j,(v,_,capacity) in enumerate(adj[u]):
                if capacity>1e-12 and v not in prev:
                    prev[v]=(u,j);queue.append(v)
                    if v==sink:break
        if sink not in prev:break
        amount=math.inf;v=sink
        while v!=source:
            u,j=prev[v];amount=min(amount,adj[u][j][2]);v=u
        v=sink
        while v!=source:
            u,j=prev[v];edge=adj[u][j]
            edge[2]-=amount;adj[v][edge[1]][2]+=amount;v=u
    else:raise ArithmeticError('aggregate max-flow budget exhausted')
    for i,(u,j) in positions.items():flow[i]=max(0.,requests[i][0]-adj[u][j][2])
    left=list(capacities)
    for amount,(_,resources) in zip(flow,requests):
        for r in resources:left[r]-=amount
    if min(left,default=0.) < -1e-8:raise ArithmeticError('aggregate node resource violation')
    return flow,[max(0.,value) for value in left]


class ActiveMeso:
    """Compiled route cohorts. Arrival vectors have one aggregate mass per group."""
    def __init__(self, links, groups, config=None):
        self.links=tuple(links);self.groups=tuple(groups);self.config=config or MesoConfig()
        c=self.config
        if (not self.links or not self.groups or not isinstance(c.route_every,int)
            or c.route_every<1 or not isinstance(c.max_state_values,int) or c.max_state_values<1
            or not all(math.isfinite(v) and v>0 for v in (c.dt,c.cost_tau_s,c.choice_tau_s,c.temperature_s))):
            raise ValueError('invalid mesoscopic configuration')
        if len({e.key for e in self.links})!=len(self.links):raise ValueError('duplicate edge key')
        if len({g.name for g in self.groups})!=len(self.groups):raise ValueError('duplicate driver group')
        for e in self.links:
            if e.tail==e.head or not all(math.isfinite(x) and x>0 for x in (e.length_m,e.speed_mps,e.capacity_vps,e.storage_veh)):
                raise ValueError('invalid link geometry/capacity/storage')
        # A route = (group index, edge indices, leg indices). Leg = (group, edge, stages, next leg).
        routes=[];legs=[];by_group=[]
        for gi,g in enumerate(self.groups):
            if (g.origin==g.destination or g.acceleration_rate<=0 or g.braking_rate<0
                or g.desired_speed_mps<=0 or not all(math.isfinite(x) for x in
                    (g.acceleration_rate,g.braking_rate,g.desired_speed_mps))):
                raise ValueError('invalid driver cohort')
            arcs=tuple((e.tail,e.head,e.length_m/min(e.speed_mps,g.desired_speed_mps)) for e in self.links)
            paths=k_shortest_paths(arcs,g.origin,g.destination,c.max_paths)
            if not paths:raise ValueError('unreachable cohort destination')
            ids=[]
            for path in paths:
                ids.append(len(routes));start=len(legs)
                for j,ei in enumerate(path):
                    e=self.links[ei];h=max(1,math.ceil(e.length_m/(min(e.speed_mps,g.desired_speed_mps)*c.dt)))
                    legs.append((gi,ei,h,start+j+1 if j+1<len(path) else -1))
                routes.append((gi,path,tuple(range(start,len(legs)))))
            by_group.append(tuple(ids))
        self.routes=tuple(routes);self.legs=tuple(legs);self.by_group=tuple(by_group)
        self.state_values=2*sum(x[2] for x in legs)+len(legs)+3*len(groups)+3*len(routes)+5
        if self.state_values>c.max_state_values:raise ValueError('compiled state budget exceeded')

    def initial_state(self):
        arrays=tuple((0.,)*h for _,_,h,_ in self.legs)
        shares=tuple(1/len(self.by_group[gi]) for gi,_,_ in self.routes)
        costs=tuple(sum(self.legs[j][2]*self.config.dt for j in ids) for _,_,ids in self.routes)
        z=(0.,)*len(self.groups)
        return MesoState(0,arrays,arrays,(0.,)*len(self.legs),z,z,z,shares,costs,(0.,)*len(self.routes))

    def _masses(self,s):
        transit=[0.]*len(self.links);ready=[0.]*len(self.links)
        for j,(_,e,_,_) in enumerate(self.legs):
            transit[e]+=math.fsum(s.stopped[j])+math.fsum(s.moving[j]);ready[e]+=s.ready[j]
        return transit,ready

    def _beta(self,group,ei,transit):
        fraction=min(1.,max(0.,transit[ei]/self.links[ei].storage_veh))
        return self.groups[group].braking_rate*fraction/max(.05,1-fraction)

    def step(self, state, arrivals=None, *, capacity_scale=None, green=None):
        """Collision -> cohort progress -> constrained node flux -> source admission.

        Routes are committed at admission. Existing mass never changes road or
        route when guidance is refreshed. All receiving space is pre-step space.
        Signal controls exit service; physical closures also prohibit new entry.
        """
        s=state;c=self.config;E=len(self.links)
        arrivals=(0.,)*len(self.groups) if arrivals is None else tuple(arrivals)
        if len(arrivals)!=len(self.groups) or not all(math.isfinite(x) and x>=0 for x in arrivals):
            raise ValueError('arrival vector must contain one nonnegative finite mass per group')
        controls={} if capacity_scale is None else capacity_scale
        signals={} if green is None else green
        keys={e.key for e in self.links}
        if not set(controls)<=keys or not set(signals)<=keys:raise ValueError('unknown controlled edge')
        scales=[float(controls.get(e.key,1.)) for e in self.links]
        if not all(math.isfinite(x) and 0<=x<=1 for x in scales):raise ValueError('capacity scales must be [0,1]')
        transit,qready=self._masses(s);occupancy=[a+b for a,b in zip(transit,qready)]
        recv=[min(e.capacity_vps*scales[i]*c.dt,max(0.,e.storage_veh-occupancy[i])) for i,e in enumerate(self.links)]
        sending=[e.capacity_vps*scales[i]*c.dt*bool(signals.get(e.key,True)) for i,e in enumerate(self.links)]
        shares=list(s.shares);perceived=list(s.perceived_costs);regret=s.candidate_regret_s
        updates=s.routing_updates
        viable=[all(scales[e]>0 for e in path) for _,path,_ in self.routes]
        if s.tick%c.route_every==0:
            updates+=1;regret=0.
            smoothing=-math.expm1(-c.route_every*c.dt/c.cost_tau_s)
            relaxation=-math.expm1(-c.route_every*c.dt/c.choice_tau_s)
            for gi,g in enumerate(self.groups):
                costs=[]
                for ei,e in enumerate(self.links):
                    h=max(1,math.ceil(e.length_m/(min(e.speed_mps,g.desired_speed_mps)*c.dt)))
                    base=h*c.dt*(1+self._beta(gi,ei,transit)/g.acceleration_rate)
                    delay=qready[ei]/(e.capacity_vps*scales[ei]) if scales[ei]>0 else 1e9
                    costs.append(base+delay)
                arcs=tuple((e.tail,e.head,costs[i] if scales[i]>0 else math.inf) for i,e in enumerate(self.links))
                phi=destination_potential(arcs,g.destination).get(g.origin,math.inf)
                ids=self.by_group[gi];raw={r:sum(costs[e] for e in self.routes[r][1]) for r in ids}
                feasible=[r for r in ids if viable[r]]
                if feasible and math.isfinite(phi):regret=max(regret,max(0.,min(raw[r] for r in feasible)-phi))
                elif math.isfinite(phi):regret=1e9  # Globally reachable but fixed pool missed all routes.
                # Unavailability is a feasibility constraint, not a travel-time sample.
                # Freeze memory while closed; otherwise reopening inherits years of
                # fictitious delay from a numerical infinity sentinel.
                for r in feasible:perceived[r]+=smoothing*(raw[r]-perceived[r])
                if feasible:
                    best=min(perceived[r] for r in feasible)
                    weights={r:math.exp(-(perceived[r]-best)/c.temperature_s) for r in feasible}
                    total=sum(weights.values());old=sum(shares[r] for r in feasible)
                    for r in ids:
                        target=weights.get(r,0.)/total
                        prior=shares[r]/old if old>0 and r in feasible else target
                        shares[r]=(1-relaxation)*prior+relaxation*target if r in feasible else 0.
                # If all candidate paths are closed: pending is retained, no fake route.
        stopped=[];moving=[];ready=list(s.ready)
        for j,(gi,ei,h,_) in enumerate(self.legs):
            ns=[0.]*h;nm=[0.]*h
            beta=self._beta(gi,ei,transit);alpha=self.groups[gi].acceleration_rate
            for k in range(h):
                a,b=collision_step(s.stopped[j][k],s.moving[j][k],alpha,beta,c.dt)
                ns[k]=a
                if k+1<h:nm[k+1]+=b
                else:ready[j]+=b
            stopped.append(ns);moving.append(nm)
        requests=[]
        for j,(_,ei,_,nextj) in enumerate(self.legs):
            resources=(ei,) if nextj<0 else (ei,E+self.legs[nextj][1])
            requests.append((ready[j],resources))
        flux,remaining=_allocate(requests,sending+recv,split=E)
        completed=list(s.completed)
        for j,amount in enumerate(flux):
            gi,_,_,nextj=self.legs[j];ready[j]=max(0.,ready[j]-amount)
            if nextj<0:completed[gi]+=amount
            else:moving[nextj][0]+=amount
        pending=[a+b for a,b in zip(s.pending,arrivals)]
        injection=[]
        for r,(gi,path,_) in enumerate(self.routes):
            total=sum(shares[x] for x in self.by_group[gi] if viable[x])
            demand=pending[gi]*shares[r]/total if viable[r] and total>0 else 0.
            injection.append((demand,(E+path[0],)))
        inflow,_=_allocate(injection,remaining)
        admitted=list(s.route_admissions)
        for r,amount in enumerate(inflow):
            gi,_,ids=self.routes[r];pending[gi]=max(0.,pending[gi]-amount)
            moving[ids[0]][0]+=amount;admitted[r]+=amount
        released=tuple(a+b for a,b in zip(s.released,arrivals))
        result=MesoState(s.tick+1,tuple(map(tuple,stopped)),tuple(map(tuple,moving)),tuple(ready),
            tuple(pending),tuple(completed),released,tuple(shares),tuple(perceived),tuple(admitted),
            s.vehicle_seconds+(sum(occupancy)+sum(s.pending)+sum(arrivals))*c.dt,updates,regret)
        diag=self.diagnostics(result)
        if diag['max_storage_excess']>1e-7 or abs(diag['mass_error'])>1e-7 or diag['max_group_mass_error']>1e-7:
            raise ArithmeticError('mass/storage invariant violated')
        return result

    def diagnostics(self,s):
        transit,ready=self._masses(s);occupancy=[a+b for a,b in zip(transit,ready)]
        group_active=[0.]*len(self.groups)
        for j,(g,_,_,_) in enumerate(self.legs):
            group_active[g]+=sum(s.stopped[j])+sum(s.moving[j])+s.ready[j]
        error=[s.released[g]-s.pending[g]-s.completed[g]-group_active[g] for g in range(len(self.groups))]
        return dict(tick=s.tick,time_s=s.tick*self.config.dt,released=sum(s.released),active=sum(occupancy),
            pending=sum(s.pending),completed=sum(s.completed),mass_error=sum(error),
            max_group_mass_error=max(map(abs,error)),
            occupancy=tuple(occupancy),ready=tuple(ready),moving=sum(map(sum,s.moving)),
            stopped=sum(map(sum,s.stopped))+sum(s.ready),
            max_storage_excess=max(0.,max(n-e.storage_veh for n,e in zip(occupancy,self.links))),
            shares=s.shares,route_admissions=s.route_admissions,vehicle_seconds=s.vehicle_seconds,
            candidate_regret_s=s.candidate_regret_s,state_values=self.state_values)

    def fingerprint(self,s):
        payload={'contract':'active_meso_two_speed_cohorts_v1','links':[asdict(x) for x in self.links],
                 'groups':[asdict(x) for x in self.groups],'config':asdict(self.config),'state':asdict(s)}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
