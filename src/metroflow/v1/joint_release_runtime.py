"""Whole-journey calendar stages around one B01/T04 road owner.

Only ServiceModel.step advances traffic. Its fleet/cargo road ledger remains
separate from the per-calendar persons/vehicle-equivalent journey ledger.
Bus boarding uses finite-window stop availability; dependent boarding requires
the entire assigned window to be eligible. Residual waiting is retained.
"""
from dataclasses import dataclass, fields
import hashlib
import json
import math
from pathlib import Path

from ..active_suffix.common import BudgetExceeded
from ..foundation_kinetics import VehicleClass
from ..ordered_network import Route
from .checkpoint import encode, decode
from .city import reject
from .journey import AccessEntry
from .release_runtime import ReleaseRuntime
from .services import ServiceState, RunState, PassengerState


@dataclass(frozen=True, slots=True)
class JointReleaseState:
    model_id: str
    service: object
    entering: tuple
    egress: tuple
    internal: tuple
    released: tuple
    completed: tuple
    receipts: tuple
    birth_carrier_s: tuple

    @property
    def time_s(self):
        return self.service.road.time_s


class JointReleaseRuntime:
    def __init__(self, city, legs, service_plan, *, step_s=1.0, max_legs=256, record_budget=20000):
        values = []
        for leg in legs:
            if len(values) >= max_legs:
                reject('joint calendar route budget exceeded; no demand omitted','BLOCKED_RESOURCE')
            values.append(leg)
        self.legs = tuple(values)
        self.indices = {leg.id:i for i,leg in enumerate(self.legs)}
        if len(self.indices) != len(self.legs) or service_plan.city_identity != city.identity:
            reject('joint calendar IDs or city differ')
        if tuple(service_plan.source_legs) != self.legs:
            reject('joint service plan source calendar differs')
        if step_s != service_plan.time_step_s:
            reject('joint step differs from service contract')
        self.step_s, self.record_budget = step_s, record_budget
        # Reuse validated car access/return construction only; this helper's
        # reference road is NEVER advanced. The service model below owns traffic.
        self.helper = None
        if any(leg.mode == 'car' or (leg.mode == 'noncar' and leg.intrazonal) for leg in self.legs):
            self.helper = ReleaseRuntime(city,self.legs,step_s=step_s,max_legs=max_legs,record_budget=record_budget)
        self.routes = self.helper.route_links if self.helper else {}
        self.internal_laws = self.helper.internal_laws if self.helper else {}
        self.plan = service_plan
        car = VehicleClass('car',preferred_mps=10.0)
        traffic = tuple(Route(k,v) for k,v in self.routes.items())
        classes = {k:car for k in self.routes}
        if not traffic and not service_plan.buses and not service_plan.freight:
            # Inert PacketNetwork clock route for internal-only activity. It is
            # never offered mass and never appears in the demand registry.
            tag = '__joint_clock__'
            if tag in self.indices:
                reject('reserved joint clock route label')
            traffic = (Route(tag,(service_plan.contract.groups[0].id,)),)
            classes[tag] = car
        self.service = service_plan.model(traffic_routes=traffic,
                         traffic_classes=classes,record_budget=record_budget)
        self.bus_meta = {m['passenger_id']:m for m in service_plan.metadata if 'passenger_id' in m}
        self.freight_meta = {m['leg_id']+':'+str(m['window']):m for m in service_plan.metadata if 'cargo_kg' in m}
        self.bus_leg = [self.indices[self.bus_meta[p.id]['leg_id']] for p in self.service.passengers]
        self.freight_leg = [self.indices[self.freight_meta[f.id]['leg_id']] for f in self.service.freight]
        assigned = {self.legs[i].id for i in self.bus_leg+self.freight_leg}
        self.unsupported = {leg.id:'no supported joint assignment' for leg in self.legs
                            if leg.id not in self.routes and leg.id not in self.internal_laws and leg.id not in assigned}
        self.identity = hashlib.sha256(json.dumps((self.service.identity,
            self.helper.identity if self.helper else None,
            [(leg.id,leg.depends_on,leg.minimum_dwell_s,leg.amounts.persons,leg.amounts.vehicles,leg.amounts.cargo_kg,
              [(w.start_s,w.end_s,w.probability) for w in leg.departures.windows]) for leg in self.legs]),
            sort_keys=True).encode()).hexdigest()

    def initial(self):
        zero = (0.0,)*len(self.legs)
        return JointReleaseState(self.identity,self.service.initial(),(),(),(),zero,zero,
                                 tuple(() for _ in self.legs),zero)

    def eligible(self, state, leg):
        if not leg.depends_on:
            return 1.0
        if leg.depends_on not in self.indices:
            return 0.0
        return math.fsum(f for t,f in state.receipts[self.indices[leg.depends_on]]
                         if t+leg.minimum_dwell_s <= state.time_s)

    def check(self,state):
        if state.model_id != self.identity or any(len(x)!=len(self.legs) for x in
                (state.released,state.completed,state.receipts,state.birth_carrier_s)):
            reject('joint checkpoint identity/schema differs')
        self.service.check(state.service)
        active = {}
        parts = [p for c in state.service.road.cells for q in c.packets for p in q.parts]
        parts += [p for queue in state.service.road.pending for q in queue for p in q.parts]
        for p in parts:
            active[p.tag] = active.get(p.tag,0.0)+p.mass
        for i,leg in enumerate(self.legs):
            carrier = ReleaseRuntime.carrier(leg)
            r,c = state.released[i],state.completed[i]
            tol = 1e-9*max(1,carrier)
            if (not all(math.isfinite(v) and v>=0 for v in (r,c,state.birth_carrier_s[i]))
                    or c>r+tol or r>carrier*leg.departures.fraction(0,state.time_s)+tol):
                reject('joint calendar conservation failure','IMPLEMENTATION_ERROR')
            if leg.id in self.unsupported and (r or c):
                reject('unsupported joint leg completed or released','IMPLEMENTATION_ERROR')
            if any(not math.isfinite(t) or not 0<=t<=state.time_s or not math.isfinite(f) or f<=0
                   for t,f in state.receipts[i]):
                reject('joint completion receipt time/fraction differs','IMPLEMENTATION_ERROR')
            if abs(math.fsum(f for _,f in state.receipts[i])*carrier-c)>tol:
                reject('joint completion receipt differs','IMPLEMENTATION_ERROR')
            if leg.depends_on and r>carrier*self.eligible(state,leg)+tol:
                reject('joint return precedes completed outward and dwell','IMPLEMENTATION_ERROR')
            egress = math.fsum(e.mass for e in state.egress if e.tag==leg.id)
            expected_birth = 0.0
            if leg.id in self.routes or leg.id in self.internal_laws:
                if r:
                    expected_birth = r*ReleaseRuntime.birth_between(leg.departures,0,r/carrier)
            bus_keys = [k for k,j in enumerate(self.bus_leg) if j==i]
            freight_keys = [k for k,j in enumerate(self.freight_leg) if j==i]
            if bus_keys:
                boarded=arrived=0.0
                for k in bus_keys:
                    p,v=self.service.passengers[k],state.service.passengers[k]
                    factor=carrier/leg.amounts.persons
                    count=(v.onboard+v.arrived)*factor
                    boarded+=count
                    arrived+=v.arrived*factor
                    expected_birth+=count*self.bus_meta[p.id]['birth_person_s']/p.persons
                if abs(r-boarded)>tol or abs(c+egress-arrived)>tol:
                    reject('joint bus stage and physical service ledger differ','IMPLEMENTATION_ERROR')
            if freight_keys:
                dispatched=arrived=0.0
                for k in freight_keys:
                    f=self.service.freight[k]
                    if state.service.freight_released[k]:
                        dispatched+=f.vehicles
                        expected_birth+=self.freight_meta[f.id]['birth_vehicle_s']
                    arrived+=state.service.freight_completed[k]
                if abs(r-dispatched)>tol or abs(c+egress-arrived)>tol:
                    reject('joint freight stage and physical service ledger differ','IMPLEMENTATION_ERROR')
            if abs(state.birth_carrier_s[i]-expected_birth)>1e-9*max(1,abs(expected_birth)):
                reject('joint original birth moment differs','IMPLEMENTATION_ERROR')
            stages = math.fsum(e.mass for e in state.entering+state.egress+state.internal if e.tag==leg.id)
            if leg.id in self.routes:
                stages += active.get(leg.id,0.0)
                if abs(r-c-stages)>tol:
                    reject('joint car stage and physical ledger differ','IMPLEMENTATION_ERROR')
            elif leg.id in self.internal_laws and abs(r-c-stages)>tol:
                reject('joint internal stage ledger differs','IMPLEMENTATION_ERROR')
        # Bind calendar/service counters to the physical class ledger as well
        # as active stage masses, so a fully completed forged cohort cannot hide.
        class_ledger = {c.name:c for c in state.service.road.class_ledger}
        if self.routes:
            physical = class_ledger['car']
            admitted = math.fsum(state.released[self.indices[k]] for k in self.routes)-math.fsum(e.mass for e in state.entering)
            outlet = math.fsum(state.completed[self.indices[k]] for k in self.routes)+math.fsum(e.mass for e in state.egress if e.tag in self.routes)
            if (abs(admitted-physical.released)>1e-9*max(1,physical.released)
                    or abs(outlet-physical.completed)>1e-9*max(1,physical.completed)):
                reject('joint car calendar and physical class ledger differ','IMPLEMENTATION_ERROR')
        if self.service.freight:
            name = self.service.network.vehicle_classes['freight:'+self.service.freight[0].id].name
            physical = class_ledger[name]
            admitted = math.fsum(f.vehicles for f,flag in zip(self.service.freight,state.service.freight_released) if flag)
            outlet = math.fsum(state.service.freight_completed)
            if (abs(admitted-physical.released)>1e-9*max(1,physical.released)
                    or abs(outlet-physical.completed)>1e-9*max(1,physical.completed)):
                reject('joint freight service and physical class ledger differ','IMPLEMENTATION_ERROR')
        for e in state.entering+state.egress+state.internal:
            if (e.tag not in self.indices or not all(math.isfinite(v) for v in (e.mass,e.born_s,e.delay_s))
                    or e.mass<=0 or e.born_s<0 or e.born_s>state.time_s+1e-8 or e.delay_s<0):
                reject('joint access checkpoint differs','IMPLEMENTATION_ERROR')

    def advance(self,state,end_s):
        self.check(state)
        count=(end_s-state.time_s)/self.step_s
        if not math.isfinite(count) or count<0 or abs(count-round(count))>1e-8:
            reject('joint horizon must align with fixed step')
        for _ in range(round(count)):
            previous=state
            t=state.time_s
            released,completed,birth=list(state.released),list(state.completed),list(state.birth_carrier_s)
            receipts=[list(x) for x in state.receipts]
            entering,egress,internal=list(state.entering),list(state.egress),list(state.internal)
            for i,leg in enumerate(self.legs):
                if leg.id not in self.routes and leg.id not in self.internal_laws:
                    continue
                carrier=ReleaseRuntime.carrier(leg)
                if not carrier:
                    continue
                lo=released[i]/carrier
                hi=min(leg.departures.fraction(0,t),self.eligible(state,leg))
                if hi<=lo:
                    continue
                mass=carrier*(hi-lo)
                born=ReleaseRuntime.birth_between(leg.departures,lo,hi)
                released[i]+=mass
                birth[i]+=mass*born
                hold=t-born if leg.depends_on else 0.0
                law=(self.internal_laws[leg.id] if leg.id in self.internal_laws
                     else self.helper.model.boundaries[leg.id].origin)
                target=internal if leg.id in self.internal_laws else entering
                target.extend(AccessEntry(leg.id,mass*w,born,delay+hold) for delay,w in law.atoms)
            offers=[]
            pending=[]
            for e in entering:
                if e.ready_s<=t+1e-10:
                    offers.append((e.tag,e.mass,e.mass*e.born_s))
                else:
                    pending.append(e)
            eligible=[]
            for p in self.service.passengers:
                meta=self.bus_meta[p.id]
                leg=self.legs[self.indices[meta['leg_id']]]
                window=leg.departures.windows[meta['window']]
                required=leg.departures.fraction(0,window.end_s)
                if not leg.depends_on or self.eligible(state,leg)+1e-10>=required:
                    eligible.append(p.id)
            try:
                service=self.service.step(state.service,offers,eligible_passengers=eligible)
            except Exception as exc:
                exc.checkpoint=previous
                raise
            end=service.road.time_s
            for event in service.last_events:
                if event.destination is None and event.tag in self.routes:
                    law=self.helper.model.boundaries[event.tag].destination
                    egress.extend(AccessEntry(event.tag,event.mass*w,event.end_s,delay) for delay,w in law.atoms)
            for k,p in enumerate(self.service.passengers):
                i=self.bus_leg[k]
                leg=self.legs[i]
                before,after=state.service.passengers[k],service.passengers[k]
                boarded=(after.onboard+after.arrived)-(before.onboard+before.arrived)
                factor=ReleaseRuntime.carrier(leg)/leg.amounts.persons
                meta=self.bus_meta[p.id]
                released[i]+=boarded*factor
                birth[i]+=boarded*factor*meta['birth_person_s']/p.persons
                arrived=after.arrived-before.arrived
                egress.extend(AccessEntry(leg.id,arrived*factor*w,end,delay)
                              for delay,w in meta['destination_access'] if arrived)
            for k,f in enumerate(self.service.freight):
                i=self.freight_leg[k]
                leg=self.legs[i]
                meta=self.freight_meta[f.id]
                if service.freight_released[k] and not state.service.freight_released[k]:
                    released[i]+=f.vehicles
                    birth[i]+=meta['birth_vehicle_s']
                arrival=service.freight_completed[k]-state.service.freight_completed[k]
                egress.extend(AccessEntry(leg.id,arrival*w,end,delay)
                              for delay,w in meta['destination_access'] if arrival)
            def finish(events):
                remaining=[]
                for e in events:
                    if e.ready_s<=end+1e-10:
                        i=self.indices[e.tag]
                        completed[i]+=e.mass
                        receipts[i].append((max(t,e.ready_s),e.mass/ReleaseRuntime.carrier(self.legs[i])))
                    else:
                        remaining.append(e)
                return tuple(remaining)
            egress,internal=finish(egress),finish(internal)
            if len(pending)+len(egress)+len(internal)+sum(map(len,receipts))>self.record_budget:
                exc=BudgetExceeded('joint journey record budget')
                exc.checkpoint=previous
                raise exc
            state=JointReleaseState(self.identity,service,tuple(pending),egress,internal,
                                    tuple(released),tuple(completed),tuple(tuple(x) for x in receipts),tuple(birth))
            self.check(state)
        return state

    def report(self,state):
        self.check(state)
        ledger={}
        moments={}
        for unit in ('persons','vehicles','cargo_kg'):
            requested=released=completed=moment=0.0
            for i,leg in enumerate(self.legs):
                amount=getattr(leg.amounts,unit)
                requested+=amount*leg.departures.fraction(0,state.time_s)
                carrier=ReleaseRuntime.carrier(leg)
                ratio=amount/carrier if carrier else 0.0
                released+=ratio*state.released[i]
                completed+=ratio*state.completed[i]
                moment+=ratio*state.birth_carrier_s[i]
            ledger[unit]=dict(requested=requested,released=released,completed=completed,
                              pending=requested-released,active=released-completed)
            moments[unit]=moment
        return dict(status='SCOPED_JOINT_MAP_EXECUTION',time_s=state.time_s,ledger=ledger,
                    released_intent_first_moments=moments,service=self.service.report(state.service),
                    unsupported=self.unsupported,assignment=self.plan.assignment_report(),
                    full_release_campaign='NOT_RUN',scope='one ServiceModel road owner; bus finite-window boarding and destination access closure')

    def save(self,path,state):
        self.check(state)
        service = state.service
        # Service records are an explicit fixed schema of tuples. Existing
        # whitelisted road/event/access codecs are reused without arbitrary types.
        raw_service = tuple(tuple(tuple(getattr(v,f.name) for f in fields(v)) for v in value)
                            if key in ('buses','passengers') else value
                            for key,value in ((f.name,getattr(service,f.name)) for f in fields(service)))
        values = tuple(raw_service if key=='service' else getattr(state,key)
                       for key in state.__dataclass_fields__)
        Path(path).write_text(json.dumps(encode(values),allow_nan=False))

    def load(self,path):
        values=list(decode(json.loads(Path(path).read_text())))
        raw=list(values[1])
        if len(raw)!=len(fields(ServiceState)):
            reject('joint service checkpoint schema differs')
        raw[2]=tuple(RunState(*x) for x in raw[2])
        raw[3]=tuple(PassengerState(*x) for x in raw[3])
        values[1]=ServiceState(*raw)
        state=JointReleaseState(*values)
        self.check(state)
        return state
