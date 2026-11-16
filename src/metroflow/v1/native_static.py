"""Marginal-only frontend inputs for the persistent native calendar engine.

No calendar/OD leg is enumerated here. Geometry is compiled once per exact
activity measure; Python retains only marginal access laws, physical road
primitives and the independently declared fixed fleet. Missing doors remain
explicit ``None`` endpoints for the native pending-demand ledger.
"""

from dataclasses import asdict
import hashlib
import json

from ..foundation_kinetics import VehicleClass
from ..ordered_network import Route
from ..terrain_city.area_access import Portal
from .access import activity_access
from .activity import intrazonal_law
from .city import reject
from .factorized_demand import FactorizedSchedule
from .release_inventory import ReleaseInventory
from .release_services import compile_service_plan
from .transport import TransportModel


def _label(value):
    """The lossless label spelling used by both native calendar compilers."""
    return json.dumps(asdict(value), sort_keys=True, allow_nan=False)


def prepare_native_static(city, schedule, inventory, *, step_s=10.0,
                          record_budget=10000, event_budget=10000):
    """Prepare O(roads + marginal support + fixed fleet) engine declarations.

    Car endpoints require exactly one registered portal. Service endpoints use
    the existing minimum-coordinate door rule, independently of car eligibility.
    Bus availability keeps the maximum *uncompressed* ingress sample delay, not
    the maximum delay-bin mean. Rust owns OD routing, assignment and advancement.

    The three one-link routes below validate physical default parameters only;
    they carry no demand and are not included in the returned route registry.
    Actual native routes are built from the calendar and declared routing graph.
    """
    if not isinstance(schedule, FactorizedSchedule):
        raise TypeError("native static preparation requires FactorizedSchedule")
    if not isinstance(inventory, ReleaseInventory):
        raise TypeError("native static preparation requires ReleaseInventory")
    if schedule.city_identity != city.identity or inventory.city_identity != city.identity:
        reject("native static city, schedule and inventory identities differ", "CONTRACT_ERROR")
    if any(m.city_identity != city.identity
           for support in (schedule.homes, schedule.jobs, schedule.services) for m in support):
        reject("native static activity belongs to another city", "CONTRACT_ERROR")

    # An empty demand tuple validates only the fixed fleet and physical graph.
    # In particular, it never sizes vehicle supply from the number of OD pairs.
    fleet = compile_service_plan(
        city, (), inventory.corridors, depot_block_id=inventory.depot_block_id,
        step_s=step_s, max_runs=inventory.policy.max_runs,
    )
    contract = fleet.contract
    if not contract.groups:
        reject("native static preparation requires a nonempty road graph", "CONTRACT_ERROR")
    vehicle_classes = {
        "car": VehicleClass("car", preferred_mps=10),
        "freight": VehicleClass("freight", preferred_mps=10, length_m=10),
        "scheduled_bus": VehicleClass("scheduled_bus", preferred_mps=10, length_m=12),
    }
    reference = TransportModel(
        contract, tuple(Route(name, (contract.groups[0].id,)) for name in vehicle_classes),
        vehicle_classes, max_step_s=step_s,
        record_budget=record_budget, event_budget=event_budget,
    ).network
    templates = {c.vehicle.name: c for c in reference.motion.templates}
    speeds = dict(reference.motion.entry_speeds)
    classes = []
    for name in reference.class_names:
        c = templates[name]
        v = c.vehicle
        classes.append([
            v.preferred_mps, v.response_s, v.accel_mps2, v.brake_mps2,
            v.min_gap_m, v.headway_s, v.length_m, c.latent,
            c.restart_s_inv, c.hazard_s_inv, c.gap_scale_m,
            speeds[name], v.length_m + reference.standing_gap_m,
        ])

    nodes = {n.id: n for n in city.roadmap.nodes}
    portals = {}
    for portal in city.portals:
        portals.setdefault(portal.block_id, []).append(portal)
    doors = {block: min(options, key=lambda p: nodes[p.node_id].xyz)
             for block, options in portals.items()}
    activities = {}
    for support in (schedule.homes, schedule.jobs, schedule.services):
        for measure in support:
            label = _label(measure)
            if label in activities:
                continue
            door = doors.get(measure.block_id)
            car_node = service_node = None
            car_atoms = service_atoms = ()
            maximum_s = 0.0
            if door is not None:
                service_node = door.node_id
                law, _ = activity_access(
                    measure, (Portal(door.id, nodes[door.node_id].xyz[:2]),), depth=0,
                )
                service_atoms = tuple((a.delay_s, a.weight) for a in law.atoms)
                maximum_s = max(a.maximum_s for a in law.atoms)
                if len(portals[measure.block_id]) == 1:
                    car_node = door.node_id
                    car_atoms = law.condition(door.id)[1]
            activities[label] = (
                label, measure.block_id, car_node, service_node,
                car_atoms, service_atoms, maximum_s,
            )

    # Only same-block home/destination pairs need geometry. Each support has
    # unique block IDs by the FactorizedSchedule contract; no H x D scan occurs.
    laws = {}
    service_assigned = (schedule.resident_stock * schedule.service_fraction *
                        (1 - schedule.external_service_fraction) -
                        schedule.unassigned_service_persons)
    targets = ((schedule.allocated_workers, schedule.jobs),
               (service_assigned * schedule.school_share, schedule.services),
               (service_assigned * (1 - schedule.school_share), schedule.services))
    pairs = set()
    for total, support in targets:
        if not total:
            continue
        by_block = {m.block_id: m for m in support}
        for home in schedule.homes:
            destination = by_block.get(home.block_id)
            if destination is not None and (home, destination) not in pairs:
                law = intrazonal_law(home, destination, depth=0)
                laws[_label(law)] = law.atoms
                pairs.add((home, destination))

    payload = dict(
        schema="native_calendar_static_v1",
        city_identity=city.identity,
        schedule_identity=schedule.identity,
        inventory_identity=inventory.identity,
        max_service_runs=inventory.policy.max_runs,
        step_s=step_s,
        record_budget=reference.record_budget,
        event_budget=reference.event_budget,
        preserve_entry_intervals=reference.preserve_entry_intervals,
        activities=list(activities.values()),
        intrazonal_laws=list(laws.items()),
        class_names=list(reference.class_names),
        classes=classes,
        groups=[[g.physics.length_m, g.physics.speed_mps, g.physics.entry_rate,
                 g.physics.exit_rate, reference.space_capacities_m[g.id], g.priority]
                for g in reference.groups],
        signals=[(g.signal.cycle_s, g.signal.green_s, g.signal.offset_s)
                 if g.signal else None for g in reference.groups],
        incoming=[list(inc) for _, inc in sorted(reference.incoming.items())],
        windows=[(reference.index[g], a, b, f) for g, a, b, f in reference.windows],
        link_ids=[g.id for g in reference.groups],
        route_arcs=[(g.id, g.tail, g.head) for g in reference.groups],
        route_costs=[(g.id, g.physics.length_m / g.physics.speed_mps)
                     for g in reference.groups],
        allowed_turns=sorted(contract.allowed_turns),
        corridors=[(c.id, c.origin_block, c.destination_block, c.departure_s,
                    c.capacity_persons, c.dwell_s) for c in inventory.corridors],
        corridor_routes=[(b.id, list(b.legs[0])) for b in fleet.buses],
        block_doors=[(block, door.node_id) for block, door in sorted(doors.items())],
        depot_block_id=inventory.depot_block_id,
        depot_node_or_None=(doors[inventory.depot_block_id].node_id
                            if inventory.depot_block_id in doors else None),
    )
    payload["identity"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return payload
