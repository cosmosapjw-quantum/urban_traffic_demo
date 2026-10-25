from dataclasses import replace
import pytest
from metroflow.environment.terrain import Terrain, Rect
from metroflow.restored_city import Junction, Section, RoadMap
from metroflow.access_development import Plot, Jobs, Development, develop


def fixture():
    t = Terrain(4, 100.0, (0.0,) * 25)
    a, b = (0.0, 100.0, 0.0), (400.0, 100.0, 0.0)
    s = Section("base", "a", "b", (a, b), "local", "surface", 1, 1, 400.0, 0.0)
    city = RoadMap("flat", t, (Junction("a", a), Junction("b", b)), (s,))
    plots = (
        Plot("west", Rect(80.0, 180.0, 120.0, 220.0), 50),
        Plot("east", Rect(280.0, 180.0, 320.0, 220.0), 50),
    )
    return Development(city, plots)


def test_population_waits_without_roads_then_legal_access_unlocks_capacity():
    state = fixture()
    waiting, receipt = develop(state, 30, (Jobs("b", 100.0),), budget_m=0.0)
    assert waiting.pending == 30 and waiting.offered == 30
    assert sum(p.residents for p in waiting.plots) == 0
    out, receipt = develop(waiting, 0, (Jobs("b", 100.0),), budget_m=110.0, max_roads=1)
    assert sum(p.residents for p in out.plots) == 30 and out.pending == 0
    assert out.built_m == pytest.approx(100.0)
    assert len(receipt["built"]) == 1 and out.epoch == 2
    assert state == fixture()


def test_jobs_change_new_development_location_not_geometry_gate():
    state = fixture()
    east, _ = develop(state, 30, (Jobs("b", 100.0),), budget_m=110.0, max_roads=1)
    west, _ = develop(state, 30, (Jobs("a", 100.0),), budget_m=110.0, max_roads=1)
    assert next(p.id for p in east.plots if p.residents) == "east"
    assert next(p.id for p in west.plots if p.residents) == "west"


def test_existing_vacancy_prevents_unnecessary_new_roads_and_overflow_waits():
    a, _ = develop(fixture(), 30, (Jobs("b", 100.0),), budget_m=110.0, max_roads=1)
    b, receipt = develop(a, 10, (Jobs("b", 100.0),), budget_m=110.0)
    assert not receipt["built"] and b.city == a.city
    assert sum(p.residents for p in b.plots) == 40
    c, _ = develop(b, 200, (Jobs("b", 100.0),), budget_m=110.0)
    assert sum(p.residents for p in c.plots) == 100 and c.pending == 140
    assert c.offered == 240 and c.built_m == pytest.approx(200.0)
    assert all(p.residents <= p.capacity for p in c.plots)


def test_footprint_exclusion_cannot_be_overridden_by_attractive_jobs():
    state = fixture()
    protected = Rect(250.0, 160.0, 350.0, 240.0)
    state = replace(
        state, city=replace(state.city, terrain=replace(state.city.terrain, protected=(protected,)))
    )
    out, receipt = develop(state, 30, (Jobs("b", 1e6),), budget_m=110.0, max_roads=1)
    assert next(p.id for p in out.plots if p.residents) == "west"
    assert dict(receipt["rejected"])["east"] == "land_exclusion"


def test_no_legal_job_access_cannot_be_mistaken_for_served_development():
    state = fixture()
    # Endpoint exists but is disconnected. A large job weight is not access.
    city = replace(state.city, nodes=state.city.nodes + (Junction("island", (390.0, 390.0, 0.0)),))
    out, receipt = develop(replace(state, city=city), 30, (Jobs("island", 100.0),), budget_m=900.0)
    assert out.pending == 30 and out.built_m == 0
    assert sum(p.residents for p in out.plots) == 0


def test_gate_rejections_and_old_stock_are_preserved():
    state = fixture()
    no, _ = develop(state, 20, (Jobs("b", 100.0),), admission_rule=lambda *a: "blocked_for_test")
    assert no.pending == 20 and no.city == state.city
    first, _ = develop(state, 30, (Jobs("b", 100.0),), budget_m=110.0, max_roads=1)
    second, _ = develop(first, 40, (Jobs("a", 100.0),), budget_m=110.0, max_roads=1)
    assert next(p for p in second.plots if p.id == "east").residents >= 30
    assert first.epoch == 1 and second.epoch == 2


def test_invalid_growth_overlapping_plots_and_budget_rejected():
    for bad in (-1, 1.5, True):
        with pytest.raises(ValueError):
            develop(fixture(), bad, (Jobs("b", 10.0),))
    with pytest.raises(ValueError):
        develop(fixture(), 1, (Jobs("missing", 10.0),))
    with pytest.raises(ValueError):
        develop(fixture(), 1, (Jobs("b", 10.0),), budget_m=-1.0)
    state = fixture()
    same = replace(state.plots[1], footprint=state.plots[0].footprint)
    with pytest.raises(ValueError):
        develop(replace(state, plots=(state.plots[0], same)), 1, (Jobs("b", 10.0),))
