"""Opt-in route-preserving KCMB finite-volume network, research variant.

No dynamic route switching, geometric conflict inference, strict temporal FIFO
or validated production V03 replacement. Each route is an immutable commodity;
its 6 kinetic moments are carried to the next link without relabelling.

The two turning policies are deliberately distinct:
 * shared_head: fixed proportional route mixture within one shared lane pool;
   one red/blocked movement stops ALL routes of that pool (partial FIFO closure).
 * independent_turn: each movement has an independent turning pocket; blocked
   route does not block others. It requires actual lanes to justify the choice.
Both have finite static 6 * n_links * n_routes + 3 * n_routes state slots.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .kcmb import KCMBClass, _finite, _micro_point, _kinetic_transition, _validate_class_moments


_FIELDS = 6
_VERSION = "kcmb_network_link_pool_v1"


@dataclass(frozen=True, slots=True)
class KCMBLink:
    name: str
    tail: str
    head: str
    length_m: float
    lanes: int
    capacity_veh_per_s: float
    backward_wave_mps: float
    priority: float = 1.

    def __post_init__(self) -> None:
        if (not all(isinstance(s,str) and s for s in (self.name,self.tail,self.head))
                or self.tail==self.head or
                isinstance(self.lanes,bool) or not isinstance(self.lanes,int) or self.lanes<1):
            raise ValueError("valid named directed link and positive lanes required")
        for key in ("length_m","capacity_veh_per_s","backward_wave_mps","priority"):
            v=_finite(getattr(self,key),key)
            if v<=0:
                raise ValueError(f"positive link {key} required")
            object.__setattr__(self,key,v)
        if not math.isfinite(self.length_m*self.lanes):
            raise ValueError("nonfinite physical lane storage")


@dataclass(frozen=True, slots=True)
class KCMBRoute:
    name: str
    vehicle: KCMBClass
    path: tuple[str,...]

    def __post_init__(self) -> None:
        if (not isinstance(self.name,str) or not self.name or
                not isinstance(self.vehicle,KCMBClass) or
                not isinstance(self.path,tuple) or len(self.path)<1 or
                not all(isinstance(x,str) and x for x in self.path)):
            raise ValueError("named class and nonempty tuple route required")
        if len(set(self.path))!=len(self.path):
            raise ValueError("repeated route link is ambiguous without a stage index")


@dataclass(frozen=True, slots=True)
class KCMBNetworkConfig:
    links: tuple[KCMBLink,...]
    routes: tuple[KCMBRoute,...]
    dt_s: float
    lane_policy: str = "shared_head"

    def __post_init__(self) -> None:
        if not isinstance(self.links,tuple) or not isinstance(self.routes,tuple):
            raise ValueError("immutable links/routes tuple required")
        if not self.links or not self.routes or len(self.routes)>64:
            raise ValueError("bounded nonempty links/routes required")
        if (any(not isinstance(x,KCMBLink) for x in self.links) or
                any(not isinstance(x,KCMBRoute) for x in self.routes) or
                len({x.name for x in self.links})!=len(self.links) or
                len({x.name for x in self.routes})!=len(self.routes)):
            raise ValueError("duplicate or malformed network links/routes")
        if self.lane_policy not in ("shared_head","independent_turn"):
            raise ValueError("explicit lane_policy required")
        dt=_finite(self.dt_s,"dt_s")
        if dt<=0:
            raise ValueError("positive dt required")
        object.__setattr__(self,"dt_s",dt)
        index={x.name:x for x in self.links}
        for r in self.routes:
            if any(link not in index for link in r.path):
                raise ValueError("route references unknown link")
            if any(index[a].head!=index[b].tail for a,b in zip(r.path,r.path[1:])):
                raise ValueError("route must be physically contiguous")
        for l in self.links:
            applicable=[r.vehicle.vmax_mps for r in self.routes if l.name in r.path]
            if applicable and dt*max(l.backward_wave_mps,*applicable)>l.length_m:
                raise ValueError("kinetic network CFL violation")
        if 6*len(self.links)*len(self.routes)+3*len(self.routes)>2_000_000:
            raise ValueError("bounded fixed network state budget exceeded")


@dataclass(frozen=True, slots=True)
class KCMBNetworkState:
    model_id: str
    tick: int
    moments: tuple[float,...]
    pending: tuple[float,...]
    released: tuple[float,...]
    completed: tuple[float,...]


def progressive_junction(
        groups: tuple[tuple[tuple[int,int|None,float,float],...],...],
        *,receive_count: Mapping[int,float],
        receive_metres: Mapping[int,float],
        weights: Sequence[float],
        theta_limits: Sequence[float] | None = None,
        ) -> dict[tuple[int,int],float]:
    """Deterministic weighted progressive filling for fixed turn mixtures.

    group item = (route index, destination link or None, demand [veh],
                  footprint [m/veh]).
    Each group shares one theta (0..limit), with flows x_ge=theta_g*d_ge.
    Sink destination None has no receiver constraint. Allocator maximizes
    all active group fractions progressively; this is NOT a max-throughput
    solver, nor a proof of invariant node entropy solution.
    """
    count=len(groups)
    if len(weights)!=count or (theta_limits is not None and len(theta_limits)!=count):
        raise ValueError("node groups/weights/limit mismatch")
    limits=tuple(theta_limits) if theta_limits is not None else (1.,)*count
    receivers=set(receive_count)
    if receivers!=set(receive_metres):
        raise ValueError("node resource keys do not match")
    for j in receivers:
        if (not isinstance(j,int) or isinstance(j,bool)
            or not math.isfinite(receive_count[j]) or receive_count[j]<0
            or not math.isfinite(receive_metres[j]) or receive_metres[j]<0):
            raise ValueError("invalid receiving resource")
    for g,weight,limit in zip(groups,weights,limits):
        if (not math.isfinite(weight) or weight<=0
            or not math.isfinite(limit) or not 0<=limit<=1):
            raise ValueError("invalid node priority/limit")
        for route,j,d,f in g:
            if (not isinstance(route,int) or route<0 or
                (j is not None and j not in receivers) or
                not math.isfinite(d) or d<0 or
                not math.isfinite(f) or f<=0):
                raise ValueError("invalid node movement")
    if not count:
        return {}
    used_count={j:0. for j in receivers}
    used_m={j:0. for j in receivers}
    # One group consumes a fixed amount per unit theta at each receiving link.
    count_coeff=[]
    metre_coeff=[]
    for g in groups:
        q={j:0. for j in receivers}
        b={j:0. for j in receivers}
        for _,j,d,f in g:
            if j is not None:
                q[j]+=d
                b[j]+=d*f
        count_coeff.append(q)
        metre_coeff.append(b)
    theta=[0.]*count
    for _ in range(count+2*len(receivers)+2):
        active=[]
        for g in range(count):
            if theta[g]>=limits[g]-1e-13:
                continue
            if not any(row[2]>0 for row in groups[g]):
                continue
            # Shared head freezes when *any* of its destinations is blocked.
            blocked=any((count_coeff[g][j]>0 and
                              used_count[j]>=receive_count[j]-1e-12)
                        or (metre_coeff[g][j]>0 and
                              used_m[j]>=receive_metres[j]-1e-12)
                        for j in receivers)
            if not blocked:
                active.append(g)
        if not active:
            break
        steps=[(limits[g]-theta[g])/weights[g] for g in active]
        for j in receivers:
            denom=math.fsum(weights[g]*count_coeff[g][j] for g in active)
            if denom>0:
                steps.append(max(0.,receive_count[j]-used_count[j])/denom)
            denom=math.fsum(weights[g]*metre_coeff[g][j] for g in active)
            if denom>0:
                steps.append(max(0.,receive_metres[j]-used_m[j])/denom)
        step=min(steps)
        if step<=1e-14:
            break
        for g in active:
            theta[g]=min(limits[g],theta[g]+step*weights[g])
        for j in receivers:
            used_count[j]=math.fsum(theta[g]*count_coeff[g][j] for g in range(count))
            used_m[j]=math.fsum(theta[g]*metre_coeff[g][j] for g in range(count))
            if used_count[j]>receive_count[j]+1e-8 or used_m[j]>receive_metres[j]+1e-8:
                raise ArithmeticError("junction received more than available capacity")
    else:
        raise ArithmeticError("junction progressive filling iteration budget")
    return {(g,i):theta[g]*row[2]
            for g,group in enumerate(groups) for i,row in enumerate(group)}


class KCMBBoundedNetwork:
    """Opt-in finite-dimensional route-cohort model. Route order is not resolved."""

    def __init__(self,config:KCMBNetworkConfig,*,backend="python"):
        if not isinstance(config,KCMBNetworkConfig):
            raise ValueError("KCMBNetworkConfig required")
        if backend not in ("python","rust"):
            raise ValueError("backend must be python or rust")
        self.config=config
        self.backend=backend
        self.n=len(config.links)
        self.k=len(config.routes)
        self.state_scalars=6*self.n*self.k+3*self.k
        self.id_to_index={link.name:i for i,link in enumerate(config.links)}
        self.route_index={route.name:k for k,route in enumerate(config.routes)}
        self._active=set()
        self._next={}
        self._first=[]
        for k,route in enumerate(config.routes):
            idx=[self.id_to_index[name] for name in route.path]
            self._first.append(idx[0])
            for z,i in enumerate(idx):
                self._active.add((i,k))
                self._next[i,k]=idx[z+1] if z+1<len(idx) else None
        self._transitions=tuple(_kinetic_transition(r.vehicle,config.dt_s) for r in config.routes)
        payload=json.dumps({"version":_VERSION,"config":asdict(config)},
                           sort_keys=True,separators=(",",":"))
        self.model_id=_VERSION+":"+sha256(payload.encode()).hexdigest()
        self._native_node=None
        if backend=="rust":
            try:
                from _metroflow_rust import allocate_kcmb_nodes
            except ImportError as exc:
                raise RuntimeError("KCMB Rust junction function not installed") from exc
            self._native_node=allocate_kcmb_nodes

    def initial(self)->KCMBNetworkState:
        return KCMBNetworkState(self.model_id,0,(0.,)*(6*self.n*self.k),
                                (0.,)*self.k,(0.,)*self.k,(0.,)*self.k)

    def _offset(self,i:int,k:int)->int:
        return 6*(i*self.k+k)

    def initial_profile(self,profile:Mapping[str,Sequence[float]])->KCMBNetworkState:
        if any(name not in self.id_to_index for name in profile):
            raise ValueError("unknown initial physical link")
        state=[0.]*(6*self.n*self.k)
        released=[0.]*self.k
        for name,row in profile.items():
            if len(row)!=self.k:
                raise ValueError("initial profile shape mismatch")
            i=self.id_to_index[name]
            length=self.config.links[i].lanes*self.config.links[i].length_m
            used=0.
            for k,amount in enumerate(row):
                m=_finite(amount,"initial vehicle mass")
                if m<0 or ((i,k) not in self._active and m>0):
                    raise ValueError("route cannot occupy initial link")
                c=self.config.routes[k].vehicle
                q=_micro_point(m,c.source_p,c.source_speed_fraction)
                off=self._offset(i,k)
                state[off:off+6]=q
                released[k]+=m
                used+=m*c.footprint_m
            if used>length+1e-10:
                raise ValueError("initial state exceeds link storage")
        s=KCMBNetworkState(self.model_id,0,tuple(state),(0.,)*self.k,
                           tuple(released),(0.,)*self.k)
        self._check(s)
        return s

    def _shape(self,state:KCMBNetworkState):
        if (not isinstance(state,KCMBNetworkState) or state.model_id!=self.model_id):
            raise ValueError("KCMB state identity differs")
        if (isinstance(state.tick,bool) or not isinstance(state.tick,int)
            or state.tick<0 or len(state.moments)!=6*self.n*self.k
            or any(len(x)!=self.k for x in
                   (state.pending,state.released,state.completed))):
            raise ValueError("KCMB state shape mismatch")

    def _check(self,state:KCMBNetworkState):
        self._shape(state)
        active=[0.]*self.k
        for i,link in enumerate(self.config.links):
            occupied=0.
            for k,r in enumerate(self.config.routes):
                off=self._offset(i,k)
                part=state.moments[off:off+6]
                _validate_class_moments(part,1e-10*max(1.,sum(part[:2])))
                mass=part[0]+part[1]
                if (i,k) not in self._active and mass>1e-10:
                    raise ValueError("route occupies an unregistered link")
                active[k]+=mass
                occupied+=mass*r.vehicle.footprint_m
            if occupied>link.length_m*link.lanes+1e-9:
                raise ValueError("link footprint storage exceeded")
        for k in range(self.k):
            p,r,d=state.pending[k],state.released[k],state.completed[k]
            if any(not math.isfinite(x) or x < -1e-11 for x in (p,r,d)):
                raise ValueError("invalid network conservation ledger")
            if abs(r-p-d-active[k])>1e-9*max(1.,r):
                raise ValueError("network mass conservation failed")

    def cell_class_mass(self,state:KCMBNetworkState,link:str,k:int)->float:
        self._shape(state)
        if link not in self.id_to_index or not 0<=k<self.k:
            raise ValueError("unknown link/route")
        off=self._offset(self.id_to_index[link],k)
        return state.moments[off]+state.moments[off+1]

    def occupied_metres(self,state:KCMBNetworkState,link:str)->float:
        return math.fsum(self.cell_class_mass(state,link,k)*r.vehicle.footprint_m
                         for k,r in enumerate(self.config.routes))

    def step(self,state:KCMBNetworkState,offers:Sequence[float], *,
             gates:Mapping[tuple[str,str|None],float]|None=None):
        self._check(state)
        offered=tuple(_finite(x,"source offer") for x in offers)
        if len(offered)!=self.k or any(x<0 for x in offered):
            raise ValueError("invalid class-boundary source shape")
        gates={} if gates is None else dict(gates)
        legal={(self.config.links[i].name,
                 self.config.links[j].name if j is not None else None)
               for (i,k),j in self._next.items()}
        for movement,value in gates.items():
            if movement not in legal or not 0<=_finite(value,"movement green")<=1:
                raise ValueError("invalid or noncausal movement gate")

        evolved=[0.]*(6*self.n*self.k)
        mass=[[0.]*self.k for _ in range(self.n)]
        sends=[[0.]*self.k for _ in range(self.n)]
        rcount={}
        rmetres={}
        for i,l in enumerate(self.config.links):
            occupied=0.
            for k,r in enumerate(self.config.routes):
                if (i,k) not in self._active:
                    continue
                off=self._offset(i,k)
                mat=self._transitions[k]
                for q in range(6):
                    evolved[off+q]=math.fsum(mat[q*6+j]*state.moments[off+j]
                                              for j in range(6))
                m=evolved[off]+evolved[off+1]
                mass[i][k]=m
                occupied+=m*r.vehicle.footprint_m
                sends[i][k]=min(m,(self.config.dt_s/l.length_m)*
                                    r.vehicle.vmax_mps*(evolved[off+2]+evolved[off+3]))
            total=math.fsum(sends[i])
            capacity=l.capacity_veh_per_s*self.config.dt_s
            if total>capacity:
                sends[i]=[amount*capacity/total for amount in sends[i]]
            rcount[i]=capacity
            rmetres[i]=max(0.,l.length_m*l.lanes-occupied)*min(
                1.,l.backward_wave_mps*self.config.dt_s/l.length_m)

        groups=[]
        priority=[]
        limits=[]
        sources={}
        for i,l in enumerate(self.config.links):
            rows=[]
            row_gates=[]
            for k,r in enumerate(self.config.routes):
                d=sends[i][k]
                if d<=0:continue
                nxt=self._next[i,k]
                name=(l.name,
                      self.config.links[nxt].name if nxt is not None else None)
                rows.append((k,nxt,d,r.vehicle.footprint_m))
                row_gates.append(gates.get(name,1.))
            if not rows:continue
            if self.config.lane_policy=="shared_head":
                groups.append(tuple(rows))
                priority.append(l.priority)
                limits.append(min(row_gates))
                sources[len(groups)-1]=(i,False)
            else:
                for row,gate in zip(rows,row_gates):
                    groups.append((row,))
                    priority.append(l.priority)
                    limits.append(gate)
                    sources[len(groups)-1]=(i,False)
        arrivals=[state.pending[k]+offered[k] for k in range(self.k)]
        for k,r in enumerate(self.config.routes):
            first=self._first[k]
            d=arrivals[k]
            if d>0:
                groups.append(((k,first,d,r.vehicle.footprint_m),))
                priority.append(1.)
                limits.append(1.)
                sources[len(groups)-1]=(None,True)
        immutable=tuple(groups)
        # Exactly factor by the physical junction. All receiving constraints
        # belong to the downstream link's tail node. A shared upstream head
        # group cannot touch two different physical junctions; source groups
        # belong to their first link's tail. Thus the resource incidence
        # matrix is block diagonal and local solves are algebraically exact.
        by_node={}
        for g,group in enumerate(immutable):
            src,is_external=sources[g]
            node=(self.config.links[self._first[group[0][0]]].tail
                  if is_external else self.config.links[src].head)
            for _,j,_,_ in group:
                if j is not None and self.config.links[j].tail!=node:
                    raise ArithmeticError("noncontiguous junction movement")
            by_node.setdefault(node,[]).append(g)
        allocated={}
        for node,global_indices in by_node.items():
            local_groups=tuple(immutable[g] for g in global_indices)
            destinations=sorted({j for group in local_groups for _,j,d,_ in group
                                 if j is not None and d>0})
            local_weights=tuple(priority[g] for g in global_indices)
            local_limits=tuple(limits[g] for g in global_indices)
            if self._native_node is None:
                values=progressive_junction(local_groups,
                    receive_count={j:rcount[j] for j in destinations},
                    receive_metres={j:rmetres[j] for j in destinations},
                    weights=local_weights,theta_limits=local_limits)
            else:
                # Native indices are local to this node, preventing a dense
                # O(n_links * n_routes) global resource incidence matrix.
                position={j:z for z,j in enumerate(destinations)}
                native_groups=[[(k, -1 if j is None else position[j], d, f)
                                for k,j,d,f in group] for group in local_groups]
                values={(g,z):v for g,z,v in self._native_node(
                    native_groups,[rcount[j] for j in destinations],
                    [rmetres[j] for j in destinations],
                    list(local_weights),list(local_limits))}
            for (local_g,z),flow in values.items():
                allocated[global_indices[local_g],z]=flow

        nxt=[0.]*len(evolved)
        for i in range(self.n):
            for k in range(self.k):
                off=self._offset(i,k)
                nxt[off:off+6]=evolved[off:off+6]
        accepted=[0.]*self.k
        finished=[0.]*self.k
        turns={}
        for g,group in enumerate(immutable):
            source_i,is_external=sources[g]
            for z,(k,dest,requested,foot) in enumerate(group):
                flow=allocated[g,z]
                if flow<-1e-12 or flow>requested+1e-10:
                    raise ArithmeticError("junction allocated outside movement demand")
                if is_external:
                    accepted[k]+=flow
                    off=self._offset(dest,k)
                    q=_micro_point(flow,self.config.routes[k].vehicle.source_p,
                                   self.config.routes[k].vehicle.source_speed_fraction)
                    for h in range(6):nxt[off+h]+=q[h]
                    continue
                if flow==0:continue
                off=self._offset(source_i,k)
                m=mass[source_i][k]
                if m<=0:
                    raise ArithmeticError("positive output with no upstream mass")
                fraction=flow/m
                if not 0<=fraction<=1+1e-12:
                    raise ArithmeticError("invalid movement split fraction")
                q=tuple(evolved[off+h]*fraction for h in range(6))
                for h in range(6):nxt[off+h]-=q[h]
                if dest is not None:
                    dst_off=self._offset(dest,k)
                    for h in range(6):nxt[dst_off+h]+=q[h]
                else:
                    finished[k]+=flow
                name=(self.config.links[source_i].name,
                      self.config.links[dest].name if dest is not None else None,
                      self.config.routes[k].name)
                turns[name]=turns.get(name,0.)+flow

        new=KCMBNetworkState(self.model_id,state.tick+1,tuple(nxt),
            tuple(max(0.,a-b) for a,b in zip(arrivals,accepted)),
            tuple(r+d for r,d in zip(state.released,offered)),
            tuple(c+d for c,d in zip(state.completed,finished)))
        self._check(new)
        return new,{"turn_flows":turns,"accepted_by_route":tuple(accepted),
                    "finished_by_route":tuple(finished),
                    "mass_error_max_veh":max(abs(
                        new.released[k]-new.pending[k]-new.completed[k]-
                        math.fsum(new.moments[self._offset(i,k)]+
                                  new.moments[self._offset(i,k)+1]
                                  for i in range(self.n))) for k in range(self.k)),
                    "state_scalar_capacity":self.state_scalars,
                    "lane_policy":self.config.lane_policy}

    def to_bytes(self,state:KCMBNetworkState)->bytes:
        self._check(state)
        return json.dumps({"format":_VERSION,**asdict(state)},sort_keys=True,
                          separators=(",",":"),allow_nan=False).encode()

    def from_bytes(self,raw:bytes)->KCMBNetworkState:
        if not isinstance(raw,(bytes,bytearray)) or len(raw)>4096+64*self.state_scalars:
            raise ValueError("network checkpoint size/budget exceeded")
        try:
            row=json.loads(raw)
            if set(row)!={"format","model_id","tick","moments","pending","released","completed"}:
                raise ValueError("network checkpoint shape")
            if row["format"]!=_VERSION or row["model_id"]!=self.model_id:
                raise ValueError("network checkpoint identity")
            state=KCMBNetworkState(row["model_id"],row["tick"],
                tuple(row["moments"]),tuple(row["pending"]),
                tuple(row["released"]),tuple(row["completed"]))
            self._check(state)
            return state
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError("network checkpoint format/identity/state invalid") from exc
