"""Fluid priority allocation with throughput-preserving residual augmentation.

Work depends on movements/resources, never on the number of represented cars.
Weighted progressive filling gives exact priority shares for simple merges;
augmenting residual paths then remove avoidable holding in general nodes.
General-node fairness is a heuristic; maximum total feasible flow is exact up
 to the declared floating comparison tolerance.
"""

from collections import deque
import math


def allocate(demands: dict, sending: dict, receiving: dict, priorities: dict | None = None) -> dict:
    keys = tuple(sorted(demands))
    priorities = priorities or {}
    if any(
        not math.isfinite(v) or v < 0
        for table in (demands, sending, receiving)
        for v in table.values()
    ):
        raise ValueError("flow limits must be finite nonnegative vehicle equivalents")
    if any(not math.isfinite(v) or v <= 0 for v in priorities.values()):
        raise ValueError("priority weights must be finite positive")
    if any(i not in sending or j not in receiving for i, j in keys):
        raise ValueError("missing movement resource")
    tol = 1e-12 * max(1.0, max(sending.values(), default=0.0), max(receiving.values(), default=0.0))
    y = {m: 0.0 for m in keys}
    si = dict(sending)
    rj = dict(receiving)
    totals = {i: math.fsum(demands[m] for m in keys if m[0] == i) for i in si}
    weights = {
        m: priorities.get(m[0], 1.0) * demands[m] / totals[m[0]] if totals[m[0]] else 0.0
        for m in keys
    }
    for _ in range(len(keys) + len(si) + len(rj) + 1):
        active = [m for m in keys if demands[m] - y[m] > tol and si[m[0]] > tol and rj[m[1]] > tol]
        if not active:
            break
        sw = {i: math.fsum(weights[m] for m in active if m[0] == i) for i in si}
        rw = {j: math.fsum(weights[m] for m in active if m[1] == j) for j in rj}
        delta = min(
            [(demands[m] - y[m]) / weights[m] for m in active]
            + [si[i] / s for i, s in sw.items() if s > 0]
            + [rj[j] / s for j, s in rw.items() if s > 0]
        )
        for m in active:
            v = delta * weights[m]
            y[m] += v
            si[m[0]] -= v
            rj[m[1]] -= v

    # Seed a residual network with the feasible progressive allocation.
    incoming = sorted(si)
    outgoing = sorted(rj)
    ia = {i: k + 1 for k, i in enumerate(incoming)}
    ja = {j: k + 1 + len(ia) for k, j in enumerate(outgoing)}
    sink = 1 + len(ia) + len(ja)
    adj = [[] for _ in range(sink + 1)]

    def add(u, v, capacity, used):
        forward = [v, len(adj[v]), max(0.0, capacity - used)]
        reverse = [u, len(adj[u]), used]
        adj[u].append(forward)
        adj[v].append(reverse)
        return forward

    for i in incoming:
        add(0, ia[i], sending[i], math.fsum(y[m] for m in keys if m[0] == i))
    refs = {m: add(ia[m[0]], ja[m[1]], demands[m], y[m]) for m in keys}
    for j in outgoing:
        add(ja[j], sink, receiving[j], math.fsum(y[m] for m in keys if m[1] == j))
    while True:
        parent = [None] * len(adj)
        parent[0] = (-1, -1)
        queue = deque([0])
        while queue and parent[sink] is None:
            u = queue.popleft()
            for k, e in enumerate(adj[u]):
                v, _, cap = e
                if cap > tol and parent[v] is None:
                    parent[v] = (u, k)
                    queue.append(v)
                    if v == sink:
                        break
        if parent[sink] is None:
            break
        v = sink
        amount = math.inf
        while v:
            u, k = parent[v]
            amount = min(amount, adj[u][k][2])
            v = u
        v = sink
        while v:
            u, k = parent[v]
            e = adj[u][k]
            e[2] -= amount
            adj[v][e[1]][2] += amount
            v = u
    # Reverse residual is the served amount; avoids cancellation D-(D-y)
    # when represented demand is much larger than physical service capacity.
    return {m: adj[refs[m][0]][refs[m][1]][2] for m in keys}
