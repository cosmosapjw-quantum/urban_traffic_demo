//! Migration of the separate original restored morphology/ramp grammar.
//! This preserves its proposal rejection and insertion ordering; not a new
//! scalable city or a claim of certified engineering interchange geometry.
use crate::{
    atlas_roads::{ground, Node, Road},
    atlas_seed::Mt,
    core_error::{CoreError, CoreResult},
    terrain_validation::{Rect, Terrain},
    v1_area::{crossing, dist, Point},
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    f64::consts::PI,
};
type P3 = [f64; 3];
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
fn xy(p: P3) -> Point {
    [p[0], p[1]]
}
fn intersects(a: Point, b: Point, r: &Rect, m: f64) -> bool {
    let (mut lo, mut hi) = (0f64, 1f64);
    for i in 0..2 {
        let (mn, mx) = if i == 0 {
            (r.xmin - m, r.xmax + m)
        } else {
            (r.ymin - m, r.ymax + m)
        };
        let d = b[i] - a[i];
        if d == 0. {
            if a[i] < mn || a[i] > mx {
                return false;
            }
        } else {
            let u = (mn - a[i]) / d;
            let v = (mx - a[i]) / d;
            lo = lo.max(u.min(v));
            hi = hi.min(u.max(v));
            if lo > hi {
                return false;
            }
        }
    }
    true
}
fn terrain(n: usize, seed: u64) -> CoreResult<Terrain> {
    if n < 4 || n % 2 != 0 || n > 90 {
        return Err(bad("even fixture n in 4..90 required"));
    }
    let spacing = 400.;
    let l = n as f64 * spacing;
    let mut rng = Mt::new(seed);
    let water = vec![Rect {
        xmin: 0.48 * l,
        ymin: -spacing,
        xmax: 0.52 * l,
        ymax: l + spacing,
    }];
    let protected = vec![Rect {
        xmin: 0.76 * l,
        ymin: 0.76 * l,
        xmax: l + spacing,
        ymax: l + spacing,
    }];
    let hx = (0.78 - 0.015 + 0.03 * rng.random()) * l;
    let hy = (0.73 - 0.015 + 0.03 * rng.random()) * l;
    let heights_m = (0..(n + 1) * (n + 1))
        .map(|k| {
            let (x, y) = (
                (k % (n + 1)) as f64 * spacing,
                (k / (n + 1)) as f64 * spacing,
            );
            if intersects([x, y], [x, y], &water[0], 0.) {
                -2.
            } else {
                20. + 0.003 * x
                    + 0.004 * y
                    + 160.
                        * (-((x - hx).powi(2) + (y - hy).powi(2)) / (2. * (0.13 * l).powi(2))).exp()
            }
        })
        .collect();
    Ok(Terrain {
        n,
        spacing_m: spacing,
        heights_m,
        water,
        protected,
        bridge_rows: vec![n / 3, 2 * n / 3],
    })
}
fn gate(t: &Terrain, p: &[Point], width: f64, facility: &str) -> Option<&'static str> {
    for w in p.windows(2) {
        if t.protected
            .iter()
            .any(|r| intersects(w[0], w[1], r, width / 2.))
        {
            return Some("protected");
        }
        if matches!(facility, "surface" | "ramp")
            && t.water
                .iter()
                .any(|r| intersects(w[0], w[1], r, width / 2.))
        {
            return Some("water");
        }
    }
    None
}
fn deck(p: &[P3]) -> CoreResult<(f64, f64)> {
    let (mut l, mut g) = (0., 0f64);
    for w in p.windows(2) {
        let d = dist(xy(w[0]), xy(w[1]));
        if d <= 1e-8 {
            return Err(bad("degenerate deck"));
        }
        let z = w[1][2] - w[0][2];
        l += d.hypot(z);
        g = g.max(z.abs() / d);
    }
    Ok((l, g))
}
struct Builder {
    t: Terrain,
    nodes: BTreeMap<String, Node>,
    sections: Vec<Road>,
    rejected: BTreeMap<String, usize>,
}
impl Builder {
    fn vertex(&mut self, key: String, p: Point, layer: u32, z: Option<f64>) -> CoreResult<String> {
        let xyz = [
            p[0],
            p[1],
            match z {
                Some(x) => x,
                None => self.t.elevation(p)?,
            },
        ];
        if self
            .nodes
            .get(&key)
            .is_some_and(|x| x.xyz != xyz || x.layer != layer)
        {
            return Err(bad("inconsistent shared junction"));
        }
        self.nodes.insert(
            key.clone(),
            Node {
                id: key.clone(),
                xyz,
                layer,
            },
        );
        Ok(key)
    }
    fn reject(&mut self, s: &str) -> bool {
        *self.rejected.entry(s.into()).or_default() += 1;
        false
    }
    fn add(
        &mut self,
        key: String,
        u: String,
        v: String,
        ps: Vec<Point>,
        h: &str,
        f: &str,
        points: Option<Vec<P3>>,
        group: Option<String>,
        role: Option<String>,
    ) -> CoreResult<bool> {
        let lanes = if f == "ramp" {
            (1, 0)
        } else {
            match h {
                "arterial" => (2, 2),
                "expressway" => (2, 0),
                _ => (1, 1),
            }
        };
        if let Some(r) = gate(&self.t, &ps, 3.5 * (lanes.0 + lanes.1) as f64 + 2., f) {
            return Ok(self.reject(r));
        }
        let is_deck = points.is_some();
        let result: CoreResult<(Vec<P3>, f64, f64)> = if let Some(p) = points {
            deck(&p).map(|(l, g)| (p, l, g))
        } else {
            (|| {
                let (mut p, mut l, mut g) = (vec![], 0., 0f64);
                for w in ps.windows(2) {
                    let (a, b, c) = ground(&self.t, w[0], w[1])?;
                    for x in a {
                        if p.last() != Some(&x) {
                            p.push(x)
                        }
                    }
                    l += b;
                    g = g.max(c);
                }
                Ok((p, l, g))
            })()
        };
        let Ok((p, l, g)) = result else {
            return Ok(self.reject("outside_terrain"));
        };
        if g > 0.12 {
            return Ok(self.reject("grade"));
        }
        if is_deck && self.t.ground_gap(&p)? < -1e-8 {
            return Ok(self.reject("buried_deck"));
        }
        if p.first() != Some(&self.nodes[&u].xyz) || p.last() != Some(&self.nodes[&v].xyz) {
            return Err(bad("endpoint geometry mismatch"));
        }
        self.sections.push(Road {
            id: key,
            start: u,
            end: v,
            points: p,
            hierarchy: h.into(),
            facility: f.into(),
            forward_lanes: lanes.0,
            backward_lanes: lanes.1,
            length_m: l,
            max_grade: g,
            failure_group: group,
            ramp_purpose: role,
        });
        Ok(true)
    }
    fn bridge(&mut self, u: String, v: String, g: String) -> CoreResult<()> {
        let (a, b) = (self.nodes[&u].xyz, self.nodes[&v].xyz);
        let mut p: Vec<_> = (0..=4)
            .map(|k| {
                let t = k as f64 / 4.;
                [
                    a[0] + t * (b[0] - a[0]),
                    a[1] + t * (b[1] - a[1]),
                    a[2] + t * (b[2] - a[2]) + 8. * (PI * t).sin(),
                ]
            })
            .collect();
        p[0] = a;
        p[4] = b;
        self.add(
            g.clone(),
            u,
            v,
            p.iter().copied().map(xy).collect(),
            "arterial",
            "bridge",
            Some(p),
            Some(g),
            None,
        )?;
        Ok(())
    }
    fn ramp_illegal(&self) -> bool {
        let s = self.sections.last().unwrap();
        for r in &self.sections[..self.sections.len() - 1] {
            let common: Vec<_> = [&s.start, &s.end]
                .into_iter()
                .filter(|k| **k == r.start || **k == r.end)
                .map(|k| xy(self.nodes[k].xyz))
                .collect();
            for a in r.points.windows(2) {
                for b in s.points.windows(2) {
                    let Some(u) = crossing(xy(a[0]), xy(a[1]), xy(b[0]), xy(b[1])) else {
                        continue;
                    };
                    let p = [
                        a[0][0] + u * (a[1][0] - a[0][0]),
                        a[0][1] + u * (a[1][1] - a[0][1]),
                    ];
                    if common.iter().any(|&x| dist(p, x) < 1e-6) {
                        continue;
                    }
                    let (dx, dy) = (b[1][0] - b[0][0], b[1][1] - b[0][1]);
                    let (ax, ay) = (a[1][0] - a[0][0], a[1][1] - a[0][1]);
                    let det = ax * dy - ay * dx;
                    let v = if det.abs() < 1e-10 {
                        ((p[0] - b[0][0]) * dx + (p[1] - b[0][1]) * dy) / (dx * dx + dy * dy)
                    } else {
                        ((b[0][0] - a[0][0]) * ay - (b[0][1] - a[0][1]) * ax) / det
                    };
                    let gap =
                        (a[0][2] + u * (a[1][2] - a[0][2]) - b[0][2] - v * (b[1][2] - b[0][2]))
                            .abs();
                    if gap < 5. - 1e-6 {
                        return true;
                    }
                }
            }
        }
        false
    }
    fn expressway(&mut self, l: f64) -> CoreResult<()> {
        let xs = [0.10, 0.24, 0.36, 0.64, 0.76, 0.90];
        let ys = [0.42 * l - 12., 0.42 * l + 12.];
        let mut z = f64::NEG_INFINITY;
        for y in ys {
            for k in 10..=90 {
                z = z.max(self.t.elevation([l * (k as f64 / 100.), y])?)
            }
        }
        z += 10.;
        let surface: BTreeSet<_> = self
            .sections
            .iter()
            .filter(|s| s.facility == "surface")
            .flat_map(|s| [s.start.clone(), s.end.clone()])
            .collect();
        let mut carriageways = vec![];
        for (d, y) in ys.into_iter().enumerate() {
            let keys = xs
                .iter()
                .enumerate()
                .map(|(i, x)| self.vertex(format!("h{d}:{i}"), [x * l, y], 1, Some(z)))
                .collect::<CoreResult<Vec<_>>>()?;
            let order: Vec<_> = if d == 0 {
                (0..5).collect()
            } else {
                (0..5).rev().collect()
            };
            for i in order {
                let (u, v) = if d == 0 {
                    (keys[i].clone(), keys[i + 1].clone())
                } else {
                    (keys[i + 1].clone(), keys[i].clone())
                };
                let p = vec![self.nodes[&u].xyz, self.nodes[&v].xyz];
                let group = if i == 2 {
                    "highway_river".into()
                } else {
                    format!("highway:{d}:{i}")
                };
                self.add(
                    format!("main:{d}:{i}"),
                    u,
                    v,
                    p.iter().copied().map(xy).collect(),
                    "expressway",
                    "mainline",
                    Some(p),
                    Some(group),
                    None,
                )?;
            }
            carriageways.push(keys);
        }
        for (d, y) in ys.into_iter().enumerate() {
            for (idx, on0) in [(1, true), (2, false), (3, true), (4, false)] {
                let on = if d == 0 { on0 } else { !on0 };
                let role = if on { "on_ramp" } else { "off_ramp" };
                let highway = carriageways[d][idx].clone();
                let dx = if on == (d == 0) { -0.07 * l } else { 0.07 * l };
                let target = [xs[idx] * l + dx, if d == 0 { 0.27 * l } else { 0.57 * l }];
                let mut candidates: Vec<_> = surface
                    .iter()
                    .filter(|s| {
                        if d == 0 {
                            self.nodes[*s].xyz[1] < y - 200.
                        } else {
                            self.nodes[*s].xyz[1] > y + 200.
                        }
                    })
                    .cloned()
                    .collect();
                candidates.sort_by(|a, b| {
                    dist(xy(self.nodes[a].xyz), target)
                        .total_cmp(&dist(xy(self.nodes[b].xyz), target))
                        .then(a.cmp(b))
                });
                for surf in candidates.into_iter().take(12) {
                    let (u, v) = if on {
                        (surf, highway.clone())
                    } else {
                        (highway.clone(), surf)
                    };
                    let (a, b) = (self.nodes[&u].xyz, self.nodes[&v].xyz);
                    let sign = if d == 0 { 1. } else { -1. };
                    if dist(xy(a), xy(b)) < 200. || sign * (b[0] - a[0]) <= 80. {
                        continue;
                    }
                    let p = ramp(a, b, sign, on);
                    if !self.add(
                        format!("{role}:{d}:{idx}"),
                        u,
                        v,
                        p.iter().copied().map(xy).collect(),
                        "collector",
                        "ramp",
                        Some(p),
                        Some(format!("interchange:{d}:{idx}")),
                        Some(role.into()),
                    )? {
                        continue;
                    }
                    if self.ramp_illegal() {
                        self.sections.pop();
                        continue;
                    }
                    break;
                }
            }
        }
        Ok(())
    }
}
fn ramp(a: P3, b: P3, sign: f64, on: bool) -> Vec<P3> {
    let handle = ((b[0] - a[0]).abs() * 0.55).min(220.);
    let mut c1 = [a[0] + 0.30 * (b[0] - a[0]), a[1] + 0.30 * (b[1] - a[1])];
    let mut c2 = [b[0] - 0.30 * (b[0] - a[0]), b[1] - 0.30 * (b[1] - a[1])];
    if on {
        c2 = [b[0] - sign * handle, b[1]]
    } else {
        c1 = [a[0] + sign * handle, a[1]]
    }
    let p: Vec<Point> = (0..25)
        .map(|k| {
            let u = k as f64 / 24.;
            std::array::from_fn(|i| {
                (1. - u).powi(3) * a[i]
                    + 3. * (1. - u).powi(2) * u * c1[i]
                    + 3. * (1. - u) * u * u * c2[i]
                    + u.powi(3) * b[i]
            })
        })
        .collect();
    let mut run = vec![0.];
    for w in p.windows(2) {
        run.push(run.last().unwrap() + dist(w[0], w[1]))
    }
    let l = *run.last().unwrap();
    let mut p: Vec<_> = p
        .iter()
        .zip(run)
        .map(|(p, d)| [p[0], p[1], a[2] + (b[2] - a[2]) * d / l])
        .collect();
    p[0] = a;
    p[24] = b;
    p
}
pub fn generate(style: &str, n: usize, seed: u64, interchanges: bool) -> CoreResult<Value> {
    if !matches!(
        style,
        "grid_core" | "organic" | "superblock_mixed" | "ring_radial"
    ) {
        return Err(bad("restored style"));
    }
    let t = terrain(n, seed)?;
    let l = n as f64 * t.spacing_m;
    let spacing = t.spacing_m;
    let mut b = Builder {
        t,
        nodes: BTreeMap::new(),
        sections: vec![],
        rejected: BTreeMap::new(),
    };
    let phase = (seed % 19) as f64 / 19. * 2. * PI;
    let warp = |x: f64, y: f64| {
        if style == "organic" {
            let a = 0.024 * l;
            [
                x + a * (PI * x / l).sin() * (2. * PI * y / l + phase).sin(),
                y + a * (2. * PI * x / l + phase).sin() * (PI * y / l).sin(),
            ]
        } else {
            [x, y]
        }
    };
    if style != "ring_radial" {
        let mut grid = BTreeMap::new();
        for y in 1..n {
            for x in 1..n {
                let p = warp(x as f64 * spacing, y as f64 * spacing);
                if gate(&b.t, &[p, p], 12., "surface").is_none() {
                    let k = b.vertex(format!("s{x}:{y}"), p, 0, None)?;
                    grid.insert((x, y), k);
                }
            }
        }
        for (&(x, y), u) in &grid {
            for (xx, yy) in [(x + 1, y), (x, y + 1)] {
                let Some(v) = grid.get(&(xx, yy)) else {
                    continue;
                };
                if style == "superblock_mixed"
                    && (x % 3 == 1 && y % 3 == 1 && yy == y || x % 3 == 2 && y % 3 == 2 && xx == x)
                {
                    continue;
                }
                let along = if yy == y { y } else { x };
                let h = if along % 4 == 0 {
                    "arterial"
                } else if along % 3 == 0 {
                    "collector"
                } else {
                    "local"
                };
                let p = (0..5)
                    .map(|k| {
                        warp(
                            (x as f64 + (xx - x) as f64 * k as f64 / 4.) * spacing,
                            (y as f64 + (yy - y) as f64 * k as f64 / 4.) * spacing,
                        )
                    })
                    .collect();
                b.add(
                    format!("grid:{u}>{v}"),
                    u.clone(),
                    v.clone(),
                    p,
                    h,
                    "surface",
                    None,
                    None,
                    None,
                )?;
            }
        }
        for row in [n / 3, n / 2, 2 * n / 3] {
            let left = grid
                .iter()
                .filter(|((x, y), _)| *y == row && (*x as f64) < n as f64 / 2.)
                .last();
            let right = grid
                .iter()
                .find(|((x, y), _)| *y == row && (*x as f64) > n as f64 / 2.);
            if let (Some((_, u)), Some((_, v))) = (left, right) {
                b.bridge(u.clone(), v.clone(), format!("bridge:{row}"))?
            }
        }
    } else {
        for (bank, cx) in [0.24 * l, 0.76 * l].into_iter().enumerate() {
            let cy = 0.5 * l;
            for (ring, radius) in [0.055 * l, 0.105 * l, 0.16 * l, 0.22 * l]
                .into_iter()
                .enumerate()
            {
                for j in 0..16 {
                    let a = j as f64 * PI / 8.;
                    b.vertex(
                        format!("r{bank}:{ring}:{j}"),
                        [cx + radius * a.cos(), cy + radius * a.sin()],
                        0,
                        None,
                    )?;
                }
                for j in 0..16 {
                    let u = format!("r{bank}:{ring}:{j}");
                    let v = format!("r{bank}:{ring}:{}", (j + 1) % 16);
                    let mut p: Vec<_> = (0..5)
                        .map(|k| {
                            let a = (j as f64 + k as f64 / 4.) * PI / 8.;
                            [cx + radius * a.cos(), cy + radius * a.sin()]
                        })
                        .collect();
                    p[0] = xy(b.nodes[&u].xyz);
                    p[4] = xy(b.nodes[&v].xyz);
                    b.add(
                        format!("arc:{u}>{v}"),
                        u.clone(),
                        v,
                        p,
                        if ring == 2 { "arterial" } else { "local" },
                        "surface",
                        None,
                        None,
                        None,
                    )?;
                    if ring > 0 && (j % 2 == 0 || ring < 3) {
                        let a = format!("r{bank}:{}:{j}", ring - 1);
                        b.add(
                            format!("spoke:{a}>{u}"),
                            a.clone(),
                            u.clone(),
                            vec![xy(b.nodes[&a].xyz), xy(b.nodes[&u].xyz)],
                            if j % 4 == 0 { "collector" } else { "local" },
                            "surface",
                            None,
                            None,
                            None,
                        )?;
                    }
                }
            }
        }
        for (j, k) in [(2, 6), (0, 8), (14, 10)] {
            b.bridge(
                format!("r0:3:{j}"),
                format!("r1:3:{k}"),
                format!("bridge:{j}"),
            )?;
        }
    }
    if interchanges {
        b.expressway(l)?
    }
    let used: BTreeSet<_> = b
        .sections
        .iter()
        .flat_map(|s| [s.start.clone(), s.end.clone()])
        .collect();
    let nodes: Vec<_> = used.into_iter().map(|k| b.nodes[&k].clone()).collect();
    Ok(
        json!({"style":style,"terrain":b.t,"nodes":nodes,"sections":b.sections,"rejected":b.rejected.iter().collect::<Vec<_>>()}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn restored_typed_ramps() {
        let x = generate("grid_core", 12, 17, true).unwrap();
        let s = x["sections"].as_array().unwrap();
        assert!(s.iter().any(|r| r["facility"] == "mainline"));
        assert!(s.iter().any(|r| r["facility"] == "ramp"));
        for r in s.iter().filter(|r| r["facility"] == "ramp") {
            assert_eq!(r["forward_lanes"], 1);
            assert_eq!(r["backward_lanes"], 0);
            assert!(matches!(
                r["ramp_purpose"].as_str(),
                Some("on_ramp" | "off_ramp")
            ));
        }
    }
}
