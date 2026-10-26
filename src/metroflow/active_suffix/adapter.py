"""Explicit research map-to-traffic contract; no calibrated road attributes.

Two directed roads per surface segment. At degree>=3 junctions, one incoming
approach receives green at a time, followed by 2 s all-red. This conservative
plan prevents declared conflicts; it is not a model of real signal optimization.
No external map/traffic measurements are used.
"""

from dataclasses import replace
from itertools import combinations
import math
from .common import Road, Signal


def roads_from_history(history, epoch):
    nodes, edges = history.nodes, history.active(epoch)
    byid = {n.id: n for n in nodes}
    incoming = {}
    speeds = {"primary": 14.0, "secondary": 11.0, "local": 8.0}
    capacities = {"primary": 1.0, "secondary": 0.5, "local": 0.3}
    roads = []
    for edge in edges:
        a, b = byid[edge.u], byid[edge.v]
        length = math.hypot(a.x - b.x, a.y - b.y)
        for u, v in ((edge.u, edge.v), (edge.v, edge.u)):
            road = Road(
                f"e{edge.id}:{u}>{v}",
                str(u),
                str(v),
                length,
                speeds.get(edge.hierarchy, 8.0),
                capacities.get(edge.hierarchy, 0.3),
                max(2.0, 0.12 * length),
            )
            incoming.setdefault(str(v), []).append(len(roads))
            roads.append(road)
    conflicts = []
    for ids in incoming.values():
        if len(ids) < 3:
            continue
        ids.sort(key=lambda i: roads[i].id)
        for phase, i in enumerate(ids):
            roads[i] = replace(roads[i], signal=Signal(30.0 * len(ids), 28.0, 30.0 * phase))
        conflicts.extend((roads[i].id, roads[j].id) for i, j in combinations(ids, 2))
    return tuple(roads), tuple(conflicts)
