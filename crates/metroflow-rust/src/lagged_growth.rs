//! M04 completed spatial accessibility and slow-epoch resident/capacity ledger.
//! Explicit entry declarations have to be supplied by a physical map compiler.
use crate::{
    causal::Observation,
    core_error::{CoreError, CoreResult},
    frozen_city::hash,
    v1_journey::fsum,
};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
fn bad(s: &str) -> CoreError {
    CoreError::value(s)
}
fn digest<T: Serialize>(x: &T) -> CoreResult<String> {
    serde_json::to_vec(x)
        .map(|v| hash(&v))
        .map_err(|e| CoreError::value(e.to_string()))
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Accessibility {
    pub city_identity: String,
    pub stamp_s: f64,
    pub costs: Vec<(String, f64)>,
    pub source_version: String,
}
pub fn compile_accessibility(
    city: &str,
    rows: &[(String, Observation)],
    epoch: f64,
) -> CoreResult<Accessibility> {
    if city.is_empty() || !epoch.is_finite() || epoch < 0. {
        return Err(bad("invalid completed epoch"));
    }
    let mut groups: BTreeMap<&str, Vec<&Observation>> = BTreeMap::new();
    let mut versions = vec![];
    for (block, o) in rows {
        o.validate()?;
        if block.is_empty()
            || o.stamp_s > epoch
            || o.end_s > epoch
            || !o.source.starts_with("T04_completed") && !o.source.starts_with("completed_")
        {
            return Err(bad("realized completed observations required"));
        }
        groups.entry(block).or_default().push(o);
        versions.push((&o.version, &o.population));
    }
    versions.sort();
    let groups: Vec<_> = groups.into_iter().collect();
    let costs: Vec<_> = groups
        .par_iter()
        .map(|(block, rs)| {
            let mass = fsum(rs.iter().map(|r| r.mass_veh));
            let elapsed = fsum(rs.iter().map(|r| r.mass_veh * r.seconds));
            if !mass.is_finite() || mass <= 0. || elapsed.is_nan() || elapsed < 0. {
                return Err(CoreError::arithmetic("accessibility moment overflow"));
            }
            Ok((block.to_string(), elapsed / mass))
        })
        .collect::<CoreResult<_>>()?;
    Ok(Accessibility {
        city_identity: city.into(),
        stamp_s: epoch,
        costs,
        source_version: digest(&versions)?,
    })
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Block {
    pub id: String,
    pub residents: u64,
    pub housing_capacity: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Entry {
    pub id: String,
    pub block: String,
    pub city_identity: String,
    pub node: String,
    pub construction_length_m: f64,
    pub capacity_veh_s: f64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Site {
    pub block: String,
    pub entry_id: String,
    pub added_capacity: u64,
    pub priority: i64,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Move {
    pub origin: String,
    pub destination: String,
    pub persons: u64,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct GrowthState {
    model: String,
    pub epoch_s: f64,
    pub allocations: Vec<u64>,
    pub added: Vec<u64>,
    pub built: Vec<bool>,
    pub original_residents: u64,
    pub requested_increment: u64,
    pub pending_increment: u64,
    pub construction_m: f64,
    pub moves: Vec<Move>,
    pub consumed_access_stamp_s: f64,
    pub status: String,
}
pub struct Growth {
    pub id: String,
    city: String,
    blocks: Vec<Block>,
    index: BTreeMap<String, usize>,
    sites: Vec<(usize, u64, f64, i64)>,
    budget: f64,
    slow: f64,
    max_access: f64,
    original: u64,
}
fn add(a: u64, b: u64) -> CoreResult<u64> {
    a.checked_add(b)
        .ok_or_else(|| CoreError::arithmetic("resident ledger overflow"))
}
impl Growth {
    // Entry registry is the *validated* upstream contract. No synthetic road,
    // mask, or geometric feasibility claim is manufactured here.
    pub fn new(
        city: &str,
        mut blocks: Vec<Block>,
        entries: Vec<Entry>,
        sites: Vec<Site>,
        budget: f64,
        slow: f64,
        max_access: f64,
    ) -> CoreResult<Self> {
        if city.is_empty()
            || !budget.is_finite()
            || budget < 0.
            || !slow.is_finite()
            || slow <= 0.
            || !max_access.is_finite()
            || max_access < 0.
            || blocks.is_empty()
            || sites.len() > 1000
        {
            return Err(bad("growth policy"));
        }
        blocks.sort_by(|a, b| a.id.cmp(&b.id));
        let index: BTreeMap<_, _> = blocks
            .iter()
            .enumerate()
            .map(|(i, b)| (b.id.clone(), i))
            .collect();
        if index.len() != blocks.len()
            || blocks
                .iter()
                .any(|b| b.id.is_empty() || b.residents > b.housing_capacity)
        {
            return Err(bad("block capacity"));
        }
        let original = blocks.iter().try_fold(0, |x, b| add(x, b.residents))?;
        let es: BTreeMap<_, _> = entries.iter().map(|e| (&e.id, e)).collect();
        if es.len() != entries.len()
            || entries.iter().any(|e| {
                e.id.is_empty()
                    || e.city_identity != city
                    || e.node.is_empty()
                    || !index.contains_key(&e.block)
                    || !e.construction_length_m.is_finite()
                    || e.construction_length_m < 0.
                    || !e.capacity_veh_s.is_finite()
                    || e.capacity_veh_s <= 0.
            })
        {
            return Err(bad("invalid declared entry registry"));
        }
        let mut registry = vec![];
        let mut ranks = BTreeSet::new();
        let mut used = BTreeSet::new();
        for s in &sites {
            let i = *index.get(&s.block).ok_or_else(|| bad("unknown site"))?;
            let e = es
                .get(&s.entry_id)
                .ok_or_else(|| bad("site entry missing"))?;
            if e.block != s.block
                || s.added_capacity == 0
                || !ranks.insert(s.priority)
                || !used.insert(i)
            {
                return Err(bad("invalid site"));
            }
            registry.push((i, s.added_capacity, e.construction_length_m, s.priority));
        }
        registry.sort_by(|a, b| b.3.cmp(&a.3));
        let id = digest(&(
            "M04_native_v1",
            city,
            &blocks,
            &entries,
            &sites,
            budget,
            slow,
            max_access,
        ))?;
        Ok(Self {
            id,
            city: city.into(),
            blocks,
            index,
            sites: registry,
            budget,
            slow,
            max_access,
            original,
        })
    }
    pub fn initial(&self) -> GrowthState {
        let n = self.blocks.len();
        GrowthState {
            model: self.id.clone(),
            epoch_s: 0.,
            allocations: self.blocks.iter().map(|b| b.residents).collect(),
            added: vec![0; n],
            built: vec![false; n],
            original_residents: self.original,
            requested_increment: 0,
            pending_increment: 0,
            construction_m: 0.,
            moves: vec![],
            consumed_access_stamp_s: -1.,
            status: "INITIAL".into(),
        }
    }
    pub fn check(&self, s: &GrowthState) -> CoreResult<()> {
        let n = self.blocks.len();
        if s.model != self.id
            || s.allocations.len() != n
            || s.added.len() != n
            || s.built.len() != n
            || s.original_residents != self.original
            || !s.epoch_s.is_finite()
            || s.epoch_s < 0.
            || !s.construction_m.is_finite()
            || s.construction_m < 0.
            || s.construction_m > self.budget + 1e-9
        {
            return Err(bad("growth state binding"));
        }
        let mut expected = vec![0; n];
        for &(i, c, _, _) in &self.sites {
            if s.built[i] {
                expected[i] = c;
            }
        }
        if s.added != expected
            || s.built
                .iter()
                .enumerate()
                .any(|(i, b)| *b && expected[i] == 0)
        {
            return Err(bad("construction registry mismatch"));
        }
        for (i, b) in self.blocks.iter().enumerate() {
            if s.allocations[i] > add(b.housing_capacity, s.added[i])? {
                return Err(bad("resident capacity exceeded"));
            }
        }
        if add(
            s.allocations.iter().try_fold(0, |x, &a| add(x, a))?,
            s.pending_increment,
        )? != add(self.original, s.requested_increment)?
        {
            return Err(bad("resident ledger failure"));
        }
        Ok(())
    }
    pub fn materialized_identity(&self, s: &GrowthState) -> CoreResult<String> {
        self.check(s)?;
        if s.requested_increment == 0 && s.moves.is_empty() && s.built.iter().all(|x| !*x) {
            return Ok(self.city.clone());
        }
        digest(&(
            "M04_next_city_stock_v1",
            &self.city,
            &s.allocations,
            &s.added,
            s.requested_increment,
            s.pending_increment,
        ))
    }
    pub fn advance(
        &self,
        s: &GrowthState,
        o: &Accessibility,
        now: f64,
        increment: u64,
        moves: &[Move],
    ) -> CoreResult<GrowthState> {
        self.check(s)?;
        if !now.is_finite()
            || now != s.epoch_s + self.slow
            || o.city_identity != self.materialized_identity(s)?
            || !o.stamp_s.is_finite()
            || o.stamp_s < 0.
            || o.stamp_s >= now
            || o.stamp_s <= s.consumed_access_stamp_s
            || o.source_version.is_empty()
        {
            return Err(bad("growth requires previous completed epoch"));
        }
        let costs: BTreeMap<_, _> = o.costs.iter().map(|(b, c)| (b, *c)).collect();
        if costs.len() != o.costs.len()
            || o.costs
                .iter()
                .any(|(b, c)| !self.index.contains_key(b) || c.is_nan() || *c < 0.)
        {
            return Err(bad("invalid accessibility support"));
        }
        let eligible = |i: usize| {
            costs
                .get(&self.blocks[i].id)
                .is_some_and(|x| x.is_finite() && *x <= self.max_access)
        };
        let mut next = s.clone();
        next.pending_increment = add(next.pending_increment, increment)?;
        next.requested_increment = add(next.requested_increment, increment)?;
        for &(i, capacity, length, _) in &self.sites {
            if !eligible(i) {
                continue;
            }
            if !next.built[i] && next.pending_increment > 0 {
                if next.construction_m + length > self.budget {
                    continue;
                }
                next.built[i] = true;
                next.construction_m += length;
                next.added[i] = add(next.added[i], capacity)?;
            }
            let free = add(self.blocks[i].housing_capacity, next.added[i])? - next.allocations[i];
            let x = free.min(next.pending_increment);
            next.allocations[i] = add(next.allocations[i], x)?;
            next.pending_increment -= x;
        }
        for m in moves {
            let i = *self
                .index
                .get(&m.origin)
                .ok_or_else(|| bad("unknown move origin"))?;
            let j = *self
                .index
                .get(&m.destination)
                .ok_or_else(|| bad("unknown move destination"))?;
            if i == j
                || m.persons == 0
                || next.allocations[i] < m.persons
                || !eligible(j)
                || add(next.allocations[j], m.persons)?
                    > add(self.blocks[j].housing_capacity, next.added[j])?
            {
                return Err(bad("explicit cohort movement infeasible"));
            }
            next.allocations[i] -= m.persons;
            next.allocations[j] = add(next.allocations[j], m.persons)?;
        }
        next.epoch_s = now;
        next.consumed_access_stamp_s = o.stamp_s;
        next.moves.extend_from_slice(moves);
        next.status = if next.pending_increment > 0 {
            "PENDING_DEVELOPMENT"
        } else {
            "APPLIED"
        }
        .into();
        self.check(&next)?;
        Ok(next)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::causal::Key;
    fn obs(seconds: f64, t: f64, m: f64) -> Observation {
        Observation {
            key: Key {
                kind: "route".into(),
                id: "trip".into(),
                class: "car".into(),
            },
            seconds,
            stamp_s: t,
            start_s: 0.,
            end_s: t,
            mass_veh: m,
            sensor_xy: [0., 0.],
            source: "T04_completed_outlet".into(),
            version: "v1".into(),
            population: "sample".into(),
            measure: "route mean".into(),
        }
    }
    #[test]
    fn weighted_completed_and_no_same_tick() {
        let rows = vec![
            ("a".into(), obs(20., 180., 2.)),
            ("a".into(), obs(50., 180., 1.)),
        ];
        let s = compile_accessibility("city", &rows, 180.).unwrap();
        assert_eq!(s.costs, [("a".into(), 30.)]);
        assert!(compile_accessibility("city", &rows, 179.).is_err());
        let mut p = rows.clone();
        p[0].1.source = "prediction".into();
        assert!(compile_accessibility("city", &p, 180.).is_err());
        let m = Growth::new(
            "city",
            vec![Block {
                id: "a".into(),
                residents: 1000,
                housing_capacity: 1000,
            }],
            vec![Entry {
                id: "door".into(),
                block: "a".into(),
                city_identity: "city".into(),
                node: "n".into(),
                construction_length_m: 25.,
                capacity_veh_s: 1.,
            }],
            vec![Site {
                block: "a".into(),
                entry_id: "door".into(),
                added_capacity: 20,
                priority: 0,
            }],
            100.,
            3600.,
            50.,
        )
        .unwrap();
        let init = m.initial();
        let old =
            compile_accessibility("city", &[("a".into(), obs(100., 180., 1.))], 180.).unwrap();
        let first = m.advance(&init, &old, 3600., 10, &[]).unwrap();
        assert_eq!(first.pending_increment, 10);
        assert_eq!(first.allocations, [1000]);
        assert!(m.advance(&first, &old, 7200., 0, &[]).is_err());
        let id = m.materialized_identity(&first).unwrap();
        let new = compile_accessibility(&id, &[("a".into(), obs(20., 3780., 1.))], 3780.).unwrap();
        let second = m.advance(&first, &new, 7200., 0, &[]).unwrap();
        assert_eq!(second.allocations, [1010]);
        assert_eq!(second.added, [20]);
        assert_eq!(second.pending_increment, 0);
        assert_eq!(second.construction_m, 25.);
        let same = compile_accessibility(&id, &[("a".into(), obs(20., 7200., 1.))], 7200.).unwrap();
        assert!(m.advance(&first, &same, 7200., 0, &[]).is_err());
        assert_eq!(init.allocations, [1000]);
    }
    #[test]
    fn relocation_atomic() {
        let m = Growth::new(
            "city",
            vec![
                Block {
                    id: "a".into(),
                    residents: 900,
                    housing_capacity: 1000,
                },
                Block {
                    id: "b".into(),
                    residents: 1000,
                    housing_capacity: 1000,
                },
            ],
            vec![],
            vec![],
            0.,
            3600.,
            50.,
        )
        .unwrap();
        let s = compile_accessibility(
            "city",
            &[
                ("a".into(), obs(20., 0., 1.)),
                ("b".into(), obs(20., 0., 1.)),
            ],
            0.,
        )
        .unwrap();
        let old = m.initial();
        let next = m
            .advance(
                &old,
                &s,
                3600.,
                0,
                &[Move {
                    origin: "b".into(),
                    destination: "a".into(),
                    persons: 10,
                }],
            )
            .unwrap();
        assert_eq!(next.allocations, [910, 990]);
        assert!(m
            .advance(
                &old,
                &s,
                3600.,
                0,
                &[Move {
                    origin: "b".into(),
                    destination: "a".into(),
                    persons: 101
                }]
            )
            .is_err());
        assert_eq!(old.allocations, [900, 1000]);
    }
}

/// Materialize exactly the checked stocks into a *new* canonical physical city.
/// No hot-swap of an occupied traffic state. Pending residents remain explicit.
pub fn materialize_snapshot(
    model: &Growth,
    state: &GrowthState,
    snapshot: serde_json::Value,
) -> CoreResult<serde_json::Value> {
    use serde_json::json;
    model.check(state)?;
    let (mut base, city) = crate::frozen_city::bind_snapshot(snapshot)?;
    if city.identity != model.city || city.blocks.len() != model.blocks.len() {
        return Err(bad("growth source snapshot differs"));
    }
    for (i, b) in city.blocks.iter().enumerate() {
        let m = &model.blocks[i];
        if b.id != m.id || b.residents != m.residents || b.housing_capacity != m.housing_capacity {
            return Err(bad("growth source stock differs"));
        }
    }
    let rows = base["blocks"]
        .as_array_mut()
        .ok_or_else(|| bad("snapshot blocks"))?;
    for row in rows {
        let id = row["id"].as_str().ok_or_else(|| bad("block id"))?;
        let i = model.index[id];
        row["residents"] = json!(state.allocations[i]);
        row["housing_capacity"] = json!(add(model.blocks[i].housing_capacity, state.added[i])?);
    }
    base["requested_population"] = json!(add(city.population, state.requested_increment)?);
    base["unplaced_residents"] = json!(add(city.unplaced_residents, state.pending_increment)?);
    base["identity"] = json!("");
    Ok(crate::frozen_city::bind_snapshot(base)?.0)
}
