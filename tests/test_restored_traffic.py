"""Observable directional/physical compilation, legal planning and aggregate runs."""

import math
from dataclasses import replace
import pytest
from metroflow.restored_city import Junction, Section, RoadMap
from metroflow.environment.terrain import Terrain
from metroflow.restored_traffic import compile_traffic
from metroflow.active_suffix import Model, Config, Demand
from metroflow.active_suffix.routing import candidate_paths, Arc


def section(
    key, u, v, points, hierarchy="local", facility="surface", lanes=(1, 1), group=None, role=None
):
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    grade = max(abs(a[2] - b[2]) / math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]))
    return Section(
        key, u, v, tuple(points), hierarchy, facility, *lanes, length, grade, group, role
    )


def interchange():
    coords = {
        "O": (0.0, 0.0, 0.0),
        "A": (100.0, 0.0, 0.0),
        "H": (300.0, 100.0, 10.0),
        "I": (500.0, 100.0, 10.0),
        "B": (700.0, 0.0, 0.0),
        "D": (800.0, 0.0, 0.0),
    }
    nodes = tuple(Junction(k, p, int(k in ("H", "I"))) for k, p in coords.items())
    specs = [
        ("oa", "O", "A", "local", "surface", (1, 1), None, None),
        ("on", "A", "H", "collector", "ramp", (1, 0), "ic", "on_ramp"),
        ("main", "H", "I", "expressway", "mainline", (2, 0), "structure", ""),
        ("off", "I", "B", "collector", "ramp", (1, 0), "ic2", "off_ramp"),
        ("bd", "B", "D", "arterial", "surface", (2, 2), None, None),
    ]
    sections = tuple(
        section(k, u, v, (coords[u], coords[v]), h, f, n, g, r or None)
        for k, u, v, h, f, n, g, r in specs
    )
    return RoadMap("fixture", Terrain(1, 1000.0, (0.0,) * 4), nodes, sections)


def test_no_reverse_mainline_or_ramp_is_created():
    c = compile_traffic(interchange(), signals=False)
    ids = {r.id for r in c.roads}
    assert ids == {"oa|0", "oa|1", "on|0", "main|0", "off|0", "bd|0", "bd|1"}
    assert ("on|0", "main|0") in c.allowed_turns
    assert ("main|0", "off|0") in c.allowed_turns
    arcs = tuple(Arc(r.id, r.tail, r.head) for r in c.roads)
    costs = {r.id: r.length_m / r.free_speed_mps for r in c.roads}
    assert candidate_paths(arcs, costs, "D", "O", 1, allowed_turns=c.allowed_turns).paths == ()


def test_lanes_set_aggregate_storage_and_capacity_without_car_records():
    city = interchange()
    r = {r.id: r for r in compile_traffic(city, signals=False).roads}
    assert r["bd|0"].storage_veh == pytest.approx(0.12 * 2 * 100.0)
    assert r["bd|0"].capacity_veh_s == pytest.approx(0.55 * 2)
    assert r["main|0"].free_speed_mps > r["oa|0"].free_speed_mps
    assert r["main|0"].priority > r["on|0"].priority


def test_geometry_curve_limits_free_speed_instead_of_endpoint_chord():
    pts = tuple(
        (10 * math.cos(k * math.pi / 16), 10 * math.sin(k * math.pi / 16), 0.0) for k in range(9)
    )
    s = section("bend", "O", "D", pts, "arterial")
    city = RoadMap(
        "curve",
        Terrain(1, 100.0, (0.0,) * 4),
        (Junction("O", pts[0]), Junction("D", pts[-1])),
        (s,),
    )
    r = compile_traffic(city, signals=False).roads[0]
    assert r.free_speed_mps <= math.sqrt(2.0 * 10.0) + 1e-7
    assert r.length_m == pytest.approx(s.length_m)


