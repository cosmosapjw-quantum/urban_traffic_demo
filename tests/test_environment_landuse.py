import pytest
from metroflow.environment.terrain import synthetic_terrain, compile_network
from metroflow.environment.landuse import apportion, zone_city


def test_stock_totals_are_exact_and_do_not_occupy_forbidden_land():
    t = synthetic_terrain(n=12)
    g = compile_network(t)
    c = zone_city(t, g, 100000, 40000)
    assert sum(z.residents for z in c.zones) == 100000
    assert sum(z.jobs for z in c.zones) == 40000
    assert any(z.use == "water" for z in c.zones)
    assert any(z.use == "protected" for z in c.zones)
    assert any(z.use == "industrial" for z in c.zones)
    for z in c.zones:
        assert 0 <= z.residents <= z.housing_capacity
        assert 0 <= z.jobs <= z.job_capacity
        if z.use in {"water", "protected", "floodplain", "steep", "inaccessible", "buffer", "park"}:
            assert z.residents == z.jobs == z.housing_capacity == z.job_capacity == 0
        if z.residents or z.jobs:
            assert z.access_node is not None


def test_capped_apportionment_redistributes_without_per_person_loop():
    assert apportion(101, (1, 200), (100.0, 1.0)) == (1, 100)
    assert sum(apportion(100000, (200000, 200000), (1.0, 2.0))) == 100000
    assert apportion(7, (3, 4), (1.0, 1.0)) == (3, 4)
    with pytest.raises(ValueError):
        apportion(8, (3, 4), (1.0, 1.0))


def test_insufficient_capacity_fails_instead_of_increasing_density():
    t = synthetic_terrain(n=6)
    g = compile_network(t)
    with pytest.raises(ValueError):
        zone_city(t, g, 10000000, 4000000)


def test_planning_replay_immutable_and_area_accounting():
    t = synthetic_terrain(n=6, seed=7)
    g = compile_network(t)
    a = zone_city(t, g, 3000, 1200)
    b = zone_city(t, g, 3000, 1200)
    assert a == b and a.zones
    assert sum(z.area_m2 for z in a.zones) == (t.n * t.spacing_m) ** 2
    assert all(z.net_area_m2 <= z.area_m2 for z in a.zones)
    assert t == a.terrain and g == a.network


def test_invalid_stock_and_weights_are_rejected():
    with pytest.raises(ValueError):
        apportion(-1, (3, 4), (1.0, 1.0))
    with pytest.raises(ValueError):
        apportion(1, (3, 4), (float("nan"), 1.0))
    with pytest.raises(ValueError):
        apportion(1, (3, 4), (0.0, 0.0))


def test_industry_buffer_uses_assigned_cell_footprints_not_region_centres():
    t = synthetic_terrain(n=12)
    c = zone_city(t, compile_network(t), 100000, 40000)
    industry = [z for z in c.zones if z.use == "industrial"]
    for z in c.zones:
        if z.housing_capacity:
            assert all(
                abs(z.x_m - i.x_m) > t.spacing_m + 150.0 or abs(z.y_m - i.y_m) > t.spacing_m + 150.0
                for i in industry
            )
    assert any(z.use == "civic" for z in c.zones)
