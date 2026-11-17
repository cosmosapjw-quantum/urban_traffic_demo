"""Persistent aggregate daily cohorts and conservative request/completion ledger.

All quantities are fluid amounts. Persons, vehicles and cargo kg are independent
units. A calendar requests trips; only explicit completion receipts move people
to an activity or home. No traffic solver or per-person objects are introduced.
"""

from dataclasses import dataclass, asdict, replace
import hashlib
import json
import math
from functools import lru_cache

from .activity import ActivityMeasure, intrazonal_law
from .city import reject
from .journey import DelayLaw
from .schedules import DepartureProfile, DAY_S, daily_profiles


@lru_cache(maxsize=8)
def calendar_profiles(day, purpose):
    """Share the eight immutable day/purpose profile pairs without approximation.

    Only departure-measure objects are shared. Cohort amounts, identities,
    purposes, dependencies and progress remain distinct.
    """
    return daily_profiles(day, purpose)


@dataclass(frozen=True, slots=True)
class Amounts:
    persons: float = 0.0
    vehicles: float = 0.0
    cargo_kg: float = 0.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in (self.persons, self.vehicles, self.cargo_kg)):
            reject("finite nonnegative persons/vehicles/cargo kg required")

    def scaled(self, fraction):
        return Amounts(*(v * fraction for v in (self.persons, self.vehicles, self.cargo_kg)))


@dataclass(frozen=True, slots=True)
class ModeShare:
    mode: str
    share: float
    occupancy_persons_veh: float | None

    def __post_init__(self):
        if (
            self.mode not in ("car", "bus", "noncar")
            or not math.isfinite(self.share)
            or self.share <= 0
        ):
            reject("positive declared car/bus/noncar mode share required")
        if self.mode == "noncar":
            if self.occupancy_persons_veh is not None:
                reject("noncar has no vehicle occupancy")
        elif (
            self.occupancy_persons_veh is None
            or not math.isfinite(self.occupancy_persons_veh)
            or self.occupancy_persons_veh < 1
        ):
            reject("declared occupancy >=1 persons/veh required")


DEFAULT_MODES = (
    ModeShare("car", 0.6, 1.25),
    ModeShare("bus", 0.25, 25.0),
    ModeShare("noncar", 0.15, None),
)


@dataclass(frozen=True, slots=True)
class Cohort:
    id: str
    home: ActivityMeasure
    destination: ActivityMeasure | None
    persons: float
    purpose: str
    mode: str
    outbound_id: str | None
    return_id: str | None


@dataclass(frozen=True, slots=True)
class TripLeg:
    id: str
    cohort_id: str | None
    origin: ActivityMeasure | None
    destination: ActivityMeasure | None
    purpose: str
    mode: str
    vehicle_class: str | None
    amounts: Amounts
    departures: DepartureProfile
    depends_on: str | None = None
    minimum_dwell_s: float = 0.0
    intrazonal: DelayLaw | None = None

    @property
    def endpoint_kind(self):
        if self.origin is None or self.destination is None:
            return "external"
        if self.intrazonal is not None:
            return "intrazonal"
        return "interzonal"

    def requested(self, start_s, end_s):
        return self.amounts.scaled(self.departures.fraction(start_s, end_s))


@dataclass(frozen=True, slots=True)
class TripSchedule:
    city_identity: str
    day: str
    resident_stock: float
    cohorts: tuple[Cohort, ...]
    legs: tuple[TripLeg, ...]
    allocated_workers: float
    unassigned_service_persons: float
    identity: str
    prior: str = "declared synthetic cohort calendar; fractional vehicles from occupancy; bus fleet operations pending B01"


@dataclass(frozen=True, slots=True)
class TripProgress:
    requested: float = 0.0
    released: float = 0.0
    completed: float = 0.0
    completion_receipts: tuple[tuple[float, float], ...] = ()  # time s, fraction


@dataclass(frozen=True, slots=True)
class DemandLedger:
    schedule_identity: str
    time_s: float
    progress: tuple[TripProgress, ...]


def _measures(measures, kind, city=None):
    measures = tuple(measures)
    if any(m.kind != kind or (city is not None and m.city_identity != city) for m in measures):
        reject("activity kind or city identity mismatch")
    if len({m.block_id for m in measures}) != len(measures):
        reject("duplicate block activity measure")
    return tuple(sorted(measures, key=lambda m: m.block_id))


