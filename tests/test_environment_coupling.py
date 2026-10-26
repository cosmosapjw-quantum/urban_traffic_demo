import pytest
from metroflow.environment.terrain import synthetic_terrain, compile_network
from metroflow.environment.landuse import zone_city
from metroflow.environment.demand import districts, plan_commute
from metroflow.environment.coupling import road_physics


def city(n=6, population=3000, seed=17):
    t = synthetic_terrain(n=n, seed=seed)
    return zone_city(t, compile_network(t), population, population * 2 // 5)


def test_environment_adapter_preserves_road_units_and_declared_conflicts():
    c = city()
    roads, conflicts = road_physics(c)
    assert len(roads) == 2 * len(c.network.links), "Every physical road needs two directed links"
    assert conflicts, "Signal conflicts must be declared, not hidden in the drawing"
    by = {e.id: e for e in c.network.links}
    from metroflow.active_suffix.common import _validate, Config, Demand

    nodes = {r.tail for r in roads}
    a, b = sorted(nodes)[:2]
    _validate(roads, (Demand(a, b, 0.0, 10.0, 0.1),), Config(), 10.0, (), conflicts)
    for r in roads:
        e = by[r.id.rsplit("|", 1)[0]]
        assert r.length_m == e.length_m
        assert 0 < r.free_speed_mps <= 12.0
        assert r.storage_veh == pytest.approx(0.12 * r.length_m)


def test_bank_aware_districts_preserve_population_and_jobs():
    c = city(n=12, population=100000)
    d = districts(c, 2)
    assert sum(z.residents for z in d) == 100000
    assert sum(z.jobs for z in d) == 40000
    zones = {z.id: z for z in c.zones}
    river = c.terrain.water[0]
    for area in d:
        sides = {-1 if zones[k].x_m < river.xmin else 1 for k in area.zone_ids}
        assert len(sides) == 1


def test_100k_stock_to_persons_vehicles_and_profile_ledger():
    c = city(n=12, population=100000)
    r, _ = road_physics(c)
    p = plan_commute(c, r, divisions=2)
    q = dict(p.ledger)
    assert q["peak_person_trips"] == 16000
    assert q["car_person_trips"] == 8800
    assert q["noncar_person_trips"] == pytest.approx(7200)
    assert q["car_vehicle_trips"] == 7040
    assert q["network_vehicle_trips"] + q["unresolved_local_vehicle_trips"] == pytest.approx(7040)
    assert q["unresolved_local_vehicle_trips"] > 0
    assert sum((d.end_s - d.start_s) * d.rate_veh_s for d in p.demands) == pytest.approx(
        q["network_vehicle_trips"]
    )
    assert p.max_margin_error < 1e-4


def test_od_budget_and_invalid_profile_never_drop_trips():
    c = city()
    roads, _ = road_physics(c)
    with pytest.raises(RuntimeError, match="OD budget"):
        plan_commute(c, roads, divisions=2, max_od_groups=1)
    with pytest.raises(ValueError):
        plan_commute(c, roads, profile=((0, 10, 0.3),))
    with pytest.raises(ValueError):
        plan_commute(c, roads, profile=((0, 10, 0.5), (5, 15, 0.5)))


def test_partial_horizon_never_claims_whole_day_clearance_or_local_trip_completion():
    from metroflow.environment.coupling import run_commute
    from metroflow.active_suffix import Config

    c = city()
    roads, _ = road_physics(c)
    p = plan_commute(c, roads, divisions=2, profile=((0.0, 600.0, 1.0),))
    r, s = run_commute(c, p, 30.0, Config(dt_s=5.0, paths_per_od=1, route_refresh_s=30.0))
    assert r["status"] == "HORIZON_REACHED"
    assert r["not_yet_released"] > 0
    assert r["mean_network_journey_s"] is None
    assert r["completed"] + r["active"] + r["pending"] == pytest.approx(r["released"])
    assert r["max_storage_ratio"] <= 1 + 1e-10
    assert r["per_car_records"] == 0
    assert r["released"] == pytest.approx(0.05 * r["planned_network_vehicles"])
    again, _ = run_commute(c, p, 30.0, Config(dt_s=5.0, paths_per_od=1, route_refresh_s=30.0))
    assert r["fingerprint"] == again["fingerprint"]
