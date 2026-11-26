//! Original half-edge faces, geometric zoning and capped integer stock allocation.
//! Lexical node order and face traversal match the original Python algorithm.
use crate::{
    atlas_roads::Roads,
    core_error::{CoreError, CoreResult},
    terrain_validation::{bounds, segment_clear, Region, Terrain},
    v1_area::{dist, inside, Point},
    v1_journey::fsum,
};
use rayon::prelude::*;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Block {
    pub id: String,
    pub boundary: Vec<String>,
    pub xy: Point,
    pub area_m2: f64,
    pub perimeter_m: f64,
    pub r#use: String,
    pub housing_capacity: u64,
    pub job_capacity: u64,
    pub residents: u64,
    pub jobs: u64,
}
fn edges(p: &[Point]) -> impl Iterator<Item = (Point, Point)> + '_ {
    p.iter()
        .copied()
        .zip(p.iter().copied().cycle().skip(1))
        .take(p.len())
}
fn polygon_clear(p: &[Point], r: &[Region]) -> bool {
    edges(p).all(|(a, b)| segment_clear(a, b, r, 0.)) && !r.iter().any(|x| inside(x.points[0], p))
}
fn slope(t: &Terrain, x: usize, y: usize) -> f64 {
    let i = y * (t.n + 1) + x;
    let (a, b, c, d) = (
        t.heights_m[i],
        t.heights_m[i + 1],
        t.heights_m[i + t.n + 1],
        t.heights_m[i + t.n + 2],
    );
    let mut m = 0f64;
    for dx in [b - a, d - c] {
        for dy in [c - a, d - b] {
            m = m.max(dx.hypot(dy));
        }
    }
    m / t.spacing_m
}
/// Integer stock assignment. One exact ordered fsum per saturation round,
/// deterministic largest remainders; work independent of resident count.
pub(crate) fn apportion(total: u64, cap: &[u64], w: &[f64]) -> CoreResult<Vec<u64>> {
    if cap.len() != w.len()
        || cap.is_empty()
        || total > 1u64 << 53
        || cap.iter().any(|&c| c > 1u64 << 53)
        || w.iter().any(|x| !x.is_finite() || *x < 0.)
    {
        return Err(bad("apportionment domain"));
    }
    let mut active: BTreeSet<_> = (0..cap.len())
        .filter(|&i| cap[i] > 0 && w[i] > 0.)
        .collect();
    let eligible = active.iter().try_fold(0u64, |s, &i| {
        s.checked_add(cap[i])
            .ok_or_else(|| bad("capacity overflow"))
    })?;
    if total > eligible {
        return Err(bad("insufficient eligible capacity"));
    }
    let mut expected = vec![0.; cap.len()];
    let mut left = total as f64;
    while !active.is_empty() && left > 0. {
        let sw = fsum(active.iter().map(|&i| w[i]));
        if !sw.is_finite() || sw <= 0. {
            return Err(bad("weight sum"));
        }
        let bound: Vec<_> = active
            .iter()
            .copied()
            .filter(|&i| left * w[i] / sw >= cap[i] as f64)
            .collect();
        if bound.is_empty() {
            for &i in &active {
                expected[i] = left * w[i] / sw;
            }
            break;
        }
        for i in bound {
            expected[i] = cap[i] as f64;
            left -= cap[i] as f64;
            active.remove(&i);
        }
    }
    let mut out: Vec<_> = cap
        .iter()
        .zip(&expected)
        .map(|(&c, &x)| c.min(x.floor() as u64))
        .collect();
    let sum = out.iter().try_fold(0u64, |s, &x| {
        s.checked_add(x).ok_or_else(|| bad("stock overflow"))
    })?;
    let extra = total
        .checked_sub(sum)
        .ok_or_else(|| bad("apportionment roundoff"))?;
    let mut order: Vec<_> = (0..out.len())
        .filter(|&i| out[i] < cap[i] && w[i] > 0.)
        .collect();
    order.sort_by(|&a, &b| {
        (expected[b] - out[b] as f64)
            .total_cmp(&(expected[a] - out[a] as f64))
            .then(a.cmp(&b))
    });
    if extra > order.len() as u64 {
        return Err(bad("apportionment remainder outside ledger"));
    }
    for &i in &order[..extra as usize] {
        out[i] += 1
    }
    if out.iter().sum::<u64>() != total {
        return Err(bad("apportionment ledger"));
    }
    Ok(out)
}
fn faces(r: &Roads) -> CoreResult<Vec<(Vec<usize>, f64)>> {
    let ids: BTreeMap<_, _> = r
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.id.as_str(), i))
        .collect();
    let p: Vec<_> = r.nodes.iter().map(|n| [n.xyz[0], n.xyz[1]]).collect();
    let mut adj = vec![Vec::new(); p.len()];
    for s in &r.sections {
        let a = ids[s.start.as_str()];
        let b = ids[s.end.as_str()];
        adj[a].push(b);
        adj[b].push(a);
    }
    for (u, ns) in adj.iter_mut().enumerate() {
        ns.sort_by(|&a, &b| {
            (p[a][1] - p[u][1])
                .atan2(p[a][0] - p[u][0])
                .total_cmp(&(p[b][1] - p[u][1]).atan2(p[b][0] - p[u][0]))
        });
        if ns.iter().collect::<BTreeSet<_>>().len() != ns.len() {
            return Err(bad("parallel face edge"));
        }
    }
    let mut seen = BTreeSet::new();
    let mut out = vec![];
    for a in 0..p.len() {
        for &b in &adj[a] {
            if seen.contains(&(a, b)) {
                continue;
            }
            let (mut u, mut v) = (a, b);
            let mut cycle = vec![];
            let mut closed = false;
            for _ in 0..=2 * r.sections.len() {
                if !seen.insert((u, v)) {
                    if (u, v) != (a, b) {
                        return Err(bad("half-edge walk not closed"));
                    }
                    closed = true;
                    break;
                }
                cycle.push(u);
                let i = adj[v]
                    .iter()
                    .position(|&n| n == u)
                    .ok_or_else(|| bad("missing reverse edge"))?;
                let j = (i + adj[v].len() - 1) % adj[v].len();
                (u, v) = (v, adj[v][j]);
            }
            if !closed {
                return Err(bad("half-edge walk budget"));
            }
            let area = 0.5
                * fsum(
                    cycle
                        .iter()
                        .zip(cycle.iter().cycle().skip(1))
                        .map(|(&a, &b)| p[a][0] * p[b][1] - p[b][0] * p[a][1]),
                );
            if area > 1e-5 {
                out.push((cycle, area))
            }
        }
    }
    if seen.len() != 2 * r.sections.len() {
        return Err(bad("half-edge census"));
    }
    let expected = r
        .sections
        .len()
        .checked_add(1)
        .and_then(|x| x.checked_sub(r.nodes.len()))
        .ok_or_else(|| bad("Euler ledger"))?;
    if expected != out.len() {
        return Err(bad(format!("Euler ledger {expected} != {}", out.len())));
    }
    Ok(out)
}
pub(crate) fn zoning(r: &Roads, kind: &str, l: f64, population: u64) -> CoreResult<Vec<Block>> {
    let faces = faces(r)?;
    let xy: Vec<_> = r.nodes.iter().map(|n| [n.xyz[0], n.xyz[1]]).collect();
    let port = if kind == "coast" {
        [0.43 * l, 0.20 * l]
    } else {
        [0.76 * l, 0.25 * l]
    };
    let nearest = |p: Point| {
        r.center_xy
            .iter()
            .map(|&c| dist(p, c))
            .fold(f64::INFINITY, f64::min)
    };
    let rows: Vec<(Block, Vec<Point>)> = faces
        .par_iter()
        .enumerate()
        .map(|(i, (cycle, area))| {
            let ps: Vec<_> = cycle.iter().map(|&k| xy[k]).collect();
            let per = fsum(edges(&ps).map(|(a, b)| dist(a, b)));
            let cross: Vec<_> = edges(&ps).map(|(a, b)| a[0] * b[1] - b[0] * a[1]).collect();
            let center: Point = std::array::from_fn(|k| {
                fsum(edges(&ps).zip(&cross).map(|((a, b), &v)| (a[k] + b[k]) * v)) / (6. * area)
            });
            let mut ok = cycle.iter().collect::<BTreeSet<_>>().len() == cycle.len()
                && *area >= 5000.
                && *area <= 180000.
                && 2. * area / per >= 20.;
            if ok {
                ok = polygon_clear(&ps, &r.land.water) && polygon_clear(&ps, &r.land.protected)
            }
            if ok {
                let t = &r.land.terrain;
                let b = bounds(&ps);
                let x0 = (b[0] / t.spacing_m) as usize;
                let x1 = ((b[2] / t.spacing_m).ceil() as usize).min(t.n);
                let y0 = (b[1] / t.spacing_m) as usize;
                let y1 = ((b[3] / t.spacing_m).ceil() as usize).min(t.n);
                ok = (x0..x1).all(|x| (y0..y1).all(|y| slope(t, x, y) <= 0.12));
            }
            let near = nearest(center);
            let u = if !ok {
                "open_space"
            } else if dist(center, port) < 0.085 * l {
                "industrial"
            } else if near < 0.10 * l {
                "mixed"
            } else if near < 0.15 * l && i % 5 == 0 {
                "commercial"
            } else {
                "residential"
            };
            (
                Block {
                    id: i.to_string(),
                    boundary: cycle.iter().map(|&k| r.nodes[k].id.clone()).collect(),
                    xy: center,
                    area_m2: *area,
                    perimeter_m: per,
                    r#use: u.into(),
                    housing_capacity: 0,
                    job_capacity: 0,
                    residents: 0,
                    jobs: 0,
                },
                ps,
            )
        })
        .collect();
    let industrial: Vec<_> = rows
        .iter()
        .filter(|(b, _)| b.r#use == "industrial")
        .map(|(_, p)| Region {
            points: p.clone(),
            bounds: bounds(p),
        })
        .collect();
    let mut blocks: Vec<_> = rows
        .into_par_iter()
        .map(|(mut b, p)| {
            if matches!(b.r#use.as_str(), "mixed" | "residential")
                && edges(&p).any(|(a, b)| !segment_clear(a, b, &industrial, 120.))
            {
                b.r#use = "buffer".into();
            }
            let (h, j) = match b.r#use.as_str() {
                "residential" => (170., 15.),
                "mixed" => (320., 250.),
                "commercial" => (0., 450.),
                "industrial" => (0., 140.),
                _ => (0., 0.),
            };
            let net = 0.65 * b.area_m2 / 10000.;
            b.housing_capacity = (net * h).floor() as u64;
            b.job_capacity = (net * j).floor() as u64;
            b
        })
        .collect();
    if blocks.is_empty() {
        return Ok(blocks);
    }
    let weights: Vec<_> = blocks
        .iter()
        .map(|b| (-nearest(b.xy) / (0.30 * l)).exp())
        .collect();
    let cap: Vec<_> = blocks.iter().map(|b| b.housing_capacity).collect();
    let jobs: Vec<_> = blocks.iter().map(|b| b.job_capacity).collect();
    let placed = population.min(cap.iter().sum());
    let employed = ((0.4 * population as f64).round_ties_even() as u64).min(jobs.iter().sum());
    let residents = apportion(
        placed,
        &cap,
        &cap.iter()
            .zip(&weights)
            .map(|(&c, &w)| c as f64 * w)
            .collect::<Vec<_>>(),
    )?;
    let employment = apportion(
        employed,
        &jobs,
        &jobs
            .iter()
            .zip(&weights)
            .map(|(&c, &w)| c as f64 * w)
            .collect::<Vec<_>>(),
    )?;
    for ((b, h), j) in blocks.iter_mut().zip(residents).zip(employment) {
        b.residents = h;
        b.jobs = j;
    }
    Ok(blocks)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn capped_stock_and_ties() {
        assert_eq!(
            apportion(10, &[2, 20, 20], &[100., 1., 1.]).unwrap(),
            [2, 4, 4]
        );
        assert_eq!(apportion(2, &[5, 5, 5], &[1., 1., 1.]).unwrap(), [1, 1, 0]);
        assert!(apportion(3, &[2, 2], &[1., 0.]).is_err())
    }
    #[test]
    fn face_stock_ledger() {
        let r = crate::atlas_roads::generate("planned", "flat", 8000., 42, 17).unwrap();
        let b = zoning(&r, "flat", 8000., 100000).unwrap();
        assert_eq!(b.len(), r.sections.len() + 1 - r.nodes.len());
        assert_eq!(b.iter().map(|b| b.residents).sum::<u64>(), 100000);
        assert!(b
            .iter()
            .all(|b| b.residents <= b.housing_capacity && b.jobs <= b.job_capacity));
    }
}
