import math
import pytest
from metroflow.terrain_city.area_access import AreaAccess, Portal


def test_area_mean_is_not_the_single_centre_to_corner_time():
    model = AreaAccess(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)))
    report = model.evaluate((Portal("gate", (0.0, 0.0)),), speed_mps=1.0, depth=3)
    exact = 100 / 3 * (math.sqrt(2) + math.log(1 + math.sqrt(2)))
    assert abs(report["mean_s"] - exact) <= report["error_bound_s"] + 1e-10
    assert report["error_bound_s"] < 8.0


def test_internal_route_cannot_cross_the_concave_missing_area():
    model = AreaAccess(((0.0, 0.0), (3.0, 0.0), (3.0, 1.0), (1.0, 1.0), (1.0, 3.0), (0.0, 3.0)))
    cost = model.cost_at((0.5, 2.5), (Portal("gate", (3.0, 0.0)),), speed_mps=1.0)
    assert cost == pytest.approx(math.sqrt(2.5) + math.sqrt(5.0))


def test_boundary_cyclic_reverse_and_collinear_samples_are_representation_only():
    p = ((0.0, 0.0), (80.0, 0.0), (80.0, 40.0), (0.0, 40.0))
    variants = (
        p,
        p[2:] + p[:2],
        tuple(reversed(p)),
        ((0.0, 0.0), (40.0, 0.0), (80.0, 0.0), (80.0, 40.0), (0.0, 40.0), (0.0, 0.0)),
    )
    reports = [AreaAccess(q).evaluate((Portal("a", (0.0, 0.0)),), depth=2) for q in variants]
    assert all(r == reports[0] for r in reports)


def test_passive_frame_covariance_of_exact_moments_and_integral_bounds():
    p = ((0.0, 0.0), (80.0, 0.0), (80.0, 40.0), (0.0, 40.0))
    base = AreaAccess(p)
    theta = 0.71
    c, s = math.cos(theta), math.sin(theta)

    def transform(p):
        return (c * p[0] - s * p[1] + 1200, s * p[0] + c * p[1] - 340)

    rotated = AreaAccess(tuple(map(transform, p)))
    assert rotated.area_m2 == pytest.approx(base.area_m2, rel=1e-12)
    assert rotated.centroid == pytest.approx(transform(base.centroid), abs=1e-10)
    A = base.covariance
    R = ((c, -s), (s, c))
    for i in range(2):
        for j in range(2):
            expected = sum(
                R[i][k] * A[k][column_index] * R[j][column_index]
                for k in range(2)
                for column_index in range(2)
            )
            assert rotated.covariance[i][j] == pytest.approx(expected, abs=1e-9)
    a = base.evaluate((Portal("x", (0.0, 0.0)),), depth=3)
    b = rotated.evaluate((Portal("renamed", transform((0.0, 0.0))),), depth=3)
    # A regenerated finite triangulation is NOT an exact coordinate gauge.
    assert abs(a["mean_s"] - b["mean_s"]) <= a["error_bound_s"] + b["error_bound_s"]


def test_exact_second_distance_moment_and_refinement_certificate():
    m = AreaAccess(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)))
    assert m.squared_distance_mean((0.0, 0.0)) == pytest.approx(20000 / 3)
    exact = 100 / 3 * (math.sqrt(2) + math.asinh(1))
    rows = [m.evaluate((Portal("x", (0.0, 0.0)),), depth=d, speed_mps=1.0) for d in range(4)]
    for r in rows:
        assert r["weight_sum"] == pytest.approx(1.0, abs=1e-12)
        assert r["mean_interval_s"][0] <= exact <= r["mean_interval_s"][1]
    for a, b in zip(rows, rows[1:]):
        assert b["error_bound_s"] == pytest.approx(a["error_bound_s"] / 2)


def test_portal_labels_do_not_affect_cost_and_symmetric_physical_gates_share_area():
    m = AreaAccess(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)))
    a = m.evaluate((Portal("left", (0.0, 50.0)), Portal("right", (100.0, 50.0))), depth=3)
    b = m.evaluate((Portal("aaa", (100.0, 50.0)), Portal("zzz", (0.0, 50.0))), depth=3)
    assert a["mean_s"] == pytest.approx(b["mean_s"])
    assert a["portal_fraction"]["left"] == pytest.approx(0.5)
    assert b["portal_fraction"]["zzz"] == pytest.approx(0.5)
    broken = m.evaluate(
        (Portal("left", (0.0, 50.0)), Portal("right", (100.0, 50.0), 200.0)), depth=3
    )
    assert broken["portal_fraction"]["left"] == 1.0


def test_added_real_portal_can_improve_service_but_keeps_mass_and_geometry():
    m = AreaAccess(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)))
    p = Portal("left", (0.0, 50.0))
    q = Portal("right", (100.0, 50.0))
    a = m.evaluate((p,), depth=3)
    b = m.evaluate((p, q), depth=3)
    assert b["mean_s"] < a["mean_s"] and b["area_m2"] == a["area_m2"]
    assert sum(b["portal_fraction"].values()) == pytest.approx(1.0)
    candidates = m.candidate_additions((p,), (q, Portal("top", (50.0, 100.0))), depth=2)
    assert candidates["not_excluded"]


def test_invalid_domains_and_ambiguously_duplicate_portals_fail():
    with pytest.raises(ValueError):
        AreaAccess(((0, 0), (1, 1), (0, 1), (1, 0)))
    m = AreaAccess(((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)))
    with pytest.raises(ValueError):
        m.evaluate((Portal("x", (5.0, 5.0)),))
    with pytest.raises(ValueError):
        m.evaluate((Portal("x", (0.0, 0.0)), Portal("y", (0.0, 0.0))))
    with pytest.raises(ValueError):
        m.evaluate((Portal("x", (0.0, 0.0)),), depth=8, max_samples=10)
    with pytest.raises(ValueError):
        m.cost_at((20.0, 20.0), (Portal("x", (0.0, 0.0)),))
