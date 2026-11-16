"""Thin frontend for the persistent, f64, V1 legal-turn Rust graph.

The native graph owns adjacency and bounded destination potentials. No fallback
to a different routing closure occurs when this backend is explicitly selected.
"""
from ..active_suffix.routing import SearchResult


class NativeRoutingGraph:
    def __init__(self, arcs, costs, allowed_turns=None, *, max_destinations=8):
        try:
            from _metroflow_rust import V1RoutingGraph
        except ImportError as exc:
            raise RuntimeError("V1 Rust routing unavailable; rebuild metroflow-rust") from exc
        arcs = tuple(arcs)
        if any(a.id not in costs for a in arcs):
            raise ValueError("costs must be nonnegative seconds, +infinity means unavailable")
        if isinstance(max_destinations, bool) or not isinstance(max_destinations, int) or max_destinations < 0:
            raise ValueError("nonnegative integer destination cache budget required")
        self._native = V1RoutingGraph(
            [(a.id, a.tail, a.head) for a in arcs], [costs[a.id] for a in arcs],
            None if allowed_turns is None else list(allowed_turns), max_destinations,
        )

    def search(self, origin, destination, k=3, expansion_budget=2000):
        if k < 1 or expansion_budget < 0:
            raise ValueError("invalid route search budget")
        paths, expanded, truncated = self._native.search(origin, destination, k, expansion_budget)
        return SearchResult(tuple(tuple(p) for p in paths), expanded, truncated)

    def search_batch(self, endpoints, k=3, expansion_budget=2000):
        if k < 1 or expansion_budget < 0:
            raise ValueError("invalid route search budget")
        return tuple(SearchResult(tuple(tuple(p) for p in paths), expanded, truncated)
                     for paths, expanded, truncated in
                     self._native.search_batch(list(endpoints), k, expansion_budget))

    @property
    def cached_destinations(self):
        return tuple(self._native.cached_destinations)

    @property
    def potential_builds(self):
        return self._native.potential_builds
