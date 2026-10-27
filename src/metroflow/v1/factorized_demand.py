"""Exact lazy independent OD calendar; storage scales with marginal support.

Iteration still costs O(H*(J+S)*modes). This changes representation, not the
coupling or transport cost. Worker shortfall is rejected unless explicitly
retained as an unassigned-at-home cohort under a separate policy.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math

from .activity import ActivityPatch, intrazonal_law
from .city import reject
from .demand import (Amounts, Cohort, DEFAULT_MODES, TripLeg, _measures,
                     compile_daily_demand)
from .schedules import daily_profiles


@dataclass(frozen=True, slots=True)
class FactorizedSchedule:
    homes: tuple
    jobs: tuple
    services: tuple
    day: str
    modes: tuple
    worker_fraction: float
    service_fraction: float
    school_share: float
    external_service_fraction: float
    freight_kg: float
    freight_kg_per_vehicle: float
    minimum_dwell_s: float
    worker_shortfall: str
    requested_workers: float
    allocated_workers: float
    unassigned_workers: float
    unassigned_service_persons: float
    resident_stock: float
    city_identity: str
    identity: str

    def iter_records(self):
        """Yield each cohort and its exact two legs, preserving dense order."""
        population = self.resident_stock
        job_support = math.fsum(m.mass for m in self.jobs)
        service_support = math.fsum(m.mass for m in self.services)
        service_assigned = (population * self.service_fraction *
                            (1 - self.external_service_fraction) - self.unassigned_service_persons)
        index = 0
        internal_laws = {}
        for home in self.homes:
            ratio = home.mass / population
            targets = (
                ('work', self.allocated_workers, self.jobs, job_support),
                ('school', service_assigned * self.school_share, self.services, service_support),
                ('service', service_assigned * (1-self.school_share), self.services, service_support),
                ('service', population*self.service_fraction*self.external_service_fraction, (None,), population),
            )
            for purpose, total, destinations, support in targets:
                if not total:
                    continue
                for dest in destinations:
                    for mode in self.modes:
                        mass = (total * ratio * dest.mass / support * mode.share if dest is not None
                                else home.mass*self.service_fraction*self.external_service_fraction*mode.share)
                        if mass <= 0:
                            continue
                        key = f'c{index}'
                        index += 1
                        outward, back = key+':out', key+':home'
                        cohort = Cohort(key, home, dest, mass, purpose, mode.mode, outward, back)
                        profile, return_profile = daily_profiles(self.day, purpose)
                        amounts = Amounts(mass, 0.0 if mode.mode == 'noncar' else mass/mode.occupancy_persons_veh)
                        internal = None
                        if dest is not None and home.block_id == dest.block_id:
                            pair = (home.block_id, dest.block_id, purpose)
                            if pair not in internal_laws:
                                internal_laws[pair] = intrazonal_law(home, dest, depth=0)
                            internal = internal_laws[pair]
                        vehicle_class = {'car':'car', 'bus':'scheduled_bus', 'noncar':None}[mode.mode]
                        yield cohort, (
                            TripLeg(outward,key,home,dest,purpose,mode.mode,vehicle_class,amounts,profile,intrazonal=internal),
                            TripLeg(back,key,dest,home,'return_home',mode.mode,vehicle_class,amounts,return_profile,
                                    outward,self.minimum_dwell_s,internal))
            for purpose, mass in (
                ('stay_home', home.mass*(1-self.worker_fraction-self.service_fraction)),
                ('unassigned_service', self.unassigned_service_persons*ratio),
                ('unassigned_work', self.unassigned_workers*ratio),
            ):
                if mass > 0:
                    yield Cohort(f'c{index}',home,None,mass,purpose,'none',None,None), ()
                    index += 1

    def iter_chunks(self, chunk_size=256):
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
            reject('positive integer materialization chunk required')
        chunk = []
        for record in self.iter_records():
            chunk.append(record)
            if len(chunk) == chunk_size:
                yield tuple(chunk)
                chunk = []
        if chunk:
            yield tuple(chunk)

    def iter_freight_legs(self):
        if self.freight_kg:
            support = math.fsum(m.mass for m in self.services)
            profile, _ = daily_profiles(self.day, 'delivery')
            for dest in self.services:
                cargo = self.freight_kg*dest.mass/support
                yield TripLeg(f'freight:{dest.block_id}',None,None,dest,'delivery','freight','freight',
                              Amounts(vehicles=cargo/self.freight_kg_per_vehicle,cargo_kg=cargo),profile)

    def iter_legs(self):
        for _, legs in self.iter_records():
            yield from legs
        yield from self.iter_freight_legs()


def _aggregate(measures, label):
    if not measures:
        return ()
    first = measures[0]
    mass = math.fsum(m.mass for m in measures)
    return (replace(first, block_id=label,
                    patches=(ActivityPatch(mass,(first.block_points[0],)),)),)


def compile_factorized_demand(residential, jobs=(), services=(), *, day='weekday',
                              worker_fraction=None, service_fraction=None, school_share=None,
                              modes=DEFAULT_MODES, external_service_fraction=0.0, freight_kg=0.0,
                              freight_kg_per_vehicle=1000.0, minimum_dwell_s=3600.0,
                              worker_shortfall='reject', max_factors=20000):
    homes = _measures(residential,'residential')
    if not homes or len({m.city_identity for m in homes}) != 1:
        reject('nonempty single-city homes required')
    city = homes[0].city_identity
    jobs, services = _measures(jobs,'job',city), _measures(services,'service',city)
    modes = tuple(modes)
    if (isinstance(max_factors,bool) or not isinstance(max_factors,int) or max_factors < 1):
        reject('positive integer factor budget required')
    if len(homes)+len(jobs)+len(services)+len(modes) > max_factors:
        reject('marginal factor budget exceeded; no demand omitted','BLOCKED_RESOURCE')
    if worker_shortfall not in ('reject','unassigned_home'):
        reject('explicit reject or unassigned_home worker policy required')
    wf = (0.5 if day == 'weekday' else 0.1) if worker_fraction is None else worker_fraction
    sf = (0.2 if day == 'weekday' else 0.4) if service_fraction is None else service_fraction
    ss = (0.25 if day == 'weekday' else 0.0) if school_share is None else school_share
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (wf,sf)) or wf+sf > 1:
        reject('disjoint resident activity fractions must be in [0,1] and sum <=1')
    population = math.fsum(m.mass for m in homes)
    requested = population*wf
    support = math.fsum(m.mass for m in jobs)
    allocated = min(requested,support) if worker_shortfall == 'unassigned_home' else requested
    # Reuse original semantic validation on constant-size marginal aggregates.
    # Distinct synthetic labels avoid creating unnecessary intrazonal geometry.
    validated = compile_daily_demand(
        _aggregate(homes,'__home'),_aggregate(jobs,'__jobs'),_aggregate(services,'__service'),
        day=day,worker_fraction=allocated/population,service_fraction=sf,school_share=ss,modes=modes,
        external_service_fraction=external_service_fraction,freight_kg=freight_kg,
        freight_kg_per_vehicle=freight_kg_per_vehicle,minimum_dwell_s=minimum_dwell_s)
    values = dict(homes=homes,jobs=jobs,services=services,day=day,modes=modes,worker_fraction=wf,
                  service_fraction=sf,school_share=ss,external_service_fraction=external_service_fraction,
                  freight_kg=freight_kg,freight_kg_per_vehicle=freight_kg_per_vehicle,
                  minimum_dwell_s=minimum_dwell_s,worker_shortfall=worker_shortfall,
                  requested_workers=requested,allocated_workers=allocated,unassigned_workers=requested-allocated,
                  unassigned_service_persons=validated.unassigned_service_persons,resident_stock=population,
                  city_identity=city)
    payload = {k: ([asdict(x) for x in v] if isinstance(v,tuple) else v) for k,v in values.items()}
    identity = hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return FactorizedSchedule(**values,identity=identity)
