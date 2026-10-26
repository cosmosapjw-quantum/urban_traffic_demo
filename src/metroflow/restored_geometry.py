"""Terrain-aware centreline calculus; xy/z in metres, slopes dimensionless.

A bilinear terrain restricted to a line is quadratic on each raster patch.
Derivative extrema are therefore at patch endpoints, not sparse sample points.
"""

import math
from .environment.terrain import intersects


def elevation(t, x, y):
    limit = t.n * t.spacing_m
    if not (0 <= x <= limit and 0 <= y <= limit):
        raise ValueError("outside terrain")
    i = min(t.n - 1, int(x / t.spacing_m))
    j = min(t.n - 1, int(y / t.spacing_m))
    u = x / t.spacing_m - i
    v = y / t.spacing_m - j
    a, b = t.heights_m[j * (t.n + 1) + i : j * (t.n + 1) + i + 2]
    c, d = t.heights_m[(j + 1) * (t.n + 1) + i : (j + 1) * (t.n + 1) + i + 2]
    return (1 - u) * (1 - v) * a + u * (1 - v) * b + (1 - u) * v * c + u * v * d


def ground_profile(t, xy):
    points = []
    length = 0.0
    grade = 0.0
    for p, q in zip(xy, xy[1:]):
        ds = math.dist(p, q)
        if ds <= 1e-10:
            raise ValueError("degenerate centreline")
        cuts = {0.0, 1.0}
        for axis in (0, 1):
            if abs(q[axis] - p[axis]) > 1e-12:
                for k in range(1, t.n):
                    s = (k * t.spacing_m - p[axis]) / (q[axis] - p[axis])
                    if 0 < s < 1:
                        cuts.add(s)
        cuts = sorted(cuts)
        for lo, hi in zip(cuts, cuts[1:]):

            def xyz(s):
                x = p[0] + s * (q[0] - p[0])
                y = p[1] + s * (q[1] - p[1])
                return x, y, elevation(t, x, y)

            a = xyz(lo)
            b = xyz(hi)
            m = xyz((lo + hi) / 2)
            span = (hi - lo) * ds
            # h(u)=A*u^2+B*u+h0, u in [0,1]; grade=(2*A*u+B)/span.
            aa = 2 * (a[2] + b[2] - 2 * m[2])
            bb = b[2] - a[2] - aa
            grade = max(grade, abs(bb / span), abs((2 * aa + bb) / span))
            # 8-panel Simpson length. Terrain grade bound is exact (up to floats).
            vals = [math.sqrt(1 + ((2 * aa * k / 8 + bb) / span) ** 2) for k in range(9)]
            length += (
                span / 24 * (vals[0] + vals[-1] + 4 * sum(vals[1:-1:2]) + 2 * sum(vals[2:-1:2]))
            )
            for k in range(8):
                pt = xyz(lo + (hi - lo) * k / 8)
                if not points or math.dist(pt, points[-1]) > 1e-9:
                    points.append(pt)
        points.append((*q, elevation(t, *q)))
    return tuple(points), length, grade


def deck_profile(points):
    ds = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    if not ds or min(ds) <= 1e-8:
        raise ValueError("degenerate deck")
    return (
        tuple(points),
        sum(math.dist(a, b) for a, b in zip(points, points[1:])),
        max(abs(b[2] - a[2]) / d for a, b, d in zip(points, points[1:], ds)),
    )


def terrain_gate(t, xy, width, facility):
    for a, b in zip(xy, xy[1:]):
        if any(intersects(a, b, r, width / 2) for r in t.protected):
            return "protected"
        if facility in ("surface", "ramp") and any(intersects(a, b, r, width / 2) for r in t.water):
            return "water"
    return None


