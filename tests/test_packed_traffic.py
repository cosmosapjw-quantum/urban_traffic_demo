import math
import pytest
from metroflow.active_suffix import Road, Demand, Config, Signal, BudgetExceeded
from metroflow.active_suffix.packed import PackedModel


@pytest.mark.parametrize("dt", (4.0, 2.0, 1.0, 0.5))
def test_aligned_freeflow_has_only_causal_roundup_not_extra_ticks(dt):
    m = PackedModel(
        (Road("r", "O", "D", 100.0, 10.0, 1.0, 100.0),),
        (Demand("O", "D", 0.0, 80.0, 0.125),),
        Config(dt_s=dt, paths_per_od=1, interaction_rate_s=0.0),
    )
    s = m.initial()
    peak = 0
    for _ in range(round(120 / dt)):
        s = m.step(s)
        peak = max(peak, len(s.transit))
    assert s.completed == pytest.approx(10.0)
    assert s.vehicle_seconds / s.completed == pytest.approx(math.ceil(10 / dt) * dt, abs=1e-10)
    assert peak <= 1


def test_unaligned_boundaries_explicitly_request_interval_reference():
    r = Road("r", "O", "D", 100.0, 10.0, 1.0, 100.0)
    with pytest.raises(ValueError, match="aligned"):
        PackedModel((r,), (Demand("O", "D", 0.3, 5.7, 0.1),), Config(dt_s=1.0))
    with pytest.raises(ValueError, match="aligned"):
        PackedModel(
            (r,),
            (Demand("O", "D", 0.0, 10.0, 0.1),),
            Config(dt_s=1.0),
            capacity_windows=(("r", 3.2, 9.7, 0.0),),
        )


def test_multiple_links_cannot_skip_their_finite_delay():
    roads = (
        Road("a", "O", "M", 70.0, 10.0, 1.0, 100.0),
        Road("b", "M", "D", 130.0, 10.0, 1.0, 100.0),
    )
    cfg = Config(dt_s=2.0, paths_per_od=1, interaction_rate_s=0.0)
    m = PackedModel(roads, (Demand("O", "D", 0.0, 4.0, 0.1),), cfg)
    s = m.initial()
    for _ in range(100):
        s = m.step(s)
    assert s.vehicle_seconds / s.completed == pytest.approx(22.0)


def test_red_closure_storage_and_mass_ledger_on_aligned_time_grid():
    r = Road("r", "O", "D", 10.0, 10.0, 0.5, 3.0, signal=Signal(10.0, 6.0))
    m = PackedModel(
        (r,),
        (Demand("O", "D", 0.0, 20.0, 1.0),),
        Config(dt_s=1.0, paths_per_od=1),
        capacity_windows=(("r", 4.0, 14.0, 0.0),),
    )
    s = m.initial()
    for _ in range(200):
        old = s
        s = m.step(s)
        occ, _ = m.occupancy(s)
        if 4 <= old.tick < 14 or old.tick % 10 >= 6:
            assert s.completed == old.completed
        assert occ[0] <= 3.0 + 1e-10
        assert s.released == pytest.approx(s.completed + sum(s.pending) + sum(occ), abs=1e-8)
    assert s.completed == pytest.approx(20.0, abs=1e-8)


def test_run_compression_preserves_every_discrete_arrival_and_distinct_suffix():
    from metroflow.active_suffix.packed import TransitRun, pack_runs

    events = (
        TransitRun(2, 8, 1, 0.25),
        TransitRun(9, 15, 1, 0.25),
        TransitRun(5, 11, 2, 0.2),
        TransitRun(6, 7, 1, 0.125),
    )
    packed = pack_runs(events)
    for sid in (1, 2):
        for tick in range(20):
            before = math.fsum(
                e.mass_per_tick
                for e in events
                if e.suffix == sid and e.first_tick <= tick <= e.last_tick
            )
            after = math.fsum(
                e.mass_per_tick
                for e in packed
                if e.suffix == sid and e.first_tick <= tick <= e.last_tick
            )
            assert after == before
    assert math.fsum(e.mass for e in packed) == math.fsum(e.mass for e in events)


def test_checkpoint_on_packed_budget_failure_is_unchanged_and_replayable():
    r = Road("r", "O", "D", 1000.0, 10.0, 2.0, 100.0)
    ds = (Demand("O", "D", 0.0, 20.0, 0.1), Demand("O", "D", 2.0, 10.0, 0.2))
    m = PackedModel(
        (r,), ds, Config(dt_s=1.0, paths_per_od=1, event_budget=1, interaction_rate_s=0.0)
    )
    s = m.initial()
    for _ in range(2):
        s = m.step(s)
    before = m.fingerprint(s)
    with pytest.raises(BudgetExceeded) as hit:
        m.step(s)
    assert hit.value.checkpoint == s and m.fingerprint(s) == before
    assert s.released == pytest.approx(s.completed + sum(s.pending) + sum(m.occupancy(s)[0]))


def test_committed_route_survives_packed_cache_eviction():
    roads = (
        Road("oa", "O", "A", 1000.0, 10.0, 1.0, 150.0),
        Road("ad", "A", "D", 100.0, 10.0, 1.0, 15.0),
        Road("ob", "O", "B", 1500.0, 10.0, 1.0, 225.0),
        Road("bd", "B", "D", 100.0, 10.0, 1.0, 15.0),
    )
    demands = (Demand("O", "D", 0.0, 80.0, 2.0),)
    cfg = Config(
        paths_per_od=1,
        max_routes_per_od=1,
        adaptive_routes=True,
        interaction_rate_s=0.0,
        route_regret_budget_s=0.0,
        route_refresh_s=5.0,
    )
    windows = (("ad", 20.0, 80.0, 0.0),)
    m = PackedModel(roads, demands, cfg, capacity_windows=windows)
    s = m.initial()
    for _ in range(20):
        s = m.step(s)
    paths = {e.suffix: m.remaining_path(s, e.suffix) for e in s.transit}
    after = m.step(s)
    assert m.remaining_path(after, after.source_roots[0][0]) == ("ob", "bd")
    for e in after.transit:
        if e.suffix in paths:
            assert m.remaining_path(after, e.suffix) == paths[e.suffix]
    for _ in range(500):
        after = m.step(after)
    assert after.completed == pytest.approx(160.0, abs=1e-8)
    assert after.link_outflow[m.index["ad"]] > 0 and after.link_outflow[m.index["bd"]] > 0
