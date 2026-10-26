"""T03 joint rate/space budgets, declared lanes, signals and class conservation."""

from dataclasses import replace
import math
import pytest
from metroflow.active_suffix.common import Signal, BudgetExceeded
from metroflow.foundation_kinetics import VehicleClass
from metroflow.ordered_network import Route
from metroflow.v1.city import CityContractError
from metroflow.v1.nodes import allocate_node, validate_signal_conflicts
from metroflow.v1.lanegroups import (
    LanePartition,
    compile_lanegroups,
    packet_model,
    lane_bulk_inputs,
)
from metroflow.v1.kinetics import coefficients
from metroflow.v1.junction_oracles import (
    group,
    physical_model,
    branch_city,
    paired_bridge_city,
    junction_oracles,
)


def test_merge_priority_three_to_one_and_id_equivariance():
    q = allocate_node(
        {"a": {"z": 1.0}, "b": {"z": 1.0}}, {"a": 10.0, "b": 10.0}, {"z": 4.0}, {"a": 3.0, "b": 1.0}
    )
    assert q == {"a": 3.0, "b": 1.0}
    p = allocate_node(
        {"renamed_b": {"q": 1.0}, "renamed_a": {"q": 1.0}},
        {"renamed_a": 10.0, "renamed_b": 10.0},
        {"q": 4.0},
        {"renamed_a": 1.0, "renamed_b": 3.0},
    )
    assert p["renamed_b"] == q["a"] and p["renamed_a"] == q["b"]
    rows = junction_oracles()
    assert all(r["status"] == "PASS" for r in rows)


def test_fixed_turns_block_shared_packet_without_reallocating_demand():
    q = allocate_node(
        {"shared": {"blocked": 0.2, "free": 0.8}, "independent": {"free": 1.0}},
        {"shared": 10.0, "independent": 10.0},
        {"blocked": 0.0, "free": 1.0},
        {"shared": 1.0, "independent": 1.0},
    )
    assert q == {"shared": 0.0, "independent": 1.0}
    with pytest.raises(CityContractError, match="fractions"):
        allocate_node({"a": {"b": 0.5}}, {"a": 1.0}, {"b": 1.0}, {"a": 1.0})


def test_mixed_class_source_storage_uses_metres_not_vehicle_count():
    car = VehicleClass()
    truck = replace(car, name="freight", length_m=12.0)
    model = physical_model(
        (group("g", "O", "D"),),
        (Route("car", ("g",)), Route("truck", ("g",))),
        classes={"car": car, "truck": truck},
        spaces={"g": 17.0},
    )
    s, _ = model.step(model.initial(), (("car", 2.0), ("truck", 2.0)))
    assert s.cells[0].occupancy == 2
    assert model.occupied_space(s.cells[0]) == 17
    assert sum(p.mass for q in s.pending for p in q) == 2
    assert {x.name: x.released for x in s.class_ledger} == {"car": 2.0, "freight": 2.0}
    for _ in range(10):
        s, _ = model.step(s)
    assert s.completed == 4 and all(x.completed == 2 for x in s.class_ledger)
    assert all(x.source_wait_seconds > 0 and x.exit_queue_seconds > 0 for x in s.class_ledger)


def test_incoming_merges_and_local_sources_share_one_physical_space_budget():
    car = VehicleClass()
    truck = replace(car, name="freight", length_m=12.0)
    model = physical_model(
        (group("a", "A", "M"), group("b", "B", "M"), group("c", "M", "D", entry=10)),
        (Route("car", ("a", "c")), Route("truck", ("b", "c")), Route("local", ("c",))),
        classes={"car": car, "truck": truck, "local": car},
        spaces={"a": 100.0, "b": 100.0, "c": 17.0},
    )
    s, _ = model.step(model.initial(), (("car", 2.0), ("truck", 2.0)))
    s, events = model.step(s, (("local", 1.0),))
    assert model.occupied_space(s.cells[model.index["c"]]) == pytest.approx(17.0)
    assert math.fsum(e.mass for e in events if e.destination == "c") == pytest.approx(2.0)
    assert math.fsum(p.mass for p in s.pending[model.index["c"]]) == 1.0
    model.check(s)


