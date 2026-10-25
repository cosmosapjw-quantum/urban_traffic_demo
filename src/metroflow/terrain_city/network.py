"""Connected city-scale road synthesis on a terrain-admissible planar substrate.

A substrate bounds geometric search; it is NOT a learned city or a universal
urban-growth model. Main roads minimize positive terrain costs. Local expansion
and loop infill have separate declared rules. Units: metres, persons, jobs.
"""

from dataclasses import dataclass, replace
from collections import Counter, defaultdict
import heapq
import math
import random
from ..restored_city import RoadMap, Junction, Section
from ..restored_geometry import elevation, ground_profile, deck_profile, minimum_ground_gap
from ..environment.landuse import apportion
from ..environment.terrain import cell_slope
from .landscape import Landscape, Polygon, make_landscape, segment_clear, polygon_clear, edges

STYLES = ("planned", "polycentric", "radial", "corridor")


@dataclass(frozen=True, slots=True)
class Block:
    id: str
    boundary: tuple[str, ...]
    xy: tuple[float, float]
    area_m2: float
    perimeter_m: float
    use: str
    housing_capacity: int
    job_capacity: int
    residents: int = 0
    jobs: int = 0


@dataclass(frozen=True, slots=True)
class Atlas:
    landscape: Landscape
    roadmap: RoadMap
    centers: tuple[str, ...]
    phases: tuple[tuple[str, int], ...]
    blocks: tuple[Block, ...]
    summary: dict