def compile_daily_demand(
    residential,
    jobs=(),
    services=(),
    *,
    day="weekday",
    worker_fraction=None,
    service_fraction=None,
    school_share=None,
    modes=DEFAULT_MODES,
    external_service_fraction=0.0,
    freight_kg=0.0,
    freight_kg_per_vehicle=1000.0,
    minimum_dwell_s=3600.0,
    max_cohorts=20000,
):
    """Allocate finite opportunity margins by proportional independent OD coupling.

    Workers are a subset of residents; service visitors are a disjoint subset.
    Insufficient jobs reject the requested calendar. Insufficient internal service
    places leave a visible unassigned cohort at home. No capacity is enlarged.
    Modes split cohorts once; outward and homeward legs refer to the same cohort.
    This fixed two-leg calendar does not claim a behavioural choice model.
    """
    homes = _measures(residential, "residential")
    if not homes or len({m.city_identity for m in homes}) != 1 or day not in ("weekday", "weekend"):
        reject("nonempty single-city homes and supported day required")
    city = homes[0].city_identity
    jobs, services = _measures(jobs, "job", city), _measures(services, "service", city)
    worker_fraction = (
        (0.5 if day == "weekday" else 0.1) if worker_fraction is None else worker_fraction
    )
    service_fraction = (
        (0.2 if day == "weekday" else 0.4) if service_fraction is None else service_fraction
    )
    school_share = (0.25 if day == "weekday" else 0.0) if school_share is None else school_share
    if (
        any(
            not math.isfinite(x) or not 0 <= x <= 1
            for x in (worker_fraction, service_fraction, external_service_fraction, school_share)
        )
        or worker_fraction + service_fraction > 1
    ):
        reject("disjoint resident activity fractions must be in [0,1] and sum <=1")
    if (
        not math.isfinite(freight_kg)
        or freight_kg < 0
        or not math.isfinite(freight_kg_per_vehicle)
        or freight_kg_per_vehicle <= 0
        or not math.isfinite(minimum_dwell_s)
        or minimum_dwell_s < 0
    ):
        reject("finite nonnegative cargo/dwell and positive freight payload required")
    modes = tuple(modes)
    if (
        len({m.mode for m in modes}) != len(modes)
        or abs(math.fsum(m.share for m in modes) - 1.0) > 1e-12
    ):
        reject("distinct mode probabilities must sum to one")
    population = math.fsum(m.mass for m in homes)
    workers = population * worker_fraction
    job_support = math.fsum(m.mass for m in jobs)
    if workers > job_support + 1e-9 * max(1.0, workers):
        reject("requested workers exceed job opportunity support", "PHYSICAL_INFEASIBLE")
    service_requested = population * service_fraction * (1 - external_service_fraction)
    service_support = math.fsum(m.mass for m in services)
    service_assigned = min(service_requested, service_support)
    if freight_kg and not services:
        reject("delivery requires explicit service opportunity endpoints", "PHYSICAL_INFEASIBLE")
    estimated = len(homes) * (
        len(modes)
        * (
            (len(jobs) if workers else 0)
            + (
                len(services) * (int(school_share > 0) + int(school_share < 1))
                if service_assigned
                else 0
            )
            + (1 if service_fraction * external_service_fraction else 0)
        )
        + 2
    )
    if isinstance(max_cohorts, bool) or not isinstance(max_cohorts, int) or max_cohorts < 1:
        reject("positive integer cohort budget required")
    if estimated > max_cohorts:
        reject("cohort/OD budget exceeded; no demand omitted", "BLOCKED_RESOURCE")
    cohorts, legs = [], []
    internal_laws = {}

    def add(home, dest, mass, purpose, mode):
        if mass <= 0:
            return
        key = f"c{len(cohorts)}"
        outward, back = key + ":out", key + ":home"
        cohorts.append(Cohort(key, home, dest, mass, purpose, mode.mode, outward, back))
        profile, return_profile = calendar_profiles(day, purpose)
        amounts = Amounts(mass, 0.0 if mode.mode == "noncar" else mass / mode.occupancy_persons_veh)
        internal = None
        if dest is not None and home.block_id == dest.block_id:
            pair = (home.block_id, dest.block_id, purpose)
            if pair not in internal_laws:
                internal_laws[pair] = intrazonal_law(home, dest, depth=0)
            internal = internal_laws[pair]
        vehicle_class = {"car": "car", "bus": "scheduled_bus", "noncar": None}[mode.mode]
        legs.extend(
            (
                TripLeg(
                    outward,
                    key,
                    home,
                    dest,
                    purpose,
                    mode.mode,
                    vehicle_class,
                    amounts,
                    profile,
                    intrazonal=internal,
                ),
                TripLeg(
                    back,
                    key,
                    dest,
                    home,
                    "return_home",
                    mode.mode,
                    vehicle_class,
                    amounts,
                    return_profile,
                    outward,
                    minimum_dwell_s,
                    internal,
                ),
            )
        )

    for home in homes:
        ratio = home.mass / population
        for purpose, total, targets, support in (
            ("work", workers, jobs, job_support),
            ("school", service_assigned * school_share, services, service_support),
            ("service", service_assigned * (1 - school_share), services, service_support),
        ):
            if total:
                for dest in targets:
                    for mode in modes:
                        add(
                            home,
                            dest,
                            total * ratio * dest.mass / support * mode.share,
                            purpose,
                            mode,
                        )
        for mode in modes:
            add(
                home,
                None,
                home.mass * service_fraction * external_service_fraction * mode.share,
                "service",
                mode,
            )
        unresolved = (service_requested - service_assigned) * ratio
        for purpose, mass in (
            ("stay_home", home.mass * (1 - worker_fraction - service_fraction)),
            ("unassigned_service", unresolved),
        ):
            if mass > 0:
                cohorts.append(
                    Cohort(f"c{len(cohorts)}", home, None, mass, purpose, "none", None, None)
                )
    if freight_kg:
        profile, _ = calendar_profiles(day, "delivery")
        for dest in services:
            cargo = freight_kg * dest.mass / service_support
            legs.append(
                TripLeg(
                    f"freight:{dest.block_id}",
                    None,
                    None,
                    dest,
                    "delivery",
                    "freight",
                    "freight",
                    Amounts(vehicles=cargo / freight_kg_per_vehicle, cargo_kg=cargo),
                    profile,
                )
            )
    if abs(math.fsum(c.persons for c in cohorts) - population) > 1e-9 * max(1.0, population):
        reject("cohort resident mass mismatch", "IMPLEMENTATION_ERROR")
    payload = dict(
        city=city,
        day=day,
        population=population,
        cohorts=[asdict(c) for c in cohorts],
        legs=[asdict(t) for t in legs],
    )
    identity = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return TripSchedule(
        city,
        day,
        population,
        tuple(cohorts),
        tuple(legs),
        workers,
        service_requested - service_assigned,
        identity,
    )