def crossing(a, b, c, d):
    """Segment contact; collinear overlaps return their midpoint witness."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    bx, by = d[0] - c[0], d[1] - c[1]
    det = ax * by - ay * bx
    if abs(det) < 1e-10:
        den = ax * ax + ay * ay
        den2 = bx * bx + by * by
        if den <= 1e-20 or den2 <= 1e-20:
            return None
        if abs((c[0] - a[0]) * ay - (c[1] - a[1]) * ax) > 1e-7:
            return None
        u0 = ((c[0] - a[0]) * ax + (c[1] - a[1]) * ay) / den
        u1 = ((d[0] - a[0]) * ax + (d[1] - a[1]) * ay) / den
        lo = max(0.0, min(u0, u1))
        hi = min(1.0, max(u0, u1))
        if hi < lo - 1e-9:
            return None
        s = (lo + hi) / 2
        p = (a[0] + s * ax, a[1] + s * ay)
        t = ((p[0] - c[0]) * bx + (p[1] - c[1]) * by) / den2
        return s, t, p
    cx, cy = c[0] - a[0], c[1] - a[1]
    s = (cx * by - cy * bx) / det
    t = (cx * ay - cy * ax) / det
    if -1e-9 <= s <= 1 + 1e-9 and -1e-9 <= t <= 1 + 1e-9:
        return s, t, (a[0] + s * ax, a[1] + s * ay)
    return None


def crossing_audit(city, minimum_clearance_m=5.0):
    """Audit nonincident centreline crossings; no planarization across layers.

    Width-adjacent parallel facilities/engineering envelopes are NOT certified.
    Shared topology endpoints are authorized junctions; every other detected
    crossing needs vertical clearance. Collinear overlaps are separately flagged.
    """
    illegal = []
    separated = []
    seen = set()
    sections = city.sections
    bounds = {
        s.id: (
            min(p[0] for p in s.points),
            min(p[1] for p in s.points),
            max(p[0] for p in s.points),
            max(p[1] for p in s.points),
        )
        for s in sections
    }
    for i, e in enumerate(sections):
        x0, y0, x1, y1 = bounds[e.id]
        for f in sections[i + 1 :]:
            a0, b0, a1, b1 = bounds[f.id]
            if x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0:
                continue
            common = {e.start, e.end} & {f.start, f.end}
            common_xy = {tuple(n.xyz[:2]) for n in city.nodes if n.id in common}
            for a, b in zip(e.points, e.points[1:]):
                for c, d in zip(f.points, f.points[1:]):
                    v = crossing(a, b, c, d)
                    if v is None:
                        continue
                    u, w, p = v
                    if any(math.dist(p, q) < 1e-6 for q in common_xy):
                        continue
                    key = (e.id, f.id, round(p[0], 4), round(p[1], 4))
                    if key in seen:
                        continue
                    seen.add(key)
                    gap = abs(a[2] + u * (b[2] - a[2]) - c[2] - w * (d[2] - c[2]))
                    row = dict(first=e.id, second=f.id, xy=p, gap_m=gap)
                    (illegal if gap < minimum_clearance_m - 1e-6 else separated).append(row)
    return dict(illegal=illegal, grade_separated=separated)


def components(city, exclude_failure=None):
    adj = {n.id: [] for n in city.nodes}
    for s in city.sections:
        if exclude_failure is not None and s.failure_group == exclude_failure:
            continue
        adj[s.start].append(s.end)
        adj[s.end].append(s.start)
    seen = {}
    idx = 0
    for n in sorted(adj):
        if n in seen:
            continue
        seen[n] = idx
        stack = [n]
        while stack:
            for v in adj[stack.pop()]:
                if v not in seen:
                    seen[v] = idx
                    stack.append(v)
        idx += 1
    return seen


def minimum_ground_gap(t, points):
    """Exact minimum of linear deck minus bilinear ground on each patch.

    A sample-only clearance check can miss a hump between two samples. Split
    at every raster boundary and test the quadratic's interior stationary point.
    """
    gap = math.inf
    for a, b in zip(points, points[1:]):
        cuts = {0.0, 1.0}
        for axis in (0, 1):
            if abs(b[axis] - a[axis]) > 1e-12:
                for k in range(1, t.n):
                    u = (k * t.spacing_m - a[axis]) / (b[axis] - a[axis])
                    if 0 < u < 1:
                        cuts.add(u)
        cuts = sorted(cuts)

        def delta(u):
            p = tuple(x + u * (y - x) for x, y in zip(a, b))
            return p[2] - elevation(t, *p[:2])

        for lo, hi in zip(cuts, cuts[1:]):
            x, y, m = delta(lo), delta(hi), delta((lo + hi) / 2)
            A = 2 * (x + y - 2 * m)
            B = y - x - A
            gap = min(gap, x, y)
            if A > 0:
                v = -B / (2 * A)
                if 0 < v < 1:
                    gap = min(gap, A * v * v + B * v + x)
    return gap
