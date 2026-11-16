"""Streaming frontend for the persistent Rust calendar registry.

This compiles exact calendar declarations and zero progress arrays, not road
routes, service assignments or a traffic state. It does not relax ReleaseDriver.
"""
from dataclasses import asdict
import itertools
import json


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
