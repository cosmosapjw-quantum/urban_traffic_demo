"""Lossless remaining-route aggregation for homogeneous active mesoscopic flow.

A suffix is an immutable (road,next_suffix) cons cell. Equal residual routes
share structure; equal suffix/due-time cohorts share mass. Source route caches
are only decision support: evicting them never rewrites committed transport.
Scientific core is stdlib; no vehicle identities or per-unit-mass iteration.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json,math
from .common import Config,Road,Demand,Signal,BudgetExceeded,_validate,_eligible_seconds
from .kinetic import relax_activity,relax_choice
from .routing import Arc,candidate_paths,destination_potential
from .node import allocate

@dataclass(frozen=True,slots=True)
class Suffix:
    id:int
    road:int
    next_id:int

@dataclass(frozen=True,slots=True)
class Arrival:
    due_tick:int
    suffix:int
    mass:float

@dataclass(frozen=True,slots=True)
class State:
    tick:int
    pending:tuple[float,...]
    queues:tuple[tuple[int,float],...]
    transit:tuple[Arrival,...]
    activity:tuple[float,...]
    choice:tuple[tuple[float,...],...]
    source_roots:tuple[tuple[int,...],...]
    suffixes:tuple[Suffix,...]
    next_suffix_id:int
    last_choice_s:float
    last_factors:tuple[float,...]
    released:float=0.
    admitted:float=0.
    completed:float=0.
    vehicle_seconds:float=0.
    link_outflow:tuple[float,...]=()
    link_visits:int=0
    route_solves:int=0
    cohort_slots_visited:int=0
    max_cached_route_regret_s:float=0.
    max_pre_repair_route_regret_s:float=0.
    routing_repairs:int=0
    route_repair_expansions:int=0
    cache_evictions:int=0
    suffixes_collected:int=0


def _path(table,sid):
    out=[];seen=set()
    while sid!=-1:
        if sid in seen or sid not in table: raise ValueError('invalid suffix DAG')
        seen.add(sid);s=table[sid];out.append(s.road);sid=s.next_id
    return tuple(out)


def _collect(table,roots,queues,events):
    live=set();stack=[s for group in roots for s in group]
    stack.extend(s for s,m in queues.items() if m>0)
    stack.extend(e.suffix for e in events if e.mass>0)
    while stack:
        sid=stack.pop()
        if sid==-1 or sid in live:continue
        if sid not in table:raise ValueError('dangling live suffix reference')
        live.add(sid);stack.append(table[sid].next_id)
    return {sid:table[sid] for sid in sorted(live)}


class Model:
    def __init__(self,roads,demands,config=Config(),allowed_turns=None,capacity_windows=(),conflicts=()):
        self.roads=tuple(sorted(roads,key=lambda r:r.id));self.demands=tuple(demands)
        self.cfg=config;self.windows=tuple(capacity_windows)
        self.turns=frozenset(allowed_turns) if allowed_turns is not None else None
        self.conflicts=tuple(conflicts)
        _validate(self.roads,self.demands,config,1.,self.windows,self.conflicts)
        if not isinstance(config.max_live_suffixes,int) or isinstance(config.max_live_suffixes,bool):
            raise ValueError('max_live_suffixes must be a positive integer')
        self.index={r.id:i for i,r in enumerate(self.roads)}
        self.arcs=tuple(Arc(r.id,r.tail,r.head) for r in self.roads)
        costs={r.id:(r.length_m/r.free_speed_mps+
            ((r.signal.cycle_s-r.signal.green_s)**2/(2*r.signal.cycle_s) if r.signal else 0.))
            if not r.signal or r.signal.green_s>0 else math.inf for r in self.roads}
        groups=[];self.search_expansions=0
        for d in self.demands:
            result=candidate_paths(self.arcs,costs,d.origin,d.destination,config.paths_per_od,
                config.path_expansion_budget,self.turns)
            if result.truncated:raise BudgetExceeded('initial candidate search limit')
            if not result.paths:raise ValueError('demand has no legal initial route')
            groups.append(tuple(tuple(self.index[e] for e in p) for p in result.paths))
            self.search_expansions+=result.expanded
        self.initial_paths=tuple(groups)

    @staticmethod
    def _intern(table,index,path,next_id):
        tail=-1
        for road in reversed(path):
            key=(road,tail)
            if key not in index:
                index[key]=next_id;table[next_id]=Suffix(next_id,road,tail);next_id+=1
            tail=index[key]
        return tail,next_id

    def initial(self):
        table={};index={};next_id=0;roots=[]
        for paths in self.initial_paths:
            group=[]
            for path in paths:
                sid,next_id=self._intern(table,index,path,next_id);group.append(sid)
            roots.append(tuple(group))
        if len(table)>self.cfg.max_live_suffixes:raise BudgetExceeded('initial suffix pool limit')
        return State(0,(0.,)*len(self.demands),(),(),(1.,)*len(self.roads),
            tuple((0.,)*len(g) for g in roots),tuple(roots),tuple(table.values()),next_id,-1.,(),
            link_outflow=(0.,)*len(self.roads))

    def remaining_path(self,state,suffix_id):
        return tuple(self.roads[i].id for i in _path({s.id:s for s in state.suffixes},suffix_id))

    def occupancy(self,state):
        table={s.id:s for s in state.suffixes}
        occ=[0.]*len(self.roads);waiting=[0.]*len(self.roads)
        for sid,mass in state.queues:
            i=table[sid].road;occ[i]+=mass;waiting[i]+=mass
        for event in state.transit:occ[table[event.suffix].road]+=event.mass
        return occ,waiting

    def step(self,state):
        try:return self._step(state)
        except BudgetExceeded as exc:
            exc.checkpoint=state
            raise

    def _mature(self,state):
        """Legacy point-calendar policy; subclasses may use bounded run records."""
        queues=dict(state.queues);future=[]
        for event in state.transit:
            if event.due_tick<=state.tick:queues[event.suffix]=queues.get(event.suffix,0.)+event.mass
            else:future.append(event)
        return queues,future

    def _arrival(self,tick,delay,suffix,mass):
        return Arrival(tick+delay,suffix,mass)

    def _pack(self,future):
        merged={}
        for event in future:
            key=(event.due_tick,event.suffix);merged[key]=merged.get(key,0.)+event.mass
        return tuple(Arrival(*key,mass) for key,mass in sorted(merged.items()) if mass>0)

    def _residence(self,state,occupied,released,completed,dt):
        return state.vehicle_seconds+dt*(math.fsum(occupied)+math.fsum(state.pending)+released)

    def _step(self,state):
        cfg=self.cfg;dt=cfg.dt_s;t=state.tick*dt;end=t+dt;tick=state.tick+1
        table={s.id:s for s in state.suffixes};index={(s.road,s.next_id):s.id for s in state.suffixes}
        next_id=state.next_suffix_id;roots=[list(g) for g in state.source_roots]
        queues,future=self._mature(state)
        occupied,_=self.occupancy(state);waiting=[0.]*len(self.roads)
        for sid,mass in queues.items():waiting[table[sid].road]+=mass
        pending=list(state.pending);released=0.
        for od,d in enumerate(self.demands):
            mass=max(0.,min(end,d.end_s)-max(t,d.start_s))*d.rate_veh_s
            pending[od]+=mass;released+=mass
        activity=tuple(relax_activity(state.activity[i],cfg.restart_rate_s,
            cfg.background_stop_rate_s+cfg.interaction_rate_s*(occupied[i]/r.storage_veh)**2,dt)
            for i,r in enumerate(self.roads))
        running=tuple(r.length_m/(r.free_speed_mps*activity[i]) for i,r in enumerate(self.roads))
        available=tuple(_eligible_seconds(r,t,dt,self.windows,False) for r in self.roads)
        factors=tuple(x/dt for x in available)
        exit_budget={i:r.capacity_veh_s*_eligible_seconds(r,t,dt,self.windows,True) for i,r in enumerate(self.roads)}
        receiving={i:min(r.capacity_veh_s*available[i],max(0.,r.storage_veh-occupied[i])) for i,r in enumerate(self.roads)}
        costs={}
        for i,r in enumerate(self.roads):
            duty=r.signal.green_s/r.signal.cycle_s if r.signal else 1.
            rate=r.capacity_veh_s*factors[i]*duty
            red=(r.signal.cycle_s-r.signal.green_s)**2/(2*r.signal.cycle_s) if r.signal else 0.
            costs[r.id]=running[i]+waiting[i]/rate+red if rate>0 else math.inf
        refresh=(state.last_choice_s<0 or t-state.last_choice_s>=cfg.route_refresh_s-1e-10 or factors!=state.last_factors)
        choice=state.choice;last_choice=state.last_choice_s;solves=state.route_solves
        regret=state.max_cached_route_regret_s;pre=state.max_pre_repair_route_regret_s
        repairs=state.routing_repairs;expansions=state.route_repair_expansions;evictions=state.cache_evictions
        if refresh:
            potentials={d:destination_potential(self.arcs,costs,d,self.turns)
                        for d in sorted({x.destination for x in self.demands})}
            solves+=len(potentials);shares=[]
            for od,d in enumerate(self.demands):
                group=roots[od];prior=list(choice[od]);paths=[_path(table,sid) for sid in group]
                c=tuple(math.fsum(costs[self.roads[i].id] for i in path) for path in paths)
                best=min((potentials[d.destination][r.id] for r in self.roads if r.tail==d.origin),default=math.inf)
                finite=any(math.isfinite(x) for x in c)
                if math.isfinite(best) and finite:pre=max(pre,max(0.,min(c)-best))
                need=math.isfinite(best) and (not finite or min(c)-best>cfg.route_regret_budget_s+1e-9)
                if need and cfg.adaptive_routes:
                    found=candidate_paths(self.arcs,costs,d.origin,d.destination,1,cfg.path_expansion_budget,self.turns)
                    expansions+=found.expanded
                    if found.truncated or not found.paths:raise BudgetExceeded('shortest-route search bound')
                    path=tuple(self.index[e] for e in found.paths[0])
                    if path not in paths:
                        sid,next_id=self._intern(table,index,path,next_id)
                        if len(group)<cfg.max_routes_per_od:group.append(sid);paths.append(path);prior.append(0.)
                        else:
                            # Candidate cache is NOT the owner of in-flight mass.
                            k=max(range(len(group)),key=lambda k:(c[k],group[k]))
                            group[k]=sid;paths[k]=path;prior[k]=0.;evictions+=1
                        repairs+=1
                        c=tuple(math.fsum(costs[self.roads[i].id] for i in p) for p in paths);finite=True
                    if min(c)-best>cfg.route_regret_budget_s+1e-8:raise BudgetExceeded('route regret bound')
                if math.isfinite(best) and not finite:raise BudgetExceeded('detour outside fixed cache')
                if math.isfinite(best):regret=max(regret,max(0.,min(c)-best))
                counts={e:sum(e in p for p in paths) for p in paths for e in p}
                sizes=tuple(math.fsum(self.roads[e].length_m/counts[e] for e in p)/
                            math.fsum(self.roads[e].length_m for e in p) for p in paths)
                response=cfg.route_refresh_s if state.last_choice_s<0 else max(dt,t-state.last_choice_s)
                shares.append(relax_choice(prior,c,response,cfg.route_response_s,cfg.temperature_s,sizes))
            choice=tuple(shares);last_choice=t
        movements={};planned=[];incoming=[0.]*len(self.roads);outgoing=[0.]*len(self.roads)
        for sid,mass in sorted(queues.items()):
            if mass<=0:continue
            s=table[sid];i=s.road;j=table[s.next_id].road if s.next_id!=-1 else -1
            movements.setdefault(self.roads[i].head,{}).setdefault((i,j),[]).append((sid,mass))
        for _,groups in sorted(movements.items()):
            demand={m:math.fsum(x[1] for x in values) for m,values in groups.items()}
            sending={i:exit_budget[i] for i,_ in groups}
            receive={j:receiving[j] if j>=0 else math.fsum(sending.values()) for _,j in groups}
            flow=allocate(demand,sending,receive,{i:self.roads[i].priority for i in sending})
            for (i,j),amount in flow.items():
                if amount<=0:continue
                total=demand[(i,j)]
                for sid,mass in groups[(i,j)]:
                    served=mass if amount>=total else min(mass,amount*(mass/total))
                    queues[sid]-=served;planned.append((sid,served));outgoing[i]+=served
                    if j>=0:incoming[j]+=served
        completed=state.completed
        for sid,mass in planned:
            nxt=table[sid].next_id
            if nxt==-1:completed+=mass
            else:
                j=table[nxt].road;delay=max(1,math.ceil(running[j]/dt-1e-12))
                future.append(self._arrival(tick,delay,nxt,mass))
        admissions=[];totals={}
        for od,group in enumerate(roots):
            for sid,share in zip(group,choice[od]):
                desired=pending[od]*share
                if desired>0:
                    i=table[sid].road;admissions.append((od,sid,desired));totals[i]=totals.get(i,0.)+desired
        admitted=state.admitted
        for od,sid,desired in admissions:
            i=table[sid].road;space=max(0.,receiving[i]-incoming[i])
            mass=desired*min(1.,space/totals[i])
            if mass<=0:continue
            pending[od]-=mass;admitted+=mass
            delay=max(1,math.ceil(running[i]/dt-1e-12));future.append(self._arrival(tick,delay,sid,mass))
        future=self._pack(future)
        queues={s:m for s,m in queues.items() if m>0}
        retained=_collect(table,roots,queues,future)
        if len(future)>cfg.event_budget:raise BudgetExceeded('arrival-calendar bound')
        if len(retained)>cfg.max_live_suffixes:raise BudgetExceeded('live suffix pool bound')
        nxt=State(tick,tuple(max(0.,x) for x in pending),tuple(sorted(queues.items())),future,activity,choice,
            tuple(tuple(g) for g in roots),tuple(retained.values()),next_id,last_choice,factors,
            state.released+released,admitted,completed,
            self._residence(state,occupied,released,completed,dt),
            tuple(a+b for a,b in zip(state.link_outflow,outgoing)),state.link_visits+len(self.roads),solves,
            state.cohort_slots_visited+len(state.transit),regret,pre,repairs,expansions,evictions,
            state.suffixes_collected+len(table)-len(retained))
        occ,_=self.occupancy(nxt)
        err=nxt.released-nxt.completed-math.fsum(nxt.pending)-math.fsum(occ)
        if abs(err)>1e-8*max(1.,nxt.released):raise ArithmeticError(f'mass ledger {err}')
        if any(n>r.storage_veh+1e-8*max(1.,r.storage_veh) for n,r in zip(occ,self.roads)):
            raise ArithmeticError('finite storage exceeded')
        return nxt

    def fingerprint(self,state):
        payload=dict(contract='shared_committed_suffix_v1',roads=[asdict(r) for r in self.roads],
            demands=[asdict(d) for d in self.demands],config=asdict(self.cfg),state=asdict(state),
            turns=sorted(self.turns) if self.turns is not None else None,windows=self.windows,conflicts=self.conflicts)
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
