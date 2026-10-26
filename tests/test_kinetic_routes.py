import pytest
from metroflow.kinetic_routes import shortest_path, k_shortest_paths, wardrop_affine


def test_dijkstra_uses_cost_not_hop_count_and_never_negative_cost():
    arcs = (("s", "a", 2.0), ("a", "t", 2.0), ("s", "t", 10.0))
    assert shortest_path(arcs, "s", "t") == (0, 1)
    with pytest.raises(ValueError):
        shortest_path((("s", "t", -1.0),), "s", "t")


def test_bounded_candidates_include_bypass_without_cycles():
    arcs = (("s", "a", 2.0), ("a", "t", 2.0), ("s", "b", 3.0), ("b", "t", 3.0), ("a", "s", 0.1))
    assert k_shortest_paths(arcs, "s", "t", 3) == ((0, 1), (2, 3))


def test_braess_user_equilibrium_is_not_system_optimality():
    arcs = (
        ("s", "a", 0.0, 100.0),
        ("a", "t", 100.0, 0.0),
        ("s", "b", 100.0, 0.0),
        ("b", "t", 0.0, 100.0),
    )
    old = wardrop_affine(arcs, "s", "t", 1.0)
    new = wardrop_affine(arcs + (("a", "b", 1.0, 0.0),), "s", "t", 1.0)
    assert old["mean_cost_s"] == pytest.approx(150.0, abs=0.01)
    assert new["mean_cost_s"] == pytest.approx(199.0, abs=0.1)
    assert new["gap"] < 0.002


def test_route_search_has_explicit_work_budget():
    with pytest.raises(RuntimeError, match="budget"):
        k_shortest_paths((("s", "a", 1.0), ("a", "t", 1.0)), "s", "t", 3, max_searches=0)
