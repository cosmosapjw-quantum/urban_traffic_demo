//! Typed preparation boundary. UI may supply these declarations, but numerical
//! coupling, route validation, passage solving and expansion are Rust-owned.
use crate::{
    access::{self, Atom, Coupled},
    input::{Group, Input, Result, Road},
    kinetics::{self, Geometry, Kinetics},
};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Write,
};
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RoadDecl {
    pub length_m: f64,
    pub cap_mps: f64,
    pub entry_veh_s: f64,
    pub exit_veh_s: f64,
    pub storage_m: f64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CohortDecl {
    pub forward: u32,
    pub backward: Option<u32>,
    pub purpose: u32,
    pub mass: f64,
    pub origin_law: u32,
    pub destination_law: u32,
    pub class: u8,
    pub phase_group: u32,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Manifest {
    pub schema: String,
    pub dwell_s: f64,
    pub roads: Vec<RoadDecl>,
    pub allowed_turns: Vec<(u32, u32)>,
    pub paths: Vec<Vec<u32>>,
    pub windows: Vec<[f64; 4]>,
    pub laws: Vec<Vec<Atom>>,
    pub cohorts: Vec<CohortDecl>,
    pub kinetics: Kinetics,
    pub max_expanded_groups: usize,
}
#[derive(Debug, Serialize)]
pub struct PrepReport {
    pub input_cohorts: usize,
    pub expanded_groups: usize,
    pub distinct_law_pairs: usize,
    pub max_group_mass_error: f64,
}
fn valid_pos(x: f64) -> bool {
    x.is_finite() && x > 0.
}
pub fn prepare(m: Manifest) -> Result<(Input, PrepReport)> {
    if m.schema != "metroflow_access_declarations_v1"
        || m.roads.is_empty()
        || m.paths.is_empty()
        || m.windows.is_empty()
        || m.max_expanded_groups == 0
        || !m.dwell_s.is_finite()
        || m.dwell_s < 0.
        || m.roads.len() >= u32::MAX as usize
        || m.paths.len() >= u32::MAX as usize
        || m.windows.len() >= u32::MAX as usize
    {
        return Err("invalid declared input".into());
    }
    if m.roads.iter().any(|r| {
        ![
            r.length_m,
            r.cap_mps,
            r.entry_veh_s,
            r.exit_veh_s,
            r.storage_m,
        ]
        .iter()
        .copied()
        .all(valid_pos)
    }) {
        return Err("invalid road declaration".into());
    }
    if m.windows.iter().any(|w| {
        w.iter().any(|x| !x.is_finite() || *x < 0. || *x > 86400.) || w[0] > w[1] || w[2] > w[3]
    }) {
        return Err("invalid departure profile".into());
    }
    let turns: BTreeSet<_> = m.allowed_turns.into_iter().collect();
    if turns
        .iter()
        .any(|&(a, b)| a as usize >= m.roads.len() || b as usize >= m.roads.len() || a == b)
    {
        return Err("invalid turn registry".into());
    }
    for p in &m.paths {
        if p.is_empty()
            || p.len() > u16::MAX as usize
            || p.iter().any(|&x| x as usize >= m.roads.len())
            || p.windows(2).any(|x| !turns.contains(&(x[0], x[1])))
        {
            return Err("illegal path".into());
        }
    }
    let mut pairs = BTreeSet::new();
    for g in &m.cohorts {
        if g.forward as usize >= m.paths.len()
            || g.backward.is_some_and(|x| x as usize >= m.paths.len())
            || g.purpose as usize >= m.windows.len()
            || g.class >= 3
            || !valid_pos(g.mass)
            || g.origin_law as usize >= m.laws.len()
            || g.destination_law as usize >= m.laws.len()
            || g.backward.is_some()
                && m.windows[g.purpose as usize][2] >= m.windows[g.purpose as usize][3]
        {
            return Err("invalid cohort declaration".into());
        }
        pairs.insert((g.origin_law, g.destination_law));
    }
    let pairs: Vec<_> = pairs.into_iter().collect();
    let cache_values: Vec<Result<Vec<Coupled>>> = pairs
        .par_iter()
        .map(|&(a, b)| access::couple(&m.laws[a as usize], &m.laws[b as usize]))
        .collect();
    let mut cache = BTreeMap::new();
    for (pair, v) in pairs.iter().copied().zip(cache_values) {
        cache.insert(pair, v?);
    }
    let n = m.cohorts.iter().try_fold(0usize, |n, g| {
        n.checked_add(cache[&(g.origin_law, g.destination_law)].len())
            .ok_or("expanded groups overflow")
    })?;
    if n > m.max_expanded_groups || n >= u32::MAX as usize {
        return Err("expanded group budget exceeded".into());
    }
    let mut groups = Vec::new();
    groups
        .try_reserve_exact(n)
        .map_err(|_| "expanded group allocation failed")?;
    let mut error = 0f64;
    for g in &m.cohorts {
        let start = groups.len();
        let mut mass = 0.;
        for a in &cache[&(g.origin_law, g.destination_law)] {
            let v = g.mass * a.weight;
            if !valid_pos(v) {
                return Err("expanded group mass underflow".into());
            }
            mass += v;
            groups.push(Group {
                forward: g.forward,
                backward: g.backward,
                purpose: g.purpose,
                mass: v,
                origin: a.origin_s,
                destination: a.destination_s,
                class: g.class,
                phase_group: g.phase_group,
            });
        }
        error = error.max((mass - g.mass).abs());
        if (mass - g.mass).abs() > 1e-12 * g.mass.max(1.) || groups.len() == start {
            return Err("expanded mass mismatch".into());
        }
    }
    let geometry: Vec<_> = m
        .roads
        .iter()
        .map(|r| Geometry {
            length_m: r.length_m,
            cap_mps: r.cap_mps,
        })
        .collect();
    let passage = kinetics::route_passages(&m.paths, &geometry, m.kinetics)?;
    let roads = m
        .roads
        .iter()
        .map(|r| Road {
            travel: r.length_m / r.cap_mps.min(m.kinetics.preferred_mps),
            entry: r.entry_veh_s,
            exit: r.exit_veh_s,
            storage: r.storage_m,
        })
        .collect();
    let report = PrepReport {
        input_cohorts: m.cohorts.len(),
        expanded_groups: n,
        distinct_law_pairs: pairs.len(),
        max_group_mass_error: error,
    };
    Ok((
        Input {
            roads,
            paths: m.paths,
            passage,
            windows: m.windows,
            groups,
            dwell: m.dwell_s,
        },
        report,
    ))
}
pub fn write_input(input: &Input, mut n: impl Write, mut p: impl Write) -> std::io::Result<()> {
    writeln!(
        n,
        "{} {} {} {} {}",
        input.roads.len(),
        input.paths.len(),
        input.groups.len(),
        input.windows.len(),
        input.dwell
    )?;
    for r in &input.roads {
        writeln!(n, "{} {} {} {}", r.travel, r.entry, r.exit, r.storage)?;
    }
    for route in &input.paths {
        write!(n, "{}", route.len())?;
        for e in route {
            write!(n, " {e}")?;
        }
        writeln!(n)?;
    }
    for w in &input.windows {
        writeln!(n, "{} {} {} {}", w[0], w[1], w[2], w[3])?;
    }
    for g in &input.groups {
        writeln!(
            n,
            "{} {} {} {} {} {} {} {}",
            g.forward,
            g.backward.map_or(-1, |x| x as i64),
            g.purpose,
            g.mass,
            g.origin,
            g.destination,
            g.class,
            g.phase_group
        )?;
    }
    writeln!(p, "{}", input.passage.len())?;
    for row in &input.passage {
        write!(p, "{}", row.len())?;
        for x in row {
            write!(p, " {x}")?;
        }
        writeln!(p)?;
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn typed_fixture_roundtrip_and_budget() {
        let manifest =
            serde_json::from_str::<Manifest>(include_str!("../fixtures/access_declarations.json"))
                .unwrap();
        let (x, r) = prepare(manifest.clone()).unwrap();
        assert_eq!(r.input_cohorts, 3);
        assert_eq!(r.expanded_groups, 5);
        let (mut a, mut b) = (Vec::new(), Vec::new());
        write_input(&x, &mut a, &mut b).unwrap();
        let y = Input::parse(
            std::str::from_utf8(&a).unwrap(),
            std::str::from_utf8(&b).unwrap(),
        )
        .unwrap();
        assert_eq!(x.passage, y.passage);
        assert_eq!(x.groups.len(), y.groups.len());
        let mut m = manifest;
        m.max_expanded_groups = 4;
        assert!(prepare(m).is_err());
    }
}
