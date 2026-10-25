"""Coarse terrain-to-network compiler. Metres, seconds, dimensionless grade.

Bilinear elevation between raster vertices; surface roads are raster edges.
Water/protected rectangles are hard exclusions, not rendering layers.
"""

from __future__ import annotations
from dataclasses import dataclass
import math
import random
from collections import Counter


@dataclass(frozen=True, slots=True)
class Rect:
    xmin: float
    ymin: float
    xmax: float
    ymax: float


@dataclass(frozen=True, slots=True)
class Terrain:
    n: int
    spacing_m: float
    heights_m: tuple[float, ...]
    water: tuple[Rect, ...] = ()
    protected: tuple[Rect, ...] = ()
    bridge_rows: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    x_m: float
    y_m: float
    z_m: float


@dataclass(frozen=True, slots=True)
class Link:
    id: str
    u: str
    v: str
    length_m: float
    grade: float
    kind: str
    construction_index_m: float


@dataclass(frozen=True, slots=True)
class Network:
    nodes: tuple[Node, ...]
    links: tuple[Link, ...]
    components: tuple[tuple[str, int], ...]
    rejected: tuple[tuple[str, int], ...]


def validate_terrain(t: Terrain) -> None:
    if isinstance(t.n, bool) or not isinstance(t.n, int) or t.n < 1:
        raise ValueError("n must be a positive integer")
    if not math.isfinite(t.spacing_m) or t.spacing_m <= 0:
        raise ValueError("spacing must be finite and positive")
    if len(t.heights_m) != (t.n + 1) ** 2 or not all(map(math.isfinite, t.heights_m)):
        raise ValueError("invalid vertex-height raster")
    for r in t.water + t.protected:
        if (
            not all(map(math.isfinite, (r.xmin, r.ymin, r.xmax, r.ymax)))
            or r.xmin >= r.xmax
            or r.ymin >= r.ymax
        ):
            raise ValueError("invalid exclusion rectangle")
    if any(
        isinstance(r, bool) or not isinstance(r, int) or not 0 <= r <= t.n for r in t.bridge_rows
    ) or len(set(t.bridge_rows)) != len(t.bridge_rows):
        raise ValueError("invalid bridge rows")


def node_id(x: int, y: int) -> str:
    return f"n{x}:{y}"


def height(t: Terrain, x: int, y: int) -> float:
    return t.heights_m[y * (t.n + 1) + x]


def cell_slope(t: Terrain, x: int, y: int) -> float:
    """Maximum |gradient| of the declared bilinear cell, attained at a corner."""
    a, b, c, d = (
        height(t, x, y),
        height(t, x + 1, y),
        height(t, x, y + 1),
        height(t, x + 1, y + 1),
    )
    return max(math.hypot(gx, gy) for gx in (b - a, d - c) for gy in (c - a, d - b)) / t.spacing_m


def intersects(p: tuple[float, float], q: tuple[float, float], r: Rect, margin=0.0) -> bool:
    """Closed segment/expanded axis-aligned box test, including tangency.

    A box expansion is conservative for a round road-width buffer at corners.
    It never permits a centreline to jump across an unsampled narrow river.
    """
    lo, hi = 0.0, 1.0
    for a, b, mn, mx in (
        (p[0], q[0], r.xmin - margin, r.xmax + margin),
        (p[1], q[1], r.ymin - margin, r.ymax + margin),
    ):
        delta = b - a
        if delta == 0:
            if not mn <= a <= mx:
                return False
        else:
            u, v = sorted(((mn - a) / delta, (mx - a) / delta))
            lo = max(lo, u)
            hi = min(hi, v)
            if lo > hi:
                return False
    return True


def overlaps(a: Rect, b: Rect, margin=0.0) -> bool:
    return (
        a.xmin <= b.xmax + margin
        and a.xmax >= b.xmin - margin
        and a.ymin <= b.ymax + margin
        and a.ymax >= b.ymin - margin
    )


