"""Uniform block-area access measure, in metres and seconds; stdlib only.

A simple obstacle-free polygon carries a uniform activity prior, not one agent
per resident. Internal travel uses a declared constant planar speed. This is an
access-mode metric, not a vehicle safety model, surveyed walking speed, or built
pavement. Polygon masks must be checked by the atlas adapter before use.
"""

from dataclasses import dataclass
import math
from .landscape import Polygon, inside, point_segment
from .block_access import segment_inside
from ..restored_geometry import crossing


@dataclass(frozen=True, slots=True)
class Portal:
    id: str
    xy: tuple[float, float]
    external_s: float = 0.0


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _canonical(points):
    p = [tuple(x) for x in points]
    if p and p[0] == p[-1]:
        p.pop()
    if len(p) < 3 or any(len(x) != 2 or not all(map(math.isfinite, x)) for x in p):
        raise ValueError("finite simple polygon required")
    if len(set(p)) != len(p):
        raise ValueError("repeated nonclosing polygon vertex")
    # A collinear sample along the same boundary is representational redundancy.
    changed = True
    while changed and len(p) > 3:
        changed = False
        for i, b in enumerate(p):
            a, c = p[i - 1], p[(i + 1) % len(p)]
            if (
                abs(_cross(a, b, c)) < 1e-12
                and (b[0] - a[0]) * (b[0] - c[0]) + (b[1] - a[1]) * (b[1] - c[1]) <= 0
            ):
                p.pop(i)
                changed = True
                break
    for i, a in enumerate(p):
        b = p[(i + 1) % len(p)]
        for j in range(i + 1, len(p)):
            if j == (i + 1) % len(p) or (j + 1) % len(p) == i:
                continue
            if crossing(a, b, p[j], p[(j + 1) % len(p)]) is not None:
                raise ValueError("self-intersecting boundary")
    area2 = math.fsum(_cross(p[0], p[i], p[i + 1]) for i in range(1, len(p) - 1))
    if abs(area2) < 1e-12:
        raise ValueError("zero-area polygon")
    if area2 < 0:
        p.reverse()
    k = min(range(len(p)), key=lambda i: p[i])
    return tuple(p[k:] + p[:k])


def _triangulate(points):
    p = list(points)
    out = []
    while len(p) > 3:
        for i, b in enumerate(p):
            a, c = p[i - 1], p[(i + 1) % len(p)]
            if _cross(a, b, c) <= 1e-12:
                continue
            other = [q for j, q in enumerate(p) if j not in (i, (i - 1) % len(p), (i + 1) % len(p))]
            if any(min(_cross(a, b, q), _cross(b, c, q), _cross(c, a, q)) >= -1e-12 for q in other):
                continue
            out.append((a, b, c))
            p.pop(i)
            break
        else:
            raise ValueError("no admissible polygon ear; inspect geometry resolution")
    if _cross(*p) <= 0:
        raise ValueError("degenerate final triangle")
    out.append(tuple(p))
    return tuple(out)


def _refine(triangles):
    result = []
    for a, b, c in triangles:
        ab = tuple((x + y) / 2 for x, y in zip(a, b))
        bc = tuple((x + y) / 2 for x, y in zip(b, c))
        ca = tuple((x + y) / 2 for x, y in zip(c, a))
        result.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
    return tuple(result)