def test_malformed_ramp_direction_is_rejected_not_repaired():
    c = interchange()
    bad = replace(
        c, sections=tuple(replace(s, backward_lanes=1) if s.id == "on" else s for s in c.sections)
    )
    with pytest.raises(ValueError, match="ramp"):
        compile_traffic(bad)


def test_elevated_projection_has_no_created_exchange():
    nodes = (
        Junction("O", (0.0, 0.0, 0.0)),
        Junction("D", (100.0, 0.0, 0.0)),
        Junction("X", (50.0, -50.0, 10.0), 1),
        Junction("Y", (50.0, 50.0, 10.0), 1),
    )
    a = section("ground", "O", "D", (nodes[0].xyz, nodes[1].xyz))
    b = section("upper", "X", "Y", (nodes[2].xyz, nodes[3].xyz), "expressway", "mainline", (2, 0))
    c = compile_traffic(
        RoadMap("flyover", Terrain(1, 100.0, (0.0,) * 4), nodes, (a, b)), signals=False
    )
    assert not any(i.startswith("ground") and j.startswith("upper") for i, j in c.allowed_turns)
    arcs = tuple(Arc(r.id, r.tail, r.head) for r in c.roads)
    assert not candidate_paths(
        arcs, {r.id: 10.0 for r in c.roads}, "O", "Y", 1, allowed_turns=c.allowed_turns
    ).paths


def test_planning_skim_obeys_same_turn_graph_as_transport():
    from metroflow.active_suffix import Road
    from metroflow.environment.demand import District, travel_skims

    roads = (
        Road("oa", "O", "A", 10.0, 10.0, 1.0, 20.0),
        Road("ad", "A", "D", 10.0, 10.0, 1.0, 20.0),
        Road("ob", "O", "B", 50.0, 10.0, 1.0, 20.0),
        Road("bd", "B", "D", 50.0, 10.0, 1.0, 20.0),
    )
    areas = (District("o", "O", 100, 0, 0, ("a",)), District("d", "D", 0, 40, 0, ("b",)))
    costs = travel_skims(roads, areas, allowed_turns=frozenset({("ob", "bd")}))
    assert costs[0][1] == pytest.approx(10.0)  # NOT the illegal 2-second node path
    assert math.isinf(costs[1][0])
    assert costs[0][0] == 120.0  # separate intrazonal planning deterrence


def test_illegal_worker_job_support_is_not_admitted_by_demand_planner():
    from metroflow.active_suffix import Road
    from metroflow.environment.terrain import Network, Node, Link
    from metroflow.environment.landuse import City, Zone
    from metroflow.environment.demand import plan_commute, DemandInfeasible

    network = Network(
        (Node("O", 100.0, 100.0, 0.0), Node("D", 700.0, 700.0, 0.0)),
        (Link("od", "O", "D", 1000.0, 0.0, "surface", 1000.0),),
        (("O", 0), ("D", 0)),
        (),
    )
    zones = (
        Zone("a", 100.0, 100.0, 10000.0, 6500.0, 0.0, "residential", "O", 100, 0, 0, 100, 0),
        Zone("b", 700.0, 700.0, 10000.0, 6500.0, 0.0, "commercial", "D", 0, 40, 0, 0, 40),
    )
    city = City(Terrain(2, 400.0, (0.0,) * 9), network, zones, 100, 40)
    roads = (
        Road("oa", "O", "A", 100.0, 10.0, 1.0, 20.0),
        Road("ad", "A", "D", 100.0, 10.0, 1.0, 20.0),
    )
    with pytest.raises(DemandInfeasible, match="support"):
        plan_commute(city, roads, divisions=2, allowed_turns=frozenset())


def bridge_diamond():
    coords = {
        "O": (0.0, 0.0, 0.0),
        "A": (100.0, 0.0, 0.0),
        "D": (200.0, 0.0, 0.0),
        "B": (100.0, 200.0, 0.0),
    }
    nodes = tuple(Junction(k, p) for k, p in coords.items())
    sections = (
        section("oa", "O", "A", (coords["O"], coords["A"])),
        section("ad", "A", "D", (coords["A"], coords["D"]), "arterial", "bridge", (2, 2), "bridge"),
        section("ob", "O", "B", (coords["O"], coords["B"])),
        section("bd", "B", "D", (coords["B"], coords["D"])),
    )
    return RoadMap("bridge_diamond", Terrain(1, 1000.0, (0.0,) * 4), nodes, sections)