def initial_ledger(schedule):
    return DemandLedger(schedule.identity, 0.0, tuple(TripProgress() for _ in schedule.legs))


def _check(schedule, ledger):
    if ledger.schedule_identity != schedule.identity or len(ledger.progress) != len(schedule.legs):
        reject("demand ledger schedule identity mismatch")


def advance_requests(schedule, ledger, time_s):
    """Record calendar intent only; no implicit departure or completion."""
    _check(schedule, ledger)
    if not math.isfinite(time_s) or not ledger.time_s <= time_s <= DAY_S:
        reject("request time must advance within the same day")
    return DemandLedger(
        schedule.identity,
        time_s,
        tuple(
            replace(p, requested=t.departures.fraction(0.0, time_s))
            for t, p in zip(schedule.legs, ledger.progress)
        ),
    )


def _update(schedule, ledger, leg_id, fraction, completion):
    _check(schedule, ledger)
    if not math.isfinite(fraction) or fraction <= 0:
        reject("positive finite trip fraction required")
    index = next((i for i, t in enumerate(schedule.legs) if t.id == leg_id), None)
    if index is None:
        reject("unknown demand leg")
    trip, p = schedule.legs[index], ledger.progress[index]
    if completion:
        if fraction > p.released - p.completed + 1e-12:
            reject("completion exceeds released trip amount")
        if len(p.completion_receipts) >= 20000:
            reject("completion receipt budget exceeded", "BLOCKED_RESOURCE")
        value = replace(
            p,
            completed=p.completed + fraction,
            completion_receipts=p.completion_receipts + ((ledger.time_s, fraction),),
        )
    else:
        if fraction > p.requested - p.released + 1e-12:
            reject("release exceeds requested trip amount")
        if trip.depends_on is not None:
            parent = next(
                q for t, q in zip(schedule.legs, ledger.progress) if t.id == trip.depends_on
            )
            eligible = math.fsum(
                f
                for when, f in parent.completion_receipts
                if when + trip.minimum_dwell_s <= ledger.time_s
            )
            if fraction > eligible - p.released + 1e-12:
                reject("return requires completed outward activity and minimum dwell")
        value = replace(p, released=p.released + fraction)
    progress = list(ledger.progress)
    progress[index] = value
    return replace(ledger, progress=tuple(progress))


