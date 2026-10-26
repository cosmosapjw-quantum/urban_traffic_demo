"""Geometry/topology/stock audits separate from visual judgement."""

from collections import Counter as Counter, defaultdict
import math
from ..restored_geometry import crossing
from ..restored_traffic import compile_traffic


def geometry_audit(atlas):
    roads = atlas.roadmap.sections
    nodes = {n.id: n for n in atlas.roadmap.nodes}
    bucket = defaultdict(list)
    tested = set()
    contacts = []
    cell = 400.0
    npairs = 0
    for idx, s in enumerate(roads):
        pts = (s.points[0], s.points[-1]) if s.facility == "surface" else s.points
        x0 = min(p[0] for p in pts)
        x1 = max(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        y1 = max(p[1] for p in pts)
        boxes = tuple(
            (i, j)
            for i in range(math.floor(x0 / cell), math.floor(x1 / cell) + 1)
            for j in range(math.floor(y0 / cell), math.floor(y1 / cell) + 1)
        )
        for other in sorted({k for box in boxes for k in bucket[box]}):
            if (other, idx) in tested:
                continue
            tested.add((other, idx))
            npairs += 1
            r = roads[other]
            rp = (r.points[0], r.points[-1]) if r.facility == "surface" else r.points
            common = {s.start, s.end} & {r.start, r.end}
            if len(common) == 1 and len(pts) == len(rp) == 2:
                # Two straight segments with one common endpoint cannot meet
                # elsewhere unless their outward rays overlap. Avoid dividing
                # by a roundoff-sized determinant on radial continuations.
                joint = nodes[next(iter(common))].xyz
                a = pts[1] if math.dist(pts[0][:2], joint[:2]) < 1e-7 else pts[0]
                b = rp[1] if math.dist(rp[0][:2], joint[:2]) < 1e-7 else rp[0]
                u = (a[0] - joint[0], a[1] - joint[1])
                v = (b[0] - joint[0], b[1] - joint[1])
                dot = u[0] * v[0] + u[1] * v[1]
                det = u[0] * v[1] - u[1] * v[0]
                if dot <= 0 or abs(det) > 1e-12 * math.hypot(*u) * math.hypot(*v):
                    continue
            for a, b in zip(pts, pts[1:]):
                for c, d in zip(rp, rp[1:]):
                    v = crossing(a, b, c, d)
                    if v is None:
                        continue
                    _, _, xy = v
                    if any(math.dist(xy, nodes[k].xyz[:2]) < 1e-6 for k in common):
                        continue
                    contacts.append(dict(first=s.id, second=r.id, xy=xy))
        for box in boxes:
            bucket[box].append(idx)
    adj = {n: [] for n in nodes}
    for s in roads:
        adj[s.start].append((s.end, s.id))
        adj[s.end].append((s.start, s.id))

    def components(skip=None):
        seen = set()
        sizes = []
        for u in adj:
            if u in seen:
                continue
            stack = [u]
            seen.add(u)
            count = 0
            while stack:
                k = stack.pop()
                count += 1
                for v, e in adj[k]:
                    if e != skip and v not in seen:
                        seen.add(v)
                        stack.append(v)
            sizes.append(count)
        return sorted(sizes, reverse=True)

    faces = [b.area_m2 for b in atlas.blocks]
    developed = [b for b in atlas.blocks if b.housing_capacity or b.job_capacity]
    compiled = compile_traffic(atlas.roadmap)
    return dict(
        illegal_projected_contacts=contacts,
        candidate_pairs_tested=npairs,
        component_sizes=components(),
        bridge_failure_components={
            s.failure_group: components(s.id) for s in roads if s.facility == "bridge"
        },
        maximum_face_m2=max(faces, default=0.0),
        median_face_m2=sorted(faces)[len(faces) // 2] if faces else 0.0,
        developed_blocks=len(developed),
        gross_developed_km2=sum(b.area_m2 for b in developed) / 1e6,
        resident_ledger_error=atlas.summary["requested_population"]
        - sum(b.residents for b in atlas.blocks)
        - atlas.summary["unplaced_residents"],
        max_road_grade=max(s.max_grade for s in roads),
        traffic_adapter_compatible=True,
        compiled_directed_links=len(compiled.roads),
        compiled_legal_turns=len(compiled.allowed_turns),
        caveat="centreline topology and declared terrain/masks only; not full pavement/junction/building design",
    )