def test_bridge_failure_expands_to_both_directions_and_rejects_unknown_group():
    from metroflow.restored_traffic import structure_windows

    c = compile_traffic(bridge_diamond(), signals=False)
    windows = structure_windows(c, (("bridge", 20.0, 120.0, 0.0),))
    assert {w[0] for w in windows} == {"ad|0", "ad|1"}
    assert all(w[1:] == (20.0, 120.0, 0.0) for w in windows)
    with pytest.raises(ValueError, match="unknown structure"):
        structure_windows(c, (("misspelled", 20.0, 120.0, 0.0),))


def test_closed_bridge_committed_mass_waits_new_choices_detour_and_all_clear():
    from metroflow.restored_traffic import structure_windows

    c = compile_traffic(bridge_diamond(), signals=False)
    cfg = Config(
        paths_per_od=1,
        max_routes_per_od=1,
        adaptive_routes=True,
        route_regret_budget_s=0.0,
        interaction_rate_s=0.0,
        route_refresh_s=5.0,
    )
    m = Model(
        c.roads,
        (Demand("O", "D", 0.0, 80.0, 0.3),),
        cfg,
        allowed_turns=c.allowed_turns,
        capacity_windows=structure_windows(c, (("bridge", 20.0, 120.0, 0.0),)),
    )
    s = m.initial()
    saved = None
    for _ in range(400):
        before = s
        s = m.step(s)
        if 20 <= before.tick < 120:
            assert s.link_outflow[m.index["ad|0"]] == before.link_outflow[m.index["ad|0"]]
            assert s.link_outflow[m.index["ad|1"]] == before.link_outflow[m.index["ad|1"]]
        if s.tick == 50:
            saved = s
    assert s.completed == pytest.approx(24.0, abs=1e-8)
    assert s.link_outflow[m.index["ad|0"]] > 0 and s.link_outflow[m.index["bd|0"]] > 0
    assert sum(m.occupancy(saved)[0]) > 0  # closing the structure never deletes cohorts
    assert s.routing_repairs >= 1


def test_saturated_mainline_ramp_merge_uses_aggregate_priority_and_supply():
    coords = {
        "U": (0.0, 0.0, 10.0),
        "M": (400.0, 0.0, 10.0),
        "D": (800.0, 0.0, 10.0),
        "R": (0.0, -200.0, 0.0),
    }
    nodes = tuple(Junction(k, p, 0 if k == "R" else 1) for k, p in coords.items())
    secs = (
        section("um", "U", "M", (coords["U"], coords["M"]), "expressway", "mainline", (2, 0)),
        section(
            "rm", "R", "M", (coords["R"], coords["M"]), "collector", "ramp", (1, 0), role="on_ramp"
        ),
        section("md", "M", "D", (coords["M"], coords["D"]), "expressway", "mainline", (2, 0)),
    )
    c = compile_traffic(RoadMap("merge", Terrain(1, 1000.0, (0.0,) * 4), nodes, secs), signals=True)
    assert all(r.signal is None for r in c.roads)
    m = Model(
        c.roads,
        (Demand("U", "D", 100.0, 101.0, 0.0), Demand("R", "D", 100.0, 101.0, 0.0)),
        Config(paths_per_od=1),
        allowed_turns=c.allowed_turns,
    )
    s = m.initial()
    s = replace(
        s,
        queues=((s.source_roots[0][0], 20.0), (s.source_roots[1][0], 20.0)),
        released=40.0,
        admitted=40.0,
    )
    s = m.step(s)
    assert s.link_outflow[m.index["um|0"]] == pytest.approx(0.96)
    assert s.link_outflow[m.index["rm|0"]] == pytest.approx(0.24)
    assert sum(m.occupancy(s)[0]) == pytest.approx(40.0)


