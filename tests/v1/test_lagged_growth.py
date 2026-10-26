from dataclasses import replace
import math
import pytest
from metroflow.v1.city import CityContractError
from metroflow.v1.access_audit import fixture_city
from metroflow.v1.activity import compile_activity
from metroflow.v1.development import (
    compile_entry,
    GrowthModel,
    DevelopmentSite,
    CohortMove,
    lagged_growth_control,
)
from metroflow.v1.accessibility import CompletedAccessibility, compile_accessibility
from metroflow.v1.observations import CostKey, CostObservation


def fixture(budget=100, capacity=20):
    city = fixture_city()
    entry = compile_entry(
        city,
        compile_activity(city, "block"),
        "east",
        capacity_veh_s=1,
        corridor=((300.0, 20.0), (310.0, 10.0)),
    )
    return GrowthModel(
        city, (DevelopmentSite("block", entry, capacity),), budget_m=budget, max_access_s=50
    )


def access(model, state, stamp, cost=20):
    return CompletedAccessibility(
        model.materialize_city(state).identity, stamp, (("block", cost),), "completed-v1"
    )


def test_bridge_bypass_lag_and_actual_next_epoch_demand():
    (row,) = lagged_growth_control()
    assert row["status"] == "PASS" and row["first_pending"] == 10 and row["second_pending"] == 0
    m = fixture()
    s = m.initial()
    before = m.compile_next_demand(s, worker_fraction=0.1, service_fraction=0)
    after = m.advance(s, access(m, s, 0), 3600, 10)
    schedule = m.compile_next_demand(after, worker_fraction=0.1, service_fraction=0)
    assert before.resident_stock == 1000 and schedule.resident_stock == 1010
    assert before.identity != schedule.identity and before.city_identity != schedule.city_identity
    assert dict(after.allocations)["block"] == 1010


def test_same_tick_future_reused_epoch_and_clock_rejected():
    m = fixture()
    s = m.initial()
    for stamp in (3600, 4000):
        with pytest.raises(CityContractError):
            m.advance(s, access(m, s, stamp), 3600, 10)
    with pytest.raises(CityContractError):
        m.advance(s, access(m, s, 0), 3599, 10)
    after = m.advance(s, access(m, s, 0), 3600, 10)
    with pytest.raises(CityContractError):
        m.advance(after, access(m, after, 0), 7200)
    with pytest.raises(CityContractError):
        m.advance(after, access(m, s, 3600), 7200)


@pytest.mark.parametrize("budget,capacity,expected", [(0, 20, 30), (100, 20, 10)])
def test_budget_and_capacity_leave_population_pending(budget, capacity, expected):
    m = fixture(budget, capacity)
    s = m.initial()
    a = m.advance(s, access(m, s, 0), 3600, 30)
    assert a.pending_increment == expected and a.status == "PENDING_DEVELOPMENT"
    assert sum(dict(a.allocations).values()) + a.pending_increment == 1030
    assert a.construction_m <= budget
    m.materialize_city(a)


def test_no_finite_supported_access_no_construction_or_zero_time_fallback():
    m = fixture()
    s = m.initial()
    unsupported = CompletedAccessibility(m.city.identity, 0, (), "none")
    after = m.advance(s, unsupported, 3600, 10)
    assert not after.built_blocks and after.pending_increment == 10
    assert after.construction_m == 0


def test_existing_residents_not_reallocated_and_increment_not_reapplied():
    m = fixture()
    s = m.initial()
    a = m.advance(s, access(m, s, 0), 3600, 10)
    b = m.advance(a, access(m, a, 3600), 7200)
    assert a.allocations == b.allocations and not b.moves
    assert b.requested_increment == 10 and b.construction_m == a.construction_m


def test_unrequested_and_infeasible_cohort_moves_rejected_atomically():
    m = fixture()
    s = m.initial()
    with pytest.raises(CityContractError):
        m.advance(s, access(m, s, 0), 3600, moves=(CohortMove("block", "missing", 10),))
    assert dict(s.allocations)["block"] == 1000


def test_completed_weighted_observation_support_not_prediction():
    m = fixture()
    a = CostObservation(
        CostKey("route", "a", "car"),
        10,
        10,
        0,
        10,
        1,
        (0.0, 0.0),
        "T04_completed_outlet",
        "v1",
        "a",
    )
    b = replace(a, seconds=30, mass_veh=3, population="b")
    snap = compile_accessibility(m.city.identity, (("block", a), ("block", b)), 10)
    assert dict(snap.costs)["block"] == 25
    with pytest.raises(CityContractError):
        compile_accessibility(m.city.identity, (("block", a),), 9)
    with pytest.raises(CityContractError):
        compile_accessibility(m.city.identity, (("block", replace(a, source="prediction")),), 10)


@pytest.mark.parametrize("value", [-1, math.nan, math.inf])
def test_forged_entry_budget_credit_and_invalid_state_rejected(value):
    m = fixture()
    entry = replace(m.sites[0].entry, construction_length_m=value)
    with pytest.raises(CityContractError):
        GrowthModel(m.city, (replace(m.sites[0], entry=entry),), budget_m=100)
    with pytest.raises(CityContractError):
        m.check(replace(m.initial(), construction_m=value))


def test_state_original_stock_cannot_be_forged():
    m = fixture()
    with pytest.raises(CityContractError):
        m.check(replace(m.initial(), original_residents=999))


def test_explicit_cohort_move_changes_only_recorded_blocks():
    from metroflow.v1.city import compile_city, PortalRef

    c = fixture_city()
    extra_nodes = tuple(
        replace(n, id=n.id + "x", xyz=(n.xyz[0] + 400, n.xyz[1], n.xyz[2])) for n in c.roadmap.nodes
    )
    extra_sections = tuple(
        replace(
            s,
            id=s.id + "x",
            start=s.start + "x",
            end=s.end + "x",
            points=tuple((p[0] + 400, p[1], p[2]) for p in s.points),
        )
        for s in c.roadmap.sections
    )
    road = replace(
        c.roadmap, nodes=c.roadmap.nodes + extra_nodes, sections=c.roadmap.sections + extra_sections
    )
    original = c.face_graph.blocks[0]
    blocks = (
        replace(original, residents=900),
        replace(
            original,
            id="second",
            boundary=tuple(k + "x" for k in original.boundary),
            xy=(original.xy[0] + 400, original.xy[1]),
        ),
    )
    city = compile_city(
        road, blocks=blocks, portals=c.portals + (PortalRef("eastx", "second", "1x"),)
    )
    m = GrowthModel(city, (), budget_m=0)
    s = m.initial()
    snapshot = CompletedAccessibility(
        city.identity, 0, (("block", 20), ("second", 20)), "completed-v1"
    )
    moved = m.advance(s, snapshot, 3600, moves=(CohortMove("second", "block", 10),))
    assert dict(moved.allocations) == {"block": 910, "second": 990}
    assert moved.moves == (CohortMove("second", "block", 10),)
    assert sum(dict(moved.allocations).values()) == 1900
    m.materialize_city(moved)
