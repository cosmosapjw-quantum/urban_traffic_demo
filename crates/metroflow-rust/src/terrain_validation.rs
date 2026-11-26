//! Original terrain and polygon-mask constraints. No sampling-only clearance.
use crate::{
    core_error::{CoreError, CoreResult},
    v1_area::{crossing, dist, inside, point_segment, Area, Point},
};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
type P3 = [f64; 3];
fn xy(p: P3) -> Point {
    [p[0], p[1]]
}
fn delta(a: P3, b: P3, t: f64) -> P3 {
    std::array::from_fn(|i| a[i] + t * (b[i] - a[i]))
}
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
pub(crate) struct Rect {
    xmin: f64,
    ymin: f64,
    xmax: f64,
    ymax: f64,
}
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
pub(crate) struct Terrain {
    pub(crate) n: usize,
    pub(crate) spacing_m: f64,
    pub(crate) heights_m: Vec<f64>,
    pub(crate) water: Vec<Rect>,
    pub(crate) protected: Vec<Rect>,
    pub(crate) bridge_rows: Vec<usize>,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
pub(crate) struct Region {
    pub(crate) points: Vec<Point>,
    pub(crate) bounds: [f64; 4],
}
#[derive(Debug, Clone, Deserialize, Serialize)]
pub(crate) struct Landscape {
    pub terrain: Terrain,
    pub(crate) water: Vec<Region>,
    pub(crate) protected: Vec<Region>,
}
impl Terrain {
    pub(crate) fn validate(&self) -> CoreResult<()> {
        if self.n == 0
            || self.n > 4096
            || !self.spacing_m.is_finite()
            || self.spacing_m <= 0.
            || self.heights_m.len() != (self.n + 1) * (self.n + 1)
            || self.heights_m.iter().any(|x| !x.is_finite())
            || self.bridge_rows.iter().any(|&r| r > self.n)
            || self.bridge_rows.iter().collect::<BTreeSet<_>>().len() != self.bridge_rows.len()
        {
            return Err(bad("invalid terrain raster"));
        }
        for r in self.water.iter().chain(&self.protected) {
            if ![r.xmin, r.ymin, r.xmax, r.ymax]
                .iter()
                .all(|x| x.is_finite())
                || r.xmin >= r.xmax
                || r.ymin >= r.ymax
            {
                return Err(bad("invalid terrain rectangle"));
            }
        }
        Ok(())
    }
    pub(crate) fn elevation(&self, p: Point) -> CoreResult<f64> {
        let lim = self.n as f64 * self.spacing_m;
        if p.iter().any(|x| !x.is_finite() || *x < 0. || *x > lim) {
            return Err(bad("outside terrain"));
        }
        let i = ((p[0] / self.spacing_m) as usize).min(self.n - 1);
        let j = ((p[1] / self.spacing_m) as usize).min(self.n - 1);
        let u = p[0] / self.spacing_m - i as f64;
        let v = p[1] / self.spacing_m - j as f64;
        let k = j * (self.n + 1) + i;
        let (a, b, c, d) = (
            self.heights_m[k],
            self.heights_m[k + 1],
            self.heights_m[k + self.n + 1],
            self.heights_m[k + self.n + 2],
        );
        Ok((1. - u) * (1. - v) * a + u * (1. - v) * b + (1. - u) * v * c + u * v * d)
    }
    pub(crate) fn cuts(&self, p: Point, q: Point) -> Vec<f64> {
        let mut cuts = vec![0., 1.];
        for a in 0..2 {
            let d = q[a] - p[a];
            if d.abs() > 1e-12 {
                let lo = ((p[a].min(q[a]) / self.spacing_m).floor() as usize).max(1);
                let hi = ((p[a].max(q[a]) / self.spacing_m).ceil() as usize).min(self.n - 1);
                for k in lo..=hi {
                    let t = (k as f64 * self.spacing_m - p[a]) / d;
                    if t > 0. && t < 1. {
                        cuts.push(t)
                    }
                }
            }
        }
        cuts.sort_by(f64::total_cmp);
        cuts.dedup_by(|a, b| *a == *b);
        cuts
    }
    pub(crate) fn ground_profile(&self, ps: &[P3]) -> CoreResult<(f64, f64)> {
        let mut length = 0.;
        let mut grade = 0f64;
        for w in ps.windows(2) {
            let p = w[0];
            let q = w[1];
            let ds = dist(xy(p), xy(q));
            if ds <= 1e-10 {
                return Err(bad("degenerate ground centreline"));
            }
            for t in self.cuts(xy(p), xy(q)).windows(2) {
                let a = self.elevation(xy(delta(p, q, t[0])))?;
                let b = self.elevation(xy(delta(p, q, t[1])))?;
                let m = self.elevation(xy(delta(p, q, (t[0] + t[1]) / 2.)))?;
                let span = (t[1] - t[0]) * ds;
                let aa = 2. * (a + b - 2. * m);
                let bb = b - a - aa;
                grade = grade
                    .max((bb / span).abs())
                    .max(((2. * aa + bb) / span).abs());
                let v: [f64; 9] = std::array::from_fn(|k| {
                    (1. + ((2. * aa * k as f64 / 8. + bb) / span).powi(2)).sqrt()
                });
                length += span / 24.
                    * (v[0] + v[8] + 4. * (v[1] + v[3] + v[5] + v[7]) + 2. * (v[2] + v[4] + v[6]));
            }
        }
        Ok((length, grade))
    }
    pub(crate) fn ground_gap(&self, ps: &[P3]) -> CoreResult<f64> {
        let mut g = f64::INFINITY;
        for w in ps.windows(2) {
            let p = w[0];
            let q = w[1];
            let dz = |u: f64| -> CoreResult<f64> {
                let r = delta(p, q, u);
                Ok(r[2] - self.elevation(xy(r))?)
            };
            for t in self.cuts(xy(p), xy(q)).windows(2) {
                let x = dz(t[0])?;
                let y = dz(t[1])?;
                let m = dz((t[0] + t[1]) / 2.)?;
                let a = 2. * (x + y - 2. * m);
                let b = y - x - a;
                g = g.min(x).min(y);
                if a > 0. {
                    let u = -b / (2. * a);
                    if u > 0. && u < 1. {
                        g = g.min(a * u * u + b * u + x)
                    }
                }
            }
        }
        Ok(g)
    }
}
pub(crate) fn bounds(ps: &[Point]) -> [f64; 4] {
    let mut a = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for p in ps {
        a[0] = a[0].min(p[0]);
        a[1] = a[1].min(p[1]);
        a[2] = a[2].max(p[0]);
        a[3] = a[3].max(p[1]);
    }
    a
}
fn overlap(a: [f64; 4], b: [f64; 4], eps: f64) -> bool {
    a[0] <= b[2] + eps && b[0] <= a[2] + eps && a[1] <= b[3] + eps && b[1] <= a[3] + eps
}
fn edges(ps: &[Point]) -> impl Iterator<Item = (Point, Point)> + '_ {
    ps.iter()
        .copied()
        .zip(ps.iter().copied().cycle().skip(1))
        .take(ps.len())
}
pub(crate) fn segment_clear(a: Point, b: Point, regions: &[Region], width: f64) -> bool {
    let bb = bounds(&[a, b]);
    for r in regions {
        if !overlap(bb, r.bounds, width) {
            continue;
        }
        if inside(a, &r.points) || inside(b, &r.points) {
            return false;
        }
        for (c, d) in edges(&r.points) {
            if crossing(a, b, c, d).is_some()
                || width > 0.
                    && [
                        point_segment(a, c, d),
                        point_segment(b, c, d),
                        point_segment(c, a, b),
                        point_segment(d, a, b),
                    ]
                    .into_iter()
                    .fold(f64::INFINITY, f64::min)
                        <= width
            {
                return false;
            }
        }
    }
    true
}
fn straight(ps: &[P3]) -> bool {
    let a = ps[0];
    let b = *ps.last().unwrap();
    let x = b[0] - a[0];
    let y = b[1] - a[1];
    let len = x.hypot(y);
    if len <= 0. {
        return false;
    }
    let mut prev = -1e-10;
    for p in ps {
        let s = ((p[0] - a[0]) * x + (p[1] - a[1]) * y) / (len * len);
        if ((p[0] - a[0]) * y - (p[1] - a[1]) * x).abs() > 1e-8 * len
            || s < -1e-10
            || s > 1. + 1e-10
            || s < prev - 1e-10
        {
            return false;
        }
        prev = s;
    }
    true
}
fn clearance(a: P3, b: P3, c: P3, d: P3) -> Option<(Point, f64)> {
    let u = crossing(xy(a), xy(b), xy(c), xy(d))?;
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let (ex, ey) = (d[0] - c[0], d[1] - c[1]);
    let det = dx * ey - dy * ex;
    let p = [a[0] + u * dx, a[1] + u * dy];
    let den = dx * dx + dy * dy;
    let other = ex * ex + ey * ey;
    let z = |t: f64| {
        let x = a[0] + t * dx;
        let y = a[1] + t * dy;
        let v = ((x - c[0]) * ex + (y - c[1]) * ey) / other;
        a[2] + t * (b[2] - a[2]) - c[2] - v * (d[2] - c[2])
    };
    if det.abs() >= 1e-10 {
        let v = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / det;
        return Some((
            p,
            (a[2] + u * (b[2] - a[2]) - c[2] - v * (d[2] - c[2])).abs(),
        ));
    }
    if den <= 1e-20 || other <= 1e-20 {
        return None;
    }
    let u0 = ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / den;
    let u1 = ((d[0] - a[0]) * dx + (d[1] - a[1]) * dy) / den;
    let x = z(0f64.max(u0.min(u1)));
    let y = z(1f64.min(u0.max(u1)));
    Some((
        p,
        if x * y <= 0. {
            0.
        } else {
            x.abs().min(y.abs())
        },
    ))
}
#[derive(Debug, Clone, Serialize, PartialEq)]
pub(crate) struct Report {
    pub sections: usize,
    pub segments: usize,
    pub crossing_candidates: usize,
    pub narrow_phase_contacts: usize,
    pub developed_blocks: usize,
    pub minimum_deck_ground_gap_m: Option<f64>,
}
impl Landscape {
    pub fn validate(&self, t: &Terrain) -> CoreResult<()> {
        t.validate()?;
        if &self.terrain != t {
            return Err(bad("landscape and road terrain differ"));
        }
        for r in self.water.iter().chain(&self.protected) {
            if r.points.len() < 3
                || r.points.iter().flatten().any(|v| !v.is_finite())
                || r.bounds != bounds(&r.points)
            {
                return Err(bad("invalid mask bounds"));
            }
            let _ = Area::new(r.points.clone())?;
        }
        Ok(())
    }
    pub fn developed_face(&self, ps: &[Point]) -> CoreResult<()> {
        let _ = Area::new(ps.to_vec())?;
        for region in [&self.water, &self.protected] {
            if edges(ps).any(|(a, b)| !segment_clear(a, b, region, 0.))
                || region.iter().any(|r| inside(r.points[0], ps))
            {
                return Err(bad("developed face intersects exclusion polygon"));
            }
        }
        Ok(())
    }
}
pub(crate) struct SectionView<'a> {
    pub id: &'a str,
    pub start: &'a str,
    pub end: &'a str,
    pub facility: &'a str,
    pub failure_group: Option<&'a str>,
    pub points: &'a [P3],
    pub length: f64,
    pub grade: f64,
    pub lanes: u32,
}
fn close(a: f64, b: f64, abs: f64) -> bool {
    (a - b).abs() <= abs.max(1e-6 * a.abs().max(b.abs()))
}
pub(crate) fn audit(
    t: &Terrain,
    l: &Landscape,
    ss: &[SectionView<'_>],
    developed_blocks: usize,
) -> CoreResult<Report> {
    l.validate(t)?;
    let results: Vec<_> = ss
        .par_iter()
        .map(|s| -> CoreResult<Option<f64>> {
            if s.points.len() < 2
                || s.points.iter().flatten().any(|x| !x.is_finite())
                || s.facility != "surface" && s.failure_group.is_none_or(|x| x.is_empty())
                || s.failure_group == Some("")
            {
                return Err(bad(format!("invalid section {}", s.id)));
            }
            for p in s.points {
                let z = t.elevation(xy(*p))?;
                if s.facility == "surface" && (z - p[2]).abs() > 1e-7 {
                    return Err(bad(format!("surface terrain {}", s.id)));
                }
            }
            let (length, grade, gap) = if s.facility == "surface" {
                let ends = [s.points[0], *s.points.last().unwrap()];
                let (a, b) = t.ground_profile(if straight(s.points) { &ends } else { s.points })?;
                (a, b, None)
            } else {
                let mut a = 0.;
                let mut b = 0f64;
                for w in s.points.windows(2) {
                    let d = dist(xy(w[0]), xy(w[1]));
                    if d <= 1e-8 {
                        return Err(bad("degenerate deck"));
                    }
                    let z = w[1][2] - w[0][2];
                    a += d.hypot(z);
                    b = b.max(z.abs() / d);
                }
                let g = t.ground_gap(s.points)?;
                if g < -1e-8 || s.facility == "mainline" && g < 5. - 1e-6 {
                    return Err(bad(format!("deck ground clearance {}", s.id)));
                }
                (a, b, Some(g))
            };
            if !close(length, s.length, 1e-6) || !close(grade, s.grade, 1e-8) {
                return Err(bad(format!(
                    "length/grade mismatch {}: ({length},{grade}) != ({},{})",
                    s.id, s.length, s.grade
                )));
            }
            let width = (3.5 * s.lanes as f64 + 2.) / 2.;
            for w in s.points.windows(2) {
                let (a, b) = (xy(w[0]), xy(w[1]));
                if !segment_clear(a, b, &l.protected, width)
                    || matches!(s.facility, "surface" | "ramp")
                        && !segment_clear(a, b, &l.water, width)
                {
                    return Err(bad(format!("footprint intersects mask {}", s.id)));
                }
            }
            if !straight(s.points) {
                for (i, w) in s.points.windows(2).enumerate() {
                    for q in s.points.windows(2).skip(i + 2) {
                        if clearance(w[0], w[1], q[0], q[1]).is_some_and(|(_, g)| g < 5. - 1e-6) {
                            return Err(bad(format!("illegal self crossing {}", s.id)));
                        }
                    }
                }
            }
            Ok(gap)
        })
        .collect();
    let mut min: Option<f64> = None;
    for x in results {
        if let Some(g) = x? {
            min = Some(min.map_or(g, |old| old.min(g)));
        }
    }
    let bb: Vec<_> = ss
        .iter()
        .map(|s| bounds(&s.points.iter().copied().map(xy).collect::<Vec<_>>()))
        .collect();
    let mut bucket: BTreeMap<(i64, i64), Vec<usize>> = BTreeMap::new();
    let mut candidates = vec![];
    for (i, b) in bb.iter().enumerate() {
        let mut cells = vec![];
        for x in (b[0] / 400.).floor() as i64..=(b[2] / 400.).floor() as i64 {
            for y in (b[1] / 400.).floor() as i64..=(b[3] / 400.).floor() as i64 {
                cells.push((x, y));
            }
        }
        let mut near = BTreeSet::new();
        for c in &cells {
            near.extend(bucket.get(c).into_iter().flatten().copied());
        }
        for j in near {
            candidates.push((i, j));
        }
        for c in cells {
            bucket.entry(c).or_default().push(i);
        }
    }
    let contacts: Vec<CoreResult<usize>> = candidates
        .par_iter()
        .map(|&(i, j)| {
            let s = &ss[i];
            let r = &ss[j];
            let common: Vec<_> = [
                (s.start, xy(s.points[0])),
                (s.end, xy(*s.points.last().unwrap())),
            ]
            .into_iter()
            .filter(|(id, _)| *id == r.start || *id == r.end)
            .map(|(_, p)| p)
            .collect();
            if common.len() == 1 && straight(s.points) && straight(r.points) {
                let joint = common[0];
                let a = if dist(xy(s.points[0]), joint) < 1e-7 {
                    xy(*s.points.last().unwrap())
                } else {
                    xy(s.points[0])
                };
                let b = if dist(xy(r.points[0]), joint) < 1e-7 {
                    xy(*r.points.last().unwrap())
                } else {
                    xy(r.points[0])
                };
                let u = [a[0] - joint[0], a[1] - joint[1]];
                let v = [b[0] - joint[0], b[1] - joint[1]];
                if u[0] * v[0] + u[1] * v[1] <= 0.
                    || (u[0] * v[1] - u[1] * v[0]).abs()
                        > 1e-12 * u[0].hypot(u[1]) * v[0].hypot(v[1])
                {
                    return Ok(0);
                }
            }
            let mut n = 0;
            for a in s.points.windows(2) {
                let ab = bounds(&[xy(a[0]), xy(a[1])]);
                for b in r.points.windows(2) {
                    if !overlap(ab, bounds(&[xy(b[0]), xy(b[1])]), 1e-8) {
                        continue;
                    }
                    if let Some((p, g)) = clearance(a[0], a[1], b[0], b[1]) {
                        if common.iter().any(|&x| dist(x, p) < 1e-6) {
                            continue;
                        }
                        n += 1;
                        if g < 5. - 1e-6 {
                            return Err(bad(format!(
                                "illegal crossing {}/{} clearance {g}",
                                s.id, r.id
                            )));
                        }
                    }
                }
            }
            Ok(n)
        })
        .collect();
    let mut n = 0;
    for v in contacts {
        n += v?;
    }
    Ok(Report {
        sections: ss.len(),
        segments: ss.iter().map(|s| s.points.len() - 1).sum(),
        crossing_candidates: candidates.len(),
        narrow_phase_contacts: n,
        developed_blocks,
        minimum_deck_ground_gap_m: min,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn interior_ground_hump_and_overlap_minimum() {
        let t = Terrain {
            n: 1,
            spacing_m: 10.,
            heights_m: vec![0., 10., 10., 0.],
            water: vec![],
            protected: vec![],
            bridge_rows: vec![],
        };
        t.validate().unwrap();
        let p = [[0., 0., 4.], [10., 10., 4.]];
        assert!((t.ground_gap(&p).unwrap() + 1.).abs() < 1e-12);
        assert_eq!(
            clearance([0., 0., 0.], [10., 0., 10.], [0., 0., 5.], [10., 0., 5.])
                .unwrap()
                .1,
            0.
        );
        assert_eq!(
            clearance([0., 0., 0.], [10., 0., 0.], [5., -1., 6.], [5., 1., 6.])
                .unwrap()
                .1,
            6.
        );
    }
}
