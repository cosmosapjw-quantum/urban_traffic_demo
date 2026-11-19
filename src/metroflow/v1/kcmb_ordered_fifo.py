"""Experimental ordered-run FIFO extension of the conservative KCMB network.

Not a replacement for production V1.  Per-link route order is explicit and
preserved, including eligibility by minimum free-flow travel delay. Kinetic
velocity/control moments remain route-aggregated: run-specific velocity moments,
arbitrary vehicle identities and full microscopic safety are NOT resolved.

Exact order representation has an explicit max_runs budget. When the budget
cannot preserve the sequence, step fails with a checkpoint and does not silently
coarsen or discard vehicles. Runs only merge if both route and ready_tick match.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from .kcmb import _finite, _micro_point, _validate_class_moments
from .kcmb_network import (
    KCMBBoundedNetwork, KCMBNetworkConfig, KCMBNetworkState, progressive_junction,
)

_VERSION="kcmb_ordered_route_runs_v2_eligible_prefix"
_EPS=1e-13


class FIFOQueueBudgetError(RuntimeError):
    """An exact route-run representation could not fit; unchanged state attached."""


@dataclass(frozen=True, slots=True)
class OrderedRun:
    route: int
    mass: float
    ready_tick: int


@dataclass(frozen=True, slots=True)
class FIFOQueueState(KCMBNetworkState):
    runs: tuple[tuple[OrderedRun, ...], ...]


def _append(queue: list[OrderedRun], run: OrderedRun) -> None:
    if run.mass <= 0.:
        return
    if queue and (queue[-1].route, queue[-1].ready_tick)==(run.route,run.ready_tick):
        prev=queue[-1]
        queue[-1]=OrderedRun(run.route,prev.mass+run.mass,run.ready_tick)
    else:
        queue.append(run)


class OrderedKCMBBoundedNetwork(KCMBBoundedNetwork):
    """Route-FIFO and finite free-flow delay in a single ordered lane per link.

    Public interface remains opt-in. Source/simultaneous-link arrivals have a
    deterministic tie policy (round, upstream link ID, route ID); it is NOT an
    observation of actual within-tick microscopic entry order.
    """

    def __init__(self, config: KCMBNetworkConfig, *, backend="python", max_runs=256):
        if config.lane_policy!="shared_head":
            raise ValueError("ordered FIFO needs a shared single-lane head policy")
        if (isinstance(max_runs,bool) or not isinstance(max_runs,int) or
                not 1<=max_runs<=100_000):
            raise ValueError("positive finite route-run budget required")
        super().__init__(config,backend=backend)
        self.max_runs=max_runs
        previous=self.model_id
        self.model_id=_VERSION+":"+sha256(
            (previous+":"+str(max_runs)).encode("utf-8")).hexdigest()
        self._lags=tuple(tuple(
            max(1,math.ceil(l.length_m/(r.vehicle.vmax_mps*config.dt_s)))
            if (i,k) in self._active else 0
            for k,r in enumerate(config.routes))
            for i,l in enumerate(config.links))
        self._by_node={}
        for i,link in enumerate(config.links):
            self._by_node.setdefault(link.head,{"senders":[],"sources":[]})[
                "senders"].append(i)
        for k,first in enumerate(self._first):
            self._by_node.setdefault(config.links[first].tail,
                {"senders":[],"sources":[]})["sources"].append(k)
        # Include each physical receiving link at precisely its own tail node.
        self._receive_at_node={}
        for i,link in enumerate(config.links):
            self._receive_at_node.setdefault(link.tail,[]).append(i)

    def initial(self)->FIFOQueueState:
        base=super().initial()
        return FIFOQueueState(base.model_id,base.tick,base.moments,
            base.pending,base.released,base.completed,
            tuple(() for _ in range(self.n)))

    def initial_profile(self,profile:Mapping[str,Sequence[float]], *,
                        order_by_link:Mapping[str,Sequence[tuple[str,float]]]|None=None):
        base=super().initial_profile(profile)
        order_by_link={} if order_by_link is None else dict(order_by_link)
        if any(link not in self.id_to_index for link in order_by_link):
            raise ValueError("order refers to unknown physical link")
        queues=[]
        for i,l in enumerate(self.config.links):
            amounts=[base.moments[self._offset(i,k)]+
                     base.moments[self._offset(i,k)+1] for k in range(self.k)]
            if l.name in order_by_link:
                runs=[]
                for name,amount in order_by_link[l.name]:
                    if name not in self.route_index:
                        raise ValueError("unknown route in initial order")
                    k=self.route_index[name]
                    mass=_finite(amount,"ordered initial mass")
                    if mass<=0 or (i,k) not in self._active:
                        raise ValueError("invalid ordered initial route/mass")
                    _append(runs,OrderedRun(k,mass,0))
                for k,expected in enumerate(amounts):
                    observed=math.fsum(v.mass for v in runs if v.route==k)
                    if not math.isclose(expected,observed,abs_tol=1e-10,rel_tol=1e-10):
                        raise ValueError("initial order disagrees with physical route inventory")
            else:
                populated=[k for k,m in enumerate(amounts) if m>0.]
                if len(populated)>1:
                    raise ValueError("explicit order required for mixed initial routes")
                runs=[OrderedRun(populated[0],amounts[populated[0]],0)] if populated else []
            queues.append(tuple(runs))
        state=FIFOQueueState(base.model_id,base.tick,base.moments,
            base.pending,base.released,base.completed,tuple(queues))
        self._check_ordered(state)
        return state

    def _check_ordered(self,state:FIFOQueueState)->None:
        if not isinstance(state,FIFOQueueState):
            raise ValueError("ordered FIFO snapshot type/identity mismatch")
        super()._check(state)
        if len(state.runs)!=self.n:
            raise ValueError("route queue shape mismatch")
        count=0
        for i,queue in enumerate(state.runs):
            if not isinstance(queue,tuple):
                raise ValueError("route queue shape must be immutable")
            count+=len(queue)
            observed=[0.]*self.k
            previous=None
            for run in queue:
                if (not isinstance(run,OrderedRun) or
                    isinstance(run.route,bool) or not isinstance(run.route,int) or
                    not 0<=run.route<self.k or (i,run.route) not in self._active or
                    not math.isfinite(run.mass) or run.mass<=0 or
                    isinstance(run.ready_tick,bool) or
                    not isinstance(run.ready_tick,int) or run.ready_tick<0):
                    raise ValueError("invalid route queue record")
                if run.mass<=1e-12:
                    # The progressive junction resolves positive demands
                    # strictly above 1e-12 vehicles. Never silently admit an
                    # unserviceable preloaded fractional vehicle.
                    raise ValueError("route FIFO run below numerical resolution")
                if previous is not None and previous==(
                        run.route,run.ready_tick):
                    raise ValueError("noncanonical adjacent route queue runs")
                previous=(run.route,run.ready_tick)
                observed[run.route]+=run.mass
            for k,total in enumerate(observed):
                off=self._offset(i,k)
                physical=state.moments[off]+state.moments[off+1]
                if not math.isclose(total,physical,rel_tol=1e-9,
                                    abs_tol=2e-9):
                    raise ValueError("route queue inventory differs from kinetic mass")
        if count>self.max_runs:
            raise ValueError("state queue run budget exceeded")

    def queue_runs(self,state:FIFOQueueState,link:str):
        self._check_ordered(state)
        if link not in self.id_to_index:
            raise ValueError("unknown link")
        return state.runs[self.id_to_index[link]]

    def queue_route_names(self,state:FIFOQueueState,link:str):
        return tuple(self.config.routes[v.route].name for v in self.queue_runs(state,link))

    def _node_allocate(self,groups, receivers, count_remaining,metres_remaining,
                       weights):
        if not groups:return []
        if self._native_node is None:
            values=progressive_junction(tuple(tuple(row for row in group) for group in groups),
                receive_count={j:count_remaining[j] for j in receivers},
                receive_metres={j:metres_remaining[j] for j in receivers},
                weights=tuple(weights))
            return [values[g,0] for g in range(len(groups))]
        local={j:i for i,j in enumerate(receivers)}
        native=[[(k,-1 if j is None else local[j],d,f) for k,j,d,f in group]
                for group in groups]
        values=self._native_node(native,
            [count_remaining[j] for j in receivers],
            [metres_remaining[j] for j in receivers],
            list(weights),[1.]*len(groups))
        mapped={(g,z):x for g,z,x in values}
        return [mapped[g,0] for g in range(len(groups))]

    def step(self,state:FIFOQueueState,offers:Sequence[float], *,
             gates:Mapping[tuple[str,str|None],float]|None=None):
        self._check_ordered(state)
        offered=tuple(_finite(v,"offered route mass") for v in offers)
        if len(offered)!=self.k or any(v<0 for v in offered):
            raise ValueError("invalid source demand shape")
        gates={} if gates is None else dict(gates)
        legal={(l.name,self.config.links[j].name if j is not None else None)
               for (i,k),j in self._next.items()
               for l in (self.config.links[i],)}
        if any(key not in legal or not 0<=_finite(value,"signal gate")<=1
               for key,value in gates.items()):
            raise ValueError("unknown or invalid movement gate")

        # Phase I: evolve only old kinetic moments, and derive flux budgets
        # from the same pre-step physical state. No new inbound mass travels
        # across multiple links in one timestep.
        updated=[0.]*len(state.moments)
        masses=[[0.]*self.k for _ in range(self.n)]
        sending=[[0.]*self.k for _ in range(self.n)]
        free_count=[0.]*self.n
        free_metres=[0.]*self.n
        for i,l in enumerate(self.config.links):
            occupied=0.
            for k,route in enumerate(self.config.routes):
                if (i,k) not in self._active:continue
                off=self._offset(i,k)
                mat=self._transitions[k]
                for row in range(6):
                    updated[off+row]=math.fsum(
                        mat[row*6+j]*state.moments[off+j] for j in range(6))
                m=updated[off]+updated[off+1]
                masses[i][k]=m
                occupied+=m*route.vehicle.footprint_m
                sending[i][k]=min(m,self.config.dt_s/l.length_m*
                    route.vehicle.vmax_mps*(updated[off+2]+updated[off+3]))
            total=math.fsum(sending[i])
            send_cap=l.capacity_veh_per_s*self.config.dt_s
            if total>send_cap:
                sending[i]=[v*send_cap/total for v in sending[i]]
            free_count[i]=send_cap
            free_metres[i]=max(0.,l.lanes*l.length_m-occupied)*min(
                1.,l.backward_wave_mps*self.config.dt_s/l.length_m)

        # Phase II: consume OLD queue fronts only. Local resources are
        # disjoint across nodes, but iterative head advances preserve order
        # when a whole route run is served before the tick ends.
        old=[deque(q) for q in state.runs]
        remaining=[[v for v in row] for row in sending]
        route_gated={}
        for (i,k),j in self._next.items():
            name=(self.config.links[i].name,
                  self.config.links[j].name if j is not None else None)
            route_gated[i,k]=sending[i][k]*gates.get(name,1.)
        arrivals=[state.pending[k]+offered[k] for k in range(self.k)]
        accepted=[0.]*self.k
        completed=[0.]*self.k
        emissions=[]
        numeric_roundoff_charge_veh=0.
        # (round, source-link-id, route-id, destination-index, mass, is_source)
        traces={}
        for node in sorted(self._by_node):
            sources=self._by_node[node]["sources"]
            senders=self._by_node[node]["senders"]
            receivers=self._receive_at_node.get(node,[])
            count_left={j:free_count[j] for j in receivers}
            metres_left={j:free_metres[j] for j in receivers}
            max_rounds=2+len(sources)+sum(len(old[i]) for i in senders)+len(receivers)
            for stage in range(max_rounds):
                candidates=[]
                priority=[]
                details=[]
                # Sources and road exits compete for the same receiving pool.
                for k in sources:
                    available=arrivals[k]-accepted[k]
                    if available>_EPS:
                        first=self._first[k]
                        candidates.append(((k,first,available,
                          self.config.routes[k].vehicle.footprint_m),))
                        priority.append(1.)
                        details.append((None,k,first))
                for i in senders:
                    if not old[i]:continue
                    front=old[i][0]
                    k=front.route
                    if front.ready_tick>state.tick+1:continue
                    dest=self._next[i,k]
                    # Numerical representation must not affect junction
                    # priorities. The demand of one kinetic route is the
                    # entire presently-eligible contiguous head PREFIX, not
                    # merely the first arbitrary stored run fragment.
                    prefix_mass=0.
                    for run in old[i]:
                        if run.route!=k or run.ready_tick>state.tick+1:
                            break
                        prefix_mass+=run.mass
                    d=min(prefix_mass,remaining[i][k],route_gated[i,k])
                    if d<=_EPS:continue
                    candidates.append(((k,dest,d,
                        self.config.routes[k].vehicle.footprint_m),))
                    priority.append(self.config.links[i].priority)
                    details.append((i,k,dest))
                if not candidates:
                    break
                values=self._node_allocate(candidates,receivers,
                                            count_left,metres_left,priority)
                if not any(v>_EPS for v in values):
                    break
                for g,(flow,(source_i,k,dest)) in enumerate(zip(values,details)):
                    if flow<=_EPS:continue
                    requested=candidates[g][0][2]
                    if source_i is not None:
                        # Atomically serve the physically eligible FIFO prefix.
                        # This removes the artificial dependence on how many
                        # adjacent same-route runs were stored. Tiny IEEE
                        # remainders at a fully served head are *charged* as
                        # actual flow rather than silently deleted or frozen.
                        nominal_flow=flow
                        to_serve=nominal_flow
                        served=0.
                        while to_serve>1e-14:
                            if not old[source_i]:
                                raise ArithmeticError("FIFO prefix exhausted before allocated flow")
                            front=old[source_i][0]
                            if front.route!=k or front.ready_tick>state.tick+1:
                                raise ArithmeticError("FIFO prefix service crossed a route/clock barrier")
                            remainder=front.mass-to_serve
                            if remainder<=1e-12:
                                served+=front.mass
                                to_serve-=front.mass
                                old[source_i].popleft()
                            else:
                                served+=to_serve
                                old[source_i][0]=OrderedRun(
                                    k,remainder,front.ready_tick)
                                to_serve=0.
                        flow=served
                        if flow-nominal_flow>1e-10:
                            raise ArithmeticError("FIFO excessive numerical completion charge")
                        if flow>nominal_flow:
                            numeric_roundoff_charge_veh+=(flow-nominal_flow)
                    if flow>requested+1e-10:
                        raise ArithmeticError("FIFO node exceeds proposed supply")
                    if dest is not None:
                        count_left[dest]-=flow
                        metres_left[dest]-=flow*self.config.routes[k].vehicle.footprint_m
                        if count_left[dest]<-1e-8 or metres_left[dest]<-1e-8:
                            raise ArithmeticError("node exceed receiving resources")
                        # Already-charged resource may have a tiny negative
                        # IEEE residual; zero it without changing booked flow.
                        count_left[dest]=max(0.,count_left[dest])
                        metres_left[dest]=max(0.,metres_left[dest])
                    if source_i is None:
                        accepted[k]+=flow
                    else:
                        remaining[source_i][k]-=flow
                        route_gated[source_i,k]-=flow
                        if dest is None:
                            completed[k]+=flow
                        key=(self.config.links[source_i].name,
                             self.config.links[dest].name if dest is not None else None,
                             self.config.routes[k].name)
                        traces[key]=traces.get(key,0.)+flow
                    emissions.append((stage,-1 if source_i is None else source_i,
                                      k,dest,flow,source_i is None))
            else:
                raise ArithmeticError("ordered FIFO local progression exceeded bounded rounds")

        # Phase III: commit pre-step mass-proportional moments to destination
        # (no intermediate time-of-arrival information in those moments).
        next_fields=list(updated)
        next_runs=[list(q) for q in old]
        next_tick=state.tick+1
        for stage,source_i,k,dest,flow,is_source in sorted(emissions):
            if is_source:
                q=_micro_point(flow,self.config.routes[k].vehicle.source_p,
                                self.config.routes[k].vehicle.source_speed_fraction)
            else:
                mass=masses[source_i][k]
                if mass<=0:
                    raise ArithmeticError("departure without pre-step route mass")
                off=self._offset(source_i,k)
                q=tuple(updated[off+a]*(flow/mass) for a in range(6))
                for a in range(6):
                    next_fields[off+a]-=q[a]
            if dest is not None:
                off=self._offset(dest,k)
                for a in range(6):
                    next_fields[off+a]+=q[a]
                _append(next_runs[dest],OrderedRun(
                    k,flow,next_tick+self._lags[dest][k]))
        run_count=sum(len(q) for q in next_runs)
        if run_count>self.max_runs:
            exc=FIFOQueueBudgetError(
                f"exact route FIFO run budget exceeded: {run_count}>{self.max_runs}")
            exc.checkpoint=state
            raise exc
        new=FIFOQueueState(self.model_id,next_tick,tuple(next_fields),
            tuple(max(0.,m-a) for m,a in zip(arrivals,accepted)),
            tuple(r+v for r,v in zip(state.released,offered)),
            tuple(c+v for c,v in zip(state.completed,completed)),
            tuple(tuple(q) for q in next_runs))
        self._check_ordered(new)
        residual=max(abs(new.released[k]-new.pending[k]-new.completed[k]-
                         math.fsum(new.moments[self._offset(i,k)]+
                         new.moments[self._offset(i,k)+1]
                         for i in range(self.n))) for k in range(self.k))
        return new,{"turn_flows":traces,
            "accepted_by_route":tuple(accepted),
            "finished_by_route":tuple(completed),
            "mass_error_max_veh":residual,
            "state_scalar_capacity":self.state_scalars,
            "run_count":run_count,"run_budget":self.max_runs,
            "numerical_completion_charge_veh":numeric_roundoff_charge_veh,
            "max_run_state_scalars":3*self.max_runs,
            "model_id":self.model_id,
            "backend":self.backend,
            "fifo_scope":"strict route-head order; within-tick arrival ties modeled"}

    def to_bytes(self,state:FIFOQueueState)->bytes:
        self._check_ordered(state)
        return json.dumps({"format":_VERSION,**asdict(state)},
            sort_keys=True,separators=(",",":"),allow_nan=False).encode()

    def from_bytes(self,raw:bytes)->FIFOQueueState:
        if not isinstance(raw,(bytes,bytearray)) or len(raw)>(
                4096+64*self.state_scalars+120*self.max_runs):
            raise ValueError("ordered FIFO checkpoint size budget exceeded")
        try:
            row=json.loads(raw)
            if set(row)!={"format","model_id","tick","moments","pending",
                           "released","completed","runs"}:
                raise ValueError("ordered FIFO checkpoint shape")
            if row["format"]!=_VERSION or row["model_id"]!=self.model_id:
                raise ValueError("ordered FIFO checkpoint identity mismatch")
            state=FIFOQueueState(row["model_id"],row["tick"],
                tuple(row["moments"]),tuple(row["pending"]),
                tuple(row["released"]),tuple(row["completed"]),
                tuple(tuple(OrderedRun(**v) for v in q) for q in row["runs"]))
            self._check_ordered(state)
            return state
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError("invalid ordered FIFO checkpoint identity/state") from exc