def release_trip(schedule, ledger, leg_id, fraction):
    """Fraction of this fixed cohort/leg; caller applies road capacity separately."""
    return _update(schedule, ledger, leg_id, fraction, False)


def complete_trip(schedule, ledger, leg_id, fraction):
    """Apply an explicit completion receipt; calendar time alone never completes."""
    return _update(schedule, ledger, leg_id, fraction, True)


def demand_report(schedule, ledger):
    _check(schedule, ledger)
    progress = {t.id: p for t, p in zip(schedule.legs, ledger.progress)}
    home, activity, external, moving = [], [], [], []
    for c in schedule.cohorts:
        if c.outbound_id is None:
            home.append(c.persons)
            continue
        a, b = progress[c.outbound_id], progress[c.return_id]
        home.append(c.persons * (1 - a.released + b.completed))
        (external if c.destination is None else activity).append(
            c.persons * (a.completed - b.released)
        )
        moving.append(c.persons * (a.released - a.completed + b.released - b.completed))
    stocks = dict(
        home=math.fsum(home),
        activity=math.fsum(activity),
        external_activity=math.fsum(external),
        in_transit=math.fsum(moving),
    )
    totals = {}
    for label, attribute in (
        ("requested", "requested"),
        ("released", "released"),
        ("completed", "completed"),
        ("pending", "pending"),
        ("active", "active"),
    ):
        fractions = [
            p.requested - p.released
            if attribute == "pending"
            else p.released - p.completed
            if attribute == "active"
            else getattr(p, attribute)
            for p in ledger.progress
        ]
        totals[label] = {
            unit: math.fsum(getattr(t.amounts, unit) * f for t, f in zip(schedule.legs, fractions))
            for unit in ("persons", "vehicles", "cargo_kg")
        }
    od = []
    for t, p in zip(schedule.legs, ledger.progress):
        od.append(
            dict(
                leg=t.id,
                origin=t.origin.block_id if t.origin else "EXTERNAL",
                destination=t.destination.block_id if t.destination else "EXTERNAL",
                purpose=t.purpose,
                mode=t.mode,
                vehicle_class=t.vehicle_class,
                endpoint_kind=t.endpoint_kind,
                requested=asdict(t.amounts.scaled(p.requested)),
            )
        )
    residual = math.fsum(stocks.values()) - schedule.resident_stock
    return dict(
        status="PASS"
        if abs(residual) <= 1e-9 * max(1.0, schedule.resident_stock)
        and min(stocks.values()) >= -1e-9
        else "NUMERICAL_ERROR",
        day=schedule.day,
        time_s=ledger.time_s,
        resident_stock=schedule.resident_stock,
        resident_stocks=stocks,
        resident_residual=residual,
        trip_amounts=totals,
        origin_destination=od,
        default_departure_bin_s=900.0,
        allocated_workers=schedule.allocated_workers,
        unassigned_service_persons=schedule.unassigned_service_persons,
        cohorts=len(schedule.cohorts),
        legs=len(schedule.legs),
        identity=schedule.identity,
        prior=schedule.prior,
        completion_semantics="explicit receipts only; pending requests are intent, not extra resident stock",
    )


@dataclass(frozen=True, slots=True)
class DepartureBatch:
    leg_id: str
    start_s: float
    end_s: float
    amounts: Amounts
    mean_birth_s: float


def iter_departures(schedule, step_s=900.0):
    """Calendar requests in <=15min default bins, never automatic releases.

    The conditional mean birth time preserves the first time moment of all
    three extensive units. The continuous profile remains the authority when
    a transport solver needs finer birth timing than a bin moment.
    """
    if not math.isfinite(step_s) or step_s <= 0:
        reject("positive finite departure bin width required")
    bins = math.ceil(DAY_S / step_s)
    if bins * len(schedule.legs) > 2000000:
        reject("departure batch budget exceeded; no demand omitted", "BLOCKED_RESOURCE")
    for i in range(bins):
        start, end = i * step_s, min(DAY_S, (i + 1) * step_s)
        for trip in schedule.legs:
            fraction = trip.departures.fraction(start, end)
            if fraction > 0:
                yield DepartureBatch(
                    trip.id,
                    start,
                    end,
                    trip.amounts.scaled(fraction),
                    trip.departures.first_moment_s(start, end) / fraction,
                )
