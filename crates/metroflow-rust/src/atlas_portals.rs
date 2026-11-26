//! Original selected legal-turn SCC and geometrically ordered synthetic entry.
use crate::{
    atlas_roads::ground,
    core_error::{CoreError, CoreResult},
    frozen_city::City,
    terrain_validation::{segment_clear, Landscape},
    v1_area::{canonical, segment_inside, triangulate, Point},
    v1_journey::fsum,
};
use rayon::prelude::*;
use serde::Serialize;
use std::{
    cmp::Ordering,
    collections::{BTreeMap, BTreeSet},
};
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
type P3 = [f64; 3];
fn cmp3(a: &P3, b: &P3) -> Ordering {
    a.iter()
        .zip(b)
        .map(|(a, b)| a.total_cmp(b))
        .find(|x| *x != Ordering::Equal)
        .unwrap_or(Ordering::Equal)
}
fn cmp2(a: &Point, b: &Point) -> Ordering {
    a[0].total_cmp(&b[0]).then(a[1].total_cmp(&b[1]))
}
fn backbone(c: &City) -> CoreResult<Vec<usize>> {
    let ids: BTreeMap<_, _> = c
        .links
        .iter()
        .enumerate()
        .map(|(i, l)| (l.id.as_str(), i))
        .collect();
    let n = ids.len();
    let mut f = vec![vec![]; n];
    let mut r = vec![vec![]; n];
    for (a, b) in &c.turns {
        let (i, j) = (ids[a.as_str()], ids[b.as_str()]);
        f[i].push(j);
        r[j].push(i);
    }
    let mut seen = vec![false; n];
    let mut order = vec![];
    for start in 0..n {
        if seen[start] {
            continue;
        }
        seen[start] = true;
        let mut stack = vec![(start, 0)];
        while let Some((u, k)) = stack.last_mut() {
            if *k == f[*u].len() {
                order.push(*u);
                stack.pop();
                continue;
            }
            let v = f[*u][*k];
            *k += 1;
            if !seen[v] {
                seen[v] = true;
                stack.push((v, 0));
            }
        }
    }
    let mut groups = vec![];
    seen.fill(false);
    for start in order.into_iter().rev() {
        if seen[start] {
            continue;
        }
        seen[start] = true;
        let mut s = vec![start];
        let mut g = vec![];
        while let Some(u) = s.pop() {
            g.push(u);
            for &v in &r[u] {
                if !seen[v] {
                    seen[v] = true;
                    s.push(v)
                }
            }
        }
        groups.push(g);
    }
    let geometry = |g: &Vec<usize>| {
        let mut p: Vec<_> = g
            .iter()
            .map(|&i| {
                let l = &c.links[i];
                (c.nodes[&l.tail].xyz, c.nodes[&l.head].xyz)
            })
            .collect();
        p.sort_by(|a, b| cmp3(&a.0, &b.0).then(cmp3(&a.1, &b.1)));
        p
    };
    groups.sort_by(|a, b| {
        b.len().cmp(&a.len()).then_with(|| {
            geometry(a)
                .iter()
                .zip(geometry(b))
                .map(|(x, y)| cmp3(&x.0, &y.0).then(cmp3(&x.1, &y.1)))
                .find(|x| *x != Ordering::Equal)
                .unwrap_or(Ordering::Equal)
        })
    });
    groups
        .into_iter()
        .next()
        .ok_or_else(|| bad("no legal-turn SCC"))
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Entry {
    pub id: String,
    pub block_id: String,
    pub node_id: String,
    pub corridor: [Point; 2],
    pub construction_length_m: f64,
    pub maximum_grade: f64,
    pub capacity_veh_s: f64,
    pub departure_link: String,
    pub arrival_link: String,
}
pub(crate) fn generate(c: &City, land: &Landscape) -> CoreResult<(Vec<Entry>, usize)> {
    if !c.portals.is_empty() {
        return Err(bad("portal-free source required"));
    }
    let backbone = backbone(c)?;
    let mut out: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    let mut inc: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for &i in &backbone {
        let l = &c.links[i];
        out.entry(&l.tail).or_default().push(&l.id);
        inc.entry(&l.head).or_default().push(&l.id);
    }
    for r in out.values_mut().chain(inc.values_mut()) {
        r.sort_unstable();
    }
    let active: Vec<_> = c
        .blocks
        .iter()
        .filter(|b| b.residents > 0 || b.jobs > 0)
        .collect();
    let rows: Vec<CoreResult<Option<Entry>>> = active
        .par_iter()
        .map(|b| {
            let poly = canonical(
                b.boundary
                    .iter()
                    .map(|n| {
                        let p = c.nodes[n].xyz;
                        [p[0], p[1]]
                    })
                    .collect(),
            )?;
            let triangles = triangulate(poly.clone())?;
            let mut choices = vec![];
            for n in &b.boundary {
                let p = c.nodes[n].xyz;
                let xy = [p[0], p[1]];
                if !out.contains_key(n.as_str()) || !inc.contains_key(n.as_str()) {
                    continue;
                }
                for tri in &triangles {
                    if !tri.contains(&xy) {
                        continue;
                    }
                    let center = std::array::from_fn(|i| fsum(tri.iter().map(|p| p[i])) / 3.);
                    if !segment_inside(center, xy, &poly)
                        || !segment_clear(center, xy, &land.water, 2.)
                        || !segment_clear(center, xy, &land.protected, 2.)
                    {
                        continue;
                    }
                    let (_, len, grade) = ground(&land.terrain, center, xy)?;
                    if len <= 0. || grade > 0.12 {
                        continue;
                    }
                    choices.push(Entry {
                        id: format!("new:{}:{n}", b.id),
                        block_id: b.id.clone(),
                        node_id: n.clone(),
                        corridor: [center, xy],
                        construction_length_m: len,
                        maximum_grade: grade,
                        capacity_veh_s: 1.,
                        departure_link: out[n.as_str()][0].to_owned(),
                        arrival_link: inc[n.as_str()][0].to_owned(),
                    });
                    break;
                }
            }
            choices.sort_by(|a, b| {
                cmp2(&a.corridor[1], &b.corridor[1]).then(cmp2(&a.corridor[0], &b.corridor[0]))
            });
            Ok(choices.into_iter().next())
        })
        .collect();
    let mut entries = vec![];
    for r in rows {
        if let Some(e) = r? {
            entries.push(e)
        }
    }
    entries.sort_by(|a, b| a.id.cmp(&b.id));
    Ok((entries, backbone.len()))
}