def test_class_fragmentation_preserves_space_flows_and_queue_moments():
    model = physical_model(
        (group("g", "O", "D", exit=0.5),), (Route("r", ("g",)),), spaces={"g": 10.0}
    )
    a, b = model.initial(), model.initial()
    for k in range(20):
        a, ea = model.step(a, (("r", 4.0),) if k == 0 else ())
        b, eb = model.step(b, (("r", 1.0),) * 4 if k == 0 else ())
        assert a.completed == pytest.approx(b.completed)
        assert a.class_ledger == b.class_ledger
        assert a.system_vehicle_seconds == pytest.approx(b.system_vehicle_seconds)
        assert ea == eb


def test_compiler_partitions_exact_lanes_and_keeps_legal_turns():
    city = branch_city()
    parts = (LanePartition("left", "a|0", 1, ("b|0",)), LanePartition("right", "a|0", 1, ("c|0",)))
    contract = compile_lanegroups(city, parts)
    groups = {g.id: g for g in contract.groups}
    assert dict(contract.spaces_m)["left"] == 100
    assert dict(contract.spaces_m)["right"] == 100
    assert groups["left"].physics.entry_rate + groups["right"].physics.entry_rate == pytest.approx(
        0.9
    )
    assert ("left", "b|0") in contract.allowed_turns
    assert ("left", "c|0") not in contract.allowed_turns
    with pytest.raises(ValueError, match="illegal route"):
        packet_model(contract, (Route("r", ("left", "c|0")),), {"r": VehicleClass()})
    with pytest.raises(CityContractError, match="lane counts"):
        compile_lanegroups(city, (LanePartition("bad", "a|0", 3),))
    with pytest.raises(CityContractError, match="illegal physical turn"):
        compile_lanegroups(city, (LanePartition("bad", "a|0", 2, ("a|0",)),))


def test_blocked_shared_vs_independent_turns_on_actual_city_contract():
    rows = {r["case"]: r for r in junction_oracles()}
    assert rows["blockedshared"]["completed"] == 0
    assert rows["independentturn"]["completed"] == 1
    assert rows["blockedshared"]["released"] == rows["independentturn"]["released"] == 2


def test_signal_conflict_is_contract_error_with_half_open_red_boundary():
    a = group("a", "A", "M", signal=Signal(4, 2))
    b = group("b", "B", "M", signal=Signal(4, 2, 2))
    assert validate_signal_conflicts((a, b), (("a", "b"),))["status"] == "PASS"
    with pytest.raises(CityContractError) as exc:
        validate_signal_conflicts((a, replace(b, signal=Signal(4, 2))), (("a", "b"),))
    assert exc.value.status == "CONTRACT_ERROR"
    with pytest.raises(CityContractError, match="align"):
        validate_signal_conflicts((replace(a, signal=Signal(4, 1.5)),), ())
    model = physical_model((group("g", "O", "D", signal=Signal(4, 2)),), (Route("r", ("g",)),))
    s = model.initial()
    for k in range(6):
        s, ev = model.step(s, (("r", 20.0),) if k == 0 else ())
        if k in (2, 3):
            assert not ev
    assert s.class_ledger[0].exit_queue_seconds > 0


def test_signal_period_resource_cap_is_not_a_gridlock_claim():
    a = group("a", "A", "M", signal=Signal(101, 1))
    b = group("b", "B", "M", signal=Signal(103, 1, 2))
    with pytest.raises(CityContractError) as exc:
        validate_signal_conflicts((a, b), (("a", "b"),), event_budget=100)
    assert exc.value.status == "BLOCKED_RESOURCE"


