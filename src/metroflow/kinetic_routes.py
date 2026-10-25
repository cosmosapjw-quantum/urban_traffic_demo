"""Pure-Python nonnegative Dijkstra guidance, bounded Yen paths, Wardrop oracle.

Costs are seconds. The equilibrium oracle accepts affine cost c_e=a_e+b_e*x_e;
it minimizes the Beckmann integral, NOT total travel time. It is a separate
static diagnostic, not evidence that a transient kinetic network is at equilibrium.
"""

from __future__ import annotations
import heapq
import math


def shortest_path(arcs, source, destination, *, banned_nodes=frozenset(), banned_edges=frozenset()):
    adj = {}
    for i, (u, v, c) in enumerate(arcs):
        if math.isnan(c) or c < 0:
            raise ValueError("Dijkstra costs must be nonnegative, not NaN")
        if (
            i not in banned_edges
            and u not in banned_nodes
            and v not in banned_nodes
            and math.isfinite(c)
        ):
            adj.setdefault(u, []).append((v, c, i))
    if source in banned_nodes or destination in banned_nodes:
        return None
    dist = {source: 0.0}
    prev = {}
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d != dist.get(u):
            continue
        if u == destination:
            out = []
            while u != source:
                u, e = prev[u]
                out.append(e)
            return tuple(reversed(out))
        for v, c, e in adj.get(u, ()):
            new = d + c
            if new < dist.get(v, math.inf):
                dist[v] = new
                prev[v] = (u, e)
                heapq.heappush(heap, (new, v))
    return None


def destination_potential(arcs, destination):
    """Reverse Dijkstra cost-to-go, not a mechanical force potential."""
    adj = {}
    for u, v, c in arcs:
        if math.isnan(c) or c < 0:
            raise ValueError("invalid Dijkstra cost")
        if math.isfinite(c):
            adj.setdefault(v, []).append((u, c))
    distances = {destination: 0.0}
    heap = [(0.0, destination)]
    while heap:
        cost, v = heapq.heappop(heap)
        if cost != distances[v]:
            continue
        for u, c in adj.get(v, ()):
            candidate = cost + c
            if candidate < distances.get(u, math.inf):
                distances[u] = candidate
                heapq.heappush(heap, (candidate, u))
    return distances


def k_shortest_paths(arcs, source, destination, k=3, *, max_searches=512):
    """Yen's loopless alternatives with a hard Dijkstra-call budget."""
    if not isinstance(k, int) or not 1 <= k <= 8:
        raise ValueError("k must be 1..8")
    calls = 0

    def search(s, **kwargs):
        nonlocal calls
        calls += 1
        if calls > max_searches:
            raise RuntimeError("route-search budget exhausted")
        return shortest_path(arcs, s, destination, **kwargs)

    first = search(source)
    if first is None:
        return ()
    accepted = [first]
    seen = {first}
    pending = []
    while len(accepted) < k:
        previous = accepted[-1]
        vertices = [source] + [arcs[e][1] for e in previous]
        for i in range(len(previous)):
            root = previous[:i]
            banned = frozenset(p[i] for p in accepted if len(p) > i and p[:i] == root)
            tail = search(vertices[i], banned_nodes=frozenset(vertices[:i]), banned_edges=banned)
            if tail is None:
                continue
            candidate = root + tail
            if candidate not in seen:
                seen.add(candidate)
                heapq.heappush(pending, (sum(arcs[e][2] for e in candidate), candidate))
        if not pending:
            break
        accepted.append(heapq.heappop(pending)[1])
    return tuple(accepted)


def wardrop_affine(arcs, source, destination, demand=1.0, *, max_iterations=5000, tolerance=1e-7):
    """Frank-Wolfe with exact line search on separable affine Beckmann cost."""
    if not math.isfinite(demand) or demand <= 0:
        raise ValueError("positive finite demand required")
    if any(not math.isfinite(a + b) or a < 0 or b < 0 for _, _, a, b in arcs):
        raise ValueError("nonnegative finite affine cost coefficients required")

    def costs(x):
        return tuple((u, v, a + b * x[i]) for i, (u, v, a, b) in enumerate(arcs))

    x = [0.0] * len(arcs)
    path = shortest_path(costs(x), source, destination)
    if path is None:
        raise ValueError("destination unreachable")
    for e in path:
        x[e] = demand
    iteration = 0
    for iteration in range(max_iterations):
        cs = costs(x)
        path = shortest_path(cs, source, destination)
        y = [demand if e in path else 0.0 for e in range(len(arcs))]
        direction = [z - v for z, v in zip(y, x)]
        gap = -sum(cs[i][2] * direction[i] for i in range(len(x)))
        objective = sum(cs[i][2] * x[i] for i in range(len(x)))
        if gap / max(1.0, objective) <= tolerance:
            break
        curvature = sum(arcs[i][3] * direction[i] ** 2 for i in range(len(x)))
        step = min(1.0, max(0.0, gap / curvature)) if curvature > 0 else 1.0
        x = [v + step * d for v, d in zip(x, direction)]
    cs = costs(x)
    path = shortest_path(cs, source, destination)
    total = sum(x[i] * cs[i][2] for i in range(len(x)))
    gap = max(0.0, total - demand * sum(cs[i][2] for i in path)) / max(1.0, total)
    return dict(
        flows=tuple(x),
        mean_cost_s=total / demand,
        gap=gap,
        iterations=iteration + 1,
        converged=gap <= tolerance,
    )