def test_layered_runner_reports_unfinished_and_preserves_budget_checkpoint():
    from metroflow.restored_traffic import run_layered

    c = compile_traffic(interchange(), signals=False)
    demand = (Demand("O", "D", 0.0, 50.0, 0.1),)
    report, s = run_layered(c, demand, 10.0, Config(paths_per_od=1, event_budget=1))
    assert report["status"] == "BLOCKED_RESOURCE"
    assert report["checkpoint_available"] and s is not None
    assert report["mean_network_journey_s"] is None
    assert report["released"] == pytest.approx(
        report["active"] + report["pending"] + report["completed"]
    )
    report, s = run_layered(c, demand, 1.0, Config(paths_per_od=1, max_live_suffixes=1))
    assert report["status"] == "BLOCKED_RESOURCE_INITIALIZATION" and s is None


def test_layered_runner_is_deterministic_and_no_individual_records():
    from metroflow.restored_traffic import run_layered

    c = compile_traffic(interchange(), signals=False)
    cfg = Config(paths_per_od=1, interaction_rate_s=0.0)
    args = (c, (Demand("O", "D", 0.0, 10.0, 0.1),), 250.0, cfg)
    a, x = run_layered(*args)
    b, y = run_layered(*args)
    assert a == b and x == y
    assert a["status"] == "CLEARED_SCOPED" and a["per_car_records"] == 0
    assert a["completed"] == pytest.approx(1.0) and a["max_storage_ratio"] <= 1.0
    assert a["max_mass_error"] < 1e-12


def test_free_flow_time_has_explicit_tick_error_bound():
    from metroflow.restored_traffic import run_layered

    c = compile_traffic(interchange(), signals=False)
    path = ("oa|0", "on|0", "main|0", "off|0", "bd|0")
    rd = {r.id: r for r in c.roads}
    exact = sum(rd[i].length_m / rd[i].free_speed_mps for i in path)
    errors = []
    for dt in (4.0, 2.0, 1.0):
        report, _ = run_layered(
            c,
            (Demand("O", "D", 0.0, 4.0, 0.01),),
            400.0,
            Config(dt_s=dt, paths_per_od=1, interaction_rate_s=0.0),
        )
        error = report["mean_network_journey_s"] - exact
        assert 0 <= error <= (3 * len(path) + 2) * dt
        errors.append(error)
    assert errors[-1] < errors[0]


def test_homogeneous_lane_and_mass_scaling_preserves_activity_and_travel_clock():
    # Scaling all lane supplies, storage and represented mass by two leaves
    # N/K, q/mu and hence the homogeneous kinetic/routing dynamics unchanged.
    city = bridge_diamond()
    scaled = replace(
        city,
        sections=tuple(
            replace(s, forward_lanes=2 * s.forward_lanes, backward_lanes=2 * s.backward_lanes)
            for s in city.sections
        ),
    )
    a, b = compile_traffic(city, signals=False), compile_traffic(scaled, signals=False)
    cfg = Config(paths_per_od=2)
    m = Model(a.roads, (Demand("O", "D", 0.0, 40.0, 0.2),), cfg, allowed_turns=a.allowed_turns)
    n = Model(b.roads, (Demand("O", "D", 0.0, 40.0, 0.4),), cfg, allowed_turns=b.allowed_turns)
    x, y = m.initial(), n.initial()
    for _ in range(150):
        x, y = m.step(x), n.step(y)
        assert y.activity == pytest.approx(x.activity, abs=1e-12)
        assert y.completed == pytest.approx(2 * x.completed, abs=1e-10)
        assert n.occupancy(y)[0] == pytest.approx([2 * z for z in m.occupancy(x)[0]], abs=1e-10)
    assert y.vehicle_seconds == pytest.approx(2 * x.vehicle_seconds, rel=1e-12)