def synthetic_terrain(n=12, spacing_m=400.0, seed=17, bridges=True) -> Terrain:
    """Authored river/woodland/hill fixture, not a hydrology or erosion solver."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 4 or n % 2:
        raise ValueError("synthetic fixture requires even n >= 4")
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("invalid spacing")
    extent = n * spacing_m
    rng = random.Random(seed)
    water = (Rect(0.48 * extent, -spacing_m, 0.52 * extent, extent + spacing_m),)
    protected = (Rect(0.76 * extent, 0.76 * extent, extent + spacing_m, extent + spacing_m),)
    hx = (0.78 + rng.uniform(-0.015, 0.015)) * extent
    hy = (0.73 + rng.uniform(-0.015, 0.015)) * extent
    hills = []
    for j in range(n + 1):
        for i in range(n + 1):
            x, y = i * spacing_m, j * spacing_m
            h = (
                20.0
                + 0.003 * x
                + 0.004 * y
                + 160.0 * math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (2 * (0.13 * extent) ** 2))
            )
            if intersects((x, y), (x, y), water[0]):
                h = -2.0
            hills.append(h)
    return Terrain(
        n, spacing_m, tuple(hills), water, protected, (n // 3, 2 * n // 3) if bridges else ()
    )


def compile_network(
    terrain: Terrain, max_grade=0.12, road_width_m=12.0, max_bridge_m=1000.0
) -> Network:
    """Compile all legal four-neighbour surface edges and declared bridge spans.

    Surface edges are linear raster boundaries. Bridges use linear bank-to-bank
    decks; terrain beneath the deck is not mistaken for road grade. No implicit
    connectivity repair, tunnel construction or budget optimization is performed.
    """
    t = terrain
    validate_terrain(t)
    if not all(math.isfinite(x) and x > 0 for x in (max_grade, road_width_m, max_bridge_m)):
        raise ValueError("road limits must be positive finite")
    margin = road_width_m / 2.0
    nodes = {}
    grid = {}
    rejected = Counter()
    for y in range(t.n + 1):
        for x in range(t.n + 1):
            p = (x * t.spacing_m, y * t.spacing_m)
            if any(intersects(p, p, r, margin) for r in t.water + t.protected):
                continue
            v = Node(node_id(x, y), *p, height(t, x, y))
            nodes[v.id] = v
            grid[x, y] = v.id
    edges = []
    keys = set()

    def admit(u, v, kind):
        a, b = nodes[u], nodes[v]
        p = (a.x_m, a.y_m)
        q = (b.x_m, b.y_m)
        horizontal = math.dist(p, q)
        grade = abs(a.z_m - b.z_m) / horizontal
        if any(intersects(p, q, r, margin) for r in t.protected):
            rejected["protected"] += 1
            return
        wet = any(intersects(p, q, r, margin) for r in t.water)
        if wet and kind != "bridge":
            rejected["water"] += 1
            return
        if kind == "bridge" and (not wet or horizontal > max_bridge_m):
            rejected["bridge_span"] += 1
            return
        if grade > max_grade:
            rejected["grade"] += 1
            return
        key = tuple(sorted((u, v)))
        if key in keys:
            return
        keys.add(key)
        length = math.hypot(horizontal, a.z_m - b.z_m)
        multiplier = (4.0 if kind == "bridge" else 1.0) * (1.0 + 4.0 * grade**2)
        edges.append(
            Link(f"{kind}:{key[0]}>{key[1]}", *key, length, grade, kind, length * multiplier)
        )

    for (x, y), u in sorted(grid.items()):
        for xy in ((x + 1, y), (x, y + 1)):
            if xy in grid:
                admit(u, grid[xy], "surface")
    # Each permitted row explicitly connects the closest dry banks of each river.
    for row in sorted(t.bridge_rows):
        for river in t.water:
            ym = row * t.spacing_m
            if not river.ymin <= ym <= river.ymax:
                continue
            left = [
                (x, k)
                for (x, y), k in grid.items()
                if y == row and x * t.spacing_m < river.xmin - margin
            ]
            right = [
                (x, k)
                for (x, y), k in grid.items()
                if y == row and x * t.spacing_m > river.xmax + margin
            ]
            if left and right:
                admit(max(left)[1], min(right)[1], "bridge")
    adj = {i: [] for i in nodes}
    for e in edges:
        adj[e.u].append(e.v)
        adj[e.v].append(e.u)
    # Retain isolated valid nodes so disconnected support is visible, not erased.
    comps = {}
    c = 0
    for start in sorted(nodes):
        if start in comps:
            continue
        comps[start] = c
        stack = [start]
        while stack:
            for nxt in adj[stack.pop()]:
                if nxt not in comps:
                    comps[nxt] = c
                    stack.append(nxt)
        c += 1
    return Network(
        tuple(nodes[k] for k in sorted(nodes)),
        tuple(sorted(edges, key=lambda e: e.id)),
        tuple(sorted(comps.items())),
        tuple(sorted(rejected.items())),
    )
