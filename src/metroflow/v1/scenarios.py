"""C02 finite synthetic two-zone city/day composition on the T04/B01 lineage.

Fixed timetable, declared modes and mean-access closure. No per-person objects.
Unserved modes and physically unfinished trips remain in the conservative ledger.
"""

from dataclasses import replace, asdict
import hashlib
import json
import math
import time
import resource

from .city import compile_city, PortalRef, reject
from .access_audit import fixture_city
from .activity import compile_activity
from .access import activity_access
from ..terrain_city.area_access import Portal
from ..restored_city import Section
from ..ordered_network import Route
from ..active_suffix.routing import Arc, candidate_paths
from ..foundation_kinetics import VehicleClass
from .kinetics import ClassMass
from .lanegroups import compile_lanegroups
from .services import ServiceModel, BusRun, PassengerCohort, FreightRun
from .demand import (
    compile_daily_demand,
    initial_ledger,
    advance_requests,
    release_trip,
    complete_trip,
    demand_report,
)

SCENARIOS = (
    "city10k_weekday",
    "city10k_weekend",
    "city1k_analytic",
    "city10k_bridgeclosure",
    "city10k_bypass",
    "city10k_growth_weekday",
)


def scenario_city(population=10000, *, bypass=False):
    base = fixture_city()
    nodes = tuple(
        replace(n, id=n.id + "x", xyz=(n.xyz[0] + 400, n.xyz[1], n.xyz[2]))
        for n in base.roadmap.nodes
    )
    sections = tuple(
        replace(
            s,
            id=s.id + "x",
            start=s.start + "x",
            end=s.end + "x",
            points=tuple((x + 400, y, z) for x, y, z in s.points),
        )
        for s in base.roadmap.sections
    )
    link = Section(
        "connector",
        "1",
        "0x",
        ((310.0, 10.0, 0.0), (410.0, 10.0, 0.0)),
        "local",
        "surface",
        1,
        1,
        100.0,
        0.0,
        "connector",
    )
    # Bypass is a real extra directed physical connection on the executed map.
    extra = ()
    if bypass:
        extra = (
            Section(
                "bypass",
                "2",
                "0x",
                ((310.0, 110.0, 0.0), (410.0, 10.0, 0.0)),
                "local",
                "surface",
                1,
                1,
                math.sqrt(20000.0),
                0.0,
                "bypass",
            ),
        )
    original = base.face_graph.blocks[0]
    blocks = (
        replace(original, residents=population, jobs=0, housing_capacity=population + 1000),
        replace(
            original,
            id="work",
            boundary=tuple(k + "x" for k in original.boundary),
            xy=(original.xy[0] + 400, original.xy[1]),
            residents=0,
            jobs=population,
            housing_capacity=population,
            job_capacity=population,
        ),
    )
    return compile_city(
        replace(
            base.roadmap,
            nodes=base.roadmap.nodes + nodes,
            sections=base.roadmap.sections + sections + (link,) + extra,
        ),
        blocks=blocks,
        portals=(PortalRef("home", "block", "1"), PortalRef("work", "work", "0x")),
    )