class AreaAccess:
    """Geodesic access inside a simple polygon and certified centroid quadrature.

    Boundary rotation/reversal and ID permutations leave the represented area
    unchanged. Triangulation refinement is an approximation change, NOT a gauge.
    Exact geometric moments are covariant. Finite quadrature orientation effects
    are bounded, not falsely declared exact rotational invariance.
    """

    def __init__(self, points):
        self.points = _canonical(points)
        self.polygon = Polygon("activity_domain", self.points)
        self.triangles = _triangulate(self.points)
        areas = [_cross(*t) / 2 for t in self.triangles]
        self.area_m2 = math.fsum(areas)
        origin = self.points[0]
        mean = [0.0, 0.0]
        second = [[0.0, 0.0], [0.0, 0.0]]
        for t, area in zip(self.triangles, areas):
            q = [(p[0] - origin[0], p[1] - origin[1]) for p in t]
            S = [math.fsum(p[k] for p in q) for k in (0, 1)]
            w = area / self.area_m2
            for k in (0, 1):
                mean[k] += w * S[k] / 3
                for column_index in (0, 1):
                    second[k][column_index] += (
                        w
                        * (math.fsum(p[k] * p[column_index] for p in q) + S[k] * S[column_index])
                        / 12
                    )
        self.centroid = tuple(mean[k] + origin[k] for k in (0, 1))
        self.covariance = tuple(
            tuple(second[k][column_index] - mean[k] * mean[column_index] for column_index in (0, 1))
            for k in (0, 1)
        )
        n = len(self.points)
        D = [[math.inf] * n for _ in range(n)]
        for i, a in enumerate(self.points):
            D[i][i] = 0.0
            for j in range(i):
                b = self.points[j]
                if segment_inside(a, b, self.polygon):
                    D[i][j] = D[j][i] = math.dist(a, b)
        for k in range(n):
            for i in range(n):
                for j in range(n):
                    D[i][j] = min(D[i][j], D[i][k] + D[k][j])
        self.distances = tuple(tuple(r) for r in D)
        self._rules = {}

    def squared_distance_mean(self, point):
        """Exact E|X-d|² = trace(Cov X)+|E X-d|²; not geodesic distance²."""
        return sum(self.covariance[k][k] for k in (0, 1)) + math.dist(self.centroid, point) ** 2

    def _portals(self, portals, speed):
        portals = tuple(portals)
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("positive finite access speed")
        if not portals or len({p.id for p in portals}) != len(portals):
            raise ValueError("unique portal labels required")
        if len({p.xy for p in portals}) != len(portals):
            raise ValueError("duplicate physical portal; do not double-count")
        prepared = []
        for p in portals:
            if (
                not p.id
                or len(p.xy) != 2
                or not all(map(math.isfinite, p.xy))
                or not math.isfinite(p.external_s)
                or p.external_s < 0
            ):
                raise ValueError("invalid portal")
            if (
                min(
                    point_segment(p.xy, a, self.points[(i + 1) % len(self.points)])
                    for i, a in enumerate(self.points)
                )
                > 1e-7
            ):
                raise ValueError("portal must lie on actual block boundary")
            tails = [
                math.dist(v, p.xy) if segment_inside(v, p.xy, self.polygon) else math.inf
                for v in self.points
            ]
            vertex = tuple(
                min(self.distances[i][j] + tails[j] for j in range(len(tails)))
                for i in range(len(tails))
            )
            prepared.append((p, vertex))
        return tuple(prepared)

    def _query(self, point, prepared, speed):
        if not inside(point, self.polygon):
            raise ValueError("activity point outside block")
        via = [
            math.dist(point, v) if segment_inside(point, v, self.polygon) else math.inf
            for v in self.points
        ]
        values = []
        for p, vertex in prepared:
            direct = (
                math.dist(point, p.xy) if segment_inside(point, p.xy, self.polygon) else math.inf
            )
            length = min(direct, min(x + y for x, y in zip(via, vertex)))
            values.append(length / speed + p.external_s)
        best = min(values)
        if not math.isfinite(best):
            raise ValueError("no internal portal route")
        ties = tuple(i for i, c in enumerate(values) if abs(c - best) <= 1e-10 * max(1.0, best))
        return best, ties

    def cost_at(self, point, portals, speed_mps=1.4):
        return self._query(point, self._portals(portals, speed_mps), speed_mps)[0]

    def route_distance(self, origin, destination):
        """Shortest internal planar distance between two declared activity points."""
        if not inside(origin, self.polygon) or not inside(destination, self.polygon):
            raise ValueError("activity point outside block")
        if segment_inside(origin, destination, self.polygon):
            return math.dist(origin, destination)
        left = [
            (i, math.dist(origin, v))
            for i, v in enumerate(self.points)
            if segment_inside(origin, v, self.polygon)
        ]
        right = [
            (i, math.dist(destination, v))
            for i, v in enumerate(self.points)
            if segment_inside(destination, v, self.polygon)
        ]
        return min(a + self.distances[i][j] + b for i, a in left for j, b in right)

    def portal_costs(self, point, portals, speed_mps=1.4):
        """Physical minimum time and tied portal IDs; no generalized utility."""
        portals = tuple(portals)
        cost, ties = self._query(point, self._portals(portals, speed_mps), speed_mps)
        return cost, tuple(portals[i].id for i in ties)

    def quadrature(self, depth=2, max_samples=20000):
        """Normalized uniform-area (point, weight, RMS radius) quadrature."""
        # Reuse the established rule and budget validation without duplicating geometry.
        self.evaluate((Portal("quadrature", self.points[0]),), depth=depth, max_samples=max_samples)
        return self._rules[depth]

    def evaluate(self, portals, speed_mps=1.4, depth=2, max_samples=20000, keep_samples=False):
        prepared = self._portals(portals, speed_mps)
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ValueError("nonnegative refinement depth")
        count = len(self.triangles) * 4**depth
        if count > max_samples:
            raise ValueError("area quadrature budget exceeded; no population omitted")
        if depth not in self._rules:
            tri = self.triangles
            for _ in range(depth):
                tri = _refine(tri)
            self._rules[depth] = tuple(
                (
                    tuple(math.fsum(p[k] for p in t) / 3 for k in (0, 1)),
                    _cross(*t) / (2 * self.area_m2),
                    math.sqrt(
                        math.fsum(
                            math.dist(tuple(math.fsum(p[k] for p in t) / 3 for k in (0, 1)), v) ** 2
                            for v in t
                        )
                        / 12.0
                    ),
                )
                for t in tri
            )
        samples = []
        shares = [0.0] * len(prepared)
        error = 0.0
        for point, weight, radius in self._rules[depth]:
            cost, ties = self._query(point, prepared, speed_mps)
            error += weight * radius / speed_mps
            for i in ties:
                shares[i] += weight / len(ties)
            samples.append((point, weight, cost, ties))
        mean = math.fsum(w * t for _, w, t, _ in samples)
        variance = math.fsum(w * (t - mean) ** 2 for _, w, t, _ in samples)
        running = 0.0
        p95 = 0.0
        for _, w, t, _ in sorted(samples, key=lambda s: s[2]):
            running += w
            p95 = t
            if running >= 0.95:
                break
        result = dict(
            area_m2=self.area_m2,
            centroid=self.centroid,
            covariance=self.covariance,
            mean_s=mean,
            error_bound_s=error,
            mean_interval_s=(max(0.0, mean - error), mean + error),
            variance_quadrature_s2=variance,
            p95_quadrature_s=p95,
            portal_fraction={p.id: f for (p, _), f in zip(prepared, shares)},
            samples=count,
            weight_sum=math.fsum(w for _, w, _, _ in samples),
            speed_mps=speed_mps,
            measure="uniform planar area; not resident microdata",
        )
        if keep_samples:
            result["quadrature"] = [
                dict(xy=p, weight=w, cost_s=t, portals=[prepared[i][0].id for i in ties])
                for p, w, t, ties in samples
            ]
        return result

    def candidate_additions(self, active, candidates, **kwargs):
        """Return scores and unresolved alternatives; labels never break a tie.

        This ranks existing boundary gateways. It does not claim to construct all
        internal corridors or assign an engineering construction cost to them.
        """
        active = tuple(active)
        candidates = tuple(candidates)
        rows = []
        for p in candidates:
            r = self.evaluate(active + (p,), **kwargs)
            rows.append(
                dict(portal=p.id, xy=p.xy, mean_s=r["mean_s"], interval_s=r["mean_interval_s"])
            )
        upper = min((r["interval_s"][1] for r in rows), default=math.inf)
        return dict(
            candidates=rows, not_excluded=[r["portal"] for r in rows if r["interval_s"][0] <= upper]
        )
