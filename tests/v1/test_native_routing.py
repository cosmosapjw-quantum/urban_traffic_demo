"""Execute the native extension against the independent Python V1 oracle.

These tests deliberately fail on a missing extension: a skipped native build
must never be presented as successful parity evidence.
"""
import math
import random

import pytest

from metroflow.active_suffix.routing import Arc, candidate_paths
from metroflow.v1.native_routing import NativeRoutingGraph


def assert_parity(arcs, costs, turns, endpoints, budgets=(0, 1, 3, 2000)):
    graph = NativeRoutingGraph(arcs, costs, turns, max_destinations=2)
    for origin, destination in endpoints:
        for k in (1, 3):
            for budget in budgets:
                expected = candidate_paths(arcs, costs, origin, destination, k,
                                           budget, allowed_turns=turns)
                assert graph.search(origin, destination, k, budget) == expected
        assert len(graph.cached_destinations) <= 2


def test_native_ties_parallel_links_zero_costs_and_unknown_endpoints():
    arcs = (Arc("z", "O", "A"), Arc("a", "O", "A"),
            Arc("2", "A", "D"), Arc("10", "A", "D"),
            Arc("loop", "O", "O"), Arc("return", "A", "O"),
            Arc("dead", "O", "X"))
    costs = {a.id: 0.0 if a.id == "loop" else 1.0 for a in arcs}
    costs["dead"] = math.inf
    for turns in (None, frozenset(), frozenset(
            (a.id, b.id) for a in arcs for b in arcs if a.head == b.tail)):
        assert_parity(arcs, costs, turns,
                      (("O", "D"), ("O", "O"), ("X", "D"),
                       ("missing", "D"), ("O", "missing")))


def test_native_randomized_exact_paths_expansions_and_truncation():
    rng = random.Random(731)
    for _ in range(30):
        nodes = tuple("ABCDE")
        arcs = tuple(Arc(f"e{i}", a, b) for i, (a, b) in enumerate(
            (a, b) for a in nodes for b in nodes if rng.random() < .32))
        costs = {a.id: rng.choice((0.0, .1, .3, 1.0, 2.0, math.inf)) for a in arcs}
        turns = frozenset((a.id, b.id) for a in arcs for b in arcs
                          if a.head == b.tail and rng.random() < .75)
        assert_parity(arcs, costs, turns, ((a, b) for a in nodes for b in nodes),
                      budgets=(0, 2, 15))


def test_native_loopless_constraint_is_not_link_state_shortest_walk():
    # The only legal walk O-A-B-A-D repeats A, so the loopless oracle rejects it.
    arcs = (Arc("oa", "O", "A"), Arc("ab", "A", "B"),
            Arc("ba", "B", "A"), Arc("ad", "A", "D"))
    costs = {a.id: 1.0 for a in arcs}
    turns = (("oa", "ab"), ("ab", "ba"), ("ba", "ad"))
    graph = NativeRoutingGraph(arcs, costs, turns)
    assert graph.search("O", "D").paths == ()
    assert_parity(arcs, costs, turns, (("O", "D"), ("B", "D")))


def test_native_f64_distinguishes_routes_below_f32_precision():
    arcs = (Arc("a", "O", "D"), Arc("z", "O", "D"))
    costs = {"a": 1.0 + 1e-12, "z": 1.0}
    graph = NativeRoutingGraph(arcs, costs)
    assert graph.search("O", "D", 1).paths == (("z",),)


def test_native_batch_preserves_query_order_and_exact_metadata():
    arcs = (Arc("ab", "A", "B"), Arc("bc", "B", "C"))
    costs = {a.id: .1 for a in arcs}
    endpoints = (("A", "C"), ("A", "B"), ("B", "A"))
    graph = NativeRoutingGraph(arcs, costs)
    assert graph.search_batch(endpoints, 2, 3) == tuple(
        candidate_paths(arcs, costs, a, b, 2, 3) for a, b in endpoints)
    assert graph.search_batch(()) == ()


def test_native_destination_cache_is_bounded_lru_and_snapshot_owned():
    arcs = (Arc("ab", "A", "B"), Arc("bc", "B", "C"), Arc("cd", "C", "D"))
    costs = {a.id: 1.0 for a in arcs}
    graph = NativeRoutingGraph(arcs, costs, max_destinations=2)
    graph.search("A", "B")
    graph.search("A", "C")
    graph.search("A", "B")
    assert graph.cached_destinations == ("C", "B")
    assert graph.potential_builds == 2
    graph.search("A", "D")
    assert graph.cached_destinations == ("B", "D")
    graph.search("A", "C")
    assert graph.potential_builds == 4
    costs["ab"] = math.inf
    assert graph.search("A", "B").paths == (("ab",),)
    no_cache = NativeRoutingGraph(arcs, {a.id: 1.0 for a in arcs}, max_destinations=0)
    no_cache.search("A", "D")
    no_cache.search("A", "D")
    assert no_cache.cached_destinations == () and no_cache.potential_builds == 2


@pytest.mark.parametrize("cost", [math.nan, -1.0, -math.inf])
def test_native_rejects_invalid_costs(cost):
    with pytest.raises(ValueError, match="costs must be nonnegative"):
        NativeRoutingGraph((Arc("a", "A", "B"),), {"a": cost})


def test_native_invalid_inputs_and_empty_graph():
    with pytest.raises(ValueError, match="duplicate links"):
        NativeRoutingGraph((Arc("a", "A", "B"), Arc("a", "B", "C")), {"a": 1.0})
    with pytest.raises(ValueError, match="costs must be nonnegative"):
        NativeRoutingGraph((Arc("a", "A", "B"),), {})
    graph = NativeRoutingGraph((), {})
    assert graph.search("A", "B") == candidate_paths((), {}, "A", "B")
    for k, budget in ((0, 2), (1, -1)):
        with pytest.raises(ValueError, match="invalid route search budget"):
            graph.search("A", "B", k, budget)
