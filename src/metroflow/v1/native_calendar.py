"""Streaming frontend for the persistent Rust calendar registry.

This compiles exact calendar declarations and zero progress arrays, not road
routes, service assignments or a traffic state. It does not relax ReleaseDriver.
"""
from dataclasses import asdict
import itertools
import json
import math


def compile_native_calendar(schedule, *, byte_budget=2 * 1024**3, page_size=4096):
    """Retain the calendar in Rust, materializing only one Python page at a time.

    Activity measures and delay laws are losslessly interned as JSON metadata.
    Quantities remain f64 and IDs are losslessly encoded, never hashed identity.
    Missing native extension fails explicitly; there is no Python fallback.
    A dependent return must follow its outward leg, as FactorizedSchedule emits.
    byte_budget accounts persistent storage; an outer process RSS/address-space
    bound must cover Python pages, FFI conversion and allocation transients.
    """
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("positive integer page_size required")
    if isinstance(byte_budget, bool) or not isinstance(byte_budget, int) or byte_budget < 1:
        raise ValueError("positive integer byte_budget required")
    from _metroflow_rust import NativeCalendar

    registry = NativeCalendar(byte_budget, schedule.city_identity, schedule.identity)
    labels, profiles = {}, {}

    def label(value):
        # Keep the object beside its handle: identity lookup avoids re-hashing
        # full immutable polygon geometry on every leg and prevents ID reuse.
        key = id(value)
        if key not in labels:
            payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
            labels[key] = (value, registry.intern_label(json.dumps(payload, sort_keys=True, allow_nan=False)))
        return labels[key][1]

    def profile(value):
        key = id(value)
        if key not in profiles:
            profiles[key] = (value, registry.intern_profile(
                [(w.start_s, w.end_s, w.probability) for w in value.windows]
            ))
        return profiles[key][1]

    source = iter(schedule.iter_legs())
    while page := tuple(itertools.islice(source, page_size)):
        rows = []
        for leg in page:
            for measure in (leg.origin, leg.destination):
                if measure is not None and measure.city_identity != schedule.city_identity:
                    raise ValueError("native calendar activity belongs to another city")
            metadata = [label(leg.origin), label(leg.destination), label(leg.purpose),
                        label(leg.mode), label(leg.vehicle_class), profile(leg.departures),
                        label(leg.intrazonal), label(leg.endpoint_kind)]
            rows.append((leg.id, leg.cohort_id, leg.depends_on, metadata,
                         (leg.amounts.persons, leg.amounts.vehicles, leg.amounts.cargo_kg),
                         leg.minimum_dwell_s))
        registry.append(rows)
    return registry


def compile_native_factorized_calendar(schedule, *, byte_budget=2 * 1024**3):
    """Generate FactorizedSchedule OD legs directly in Rust.

    Python serializes marginal activity/profile/law declarations only. Rust
    performs the Cartesian enumeration, amount arithmetic and compact storage.
    The original streaming compiler remains an explicit independent oracle.
    No road/service state is activated by this calendar-only operation.
    """
    from _metroflow_rust import NativeCalendar
    from .activity import intrazonal_law
    from .demand import calendar_profiles
    from .factorized_demand import FactorizedSchedule

    if not isinstance(schedule, FactorizedSchedule):
        raise TypeError("direct native generation requires FactorizedSchedule")
    if isinstance(byte_budget, bool) or not isinstance(byte_budget, int) or byte_budget < 1:
        raise ValueError("positive integer byte_budget required")
    registry = NativeCalendar(byte_budget, schedule.city_identity, schedule.identity)
    labels, profiles = {}, {}

    def label(value):
        key = id(value)
        if key not in labels:
            payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
            labels[key] = (value, registry.intern_label(
                json.dumps(payload, sort_keys=True, allow_nan=False)))
        return labels[key][1]

    def profile(value):
        key = id(value)
        if key not in profiles:
            profiles[key] = (value, registry.intern_profile(
                [(w.start_s, w.end_s, w.probability) for w in value.windows]))
        return profiles[key][1]

    for support in (schedule.homes, schedule.jobs, schedule.services):
        if any(m.city_identity != schedule.city_identity for m in support):
            raise ValueError("native calendar activity belongs to another city")
    population = schedule.resident_stock
    job_support = math.fsum(m.mass for m in schedule.jobs)
    service_support = math.fsum(m.mass for m in schedule.services)
    service_assigned = (population * schedule.service_fraction *
                        (1 - schedule.external_service_fraction) -
                        schedule.unassigned_service_persons)
    target_specs = (
        ("work", schedule.allocated_workers, schedule.jobs, job_support, False),
        ("school", service_assigned * schedule.school_share,
         schedule.services, service_support, False),
        ("service", service_assigned * (1 - schedule.school_share),
         schedule.services, service_support, False),
        ("service", population * schedule.service_fraction * schedule.external_service_fraction,
         (None,), population, True),
    )
    none = label(None)
    targets, laws = [], []
    homes = []
    for home in schedule.homes:
        ratio = home.mass / population
        stationary = sum(mass > 0 for mass in (
            home.mass * (1 - schedule.worker_fraction - schedule.service_fraction),
            schedule.unassigned_service_persons * ratio,
            schedule.unassigned_workers * ratio,
        ))
        homes.append((label(home), home.mass, stationary))
    for purpose, total, destinations, support, external in target_specs:
        if not total:
            continue
        outward, back = calendar_profiles(schedule.day, purpose)
        destinations_by_block = {d.block_id: d for d in destinations if d is not None}
        targets.append((label(purpose), profile(outward), profile(back), total, support,
                        external, [(none if d is None else label(d),
                                    0.0 if d is None else d.mass) for d in destinations]))
        # Only matching blocks require intrazonal geometry, not the H x D pairs.
        for home in schedule.homes:
            destination = destinations_by_block.get(home.block_id)
            if destination is not None:
                laws.append((label(home), label(destination), label(purpose),
                             label(intrazonal_law(home, destination, depth=0))))
    modes = [(label(m.mode), label({"car": "car", "bus": "scheduled_bus", "noncar": None}[m.mode]),
              m.share, 1.0 if m.mode == "noncar" else m.occupancy_persons_veh,
              m.mode == "noncar") for m in schedule.modes]
    freight = []
    if schedule.freight_kg:
        freight = [(f"freight:{d.block_id}", label(d),
                    schedule.freight_kg * d.mass / service_support) for d in schedule.services]
    delivery, _ = calendar_profiles(schedule.day, "delivery")
    constants = [none, label("return_home"), label("interzonal"), label("intrazonal"),
                 label("external"), label("delivery"), label("freight"), label("freight")]
    registry.build_factorized(homes, targets, modes, laws, freight,
                              (population, schedule.service_fraction,
                               schedule.external_service_fraction, schedule.minimum_dwell_s,
                               schedule.freight_kg_per_vehicle), constants, profile(delivery))
    return registry


def decode_native_leg(registry, index):
    """Read one lossless record for inspection without rebuilding all Python legs."""
    ident, cohort, parent, metadata, amounts, dwell = registry.leg(index)
    keys = ("origin", "destination", "purpose", "mode", "vehicle_class",
            "departures", "intrazonal", "endpoint_kind")
    result = {"id": ident, "cohort_id": cohort, "depends_on": parent,
              "amounts": dict(zip(("persons", "vehicles", "cargo_kg"), amounts)),
              "minimum_dwell_s": dwell}
    for j, (key, handle) in enumerate(zip(keys, metadata)):
        result[key] = registry.profile(handle) if j == 5 else json.loads(registry.label(handle))
    return result
