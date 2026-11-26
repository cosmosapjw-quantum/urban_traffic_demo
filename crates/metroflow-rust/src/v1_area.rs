//! Port of the existing uniform, simple-polygon, depth-zero access geometry.
//! No new distance closure, no Cartesian resident enumeration.
use crate::core_error::{CoreError, CoreResult};
use crate::v1_journey::fsum;
use std::collections::BTreeMap;
pub(crate) type Point = [f64; 2];
pub(crate) type Law = Vec<(f64, f64)>;

pub(crate) fn cross(a: Point, b: Point, c: Point) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
pub(crate) fn dist(a: Point, b: Point) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}
pub(crate) fn point_segment(p: Point, a: Point, b: Point) -> f64 {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let den = dx * dx + dy * dy;
    let u = if den == 0. {
        0.
    } else {
        (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den).clamp(0., 1.)
    };
    (p[0] - a[0] - u * dx).hypot(p[1] - a[1] - u * dy)
}
fn edges(p: &[Point]) -> impl Iterator<Item = (Point, Point)> + '_ {
    p.iter()
        .copied()
        .zip(p.iter().copied().cycle().skip(1))
        .take(p.len())
}
pub(crate) fn inside(x: Point, p: &[Point]) -> bool {
    if x.iter().any(|v| !v.is_finite()) {
        return false;
    }
    let mut hit = false;
    for (a, b) in edges(p) {
        if point_segment(x, a, b) < 1e-8 {
            return true;
        }
        if (a[1] > x[1]) != (b[1] > x[1])
            && x[0] < (b[0] - a[0]) * (x[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            hit = !hit
        }
    }
    hit
}
// Same closed-contact tolerance and collinear-overlap midpoint as restored_geometry.
pub(crate) fn crossing(a: Point, b: Point, c: Point, d: Point) -> Option<f64> {
    let (ax, ay) = (b[0] - a[0], b[1] - a[1]);
    let (bx, by) = (d[0] - c[0], d[1] - c[1]);
    let det = ax * by - ay * bx;
    let (cx, cy) = (c[0] - a[0], c[1] - a[1]);
    if det.abs() < 1e-10 {
        let den = ax * ax + ay * ay;
        let den2 = bx * bx + by * by;
        if den <= 1e-20 || den2 <= 1e-20 || (cx * ay - cy * ax).abs() > 1e-7 {
            return None;
        }
        let u0 = (cx * ax + cy * ay) / den;
        let u1 = ((d[0] - a[0]) * ax + (d[1] - a[1]) * ay) / den;
        let lo = 0f64.max(u0.min(u1));
        let hi = 1f64.min(u0.max(u1));
        if hi < lo - 1e-9 {
            return None;
        }
        return Some((lo + hi) / 2.);
    }
    let s = (cx * by - cy * bx) / det;
    let t = (cx * ay - cy * ax) / det;
    if (-1e-9..=1. + 1e-9).contains(&s) && (-1e-9..=1. + 1e-9).contains(&t) {
        Some(s)
    } else {
        None
    }
}
pub(crate) fn segment_inside(a: Point, b: Point, p: &[Point]) -> bool {
    if !inside(a, p) || !inside(b, p) {
        return false;
    }
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let den = dx * dx + dy * dy;
    if den == 0. {
        return true;
    }
    let mut cuts = vec![0., 1.];
    for (c, d) in edges(p) {
        if let Some(x) = crossing(a, b, c, d) {
            cuts.push(x.clamp(0., 1.))
        }
        for r in [c, d] {
            let u = ((r[0] - a[0]) * dx + (r[1] - a[1]) * dy) / den;
            if u > 0. && u < 1. && ((r[0] - a[0]) * dy - (r[1] - a[1]) * dx).abs() < 1e-8 {
                cuts.push(u)
            }
        }
    }
    cuts.sort_by(f64::total_cmp);
    cuts.dedup_by(|x, y| *x == *y);
    cuts.windows(2).filter(|w| w[1] - w[0] > 1e-12).all(|w| {
        let t = (w[0] + w[1]) / 2.;
        inside([a[0] + t * dx, a[1] + t * dy], p)
    })
}
fn point_cmp(a: &Point, b: &Point) -> std::cmp::Ordering {
    a[0].total_cmp(&b[0]).then(a[1].total_cmp(&b[1]))
}
pub(crate) fn canonical(mut p: Vec<Point>) -> CoreResult<Vec<Point>> {
    if p.len() > 1 && p.first() == p.last() {
        p.pop();
    }
    if p.len() < 3 || p.len() > 256 || p.iter().flatten().any(|x| !x.is_finite()) {
        return Err(CoreError::value(
            "finite simple polygon required (<=256 vertices)",
        ));
    }
    for i in 0..p.len() {
        if p[..i].contains(&p[i]) {
            return Err(CoreError::value("repeated polygon vertex"));
        }
    }
    loop {
        if p.len() <= 3 {
            break;
        }
        let mut removed = false;
        for i in 0..p.len() {
            let (a, b, c) = (p[(i + p.len() - 1) % p.len()], p[i], p[(i + 1) % p.len()]);
            if cross(a, b, c).abs() < 1e-12
                && (b[0] - a[0]) * (b[0] - c[0]) + (b[1] - a[1]) * (b[1] - c[1]) <= 0.
            {
                p.remove(i);
                removed = true;
                break;
            }
        }
        if !removed {
            break;
        }
    }
    let n = p.len();
    for i in 0..n {
        for j in i + 1..n {
            if j == (i + 1) % n || (j + 1) % n == i {
                continue;
            }
            if crossing(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n]).is_some() {
                return Err(CoreError::value("self-intersecting boundary"));
            }
        }
    }
    let a = fsum((1..n - 1).map(|i| cross(p[0], p[i], p[i + 1])));
    if a.abs() < 1e-12 {
        return Err(CoreError::value("zero polygon area"));
    }
    if a < 0. {
        p.reverse()
    }
    let k = (0..n).min_by(|&i, &j| point_cmp(&p[i], &p[j])).unwrap();
    p.rotate_left(k);
    Ok(p)
}
pub(crate) fn triangulate(mut p: Vec<Point>) -> CoreResult<Vec<[Point; 3]>> {
    let mut result = Vec::with_capacity(p.len() - 2);
    while p.len() > 3 {
        let n = p.len();
        let mut selected = None;
        for i in 0..n {
            let j = (i + n - 1) % n;
            let k = (i + 1) % n;
            let (a, b, c) = (p[j], p[i], p[k]);
            if cross(a, b, c) <= 1e-12 {
                continue;
            }
            if p.iter().enumerate().any(|(l, &q)| {
                l != i
                    && l != j
                    && l != k
                    && cross(a, b, q).min(cross(b, c, q)).min(cross(c, a, q)) >= -1e-12
            }) {
                continue;
            }
            selected = Some((i, [a, b, c]));
            break;
        }
        let (i, t) = selected.ok_or_else(|| CoreError::value("no admissible polygon ear"))?;
        result.push(t);
        p.remove(i);
    }
    let t = [p[0], p[1], p[2]];
    if cross(t[0], t[1], t[2]) <= 0. {
        return Err(CoreError::value("degenerate final triangle"));
    }
    result.push(t);
    Ok(result)
}
pub(crate) struct Area {
    points: Vec<Point>,
    samples: Vec<(Point, f64)>,
    distances: Vec<f64>,
    // Reuse visibility from every centroid in portal and intrazonal laws.
    visible: Vec<Vec<f64>>,
}
impl Area {
    pub(crate) fn new(points: Vec<Point>) -> CoreResult<Self> {
        let points = canonical(points)?;
        let triangles = triangulate(points.clone())?;
        let a = fsum(triangles.iter().map(|t| cross(t[0], t[1], t[2]) / 2.));
        let samples: Vec<_> = triangles
            .iter()
            .map(|t| {
                let c = std::array::from_fn(|k| fsum(t.iter().map(|p| p[k])) / 3.);
                (c, cross(t[0], t[1], t[2]) / (2. * a))
            })
            .collect();
        let n = points.len();
        let mut distances = vec![f64::INFINITY; n * n];
        for i in 0..n {
            distances[i * n + i] = 0.;
            for j in 0..i {
                if segment_inside(points[i], points[j], &points) {
                    let d = dist(points[i], points[j]);
                    distances[i * n + j] = d;
                    distances[j * n + i] = d;
                }
            }
        }
        // Contiguous row-major min-plus update. For nonnegative distances D[k,k]=0
        // the pivot row is unchanged, so a single reusable pivot buffer is exact.
        crate::geometry_simd::closure(
            &mut distances,
            n,
            std::env::var_os("METROFLOW_AVX_GEOMETRY").is_some(),
        );
        let visible = samples
            .iter()
            .map(|&(x, _)| {
                points
                    .iter()
                    .map(|&v| {
                        if segment_inside(x, v, &points) {
                            dist(x, v)
                        } else {
                            f64::INFINITY
                        }
                    })
                    .collect()
            })
            .collect();
        Ok(Self {
            points,
            samples,
            distances,
            visible,
        })
    }
    fn tails(&self, a: Point) -> Vec<f64> {
        self.points
            .iter()
            .map(|&v| {
                if segment_inside(a, v, &self.points) {
                    dist(a, v)
                } else {
                    f64::INFINITY
                }
            })
            .collect()
    }
    fn distance_cached(&self, a: Point, b: Point, left: &[f64], right: &[f64]) -> CoreResult<f64> {
        if segment_inside(a, b, &self.points) {
            return Ok(dist(a, b));
        }
        let n = self.points.len();
        let mut best = f64::INFINITY;
        for (i, &x) in left.iter().enumerate() {
            if !x.is_finite() {
                continue;
            }
            for (j, &y) in right.iter().enumerate() {
                best = best.min(x + self.distances[i * n + j] + y);
            }
        }
        if best.is_finite() {
            Ok(best)
        } else {
            Err(CoreError::value("no internal geodesic"))
        }
    }
    pub(crate) fn distance(&self, a: Point, b: Point) -> CoreResult<f64> {
        if !inside(a, &self.points) || !inside(b, &self.points) {
            return Err(CoreError::value("activity point outside block"));
        }
        self.distance_cached(a, b, &self.tails(a), &self.tails(b))
    }
    pub(crate) fn access(&self, door: Point, stock: f64) -> CoreResult<(Law, f64)> {
        if !stock.is_finite()
            || stock <= 0.
            || edges(&self.points).all(|(a, b)| point_segment(door, a, b) > 1e-7)
        {
            return Err(CoreError::value("invalid activity stock or door"));
        }
        let tails = self.tails(door);
        let n = self.points.len();
        // Original portal query computes vertex-to-door distance before combining
        // the centroid's visible vertices. Keep that floating operation order.
        let vertex: Vec<_> = (0..n)
            .map(|i| {
                (0..n)
                    .map(|j| self.distances[i * n + j] + tails[j])
                    .fold(f64::INFINITY, f64::min)
            })
            .collect();
        let mut bins: BTreeMap<u64, Vec<(f64, f64)>> = BTreeMap::new();
        let mut maximum = 0f64;
        for (i, &(p, w)) in self.samples.iter().enumerate() {
            let direct = if segment_inside(p, door, &self.points) {
                dist(p, door)
            } else {
                f64::INFINITY
            };
            let d = direct.min(
                self.visible[i]
                    .iter()
                    .zip(&vertex)
                    .map(|(a, b)| a + b)
                    .fold(f64::INFINITY, f64::min),
            ) / 1.4;
            if !d.is_finite() {
                return Err(CoreError::value("no portal route"));
            }
            maximum = maximum.max(d);
            bins.entry((d / 2.).floor() as u64)
                .or_default()
                .push((w * stock / stock, d));
        }
        if bins.len() > 256 {
            return Err(CoreError::resource("access atom budget"));
        }
        let law: Law = bins
            .into_values()
            .map(|r| {
                let m = fsum(r.iter().map(|x| x.0));
                (fsum(r.iter().map(|x| x.0 * x.1)) / m, m)
            })
            .collect();
        if (fsum(law.iter().map(|x| x.1)) - 1.).abs() > 1e-10 {
            return Err(CoreError::arithmetic("access law mass"));
        }
        Ok((law, maximum))
    }
    pub(crate) fn internal(&self, a: f64, b: f64) -> CoreResult<Law> {
        if !a.is_finite() || !b.is_finite() || a <= 0. || b <= 0. {
            return Err(CoreError::value("invalid stock"));
        }
        let n = self.samples.len();
        if n * n > 20000 {
            return Err(CoreError::resource("intrazonal pair budget"));
        }
        let mut law = Vec::with_capacity(n * n);
        for (i, &(x, wx)) in self.samples.iter().enumerate() {
            for (j, &(y, wy)) in self.samples.iter().enumerate() {
                let d = self.distance_cached(x, y, &self.visible[i], &self.visible[j])? / 1.4;
                law.push((d, (wx * a / a) * (wy * b / b)));
            }
        }
        if (fsum(law.iter().map(|x| x.1)) - 1.).abs() > 1e-10 {
            return Err(CoreError::arithmetic("intrazonal law mass"));
        }
        Ok(law)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn square() -> Vec<Point> {
        vec![[0., 0.], [10., 0.], [10., 10.], [0., 10.]]
    }
    #[test]
    fn square_depth0_and_internal_mass() {
        let a = Area::new(square()).unwrap();
        let (law, max) = a.access([0., 0.], 1000.).unwrap();
        assert_eq!(law.len(), 2);
        assert!((law.iter().map(|p| p.1).sum::<f64>() - 1.).abs() < 1e-12);
        assert!(max > 5.);
        let q = a.internal(1000., 50.).unwrap();
        assert_eq!(q.len(), 4);
        assert_eq!(q.iter().filter(|x| x.0 == 0.).count(), 2);
        assert!((q.iter().map(|p| p.1).sum::<f64>() - 1.).abs() < 1e-12);
    }
    #[test]
    fn concave_shortest_and_fail_closed() {
        let a = Area::new(vec![
            [0., 0.],
            [4., 0.],
            [4., 1.],
            [1., 1.],
            [1., 4.],
            [0., 4.],
        ])
        .unwrap();
        let d = a.distance([3., 0.5], [0.5, 3.]).unwrap();
        assert!((d - 2. * 4.25_f64.sqrt()).abs() < 1e-12);
        assert!(a.distance([3., 3.], [0., 0.]).is_err());
        assert!(Area::new(vec![[0., 0.], [2., 2.], [0., 2.], [2., 0.]]).is_err());
    }
}