def test_bridge_closes_paired_directions_without_deleting_inflight_mass():
    contract = compile_lanegroups(paired_bridge_city(), failures=(("bridge", 1.0, 20.0, 0.0),))
    assert {w[0] for w in contract.windows} == {"bc|0", "bc|1"}
    routes = (Route("f", ("bc|0",)), Route("b", ("bc|1",)))
    model = packet_model(contract, routes, {r.tag: VehicleClass() for r in routes})
    s, _ = model.step(model.initial(), (("f", 1.0), ("b", 1.0)))
    inflight = sum(c.occupancy for c in s.cells)
    assert inflight > 0
    for k in range(1, 20):
        s, ev = model.step(s, (("f", 1.0), ("b", 1.0)) if k == 1 else ())
        assert not ev
        assert sum(c.occupancy for c in s.cells) == inflight
        assert s.completed == 0
    assert s.released == 4
    for _ in range(60):
        s, _ = model.step(s)
    assert s.completed == pytest.approx(4)
    model.check(s)


def test_event_budget_failure_preserves_last_state_and_is_not_demand_reduction():
    model = physical_model((group("g", "O", "D"),), (Route("r", ("g",)),), event_budget=1)
    s, _ = model.step(model.initial(), (("r", 1.0),))
    with pytest.raises(BudgetExceeded) as exc:
        model.step(s)
    assert exc.value.checkpoint is s
    assert s.released == 1 and s.completed == 0


def test_lane_class_masses_feed_t02_without_replacing_the_packet_clock():
    car = VehicleClass()
    truck = replace(car, name="freight", length_m=12.0, response_s=4.0)
    model = physical_model(
        (group("g", "O", "D"),),
        (Route("car", ("g",)), Route("truck", ("g",))),
        classes={"car": car, "truck": truck},
        spaces={"g": 100.0},
        standing_gap_m=2.0,
    )
    s, _ = model.step(model.initial(), (("car", 1.0), ("truck", 1.0)))
    bulk, environment = lane_bulk_inputs(model, s, "g", speed_mps=3.0)
    assert bulk.mass_veh == 2 and bulk.time_s == s.time_s
    assert coefficients(bulk, environment).mean_gap_m == (100 - 5 - 12) / 2
    assert model.occupied_space(s.cells[0]) == 21
    assert bulk.classes[1].vehicle == truck


def test_physical_parameters_and_city_identity_bind_state_cache():
    city = branch_city()
    c = compile_lanegroups(city)
    routes = (Route("r", ("a|0", "c|0")),)
    m = packet_model(c, routes, {"r": VehicleClass()})
    other = packet_model(c, routes, {"r": replace(VehicleClass(), length_m=6.0)})
    with pytest.raises(ValueError, match="identity"):
        other.check(m.initial())
    with pytest.raises(ValueError, match="every route class"):
        packet_model(c, routes, {})


def test_junction_cli_executes_the_actual_packet_solver(tmp_path):
    import json
    import subprocess
    import sys

    out = tmp_path / "junction.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "metroflow.v1",
            "physics-oracles",
            "--suite",
            "junctions",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    report = json.loads(out.read_text())
    assert report["status"] == "PASS"
    assert {x["case"] for x in report["cases"]} == {
        "merge3:1",
        "blockedshared",
        "independentturn",
        "redboundary",
        "bridgepairedclosure",
        "class_storage",
    }


def test_ramp_failure_and_layer_permissions_survive_the_lane_compiler():
    from test_restored_traffic import interchange
    from metroflow.v1.city import compile_city

    contract = compile_lanegroups(compile_city(interchange()), failures=(("ic", 0.0, 20.0, 0.0),))
    assert {w[0] for w in contract.windows} == {"on|0"}
    assert ("on|0", "main|0") in contract.allowed_turns
    assert ("main|0", "off|0") in contract.allowed_turns
    assert not any(g.id in ("on|1", "off|1", "main|1") for g in contract.groups)
    route = Route("r", ("oa|0", "on|0", "main|0", "off|0", "bd|0"))
    model = packet_model(contract, (route,), {"r": VehicleClass()})
    model.check(model.initial())
