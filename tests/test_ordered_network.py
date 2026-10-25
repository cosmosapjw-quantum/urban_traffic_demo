import math
from dataclasses import replace
import pytest
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group, Route, Network, BudgetExceeded
from metroflow.active_suffix.common import Signal


def lane(length=10.0, storage=10.0, rate=1.0):
    return Lane(length, 10.0, rate, rate, storage, interaction_rate=0.0)


def advance(model, steps, offers=()):
    s = model.initial()
    events = []
    for i in range(steps):
        s, e = model.step(s, offers if i == 0 else ())
        events.extend(e)
    return s, events


def test_two_link_handoff_closes_mass_and_residence_without_zero_time_hop():
    m = Network(
        (Group("a", "O", "M", lane()), Group("b", "M", "D", lane())), (Route("r", ("a", "b")),)
    )
    s, events = advance(m, 15, (("r", 1.0),))
    assert s.completed == pytest.approx(1.0)
    assert sum(x.occupancy for x in s.lanes) == pytest.approx(0.0)
    assert s.released == pytest.approx(
        s.completed + sum(x.occupancy for x in s.lanes) + sum(x.mass for x in s.pending)
    )
    assert s.system_vehicle_seconds == pytest.approx(
        sum(x.network_vehicle_seconds for x in s.lanes)
        + s.source_wait_seconds
        + s.transfer_hold_seconds
    )
    assert s.transfer_hold_seconds > 0
    a = next(e for e in events if e.source == "a")
    b = next(e for e in events if e.source == "b")
    assert b.start_s >= math.ceil(a.end_s) + 1.0


def test_merge_receiving_is_shared_by_priorities_not_copied_to_each_input():
    groups = (
        Group("a", "A", "M", lane(), 3.0),
        Group("b", "B", "M", lane(), 1.0),
        Group("c", "M", "D", lane()),
    )
    m = Network(groups, (Route("x", ("a", "c")), Route("y", ("b", "c"))))
    s, events = advance(m, 5, (("x", 3.0), ("y", 3.0)))
    flows = {
        k: sum(e.mass for e in events if e.source == k and e.start_s == 2.0) for k in ("a", "b")
    }
    assert flows["a"] == pytest.approx(0.75) and flows["b"] == pytest.approx(0.25)
    assert all(x.occupancy <= g.physics.storage + 1e-10 for g, x in zip(m.groups, s.lanes))


def test_shared_fifo_blocked_head_is_not_bypassed_and_independent_group_is_not_blocked():
    groups = (
        Group("a", "O", "M", lane()),
        Group("b", "M", "B", lane()),
        Group("c", "M", "C", lane()),
        Group("z", "Z", "M", lane()),
    )
    routes = (Route("blocked", ("a", "b")), Route("behind", ("a", "c")), Route("free", ("z", "c")))
    m = Network(groups, routes, windows=(("b", 0.0, 10.0, 0.0),))
    s, events = advance(m, 9, (("blocked", 0.5), ("behind", 0.5), ("free", 0.5)))
    assert not any(e.tag in ("blocked", "behind") for e in events)
    assert any(e.tag == "free" and e.destination is None for e in events)
    for _ in range(15):
        s, e = m.step(s)
    assert s.completed == pytest.approx(1.5)


def test_signal_green_rate_and_storage_close_without_hidden_mass_drop():
    groups = (
        Group("a", "O", "M", lane(storage=1.0), signal=Signal(4.0, 2.0, 0.0)),
        Group("b", "M", "D", lane(storage=1.0)),
    )
    m = Network(groups, (Route("r", ("a", "b")),))
    s, events = advance(m, 40, (("r", 5.0),))
    assert s.completed == pytest.approx(5.0)
    assert all(int(e.start_s) % 4 < 2 for e in events if e.source == "a")


def test_invalid_routes_and_misaligned_events_rejected():
    groups = (Group("a", "O", "M", lane()), Group("b", "M", "D", lane()))
    with pytest.raises(ValueError):
        Network(groups, (Route("r", ("b", "a")),))
    with pytest.raises(ValueError):
        Network(groups, (Route("r", ("a", "b")),), allowed_turns=frozenset())
    with pytest.raises(ValueError):
        Network(groups, (Route("r", ("a", "b")),), windows=(("b", 0.5, 10.0, 0.0),))


def test_resource_failure_is_atomic_and_replay_is_deterministic():
    m = Network(
        (Group("a", "O", "D", lane()),), (Route("x", ("a",)), Route("y", ("a",))), record_budget=1
    )
    old = m.initial()
    with pytest.raises(BudgetExceeded) as err:
        m.step(old, (("x", 0.5), ("y", 0.5)))
    assert err.value.checkpoint == old and old.released == 0
    n = Network((Group("a", "O", "D", lane()),), (Route("x", ("a",)),))
    assert advance(n, 10, (("x", 2.0),)) == advance(n, 10, (("x", 2.0),))


def test_state_nonfinite_and_local_vehicle_ledgers_are_rejected():
    m = Network((Group("a", "O", "D", lane()),), (Route("r", ("a",)),))
    s = m.initial()
    with pytest.raises((ValueError, ArithmeticError)):
        m.step(replace(s, lanes=(replace(s.lanes[0], admitted=float("nan")),)))
    with pytest.raises((ValueError, ArithmeticError)):
        m.step(replace(s, lanes=(replace(s.lanes[0], admitted=1.0),)))


def test_same_route_partition_does_not_change_aggregate_physics():
    m = Network(
        (Group("a", "O", "M", lane(30.0)), Group("b", "M", "D", lane(20.0))),
        (Route("r", ("a", "b")),),
    )
    a, b = m.initial(), m.initial()
    for i in range(60):
        a, _ = m.step(a, (("r", 1.0),) if i == 0 else ())
        b, _ = m.step(b, (("r", 0.1),) * 10 if i == 0 else ())
        assert a.completed == pytest.approx(b.completed, abs=1e-10)
        assert a.system_vehicle_seconds == pytest.approx(b.system_vehicle_seconds, abs=1e-9)
        assert [x.occupancy for x in a.lanes] == pytest.approx(
            [x.occupancy for x in b.lanes], abs=1e-10
        )


def test_same_lane_input_order_survives_activity_recovery_in_network():
    m = Network(
        (Group("a", "O", "D", Lane(100.0, 10.0, 1.0, 1.0, 30.0, interaction_rate=0.0)),),
        (Route("first", ("a",)), Route("later", ("a",))),
    )
    s = m.initial()
    s = replace(s, lanes=(replace(s.lanes[0], activity=0.1),))
    exits = []
    for i in range(80):
        s, e = m.step(s, (("first", 0.1),) if i == 0 else (("later", 0.1),) if i == 10 else ())
        exits.extend(e)
    first = [x.end_s for x in exits if x.tag == "first"]
    later = [x.start_s for x in exits if x.tag == "later"]
    assert first and later and max(first) <= min(later)


def test_grid_refinement_reports_explicit_transfer_residence():
    values = []
    for dt in (1.0, 0.5, 0.25):
        groups = (
            Group("a", "O", "M", lane(103.0, rate=10.0)),
            Group("b", "M", "D", lane(107.0, rate=10.0)),
        )
        m = Network(groups, (Route("r", ("a", "b")),), dt_s=dt)
        s, _ = advance(m, round(50 / dt), (("r", 0.1),))
        mean = s.system_vehicle_seconds / s.completed
        assert mean >= 21.0  # 210m / 10m/s, no instantaneous jump across nodes
        values.append(mean)
    assert values[-1] < values[0]
