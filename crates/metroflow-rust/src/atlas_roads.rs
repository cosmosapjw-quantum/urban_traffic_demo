//! Original admissible substrate -> bridge candidates -> positive-cost backbone
//! -> collector trees -> seeded infill -> fringe pruning. All graph states are
//! dense lexical ranks, independent candidate geometry is computed by Rayon.
use crate::{
    atlas_seed::{self, Mt},
    core_error::{CoreError, CoreResult},
    terrain_validation::{segment_clear, Landscape, Terrain},
    v1_area::{dist, Point},
};
use rayon::prelude::*;
use serde::Serialize;
use std::{
    cmp::Ordering,
    collections::{BTreeMap, BTreeSet, BinaryHeap},
    f64::consts::PI,
};
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
type P3 = [f64; 3];
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Road {
    pub id: String,
    pub start: String,
    pub end: String,
    pub points: Vec<P3>,
    pub hierarchy: String,
    pub facility: String,
    pub forward_lanes: u32,
    pub backward_lanes: u32,
    pub length_m: f64,
    pub max_grade: f64,
    pub failure_group: Option<String>,
    pub ramp_purpose: Option<String>,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Node {
    pub id: String,
    pub xyz: P3,
    pub layer: u32,
}
pub(crate) struct Roads {
    pub land: Landscape,
    pub nodes: Vec<Node>,
    pub sections: Vec<Road>,
    pub centers: Vec<String>,
    pub center_xy: Vec<Point>,
    pub rejected: BTreeMap<String, usize>,
    pub phases: Vec<(String, usize)>,
    pub bridge_candidates: usize,
    pub unserved_centers: usize,
    pub orbital_unreachable: usize,
    pub orbital_connectors: usize,
    pub removed: usize,
    pub gateways: Vec<String>,
}
pub(crate) fn ground(t: &Terrain, a: Point, b: Point) -> CoreResult<(Vec<P3>, f64, f64)> {
    let p = [a[0], a[1], t.elevation(a)?];
    let q = [b[0], b[1], t.elevation(b)?];
    let (length, grade) = t.ground_profile(&[p, q])?;
    let mut points = vec![];
    for w in t.cuts(a, b).windows(2) {
        for k in 0..8 {
            let u = w[0] + (w[1] - w[0]) * k as f64 / 8.;
            let xy = [a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1])];
            let z = t.elevation(xy)?;
            let x = [xy[0], xy[1], z];
            if points
                .last()
                .is_none_or(|r: &P3| (x[0] - r[0]).hypot(x[1] - r[1]).hypot(x[2] - r[2]) > 1e-9)
            {
                points.push(x);
            }
        }
    }
    points.push(q);
    Ok((points, length, grade))
}
fn deck(points: &[P3]) -> CoreResult<(f64, f64)> {
    let (mut length, mut grade) = (0., 0f64);
    for w in points.windows(2) {
        let a = w[0];
        let b = w[1];
        let d = (b[0] - a[0]).hypot(b[1] - a[1]);
        if d <= 1e-8 {
            return Err(bad("degenerate bridge"));
        }
        let z = b[2] - a[2];
        length += d.hypot(z);
        grade = grade.max(z.abs() / d);
    }
    Ok((length, grade))
}
#[derive(Clone, Copy)]
struct Heap(f64, f64, usize, usize);
impl PartialEq for Heap {
    fn eq(&self, o: &Self) -> bool {
        self.cmp(o) == Ordering::Equal
    }
}
impl Eq for Heap {}
impl Ord for Heap {
    fn cmp(&self, o: &Self) -> Ordering {
        o.0.total_cmp(&self.0)
            .then(o.1.total_cmp(&self.1))
            .then(o.2.cmp(&self.2))
            .then(o.3.cmp(&self.3))
    }
}
impl PartialOrd for Heap {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
type Adj = Vec<Vec<(usize, usize, f64)>>;
fn dijkstra(adj: &Adj, sources: &BTreeSet<usize>) -> (Vec<f64>, Vec<Option<(usize, usize)>>) {
    let mut d = vec![f64::INFINITY; adj.len()];
    let mut parent = vec![None; adj.len()];
    let mut heap = BinaryHeap::new();
    for &s in sources {
        d[s] = 0.;
        heap.push(Heap(0., 0., 0, s));
    }
    while let Some(Heap(value, _, _, u)) = heap.pop() {
        if value != d[u] {
            continue;
        }
        for &(v, e, w) in &adj[u] {
            let z = value + w;
            if z < d[v] {
                d[v] = z;
                parent[v] = Some((u, e));
                heap.push(Heap(z, 0., 0, v));
            }
        }
    }
    (d, parent)
}
fn walk(parent: &[Option<(usize, usize)>], mut u: usize) -> Vec<usize> {
    let mut r = vec![];
    while let Some((p, e)) = parent[u] {
        r.push(e);
        u = p;
    }
    r
}
fn route(adj: &Adj, xy: &[Point], a: usize, b: usize, pen: f64) -> Vec<usize> {
    if a == b {
        return vec![];
    }
    // Sentinel 0 precedes all real lexical ranks (rank+1) as Python's "".
    let mut d = BTreeMap::new();
    let mut parent = BTreeMap::new();
    let mut heap = BinaryHeap::new();
    let initial = (0, a);
    d.insert(initial, 0.);
    heap.push(Heap(dist(xy[a], xy[b]), 0., 0, a));
    while let Some(Heap(_, value, prev, u)) = heap.pop() {
        let state = (prev, u);
        if value != d[&state] {
            continue;
        }
        if u == b {
            let mut k = state;
            let mut result = vec![];
            while let Some(&(s, e)) = parent.get(&k) {
                result.push(e);
                k = s;
            }
            result.reverse();
            return result;
        }
        for &(v, e, cost) in &adj[u] {
            if prev == v + 1 {
                continue;
            }
            let mut bend = 0.;
            if prev > 0 {
                let p = xy[prev - 1];
                let q = xy[u];
                let r = xy[v];
                let x = [q[0] - p[0], q[1] - p[1]];
                let y = [r[0] - q[0], r[1] - q[1]];
                let c = (x[0] * y[0] + x[1] * y[1]) / (x[0].hypot(x[1]) * y[0].hypot(y[1]));
                bend = pen * (1. - c.clamp(-1., 1.));
            }
            let new = (u + 1, v);
            let alt = value + cost + bend;
            if alt < d.get(&new).copied().unwrap_or(f64::INFINITY) {
                d.insert(new, alt);
                parent.insert(new, (state, e));
                heap.push(Heap(alt + dist(xy[v], xy[b]), alt, new.0, new.1));
            }
        }
    }
    vec![]
}
fn nearest(xy: &[Point], ids: impl Iterator<Item = usize>, p: Point) -> CoreResult<usize> {
    ids.min_by(|&a, &b| dist(xy[a], p).total_cmp(&dist(xy[b], p)).then(a.cmp(&b)))
        .ok_or_else(|| bad("no feasible nearest node"))
}
pub(crate) fn generate(style: &str, kind: &str, l: f64, n: usize, seed: u64) -> CoreResult<Roads> {
    let land = atlas_seed::landscape(kind, l, seed)?;
    let mesh = atlas_seed::mesh(style, l, n, seed)?;
    let nominal = atlas_seed::centers(style, kind, l);
    let ids: Vec<_> = mesh.xy.keys().cloned().collect();
    let ranks: BTreeMap<_, _> = ids
        .iter()
        .enumerate()
        .map(|(i, s)| (s.as_str(), i))
        .collect();
    let xy: Vec<_> = ids.iter().map(|s| mesh.xy[s]).collect();
    let status: Vec<_> = xy
        .par_iter()
        .map(|&p| {
            if !segment_clear(p, p, &land.protected, 14.) {
                2
            } else if !segment_clear(p, p, &land.water, 14.) {
                1
            } else {
                0
            }
        })
        .collect();
    let pairs: Vec<_> = mesh
        .pairs
        .iter()
        .map(|(a, b)| (ranks[a.as_str()], ranks[b.as_str()]))
        .collect();
    let rows: Vec<CoreResult<(Option<Road>, Option<&str>)>> = pairs
        .par_iter()
        .map(|&(a, b)| {
            if status[a] != 0 || status[b] != 0 {
                return Ok((None, None));
            }
            if !segment_clear(xy[a], xy[b], &land.water, 14.)
                || !segment_clear(xy[a], xy[b], &land.protected, 14.)
            {
                return Ok((None, Some("footprint")));
            }
            let (pts, length, grade) = ground(&land.terrain, xy[a], xy[b])?;
            if grade > 0.08 {
                return Ok((None, Some("grade")));
            }
            Ok((
                Some(Road {
                    id: format!("s:{}>{}", ids[a], ids[b]),
                    start: ids[a].clone(),
                    end: ids[b].clone(),
                    points: pts,
                    hierarchy: "local".into(),
                    facility: "surface".into(),
                    forward_lanes: 1,
                    backward_lanes: 1,
                    length_m: length,
                    max_grade: grade,
                    failure_group: None,
                    ramp_purpose: None,
                }),
                None,
            ))
        })
        .collect();
    let mut adj: Adj = vec![vec![]; ids.len()];
    let mut roads = vec![];
    let mut endpoints = vec![];
    let mut rejected: BTreeMap<String, usize> = BTreeMap::new();
    fn insert(
        roads: &mut Vec<Road>,
        endpoints: &mut Vec<(usize, usize)>,
        adj: &mut Adj,
        r: Road,
        a: usize,
        b: usize,
        w: f64,
    ) {
        let e = roads.len();
        roads.push(r);
        endpoints.push((a, b));
        adj[a].push((b, e, w));
        adj[b].push((a, e, w));
    }
    for (row, &(a, b)) in rows.into_iter().zip(&pairs) {
        let (r, reason) = row?;
        if let Some(s) = reason {
            *rejected.entry(s.into()).or_default() += 1
        }
        if let Some(r) = r {
            let w = r.length_m * (1. + 5. * (r.max_grade / 0.08).powi(2));
            insert(&mut roads, &mut endpoints, &mut adj, r, a, b, w);
        }
    }
    let mut proposals: Vec<(f64, Road, Point, Vec<usize>)> = vec![];
    let mut seen = BTreeSet::new();
    for chain in &mesh.chains {
        let (mut left, mut middle): (Option<usize>, Vec<usize>) = (None, vec![]);
        for name in chain {
            let key = ranks[name.as_str()];
            match status[key] {
                0 => {
                    if let Some(a) = left {
                        if !middle.is_empty()
                            && a != key
                            && !adj[a].is_empty()
                            && !adj[key].is_empty()
                        {
                            let pair = (a.min(key), a.max(key));
                            if seen.insert(pair) {
                                let path: Vec<_> = std::iter::once(a)
                                    .chain(middle.iter().copied())
                                    .chain(std::iter::once(key))
                                    .collect();
                                let ps: Vec<_> = path.iter().map(|&k| xy[k]).collect();
                                let mut run = vec![0.];
                                for w in ps.windows(2) {
                                    run.push(run.last().unwrap() + dist(w[0], w[1]));
                                }
                                let len = *run.last().unwrap();
                                if len > 40.
                                    && len < 900.
                                    && len / dist(xy[a], xy[key]) < 1.12
                                    && ps
                                        .windows(2)
                                        .all(|w| segment_clear(w[0], w[1], &land.protected, 14.))
                                {
                                    let za = land.terrain.elevation(ps[0])?;
                                    let zb = land.terrain.elevation(*ps.last().unwrap())?;
                                    let mut pts: Vec<_> = ps
                                        .iter()
                                        .zip(&run)
                                        .map(|(p, &d)| {
                                            [
                                                p[0],
                                                p[1],
                                                za + (zb - za) * d / len
                                                    + 8. * (PI * d / len).sin(),
                                            ]
                                        })
                                        .collect();
                                    let last = pts.len() - 1;
                                    pts[0][2] = za;
                                    pts[last][2] = zb;
                                    let (length, grade) = deck(&pts)?;
                                    if grade <= 0.08 && land.terrain.ground_gap(&pts)? >= -1e-7 {
                                        let mid = ps[ps.len() / 2];
                                        let score = length * 4.
                                            + 0.4
                                                * nominal
                                                    .iter()
                                                    .map(|&c| dist(mid, c))
                                                    .fold(f64::INFINITY, f64::min);
                                        proposals.push((
                                            score,
                                            Road {
                                                id: format!("b:{}>{}", ids[pair.0], ids[pair.1]),
                                                start: ids[a].clone(),
                                                end: ids[key].clone(),
                                                points: pts,
                                                hierarchy: "arterial".into(),
                                                facility: "bridge".into(),
                                                forward_lanes: 2,
                                                backward_lanes: 2,
                                                length_m: length,
                                                max_grade: grade,
                                                failure_group: Some(format!(
                                                    "bridge:{}",
                                                    proposals.len()
                                                )),
                                                ramp_purpose: None,
                                            },
                                            mid,
                                            path,
                                        ));
                                    }
                                }
                            }
                        }
                    }
                    left = Some(key);
                    middle.clear();
                }
                1 if left.is_some() => middle.push(key),
                _ => {
                    left = None;
                    middle.clear();
                }
            }
        }
    }
    let bridge_candidates = proposals.len();
    proposals.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.id.cmp(&b.1.id)));
    let mut occupied = BTreeSet::new();
    let mut mids = vec![];
    for (_, r, mid, path) in proposals {
        if mids.len() >= 3 {
            break;
        }
        if path.iter().any(|k| occupied.contains(k))
            || mids.iter().any(|&p| dist(mid, p) < 0.13 * l)
        {
            continue;
        }
        occupied.extend(path);
        mids.push(mid);
        let (a, b) = (ranks[r.start.as_str()], ranks[r.end.as_str()]);
        let w = r.length_m * 4.;
        insert(&mut roads, &mut endpoints, &mut adj, r, a, b, w);
    }
    let mut centers = vec![];
    for p in nominal {
        let k = nearest(&xy, (0..xy.len()).filter(|&i| !adj[i].is_empty()), p)?;
        if !centers.contains(&k) {
            centers.push(k)
        }
    }
    let (root_dist, parent) = dijkstra(&adj, &BTreeSet::from([centers[0]]));
    let n_centers = centers.len();
    centers.retain(|&k| root_dist[k].is_finite());
    let unserved_centers = n_centers - centers.len();
    let gateways = [
        [0.08 * l, 0.5 * l],
        [0.92 * l, 0.5 * l],
        [0.5 * l, 0.08 * l],
        [0.5 * l, 0.92 * l],
    ]
    .into_iter()
    .map(|p| nearest(&xy, (0..xy.len()).filter(|&i| root_dist[i].is_finite()), p))
    .collect::<CoreResult<Vec<_>>>()?;
    let requests: Vec<_> = centers[1..]
        .iter()
        .chain(&gateways)
        .map(|&b| (centers[0], b))
        .chain(centers.windows(2).map(|w| (w[0], w[1])))
        .collect();
    let paths: Vec<_> = requests
        .par_iter()
        .map(|&(a, b)| route(&adj, &xy, a, b, 2. * l / n as f64))
        .collect();
    let mut arterial: BTreeSet<_> = paths.into_iter().flatten().collect();
    let (mut orbital_unreachable, mut orbital_connectors) = (0, 0);
    if style == "radial" {
        let prefix = format!("r{}:", (0.23 * n as f64).round_ties_even() as usize);
        let mut orbit = vec![];
        let mut oa: Vec<Vec<usize>> = vec![vec![]; xy.len()];
        for (e, r) in roads.iter().enumerate() {
            if r.facility == "surface" && r.start.starts_with(&prefix) && r.end.starts_with(&prefix)
            {
                let (a, b) = endpoints[e];
                if root_dist[a].is_finite() && root_dist[b].is_finite() {
                    orbit.push(e);
                    oa[a].push(b);
                    oa[b].push(a);
                } else {
                    orbital_unreachable += 1
                }
            }
        }
        let mut seen = BTreeSet::new();
        for start in 0..xy.len() {
            if oa[start].is_empty() || !seen.insert(start) {
                continue;
            }
            let mut group = vec![];
            let mut stack = vec![start];
            while let Some(u) = stack.pop() {
                group.push(u);
                for &v in &oa[u] {
                    if seen.insert(v) {
                        stack.push(v)
                    }
                }
            }
            let entry = *group
                .iter()
                .min_by(|&&a, &&b| root_dist[a].total_cmp(&root_dist[b]).then(a.cmp(&b)))
                .unwrap();
            arterial.extend(walk(&parent, entry));
            orbital_connectors += 1;
        }
        arterial.extend(orbit);
    }
    let mut trunks: BTreeSet<_> = arterial
        .iter()
        .flat_map(|&e| [endpoints[e].0, endpoints[e].1])
        .collect();
    if trunks.is_empty() {
        trunks.insert(centers[0]);
    }
    let (access, previous) = dijkstra(&adj, &trunks);
    let center_xy: Vec<_> = centers.iter().map(|&k| xy[k]).collect();
    let intensity = |p: Point| {
        center_xy
            .iter()
            .map(|c| {
                if style == "corridor" {
                    (-((p[0] - c[0]) / (0.24 * l)).powi(2) - ((p[1] - c[1]) / (0.13 * l)).powi(2))
                        .exp()
                } else {
                    let r = if style == "planned" {
                        0.31
                    } else if style == "radial" {
                        0.30
                    } else {
                        0.235
                    } * l;
                    (-(dist(p, *c) / r).powi(2)).exp()
                }
            })
            .fold(0., f64::max)
    };
    let target: Vec<_> = xy
        .par_iter()
        .zip(&access)
        .map(|(&p, &a)| a.is_finite() && intensity(p) >= 0.24)
        .collect();
    let nt = target.iter().filter(|&&x| x).count();
    let mut selected = arterial.clone();
    let mut flow: Vec<_> = target.iter().map(|&x| usize::from(x)).collect();
    let mut order: Vec<_> = (0..xy.len()).filter(|&i| access[i].is_finite()).collect();
    order.sort_by(|&a, &b| access[b].total_cmp(&access[a]).then(a.cmp(&b)));
    for k in order {
        if flow[k] > 0 {
            if let Some((p, e)) = previous[k] {
                selected.insert(e);
                flow[p] += flow[k]
            }
        }
    }
    let mut phases: BTreeMap<_, _> = selected
        .iter()
        .map(|&e| (e, usize::from(!arterial.contains(&e))))
        .collect();
    let mut rng = Mt::new(seed.checked_add(1701).ok_or_else(|| bad("seed overflow"))?);
    let prob = match style {
        "planned" => 0.92,
        "polycentric" => 0.68,
        "radial" => 0.85,
        _ => 0.52,
    };
    let mut sorted: Vec<_> = (0..roads.len()).collect();
    sorted.sort_by(|&a, &b| roads[a].id.cmp(&roads[b].id));
    for &e in &sorted {
        let (a, b) = endpoints[e];
        if roads[e].facility != "bridge" && target[a] && target[b] && rng.random() < prob {
            selected.insert(e);
            phases.entry(e).or_insert(2);
        }
    }
    let mut incident: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); xy.len()];
    for &e in &selected {
        let (a, b) = endpoints[e];
        incident[a].insert(e);
        incident[b].insert(e);
    }
    let protected: BTreeSet<_> = centers.iter().chain(&gateways).copied().collect();
    let mut todo: Vec<_> = (0..xy.len())
        .filter(|&k| incident[k].len() == 1 && !protected.contains(&k))
        .collect();
    let mut removed = 0;
    while let Some(u) = todo.pop() {
        if incident[u].len() != 1 {
            continue;
        }
        let e = *incident[u].iter().next().unwrap();
        if arterial.contains(&e) {
            continue;
        }
        let (a, b) = endpoints[e];
        let v = if a == u { b } else { a };
        selected.remove(&e);
        phases.remove(&e);
        removed += 1;
        incident[u].remove(&e);
        incident[v].remove(&e);
        if incident[v].len() == 1 && !protected.contains(&v) {
            todo.push(v)
        }
    }
    let mut sections = vec![];
    let mut used = BTreeSet::new();
    for e in sorted {
        if !selected.contains(&e) {
            continue;
        }
        let mut r = roads[e].clone();
        let (a, b) = endpoints[e];
        let h = if arterial.contains(&e) || r.facility == "bridge" {
            "arterial"
        } else if flow[a].max(flow[b]) >= 4usize.max(nt / 150) && phases[&e] == 1 {
            "collector"
        } else {
            "local"
        };
        r.hierarchy = h.into();
        r.forward_lanes = if h == "arterial" { 2 } else { 1 };
        r.backward_lanes = r.forward_lanes;
        sections.push(r);
        used.extend([a, b]);
    }
    let nodes = used
        .into_iter()
        .map(|i| {
            Ok(Node {
                id: ids[i].clone(),
                xyz: [xy[i][0], xy[i][1], land.terrain.elevation(xy[i])?],
                layer: 0,
            })
        })
        .collect::<CoreResult<Vec<_>>>()?;
    let mut phase_rows: Vec<_> = phases
        .into_iter()
        .map(|(i, p)| (roads[i].id.clone(), p))
        .collect();
    phase_rows.sort();
    Ok(Roads {
        land,
        nodes,
        sections,
        centers: centers.into_iter().map(|i| ids[i].clone()).collect(),
        center_xy,
        rejected,
        phases: phase_rows,
        bridge_candidates,
        unserved_centers,
        orbital_unreachable,
        orbital_connectors,
        removed,
        gateways: gateways.into_iter().map(|i| ids[i].clone()).collect(),
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn small_connected_roads() {
        let r = generate("planned", "flat", 8000., 12, 17).unwrap();
        assert!(r.sections.len() >= r.nodes.len() - 1);
        assert!(r.sections.iter().all(|s| s.max_grade <= 0.08));
        assert_eq!(r.sections.len(), r.phases.len());
    }
}
