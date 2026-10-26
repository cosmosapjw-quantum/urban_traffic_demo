"""M03 acceptance through physical city and declared activity interfaces."""

import math
import pytest
from metroflow.v1.activity import ActivityPatch, compile_activity, intrazonal_law
from metroflow.v1.access import activity_access
from metroflow.v1.development import compile_entry, select_entries
from metroflow.v1.city import CityContractError
from metroflow.v1.access_audit import fixture_city


def test_stock_and_uniform_fallback():
    c = fixture_city()
    m = compile_activity(c, "block")
    assert m.mass == 1000 and m.units == "persons"
    assert "fallback" in m.patches[0].prior
    assert math.fsum(w for _, w, _ in m.quadrature()) == pytest.approx(1.0)
    with pytest.raises(CityContractError, match="mass"):
        compile_activity(c, "block", patches=(ActivityPatch(999, ((20.0, 20.0),)),))


def test_unsupported_and_concavity():
    with pytest.raises(CityContractError) as error:
        ActivityPatch(1000, ((20.0, 20.0),), holes=(((1.0, 1.0),),))
    assert error.value.status == "UNSUPPORTED_GEOMETRY"
    with pytest.raises(CityContractError, match="outside"):
        compile_activity(fixture_city(), "block", patches=(ActivityPatch(1000, ((200.0, 200.0),)),))


def test_intrazonal_geodesic_is_positive_and_not_euclidean_shortcut():
    c = fixture_city()
    a = compile_activity(c, "block", patches=(ActivityPatch(1000, ((280.0, 40.0),)),))
    b = compile_activity(c, "block", patches=(ActivityPatch(1000, ((40.0, 280.0),)),))
    law = intrazonal_law(a, b, speed_mps=1.0)
    expected = 2 * math.hypot(170, 70)
    assert law.atoms == ((pytest.approx(expected), 1.0),)
    assert expected > math.dist((280, 40), (40, 280))
    assert a.warnings


def test_activity_subdivision_preserves_mass_mean_and_gate_load():
    from metroflow.terrain_city.area_access import Portal

    c = fixture_city()
    patches = (ActivityPatch(800, ((280.0, 40.0),)), ActivityPatch(200, ((40.0, 280.0),)))
    a = compile_activity(c, "block", patches=patches)
    b = compile_activity(
        c,
        "block",
        patches=tuple(ActivityPatch(p.mass / 4, p.points) for p in patches for _ in range(4)),
    )
    doors = (Portal("east", (310.0, 10.0)), Portal("north", (10.0, 310.0)))
    la, ra = activity_access(a, doors)
    lb, rb = activity_access(b, doors)
    assert a.mass == b.mass == 1000
    assert la.mean_s == pytest.approx(lb.mean_s)
    assert dict(la.portal_weights()) == pytest.approx(dict(lb.portal_weights()))
    assert dict(la.portal_weights()) == {"east": 0.8, "north": 0.2}
    assert ra["quantile_certificate"] == rb["quantile_certificate"] == "NOT_CERTIFIED"
    with pytest.raises(ValueError, match="generalized"):
        activity_access(a, (Portal("east", (310.0, 10.0), 20.0),))


def test_multiple_doors_capacity_and_budget_without_mass_deletion():
    c = fixture_city()
    m = compile_activity(
        c,
        "block",
        patches=(ActivityPatch(500, ((280.0, 40.0),)), ActivityPatch(500, ((40.0, 280.0),))),
    )
    east = compile_entry(c, m, "east", capacity_veh_s=0.5, corridor=((280.0, 40.0), (310.0, 10.0)))
    north = compile_entry(
        c, m, "north", capacity_veh_s=0.5, corridor=((40.0, 280.0), (10.0, 310.0))
    )
    result = select_entries(
        m,
        (east, north),
        construction_budget_m=100,
        max_distance_m=100,
        forecast_vehicles=100,
        horizon_s=100,
    )
    assert result["status"] == "PASS"
    assert set(result["alternatives"][0]["portals"]) == {"east", "north"}
    assert all(not row["feasible"] for row in result["candidates"] if len(row["portals"]) == 1)
    blocked = select_entries(
        m,
        (east, north),
        construction_budget_m=1,
        max_distance_m=100,
        forecast_vehicles=100,
        horizon_s=100,
    )
    assert blocked["status"] == "PHYSICAL_INFEASIBLE" and blocked["total_activity"] == 1000
    overloaded = select_entries(
        m,
        (east, north),
        construction_budget_m=100,
        max_distance_m=100,
        forecast_vehicles=200,
        horizon_s=100,
    )
    assert overloaded["status"] == "PHYSICAL_INFEASIBLE"
    assert overloaded["candidates"][-1]["excess_vehicles"] == 100
    with pytest.raises(CityContractError, match="corridor"):
        compile_entry(c, m, "east", capacity_veh_s=1, corridor=((40.0, 280.0), (310.0, 10.0)))


