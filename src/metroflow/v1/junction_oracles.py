"""Deterministic small junction fixtures, using the selected PacketNetwork lineage."""

from dataclasses import replace
import math
from ..ordered_lane import Lane
from ..ordered_network import Group, Route
from ..packet_network import PacketNetwork
from ..foundation_kinetics import VehicleClass
from ..environment.terrain import Terrain
from ..restored_city import Junction, Section, RoadMap
from ..active_suffix.common import Signal
from .city import compile_city
from .nodes import allocate_node, validate_signal_conflicts
from .lanegroups import LanePartition, compile_lanegroups, packet_model


def physical_model(groups, routes, *, classes=None, spaces=None, **kwargs):
    groups, routes = tuple(groups), tuple(routes)
    classes = classes or {r.tag: VehicleClass() for r in routes}
    spaces = spaces or {g.id: 200.0 for g in groups}
    return PacketNetwork(
        groups, routes, vehicle_classes=classes, space_capacities_m=spaces, **kwargs
    )


def group(key, tail, head, *, priority=1.0, entry=10.0, exit=10.0, signal=None):
    return Group(
        key, tail, head, Lane(1.0, 10.0, entry, exit, 200.0, interaction_rate=0.0), priority, signal
    )


def run(model, steps, offers=()):
    state = model.initial()
    events = []
    for k in range(steps):
        state, current = model.step(state, offers if k == 0 else ())
        events.extend(current)
    return state, tuple(events)


def branch_city():
    a, m, b, c = (
        Junction(k, xy)
        for k, xy in [
            ("a", (10.0, 50.0, 0.0)),
            ("m", (110.0, 50.0, 0.0)),
            ("b", (210.0, 50.0, 0.0)),
            ("c", (110.0, 150.0, 0.0)),
        ]
    )
    sections = tuple(
        Section(
            k,
            u.id,
            v.id,
            (u.xyz, v.xyz),
            "local",
            "surface",
            lanes,
            0,
            math.dist(u.xyz, v.xyz),
            0.0,
            failure,
        )
        for k, u, v, lanes, failure in [
            ("a", a, m, 2, None),
            ("b", m, b, 1, "leg-b"),
            ("c", m, c, 1, None),
        ]
    )
    return compile_city(RoadMap("junction", Terrain(1, 1000.0, (0.0,) * 4), (a, m, b, c), sections))


def paired_bridge_city():
    a, b, c = (
        Junction(k, xy)
        for k, xy in [
            ("a", (10.0, 50.0, 0.0)),
            ("b", (110.0, 50.0, 0.0)),
            ("c", (210.0, 50.0, 0.0)),
        ]
    )
    sections = tuple(
        Section(k, u.id, v.id, (u.xyz, v.xyz), "local", facility, 1, 1, 100.0, 0.0, failure)
        for k, u, v, facility, failure in [
            ("ab", a, b, "surface", None),
            ("bc", b, c, "bridge", "bridge"),
        ]
    )
    return compile_city(RoadMap("bridge", Terrain(1, 1000.0, (0.0,) * 4), (a, b, c), sections))


def junction_oracles():
    rows = []
    rates = allocate_node(
        {"a": {"c": 1.0}, "b": {"c": 1.0}}, {"a": 10.0, "b": 10.0}, {"c": 4.0}, {"a": 3.0, "b": 1.0}
    )
    model = physical_model(
        (group("a", "A", "M", priority=3), group("b", "B", "M"), group("c", "M", "D", entry=4)),
        (Route("F", ("a", "c")), Route("G", ("b", "c"))),
    )
    state, events = run(model, 2, (("F", 10.0), ("G", 10.0)))
    amounts = {
        tag: math.fsum(e.mass for e in events if e.source in ("a", "b") and e.tag == tag)
        for tag in ("F", "G")
    }
    rows.append(
        dict(
            case="merge3:1",
            status="PASS"
            if rates == {"a": 3.0, "b": 1.0} and math.isclose(amounts["F"], 3 * amounts["G"])
            else "NOT_ACCEPTED",
            rates_veh_s=rates,
            transferred_veh=amounts,
        )
    )
    city = branch_city()
    for independent in (False, True):
        parts = (
            (LanePartition("left", "a|0", 1, ("b|0",)), LanePartition("right", "a|0", 1, ("c|0",)))
            if independent
            else ()
        )
        contract = compile_lanegroups(city, parts, failures=(("leg-b", 0.0, 100.0, 0.0),))
        routes = (
            Route("X", ("left" if independent else "a|0", "b|0")),
            Route("Y", ("right" if independent else "a|0", "c|0")),
        )
        model = packet_model(contract, routes, {r.tag: VehicleClass() for r in routes})
        state, events = run(model, 60, (("X", 1.0), ("Y", 1.0)))
        moved = math.fsum(e.mass for e in events if e.tag == "Y" and e.destination is None)
        rows.append(
            dict(
                case="independentturn" if independent else "blockedshared",
                status="PASS" if (moved > 0 if independent else moved == 0) else "NOT_ACCEPTED",
                unblocked_turn_completed_veh=moved,
                released=state.released,
                completed=state.completed,
            )
        )
    signal = Signal(4.0, 2.0)
    g = group("g", "O", "D", signal=signal)
    model = physical_model((g,), (Route("R", ("g",)),))
    state, events = run(model, 6, (("R", 20.0),))
    valid = all(
        not 2 <= e.start_s % 4 < 4 and e.end_s <= e.start_s - e.start_s % 4 + 2 + 1e-9
        for e in events
    )
    rows.append(
        dict(
            case="redboundary",
            status="PASS" if valid and events else "NOT_ACCEPTED",
            events=len(events),
        )
    )
    city = paired_bridge_city()
    contract = compile_lanegroups(city, failures=(("bridge", 1.0, 20.0, 0.0),))
    rows.append(
        dict(
            case="bridgepairedclosure",
            status="PASS"
            if {w[0] for w in contract.windows} == {"bc|0", "bc|1"}
            else "NOT_ACCEPTED",
            closed_groups=[w[0] for w in contract.windows],
        )
    )
    car, truck = VehicleClass(), VehicleClass("freight", 15.0, 4.0, 0.7, 2.0, 3.0, 1.5, 12.0)
    model = physical_model(
        (group("g", "O", "D"),),
        (Route("car", ("g",)), Route("truck", ("g",))),
        classes={"car": car, "truck": truck},
        spaces={"g": 17.0},
    )
    state, _ = run(model, 1, (("car", 2.0), ("truck", 2.0)))
    used = model.occupied_space(state.cells[0])
    rows.append(
        dict(
            case="class_storage",
            status="PASS"
            if abs(used - 17) < 1e-9 and abs(state.cells[0].occupancy - 2) < 1e-9
            else "NOT_ACCEPTED",
            occupied_m=used,
            admitted_veh=state.cells[0].occupancy,
        )
    )
    validate_signal_conflicts(
        (g, replace(g, id="other", tail="P", signal=Signal(4.0, 2.0, 2.0))), (("g", "other"),)
    )
    return rows