def substrate(style, L, n, seed):
    """Embedded mesh and noncrossing candidate chains, before terrain rejection."""
    rng = random.Random(seed)
    xy = {}
    chains = []
    pairs = set()

    def chain(nodes, closed=False):
        nodes = tuple(nodes)
        if closed:
            nodes = nodes + (nodes[0],)
        chains.append(nodes)
        for a, b in zip(nodes, nodes[1:]):
            pairs.add(tuple(sorted((a, b))))

    if style == "radial":
        center = (0.49 * L, 0.50 * L)
        xy["v0"] = center
        prev = ["v0"]
        m = 6
        spacing = L / n
        for k in range(1, max(3, n // 2)):
            r = k * spacing
            while 2 * math.pi * r / m > 1.45 * spacing:
                m *= 2
            ids = []
            for j in range(m):
                angle = j * 2 * math.pi / m
                # Smooth radius perturbation preserves ordered concentric layers.
                rr = r * (1 + 0.018 * math.sin(3 * angle + 0.3))
                p = (center[0] + rr * math.cos(angle), center[1] + rr * math.sin(angle))
                key = f"r{k}:{j}"
                xy[key] = p
                ids.append(key)
            chain(ids, True)
            if k == 1:
                for key in ids:
                    chain(("v0", key))
            elif len(ids) == len(prev):
                for a, b in zip(prev, ids):
                    chain((a, b))
            else:
                for j, a in enumerate(prev):
                    chain((a, ids[2 * j]))
            prev = ids
        # Long same-angle chains also provide bridge search corridors.
        for j in range(96):
            angle = j * 2 * math.pi / 96
            seq = []
            for k in range(1, max(3, n // 2)):
                candidates = [key for key in xy if key.startswith(f"r{k}:")]
                mlen = len(candidates)
                idx = round(j * mlen / 96) % mlen
                if abs(idx / mlen - j / 96) < 1e-10:
                    seq.append(f"r{k}:{idx}")
            if len(seq) > 1:
                chains.append(tuple(seq))
    else:
        step = L / n
        phase = (seed % 19) / 19 * 2 * math.pi
        for j in range(1, n):
            for i in range(1, n):
                x, y = i * step, j * step
                if style == "planned":
                    x += 0.025 * step * rng.uniform(-1, 1)
                    y += 0.025 * step * rng.uniform(-1, 1)
                elif style == "corridor":
                    y = (
                        0.48 * L
                        + 0.12 * L * math.sin(1.6 * math.pi * x / L - 0.5)
                        + (y - 0.5 * L) * 0.76
                    )
                    x += 0.06 * step * rng.uniform(-1, 1)
                    y += 0.06 * step * rng.uniform(-1, 1)
                else:
                    x += 0.028 * L * math.sin(math.pi * x / L) * math.sin(
                        2 * math.pi * y / L + phase
                    ) + 0.12 * step * rng.uniform(-1, 1)
                    y += 0.025 * L * math.sin(2 * math.pi * x / L + phase) * math.sin(
                        math.pi * y / L
                    ) + 0.12 * step * rng.uniform(-1, 1)
                if 0 < x < L and 0 < y < L:
                    xy[f"g{i}:{j}"] = (x, y)
        for j in range(1, n):
            chain([f"g{i}:{j}" for i in range(1, n) if f"g{i}:{j}" in xy])
        for i in range(1, n):
            chain([f"g{i}:{j}" for j in range(1, n) if f"g{i}:{j}" in xy])
    return xy, sorted(pairs), chains


def centers_for(style, land):
    L = land.size_m
    if style == "radial":
        return ((0.49 * L, 0.50 * L), (0.72 * L, 0.35 * L), (0.28 * L, 0.65 * L))
    if land.kind == "coast":
        return ((0.43 * L, 0.40 * L), (0.45 * L, 0.72 * L), (0.68 * L, 0.38 * L))
    if style == "corridor" or land.kind == "valley":
        return tuple(
            (
                x * L,
                (0.48 + 0.12 * math.sin(1.6 * math.pi * x - 0.5) + (0.055 if i % 2 else -0.055))
                * L,
            )
            for i, x in enumerate((0.25, 0.52, 0.76))
        )
    if style == "planned":
        return ((0.48 * L, 0.46 * L), (0.73 * L, 0.67 * L))
    return ((0.30 * L, 0.43 * L), (0.64 * L, 0.38 * L), (0.48 * L, 0.71 * L))


def _dijkstra(adj, sources):
    dist = {s: 0.0 for s in sources}
    parent = {}
    heap = [(0.0, s) for s in sorted(sources)]
    heapq.heapify(heap)
    while heap:
        value, u = heapq.heappop(heap)
        if value != dist[u]:
            continue
        for v, e, w in adj.get(u, ()):
            alt = value + w
            if alt < dist.get(v, math.inf):
                dist[v] = alt
                parent[v] = (u, e)
                heapq.heappush(heap, (alt, v))
    return dist, parent


def _walk(parent, start):
    result = []
    while start in parent:
        prev, e = parent[start]
        result.append(e)
        start = prev
    return result


def _faces(xy, pairs):
    adj = defaultdict(list)
    for a, b in pairs:
        adj[a].append(b)
        adj[b].append(a)
    for u, ns in adj.items():
        ns.sort(key=lambda v: math.atan2(xy[v][1] - xy[u][1], xy[v][0] - xy[u][0]))
    seen = set()
    faces = []
    for a in sorted(adj):
        for b in adj[a]:
            if (a, b) in seen:
                continue
            start = (a, b)
            u, v = start
            cycle = []
            for _ in range(2 * len(pairs) + 1):
                if (u, v) in seen:
                    if (u, v) != start:
                        raise ArithmeticError("half-edge walk not closed")
                    break
                seen.add((u, v))
                cycle.append(u)
                nxt = adj[v][(adj[v].index(u) - 1) % len(adj[v])]
                u, v = v, nxt
            else:
                raise ArithmeticError("half-edge walk budget")
            pts = tuple(xy[u] for u in cycle)
            area = 0.5 * sum(p[0] * q[1] - q[0] * p[1] for p, q in edges(pts))
            if area > 1e-5:
                faces.append((tuple(cycle), area))
    if len(seen) != 2 * len(pairs):
        raise ArithmeticError("missing half edges")
    return faces


def _blocks(roadmap, land, center_xy, population):
    xy = {n.id: n.xyz[:2] for n in roadmap.nodes}
    faces = _faces(xy, [(s.start, s.end) for s in roadmap.sections])
    raw = []
    industrial = []
    L = land.size_m
    port = (0.43 * L, 0.20 * L) if land.kind == "coast" else (0.76 * L, 0.25 * L)
    for idx, (ids, area) in enumerate(faces):
        pts = tuple(xy[n] for n in ids)
        per = sum(math.dist(a, b) for a, b in edges(pts))
        # Area centroid, not a vertex-average bias toward tessellated edges.
        cross = [a[0] * b[1] - b[0] * a[1] for a, b in edges(pts)]
        cx = sum((a[0] + b[0]) * v for (a, b), v in zip(edges(pts), cross)) / (6 * area)
        cy = sum((a[1] + b[1]) * v for (a, b), v in zip(edges(pts), cross)) / (6 * area)
        simple = len(ids) == len(set(ids))
        ok = simple and area >= 5000 and area <= 180000 and 2 * area / per >= 20
        if ok:
            ok = polygon_clear(pts, land.water + land.protected)
        if ok:
            d = land.terrain.spacing_m
            x0 = max(0, int(min(p[0] for p in pts) / d))
            x1 = min(land.terrain.n, math.ceil(max(p[0] for p in pts) / d))
            y0 = max(0, int(min(p[1] for p in pts) / d))
            y1 = min(land.terrain.n, math.ceil(max(p[1] for p in pts) / d))
            ok = all(
                cell_slope(land.terrain, x, y) <= 0.12 for x in range(x0, x1) for y in range(y0, y1)
            )
        nearest = min(math.dist((cx, cy), c) for c in center_xy)
        use = "open_space"
        if ok:
            if math.dist((cx, cy), port) < 0.085 * L:
                use = "industrial"
                industrial.append(Polygon(str(idx), pts))
            elif nearest < 0.10 * L:
                use = "mixed"
            elif nearest < 0.15 * L and idx % 5 == 0:
                use = "commercial"
            else:
                use = "residential"
        raw.append(Block(str(idx), ids, (cx, cy), area, per, use, 0, 0))
    density = {
        "residential": (170.0, 15.0),
        "mixed": (320.0, 250.0),
        "commercial": (0.0, 450.0),
        "industrial": (0.0, 140.0),
    }
    blocks = []
    for block in raw:
        use = block.use
        pts = tuple(xy[n] for n in block.boundary)
        if use in ("residential", "mixed") and any(
            not segment_clear(a, b, industrial, 120.0) for a, b in edges(pts)
        ):
            use = "buffer"
        h, j = density.get(use, (0.0, 0.0))
        net = 0.65 * block.area_m2 / 10000.0
        blocks.append(
            replace(
                block,
                use=use,
                housing_capacity=math.floor(net * h),
                job_capacity=math.floor(net * j),
            )
        )
    weights = tuple(
        math.exp(-min(math.dist(b.xy, c) for c in center_xy) / (0.30 * L)) for b in blocks
    )
    cap = tuple(b.housing_capacity for b in blocks)
    jcap = tuple(b.job_capacity for b in blocks)
    placed = min(population, sum(cap))
    jobs = min(round(0.4 * population), sum(jcap))
    residents = apportion(placed, cap, tuple(c * w for c, w in zip(cap, weights))) if blocks else ()
    employment = (
        apportion(jobs, jcap, tuple(c * w for c, w in zip(jcap, weights))) if blocks else ()
    )
    return tuple(
        replace(b, residents=h, jobs=j) for b, h, j in zip(blocks, residents, employment)
    ), len(faces)


def generate(
    style="polycentric", terrain="river", size_m=8000.0, resolution=42, seed=17, population=100000
):
    if style not in STYLES:
        raise ValueError("unsupported city style")
    if (
        isinstance(resolution, bool)
        or not isinstance(resolution, int)
        or not 12 <= resolution <= 90
    ):
        raise ValueError("mesh resolution must be in [12,90]")
    if isinstance(population, bool) or not isinstance(population, int) or population < 0:
        raise ValueError("population must be nonnegative integer")
    land = make_landscape(terrain, size_m, seed)
    L = land.size_m
    xy, pairs, chains = substrate(style, L, resolution, seed)
    status = {}
    rejected = Counter()
    for k, p in xy.items():
        if not segment_clear(p, p, land.protected, 14.0):
            status[k] = "protected"
        elif not segment_clear(p, p, land.water, 14.0):
            status[k] = "water"
        else:
            status[k] = "dry"
    candidates = {}
    adj = defaultdict(list)

    def insert(s, cost):
        candidates[s.id] = s
        adj[s.start].append((s.end, s.id, cost))
        adj[s.end].append((s.start, s.id, cost))

    for a, b in pairs:
        if status[a] != "dry" or status[b] != "dry":
            continue
        if not segment_clear(xy[a], xy[b], land.water + land.protected, 14.0):
            rejected["footprint"] += 1
            continue
        pts, length, grade = ground_profile(land.terrain, (xy[a], xy[b]))
        if grade > 0.08:
            rejected["grade"] += 1
            continue
        s = Section(f"s:{a}>{b}", a, b, pts, "local", "surface", 1, 1, length, grade)
        insert(s, length * (1 + 5 * (grade / 0.08) ** 2))
    nominal = centers_for(style, land)
    proposals = []
    seen = set()
    for chain in chains:
        left = None
        middle = []
        for key in chain:
            if status[key] == "dry":
                if left is not None and middle and left != key:
                    pair = tuple(sorted((left, key)))
                    if pair not in seen and left in adj and key in adj:
                        seen.add(pair)
                        path = (left, *middle, key)
                        ptsxy = tuple(xy[v] for v in path)
                        run = [0.0]
                        for p, q in zip(ptsxy, ptsxy[1:]):
                            run.append(run[-1] + math.dist(p, q))
                        length = run[-1]
                        if 40 < length < 900 and length / math.dist(xy[left], xy[key]) < 1.12:
                            if all(
                                segment_clear(p, q, land.protected, 14.0)
                                for p, q in zip(ptsxy, ptsxy[1:])
                            ):
                                za = elevation(land.terrain, *ptsxy[0])
                                zb = elevation(land.terrain, *ptsxy[-1])
                                pts = tuple(
                                    (
                                        *p,
                                        za
                                        + (zb - za) * d / length
                                        + 8 * math.sin(math.pi * d / length),
                                    )
                                    for p, d in zip(ptsxy, run)
                                )
                                pts = ((*ptsxy[0], za), *pts[1:-1], (*ptsxy[-1], zb))
                                pts, leng, grade = deck_profile(pts)
                                if grade <= 0.08 and minimum_ground_gap(land.terrain, pts) >= -1e-7:
                                    mid = ptsxy[len(ptsxy) // 2]
                                    score = leng * 4 + 0.4 * min(math.dist(mid, c) for c in nominal)
                                    s = Section(
                                        f"b:{pair[0]}>{pair[1]}",
                                        left,
                                        key,
                                        pts,
                                        "arterial",
                                        "bridge",
                                        2,
                                        2,
                                        leng,
                                        grade,
                                        f"bridge:{len(proposals)}",
                                    )
                                    proposals.append((score, s, mid, frozenset(path)))
                left = key
                middle = []
            elif status[key] == "water" and left is not None:
                middle.append(key)
            else:
                left = None
                middle = []
    bridges = []
    occupied = set()
    for score, s, mid, path in sorted(proposals, key=lambda x: (x[0], x[1].id)):
        if len(bridges) >= 3:
            break
        if occupied & path or any(math.dist(mid, p) < 0.13 * L for p in bridges):
            continue
        occupied.update(path)
        bridges.append(mid)
        insert(s, s.length_m * 4)
    if not adj:
        raise ValueError("no terrain-admissible road graph")
    centers = tuple(
        dict.fromkeys(min(adj, key=lambda k: (math.dist(xy[k], p), k)) for p in nominal)
    )
    dist, parent = _dijkstra(adj, (centers[0],))
    unreachable = [c for c in centers if c not in dist]
    centers = tuple(c for c in centers if c in dist)
    # Gateways belong to the same feasible component; never add an illegal line.
    aims = ((0.08 * L, 0.5 * L), (0.92 * L, 0.5 * L), (0.5 * L, 0.08 * L), (0.5 * L, 0.92 * L))
    gateways = tuple(min(dist, key=lambda k: (math.dist(xy[k], p), k)) for p in aims)
    arterial = set()
    for target in centers[1:] + gateways:
        arterial.update(route_path(adj, xy, centers[0], target, 2 * L / resolution))
    for start, end in zip(centers, centers[1:]):
        arterial.update(route_path(adj, xy, start, end, 2 * L / resolution))
    # Orbital remnants are not separate roots: join every reachable arc to the
    # existing backbone; unrouteable arcs remain explicit rejected proposals.
    orbital_unreachable = 0
    orbital_connectors = 0
    if style == "radial":
        ring = round(0.23 * resolution)
        prefix = f"r{ring}:"
        orbit = {}
        for e, edge in candidates.items():
            if (
                edge.facility == "surface"
                and edge.start.startswith(prefix)
                and edge.end.startswith(prefix)
            ):
                if edge.start in dist and edge.end in dist:
                    orbit[e] = edge
                else:
                    orbital_unreachable += 1
        orbital_adj = defaultdict(list)
        for e, edge in orbit.items():
            orbital_adj[edge.start].append(edge.end)
            orbital_adj[edge.end].append(edge.start)
        seen_orbit = set()
        for start in sorted(orbital_adj):
            if start in seen_orbit:
                continue
            group = []
            stack = [start]
            seen_orbit.add(start)
            while stack:
                u = stack.pop()
                group.append(u)
                for v in orbital_adj[u]:
                    if v not in seen_orbit:
                        seen_orbit.add(v)
                        stack.append(v)
            entry = min(group, key=lambda k: (dist[k], k))
            arterial.update(_walk(parent, entry))
            orbital_connectors += 1
        arterial.update(orbit)
    trunknodes = {k for eid in arterial for k in (candidates[eid].start, candidates[eid].end)} or {
        centers[0]
    }
    access, previous = _dijkstra(adj, trunknodes)
    center_xy = tuple(xy[c] for c in centers)

    def intensity(p):
        if style == "corridor":
            return max(
                math.exp(-(((p[0] - c[0]) / (0.24 * L)) ** 2) - ((p[1] - c[1]) / (0.13 * L)) ** 2)
                for c in center_xy
            )
        radius = (0.31 if style == "planned" else 0.30 if style == "radial" else 0.235) * L
        return max(math.exp(-((math.dist(p, c) / radius) ** 2)) for c in center_xy)

    targets = {k for k in access if intensity(xy[k]) >= 0.24}
    selected = set(arterial)
    flow = Counter({k: 1 for k in targets})
    for k in sorted(access, key=lambda k: (-access[k], k)):
        if k in previous and flow[k]:
            p, e = previous[k]
            selected.add(e)
            flow[p] += flow[k]
    phases = {e: 0 if e in arterial else 1 for e in selected}
    # Independent local cycle infill; no degrees of freedom proportional to population.
    rng = random.Random(seed + 1701)
    prob = {"planned": 0.92, "polycentric": 0.68, "radial": 0.85, "corridor": 0.52}[style]
    for eid, s in sorted(candidates.items()):
        if s.facility == "bridge":
            continue
        if s.start in targets and s.end in targets and rng.random() < prob:
            selected.add(eid)
            phases.setdefault(eid, 2)
    # Remove unsupported fringe branches, not authored cul-de-sacs: this model
    # places development only in closed blocks. Preserve centers and gateways.
    incident = defaultdict(set)
    for eid in selected:
        edge = candidates[eid]
        incident[edge.start].add(eid)
        incident[edge.end].add(eid)
    protected_nodes = set(centers) | set(gateways)
    todo = [k for k in sorted(incident) if len(incident[k]) == 1 and k not in protected_nodes]
    removed = 0
    while todo:
        u = todo.pop()
        if len(incident[u]) != 1:
            continue
        eid = next(iter(incident[u]))
        if eid in arterial:
            continue
        edge = candidates[eid]
        v = edge.end if edge.start == u else edge.start
        selected.remove(eid)
        phases.pop(eid, None)
        removed += 1
        incident[u].remove(eid)
        incident[v].remove(eid)
        if len(incident[v]) == 1 and v not in protected_nodes:
            todo.append(v)
    sections = []
    for eid in sorted(selected):
        s = candidates[eid]
        h = (
            "arterial"
            if eid in arterial or s.facility == "bridge"
            else "collector"
            if max(flow[s.start], flow[s.end]) >= max(4, len(targets) // 150) and phases[eid] == 1
            else "local"
        )
        lanes = 2 if h == "arterial" else 1
        sections.append(replace(s, hierarchy=h, forward_lanes=lanes, backward_lanes=lanes))
    used = {v for s in sections for v in (s.start, s.end)}
    nodes = tuple(Junction(k, (*xy[k], elevation(land.terrain, *xy[k]))) for k in sorted(used))
    # Polygon masks live in Atlas.landscape. Old rectangle-only landuse APIs are
    # not valid for this map; traffic compiler may consume its explicit topology.
    roadmap = RoadMap(style, land.terrain, nodes, tuple(sections), tuple(sorted(rejected.items())))
    blocks, nfaces = _blocks(roadmap, land, center_xy, population)
    degree = Counter(v for s in sections for v in (s.start, s.end))
    cycle = len(sections) - len(nodes) + 1
    if cycle != nfaces:
        raise ArithmeticError(f"planar face ledger {cycle} != {nfaces}")
    summary = dict(
        style=style,
        terrain=terrain,
        size_m=L,
        resolution=resolution,
        seed=seed,
        nodes=len(nodes),
        physical_links=len(sections),
        components=1,
        cycle_rank=cycle,
        bounded_faces=nfaces,
        degree_histogram={str(k): v for k, v in sorted(Counter(degree.values()).items())},
        deadend_fraction=sum(d == 1 for d in degree.values()) / len(nodes),
        max_degree=max(degree.values()),
        total_length_km=math.fsum(s.length_m for s in sections) / 1000,
        hierarchy_length_km={
            h: math.fsum(s.length_m for s in sections if s.hierarchy == h) / 1000
            for h in ("arterial", "collector", "local")
        },
        bridges=sum(s.facility == "bridge" for s in sections),
        candidate_bridge_count=len(proposals),
        unserved_center_proposals=len(unreachable),
        unserved_orbital_edges=orbital_unreachable,
        orbital_components_joined=orbital_connectors,
        rejected=dict(rejected),
        removed_unbacked_stubs=removed,
        gateways=gateways,
        housing_capacity=sum(b.housing_capacity for b in blocks),
        resident_stock=sum(b.residents for b in blocks),
        unplaced_residents=population - sum(b.residents for b in blocks),
        job_stock=sum(b.jobs for b in blocks),
        requested_population=population,
        unplaced_jobs=round(0.4 * population) - sum(b.jobs for b in blocks),
        land_use_counts=dict(Counter(b.use for b in blocks)),
        illegal_surface_water=sum(
            not all(
                segment_clear(a[:2], b[:2], land.water, 14.0)
                for a, b in zip(s.points, s.points[1:])
            )
            for s in sections
            if s.facility == "surface"
        ),
        illegal_protected=sum(
            not all(
                segment_clear(a[:2], b[:2], land.protected, 14.0)
                for a, b in zip(s.points, s.points[1:])
            )
            for s in sections
        ),
        max_grade=max(s.max_grade for s in sections),
        max_bridge_span_m=max(
            (s.length_m for s in sections if s.facility == "bridge"), default=0.0
        ),
    )
    return Atlas(land, roadmap, centers, tuple(sorted(phases.items())), blocks, summary)


def route_path(adj, xy, start, end, turn_penalty_m=0.0):
    """A* on incoming-edge states. Positive angular cost suppresses staircases.

    Costs are construction proxies in metres, not traffic time. The Euclidean
    heuristic is admissible when edge cost >= endpoint distance, as generated.
    """
    if start == end:
        return ()
    initial = ("", start)
    dist = {initial: 0.0}
    parent = {}
    heap = [(math.dist(xy[start], xy[end]), 0.0, initial)]
    while heap:
        _, value, state = heapq.heappop(heap)
        if value != dist[state]:
            continue
        prev, u = state
        if u == end:
            result = []
            while state in parent:
                state, e = parent[state]
                result.append(e)
            return tuple(reversed(result))
        for v, e, cost in adj[u]:
            if v == prev:
                continue
            bend = 0.0
            if prev:
                a = (xy[u][0] - xy[prev][0], xy[u][1] - xy[prev][1])
                b = (xy[v][0] - xy[u][0], xy[v][1] - xy[u][1])
                cosine = (a[0] * b[0] + a[1] * b[1]) / (math.hypot(*a) * math.hypot(*b))
                bend = turn_penalty_m * (1 - max(-1.0, min(1.0, cosine)))
            new = (u, v)
            alt = value + cost + bend
            if alt < dist.get(new, math.inf):
                dist[new] = alt
                parent[new] = (state, e)
                heapq.heappush(heap, (alt + math.dist(xy[v], xy[end]), alt, new))
    return ()