def test_conditional_budget_and_refinement_error_are_separate():
    from metroflow.terrain_city.area_access import Portal

    m = compile_activity(fixture_city(), "block")
    doors = (Portal("east", (310.0, 10.0)), Portal("north", (10.0, 310.0)))
    a, ra = activity_access(m, doors, depth=1, bin_s=20.0)
    b, rb = activity_access(m, doors, depth=2, bin_s=20.0)
    assert abs(a.mean_s - b.mean_s) <= a.quadrature_mean_bound_s + b.quadrature_mean_bound_s
    assert rb["quadrature_mean_bound_s"] < ra["quadrature_mean_bound_s"]
    assert b.original_variance_s2 == pytest.approx(b.compressed_variance_s2 + b.variance_loss_s2)
    with pytest.raises(ValueError, match="budget"):
        activity_access(m, doors, depth=2, bin_s=0.01, max_atoms_per_portal=1)


def test_job_service_units_and_point_concentration_aggregation():
    c = fixture_city()
    assert compile_activity(c, "block", "job").mass == 200
    s = compile_activity(c, "block", "service", service_stock=50)
    assert s.mass == 50 and s.units == "opportunities"
    m = compile_activity(
        c, "block", patches=tuple(ActivityPatch(10, ((40.0, 40.0),)) for _ in range(100))
    )
    assert m.warnings


def test_gate_conditioning_retains_probability_and_per_gate_budget():
    from metroflow.terrain_city.area_access import Portal

    c = fixture_city()
    m = compile_activity(
        c,
        "block",
        patches=(ActivityPatch(800, ((280.0, 40.0),)), ActivityPatch(200, ((40.0, 280.0),))),
    )
    law, _ = activity_access(
        m, (Portal("a", (310.0, 10.0)), Portal("b", (10.0, 310.0))), max_atoms_per_portal=1
    )
    assert len(law.atoms) == 2  # Budget is per conditional gate, not global.
    probability, conditional = law.condition("a")
    assert probability == 0.8 and sum(w for _, w in conditional) == 1
    assert m.mass * probability == 800
    for budget in (True, 0, 257):
        with pytest.raises(ValueError, match="budget"):
            activity_access(m, (Portal("a", (310.0, 10.0)),), max_atoms_per_portal=budget)


def test_existing_entries_remain_and_labels_do_not_choose_ties():
    from dataclasses import replace

    c = fixture_city()
    m = compile_activity(c, "block", patches=(ActivityPatch(1000, ((40.0, 40.0),)),))
    east = compile_entry(
        c, m, "east", capacity_veh_s=1, corridor=((40.0, 40.0), (310.0, 10.0)), existing=True
    )
    north = compile_entry(c, m, "north", capacity_veh_s=1, corridor=((40.0, 40.0), (10.0, 310.0)))
    result = select_entries(
        m,
        (east, north),
        construction_budget_m=0,
        max_distance_m=1000,
        forecast_vehicles=0,
        horizon_s=100,
    )
    assert result["alternatives"][0]["portals"] == ("east",)
    assert east.construction_length_m == 0
    with pytest.raises(CityContractError, match="different city"):
        select_entries(
            m,
            (replace(east, city_identity="stale"),),
            construction_budget_m=0,
            max_distance_m=1000,
            forecast_vehicles=0,
            horizon_s=100,
        )
    # Equal physical objective retains both alternatives instead of sorting IDs.
    equal = (replace(east, existing=False), replace(north, construction_length_m=0))
    result = select_entries(
        m,
        equal,
        construction_budget_m=0,
        max_distance_m=1000,
        forecast_vehicles=0,
        horizon_s=100,
        load_weight_s=0,
    )
    assert len(result["alternatives"]) == 3
