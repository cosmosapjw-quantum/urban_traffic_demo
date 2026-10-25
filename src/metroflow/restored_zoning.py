"""Reuse terrain/stock rules with actual surface-road frontage, not grid IDs."""

import math
from collections import Counter
from .environment.terrain import Node, Link, Network
from .environment.landuse import zone_city
from .restored_geometry import components, terrain_gate, ground_profile


def attach_zones(roadmap, population=100000, jobs=40000, max_access_m=500.0):
    if not math.isfinite(max_access_m) or max_access_m <= 0:
        raise ValueError("invalid frontage radius")
    comp = components(roadmap)
    sizes = Counter(comp.values())
    main = min(sizes, key=lambda i: (-sizes[i], i))
    by = {n.id: n for n in roadmap.nodes}
    eligible = {
        v
        for s in roadmap.sections
        if s.facility == "surface"
        for v in (s.start, s.end)
        if comp[v] == main and by[v].layer == 0
    }
    front = {}
    distance = {}
    t = roadmap.terrain
    for j in range(t.n):
        for i in range(t.n):
            p = ((i + 0.5) * t.spacing_m, (j + 0.5) * t.spacing_m)
            for key in sorted(eligible, key=lambda k: (math.dist(p, by[k].xyz[:2]), k)):
                q = by[key].xyz[:2]
                d = math.dist(p, q)
                if d > max_access_m:
                    break
                if terrain_gate(t, (p, q), 2.0, "surface"):
                    continue
                if d > 1e-8 and ground_profile(t, (p, q))[2] > 0.12:
                    continue
                front[i, j] = (key,)
                distance[f"z{i}:{j}"] = d
                break
    network = Network(
        tuple(Node(n.id, *n.xyz) for n in roadmap.nodes),
        tuple(
            Link(
                s.id,
                s.start,
                s.end,
                s.length_m,
                s.max_grade,
                s.facility,
                s.length_m * (4.0 if s.facility != "surface" else 1.0),
            )
            for s in roadmap.sections
        ),
        tuple(sorted(comp.items())),
        roadmap.rejected,
    )
    city = zone_city(t, network, population, jobs, frontage_nodes=front)
    return city, {z.id: distance[z.id] for z in city.zones if z.access_node is not None}