def compile_scenario(name="city10k_weekday", *, population=None, step_s=10.0):
    if name not in SCENARIOS or not math.isfinite(step_s) or step_s <= 0 or 3600 % step_s:
        reject("supported scenario and whole-hour aligned positive step required")
    population = population or (1000 if name == "city1k_analytic" else 10000)
    growth = name == "city10k_growth_weekday"
    city = scenario_city(population, bypass=name == "city10k_bypass")
    growth_evidence = None
    if growth:
        from .development import GrowthModel, DevelopmentSite, compile_entry
        from .timing_oracles import timing_fixture
        from .observations import completed_route_observations
        from .accessibility import compile_accessibility

        physical = timing_fixture(0.1, window=0, lengths=(100.0,))
        completed = physical.advance(physical.initial(), 60)
        observations = completed_route_observations(
            physical,
            completed,
            since_s=0,
            sensor_xy={"trip": (0.0, 0.0)},
            version=physical.identity,
        )
        entry = compile_entry(
            city,
            compile_activity(city, "block"),
            "home",
            capacity_veh_s=1,
            corridor=((300.0, 20.0), (310.0, 10.0)),
        )
        gm = GrowthModel(city, (DevelopmentSite("block", entry, 100),), budget_m=100)
        snapshot = compile_accessibility(
            city.identity, tuple(("block", o) for o in observations), 60
        )
        gs = gm.advance(gm.initial(), snapshot, 3600, requested_increment=100)
        city = gm.materialize_city(gs)
        growth_evidence = dict(
            previous_population=population,
            pending=gs.pending_increment,
            completed_access_stamp_s=60,
            slow_response_s=3600,
            next_calendar_population=sum(dict(gs.allocations).values()),
        )
    day = "weekend" if name == "city10k_weekend" else "weekday"
    homes = (compile_activity(city, "block"),)
    jobs = (compile_activity(city, "work", "job"),)
    services = (compile_activity(city, "work", "service", service_stock=population),)
    schedule = compile_daily_demand(
        homes,
        jobs,
        services,
        day=day,
        freight_kg=1000,
        service_fraction=0.2 if day == "weekday" else 0.4,
        school_share=0.0,
    )
    contract = compile_lanegroups(city, dt_s=step_s)
    if name == "city10k_bridgeclosure":
        # A declared intervention window affects the same physical connector in both directions.
        ids = [b.link_id for b in city.transport_graph.crosswalk if b.section_id == "connector"]
        contract = replace(contract, windows=tuple((e, 7 * 3600.0, 12 * 3600.0, 0.0) for e in ids))
    groups = {g.id: g for g in contract.groups}
    arcs = tuple(Arc(g.id, g.tail, g.head) for g in contract.groups)
    costs = {g.id: g.physics.length_m / g.physics.speed_mps for g in contract.groups}
    gates = {"block": "1", "work": "0x"}
    routes, access = {}, {}
    for trip in schedule.legs:
        if trip.mode == "freight":
            origin, dest = "1", "0x"
        elif trip.endpoint_kind == "interzonal":
            origin, dest = gates[trip.origin.block_id], gates[trip.destination.block_id]
        else:
            continue
        found = candidate_paths(
            arcs, costs, origin, dest, 1, allowed_turns=contract.allowed_turns
        ).paths
        if not found:
            continue
        routes[trip.id] = found[0]
        means = []
        for measure, node in ((trip.origin, origin), (trip.destination, dest)):
            if measure is None:
                means.append(0.0)
            else:
                xy = next(n.xyz[:2] for n in city.roadmap.nodes if n.id == node)
                law, _ = activity_access(measure, (Portal(node, xy),), depth=0)
                means.append(law.mean_s)
        access[trip.id] = tuple(means)
    bus_class = VehicleClass("scheduled_bus", preferred_mps=10.0, length_m=12.0)
    freight_class = VehicleClass("freight", preferred_mps=10.0, length_m=10.0)
    car_class = VehicleClass("car", preferred_mps=10.0)
    buses = []
    passengers = []
    freight = []
    traffic = []
    classes = {}
    bus_index = {}
    freight_index = {}
    for trip in schedule.legs:
        if trip.id not in routes:
            continue
        if trip.mode == "bus":
            departure = max(w.end_s for w in trip.departures.windows) + 600
            bus_index[trip.id] = len(passengers)
            buses.append(
                BusRun(trip.id, (routes[trip.id],), (departure,), 100.0, 10.0, frozenset(groups))
            )
            passengers.append(
                PassengerCohort(trip.id, trip.id, 0, 1, departure - 10, trip.amounts.persons)
            )
        elif trip.mode == "freight":
            indices = []
            for i, w in enumerate(trip.departures.windows):
                indices.append(len(freight))
                freight.append(
                    FreightRun(
                        trip.id + ":" + str(i),
                        routes[trip.id],
                        w.end_s,
                        trip.amounts.vehicles * w.probability,
                        trip.amounts.cargo_kg * w.probability,
                        2000.0,
                        5000.0,
                        frozenset(groups),
                    )
                )
            freight_index[trip.id] = tuple(indices)
        elif trip.mode == "car":
            tag = "daily:" + trip.id
            traffic.append(Route(tag, routes[trip.id]))
            classes[tag] = car_class
    control = hashlib.sha256(
        json.dumps(
            [
                (
                    t.origin.block_id if t.origin else None,
                    t.destination.block_id if t.destination else None,
                    t.mode,
                    t.purpose,
                    asdict(t.amounts),
                    asdict(t.departures),
                )
                for t in schedule.legs
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    model = ServiceModel(
        contract,
        buses,
        passengers,
        freight,
        bus_class=bus_class,
        freight_class=freight_class,
        step_s=step_s,
        traffic_routes=traffic,
        traffic_classes=classes,
        templates=tuple(
            ClassMass(c, 1.0, 1.0, 0.0, 0.0) for c in (car_class, bus_class, freight_class)
        ),
        entry_speeds={c.name: 10.0 for c in (car_class, bus_class, freight_class)},
        record_budget=200000,
    )
    return dict(
        name=name,
        city=city,
        schedule=schedule,
        model=model,
        routes=routes,
        access=access,
        bus_index=bus_index,
        freight_index=freight_index,
        step_s=step_s,
        intervention="endogenous_population_increment100"
        if growth
        else "controlled_same_calendar"
        if name in ("city10k_bypass", "city10k_bridgeclosure")
        else "baseline",
        growth_evidence=growth_evidence,
        demand_control_identity=control,
        routing_policy="fixed legal free-time route; no present incident truth lookup",
    )


def run_scenario(name="city10k_weekday", *, days=1, out=None, population=None, step_s=10.0):
    """Execute an actual full day. Multi-day reallocation is explicitly unsupported."""
    if days != 1:
        reject(
            "one frozen daily calendar per run; multi-day recomposition unsupported",
            "UNSUPPORTED_REQUEST",
        )
    started = time.perf_counter()
    spec = compile_scenario(name, population=population, step_s=step_s)
    schedule, model = spec["schedule"], spec["model"]
    road = model.initial()
    ledger = initial_ledger(schedule)
    n = len(schedule.legs)
    pending_birth = [0.0] * n
    offered = [0.0] * n
    source = []
    finish = []
    history = []
    event_count = 0
    sum_exit_birth = 0.0
    exit_mass = 0.0
    class_durations = {}
    am = pm = 0.0
    # Queues contain extensive fractions/time moments, never passenger IDs.
    for tick in range(round(86400 / step_s)):
        t = tick * step_s
        end = t + step_s
        ledger = advance_requests(schedule, ledger, t)
        for i, trip in enumerate(schedule.legs):
            pending_birth[i] += trip.departures.first_moment_s(max(0.0, t - step_s), t)
        # Complete only physical/delay receipts due at this actual boundary.
        remaining = []
        for due, i, f in finish:
            if due <= t + 1e-8:
                ledger = complete_trip(schedule, ledger, schedule.legs[i].id, f)
            else:
                remaining.append((due, i, f))
        finish = remaining
        offers = []
        remaining = []
        for due, i, f, birth in source:
            if due <= t + 1e-8:
                trip = schedule.legs[i]
                offers.append(
                    ("daily:" + trip.id, trip.amounts.vehicles * f, trip.amounts.vehicles * birth)
                )
                offered[i] += f
                if t < 12 * 3600:
                    am += trip.amounts.vehicles * f
                else:
                    pm += trip.amounts.vehicles * f
            else:
                remaining.append((due, i, f, birth))
        source = remaining
        eligible_bus = set()
        for i, trip in enumerate(schedule.legs):
            p = ledger.progress[i]
            eligible = p.requested - p.released
            if trip.depends_on:
                parent = next(
                    q for leg, q in zip(schedule.legs, ledger.progress) if leg.id == trip.depends_on
                )
                allowed = math.fsum(
                    f for when, f in parent.completion_receipts if when + trip.minimum_dwell_s <= t
                )
                eligible = min(eligible, max(0.0, allowed - p.released))
            if trip.mode == "bus":
                if eligible > 1e-12:
                    eligible_bus.add(trip.id)
                continue
            if trip.mode == "freight" or eligible <= 1e-12:
                continue
            if trip.id not in spec["routes"]:
                # Unsupported/external/intrazonal remains visible pending, never zero-time complete.
                continue
            total_pending = p.requested - p.released
            birth = pending_birth[i] * eligible / total_pending
            pending_birth[i] -= birth
            ledger = release_trip(schedule, ledger, trip.id, eligible)
            origin, egress = spec["access"][trip.id]
            if trip.mode == "car":
                source.append((t + origin, i, eligible, birth))
            else:
                length = math.fsum(
                    next(g.physics.length_m for g in model.network.groups if g.id == e)
                    for e in spec["routes"][trip.id]
                )
                finish.append((t + origin + length / 1.4 + egress, i, eligible))
        before = road
        road = model.step(road, offers=tuple(offers), eligible_passengers=eligible_bus)
        events = road.last_events
        for e in events:
            if e.destination is not None:
                continue
            event_count += 1
            exit_mass += e.mass
            elapsed = e.mass * (e.start_s + e.end_s) / 2 - e.birth_moment
            sum_exit_birth += elapsed
            cls = model.network.vehicle_classes[e.tag].name
            total, mass = class_durations.get(cls, (0.0, 0.0))
            class_durations[cls] = (total + elapsed, mass + e.mass)
            if e.tag.startswith("daily:"):
                leg = e.tag[len("daily:") :]
                i = next(i for i, x in enumerate(schedule.legs) if x.id == leg)
                f = e.mass / schedule.legs[i].amounts.vehicles
                finish.append((end + spec["access"][leg][1], i, f))
        ledger = advance_requests(schedule, ledger, end)
        for i, trip in enumerate(schedule.legs):
            if trip.mode == "bus" and trip.id in spec["bus_index"]:
                k = spec["bus_index"][trip.id]
                a, b = before.passengers[k], road.passengers[k]
                released = (a.waiting - b.waiting) / trip.amounts.persons
                complete = (b.arrived - a.arrived) / trip.amounts.persons
                if released > 1e-12:
                    ledger = release_trip(schedule, ledger, trip.id, released)
                if complete > 1e-12:
                    finish.append((end + spec["access"][trip.id][1], i, complete))
            elif trip.mode == "freight":
                indices = spec["freight_index"].get(trip.id, ())
                for k in indices:
                    f = model.freight[k]
                    if road.freight_released[k] and not before.freight_released[k]:
                        ledger = release_trip(
                            schedule, ledger, trip.id, f.vehicles / trip.amounts.vehicles
                        )
                    delta = road.freight_completed[k] - before.freight_completed[k]
                    if delta > 1e-12:
                        ledger = complete_trip(
                            schedule, ledger, trip.id, delta / trip.amounts.vehicles
                        )
        if (tick + 1) % round(3600 / step_s) == 0:
            history.append(
                dict(
                    time_s=end,
                    released_veh=road.road.released,
                    completed_veh=road.road.completed,
                    active_veh=road.road.released - road.road.completed,
                )
            )
    for due, i, f in finish:
        if due <= 86400.0 + 1e-8:
            ledger = complete_trip(schedule, ledger, schedule.legs[i].id, f)
    finish = [(due, i, f) for due, i, f in finish if due > 86400.0 + 1e-8]
    report = demand_report(schedule, ledger)
    service = model.report(road)
    if (
        abs(
            road.road.released
            - road.road.completed
            - math.fsum(c.occupancy for c in road.road.cells)
            - math.fsum(p.mass for group in road.road.pending for p in group)
        )
        > 1e-6
    ):
        reject("road day mass ledger failure", "IMPLEMENTATION_ERROR")
    scheduled = sum(t.amounts.persons for t in schedule.legs)
    completed = report["trip_amounts"]["completed"]["persons"]
    result = dict(
        status=report["status"],
        scenario=name,
        day=schedule.day,
        time_s=86400.0,
        city_identity=spec["city"].identity,
        demand_identity=schedule.identity,
        demand_control_identity=spec["demand_control_identity"],
        resident_stock=schedule.resident_stock,
        road_throughput_veh_s=road.road.completed / 86400.0,
        road_active_density_veh_per_m=(road.road.released - road.road.completed)
        / math.fsum(dict(spec["model"].network.space_capacities_m).values()),
        intervention=spec["intervention"],
        growth_evidence=spec["growth_evidence"],
        demand=report,
        services=service,
        service_passenger_measure="planned person-trip bookings incl conditional returns; not extra resident stock physically at stops",
        hourly=history,
        am_actual_road_vehicles=am,
        pm_actual_road_vehicles=pm,
        completed_outlet_events=event_count,
        recorded_birth_to_outlet_mean_s=sum_exit_birth / exit_mass if exit_mass else None,
        class_recorded_birth_to_outlet_mean_s={c: t / m for c, (t, m) in class_durations.items()},
        clock_scope={
            "car": "calendar first moment through origin access and actual road outlet",
            "scheduled_bus": "actual scheduled run source offer to actual outlet",
            "freight": "actual run source offer to actual outlet",
        },
        whole_person_trip_mean_s=None,
        p95_s=None,
        p95_status="UNSUPPORTED_JOINT_TRIP_DISTRIBUTION",
        completed_person_trips=completed,
        scheduled_person_trips=scheduled,
        unfinished_person_trips=scheduled - completed,
        access_pending_records=len(source),
        egress_or_noncar_pending_records=len(finish),
        access_pending_persons=math.fsum(
            schedule.legs[i].amounts.persons * f for _, i, f, _ in source
        ),
        egress_or_noncar_pending_persons=math.fsum(
            schedule.legs[i].amounts.persons * f for _, i, f in finish
        ),
        road_source_pending_vehicles=math.fsum(p.mass for q in road.road.pending for p in q),
        road_active_vehicles=math.fsum(c.occupancy for c in road.road.cells),
        bus_calendar_vehicle_equivalents_are_not_emitted=True,
        analytic_scope="calendar integral and finite scheduled boarding/fleet counts; not analytic travel time",
        calendar_unreleased_person_trips=report["trip_amounts"]["pending"]["persons"],
        wall_s=time.perf_counter() - started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        step_s=step_s,
        routing_policy=spec["routing_policy"],
        approximations=[
            "step-boundary source and arrival times",
            "mean internal access/egress delay; not full joint law",
            "fixed timetable capacity100 independent demand",
            "road routing frozen legal baseline, not dynamic assignment",
        ],
        unrun_metrics={"full_ci": None, "full_city_100k_performance": None},
    )
    if out:
        from .reporting import write_scenario_report

        write_scenario_report(out, result, spec["city"])
    return result
