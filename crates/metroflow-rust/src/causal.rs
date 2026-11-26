//! R01 completed-observation channels and immutable snapshots.
use crate::core_error::{CoreError, CoreResult};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;
fn bad(s: &str) -> CoreError {
    CoreError::value(s)
}
fn finite(x: f64) -> bool {
    x.is_finite() && x >= 0.
}
fn cost(x: f64) -> bool {
    !x.is_nan() && x >= 0.
}
fn identity<T: Serialize>(x: &T) -> CoreResult<String> {
    // All identity-critical extended-real costs/radii are encoded by bits below.
    serde_json::to_vec(x)
        .map(|b| crate::frozen_city::hash(&b))
        .map_err(|e| CoreError::value(e.to_string()))
}
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
pub struct Key {
    pub kind: String,
    pub id: String,
    pub class: String,
}
impl Key {
    fn valid(&self) -> bool {
        matches!(self.kind.as_str(), "link" | "route")
            && !self.id.is_empty()
            && !self.class.is_empty()
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Prior {
    pub key: Key,
    pub seconds: f64,
    pub version: String,
    pub measure: String,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Channel {
    pub id: String,
    pub kind: String,
    pub coverage: Vec<Key>,
    pub radius_m: f64,
    pub latency_s: f64,
    pub propagation_mps: f64,
    pub max_age_s: f64,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Observation {
    pub key: Key,
    pub seconds: f64,
    pub stamp_s: f64,
    pub start_s: f64,
    pub end_s: f64,
    pub mass_veh: f64,
    pub sensor_xy: [f64; 2],
    pub source: String,
    pub version: String,
    pub population: String,
    pub measure: String,
}
impl Observation {
    pub fn validate(&self) -> CoreResult<()> {
        if !self.key.valid()
            || !cost(self.seconds)
            || ![self.stamp_s, self.start_s, self.end_s, self.mass_veh]
                .into_iter()
                .all(finite)
            || self.mass_veh == 0.
            || self.start_s > self.end_s
            || self.end_s > self.stamp_s
            || self.sensor_xy.iter().any(|x| !x.is_finite())
            || [&self.source, &self.version, &self.population, &self.measure]
                .iter()
                .any(|x| x.is_empty())
        {
            return Err(bad("invalid observation"));
        }
        Ok(())
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Report {
    pub channel: String,
    pub observation: Observation,
}
#[derive(Clone, Debug, PartialEq)]
pub struct InfoState {
    model: String,
    pub time_s: f64,
    rows: Arc<Vec<Report>>,
}
impl InfoState {
    pub fn reports(&self) -> &[Report] {
        &self.rows
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Delivered {
    pub key: Key,
    pub seconds: f64,
    pub source: String,
    pub version: String,
    pub measure: String,
    pub stamp_s: Option<f64>,
    pub age_s: Option<f64>,
    pub delivered_s: Option<f64>,
    pub population: Option<String>,
}
impl Delivered {
    pub fn is_delivered(&self) -> bool {
        self.stamp_s.is_some()
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct DecisionObservation {
    pub decision: String,
    pub time_s: f64,
    pub costs: Vec<Delivered>,
    pub coverage_fraction: f64,
}
pub struct Information {
    pub id: String,
    priors: Vec<Prior>,
    channels: Vec<Channel>,
    prior_idx: BTreeMap<Key, usize>,
    channel_idx: BTreeMap<String, usize>,
    coverage: Vec<BTreeSet<Key>>,
    budget: usize,
}
impl Information {
    pub fn new(priors: Vec<Prior>, channels: Vec<Channel>, budget: usize) -> CoreResult<Self> {
        let prior_idx: BTreeMap<_, _> = priors
            .iter()
            .enumerate()
            .map(|(i, p)| (p.key.clone(), i))
            .collect();
        let channel_idx: BTreeMap<_, _> = channels
            .iter()
            .enumerate()
            .map(|(i, c)| (c.id.clone(), i))
            .collect();
        if budget == 0
            || priors.is_empty()
            || prior_idx.len() != priors.len()
            || channel_idx.len() != channels.len()
        {
            return Err(bad("invalid prior/channel registry"));
        }
        for p in &priors {
            if !p.key.valid() || !cost(p.seconds) || p.version.is_empty() || p.measure.is_empty() {
                return Err(bad("invalid prior"));
            }
        }
        let mut coverage = Vec::new();
        for c in &channels {
            let keys: BTreeSet<_> = c.coverage.iter().cloned().collect();
            if c.id.is_empty()
                || !matches!(c.kind.as_str(), "direct" | "v2v" | "server" | "history")
                || !cost(c.radius_m)
                || !finite(c.latency_s)
                || !finite(c.max_age_s)
                || !finite(c.propagation_mps)
                || c.propagation_mps == 0.
                || matches!(c.kind.as_str(), "direct" | "v2v") && !c.radius_m.is_finite()
                || keys.len() != c.coverage.len()
                || keys.iter().any(|k| !prior_idx.contains_key(k))
            {
                return Err(bad("invalid channel"));
            }
            coverage.push(keys);
        }
        let id = identity(&(
            "R01_native_v1",
            budget,
            priors
                .iter()
                .map(|p| (&p.key, p.seconds.to_bits(), &p.version, &p.measure))
                .collect::<Vec<_>>(),
            channels
                .iter()
                .map(|c| {
                    (
                        &c.id,
                        &c.kind,
                        &c.coverage,
                        c.radius_m.to_bits(),
                        c.latency_s.to_bits(),
                        c.propagation_mps.to_bits(),
                        c.max_age_s.to_bits(),
                    )
                })
                .collect::<Vec<_>>(),
        ))?;
        Ok(Self {
            id,
            priors,
            channels,
            prior_idx,
            channel_idx,
            coverage,
            budget,
        })
    }
    pub fn initial(&self) -> InfoState {
        InfoState {
            model: self.id.clone(),
            time_s: 0.,
            rows: Arc::new(vec![]),
        }
    }
    fn validate_report(&self, r: &Report, now: f64) -> CoreResult<usize> {
        r.observation.validate()?;
        let o = &r.observation;
        let &i = self
            .channel_idx
            .get(&r.channel)
            .ok_or_else(|| bad("unknown channel"))?;
        if !self.coverage[i].contains(&o.key) {
            return Err(bad("report outside coverage"));
        }
        if o.stamp_s > now {
            return Err(bad("future report"));
        }
        if o.measure != self.priors[self.prior_idx[&o.key]].measure {
            return Err(bad("unlike estimands"));
        }
        Ok(i)
    }
    fn check(&self, s: &InfoState) -> CoreResult<()> {
        if s.model != self.id || !finite(s.time_s) || s.rows.len() > self.budget {
            return Err(bad("information snapshot binding"));
        }
        for r in s.rows.iter() {
            self.validate_report(r, s.time_s)?;
        }
        Ok(())
    }
    pub fn advance(&self, s: &InfoState, now: f64, incoming: &[Report]) -> CoreResult<InfoState> {
        self.check(s)?;
        if !finite(now) || now < s.time_s {
            return Err(bad("nonmonotone clock"));
        }
        // Stable stamp/channel/key ordering; duplicate reports are idempotent. No
        // latest-only pruning: a newer, undelivered observation may not hide an older one.
        let mut keep: BTreeMap<(u64, &str, &Key), &Report> = BTreeMap::new();
        for r in s.rows.iter().chain(incoming) {
            let i = self.validate_report(r, now)?;
            let o = &r.observation;
            if now - o.stamp_s > self.channels[i].max_age_s {
                continue;
            }
            let k = (
                if o.stamp_s == 0. {
                    0
                } else {
                    o.stamp_s.to_bits()
                },
                r.channel.as_str(),
                &o.key,
            );
            if let Some(old) = keep.get(&k) {
                if *old != r {
                    return Err(bad("conflicting reports"));
                }
            } else {
                if keep.len() == self.budget {
                    return Err(CoreError::resource("R01 record budget"));
                }
                keep.insert(k, r);
            }
        }
        Ok(InfoState {
            model: self.id.clone(),
            time_s: now,
            rows: Arc::new(keep.into_values().cloned().collect()),
        })
    }
    pub fn observe(
        &self,
        s: &InfoState,
        xy: [f64; 2],
        decision: &str,
    ) -> CoreResult<DecisionObservation> {
        self.check(s)?;
        if !matches!(decision, "origin" | "en_route") || xy.iter().any(|x| !x.is_finite()) {
            return Err(bad("invalid decision/location"));
        }
        // O(P+R) indexing rather than P*C*R nested scans. Parallel map independent
        // prior slots; output order follows declaration; no floating parallel sum.
        let mut by = vec![Vec::new(); self.priors.len()];
        for r in s.rows.iter() {
            by[self.prior_idx[&r.observation.key]].push((self.channel_idx[&r.channel], r));
        }
        let costs: Vec<_> = self
            .priors
            .par_iter()
            .zip(by.par_iter())
            .map(|(p, rows)| {
                let mut best: Option<(usize, &Report, f64)> = None;
                for &(i, r) in rows {
                    let c = &self.channels[i];
                    let o = &r.observation;
                    let d = (xy[0] - o.sensor_xy[0]).hypot(xy[1] - o.sensor_xy[1]);
                    let t = o.stamp_s + c.latency_s + d / c.propagation_mps;
                    if d <= c.radius_m
                        && t <= s.time_s
                        && s.time_s - o.stamp_s <= c.max_age_s
                        && best.is_none_or(|(j, b, _)| {
                            o.stamp_s > b.observation.stamp_s
                                || (o.stamp_s == b.observation.stamp_s && i < j)
                        })
                    {
                        best = Some((i, r, t))
                    }
                }
                if let Some((i, r, t)) = best {
                    let o = &r.observation;
                    Delivered {
                        key: p.key.clone(),
                        seconds: o.seconds,
                        source: format!("{}:{}", self.channels[i].id, o.source),
                        version: o.version.clone(),
                        measure: o.measure.clone(),
                        stamp_s: Some(o.stamp_s),
                        age_s: Some(s.time_s - o.stamp_s),
                        delivered_s: Some(t),
                        population: Some(o.population.clone()),
                    }
                } else {
                    Delivered {
                        key: p.key.clone(),
                        seconds: p.seconds,
                        source: "DECLARED_PRIOR".into(),
                        version: p.version.clone(),
                        measure: p.measure.clone(),
                        stamp_s: None,
                        age_s: None,
                        delivered_s: None,
                        population: None,
                    }
                }
            })
            .collect();
        let coverage_fraction =
            costs.iter().filter(|c| c.is_delivered()).count() as f64 / costs.len() as f64;
        Ok(DecisionObservation {
            decision: decision.into(),
            time_s: s.time_s,
            costs,
            coverage_fraction,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn key() -> Key {
        Key {
            kind: "link".into(),
            id: "ab".into(),
            class: "car".into(),
        }
    }
    fn report(t: f64, seconds: f64, x: f64) -> Report {
        Report {
            channel: "local".into(),
            observation: Observation {
                key: key(),
                seconds,
                stamp_s: t,
                start_s: 0.,
                end_s: t,
                mass_veh: 1.,
                sensor_xy: [x, 0.],
                source: "sensor".into(),
                version: "v1".into(),
                population: "sample".into(),
                measure: "link mean".into(),
            },
        }
    }
    fn model(b: usize) -> Information {
        Information::new(
            vec![Prior {
                key: key(),
                seconds: 21.,
                version: "prior".into(),
                measure: "link mean".into(),
            }],
            vec![Channel {
                id: "local".into(),
                kind: "direct".into(),
                coverage: vec![key()],
                radius_m: 100.,
                latency_s: 5.,
                propagation_mps: 10.,
                max_age_s: 100.,
            }],
            b,
        )
        .unwrap()
    }
    #[test]
    fn nonanticipation_and_atomic_history() {
        let m = model(2);
        let s = m
            .advance(
                &m.initial(),
                20.,
                &[report(10., 50., 0.), report(19., 500., 0.)],
            )
            .unwrap();
        assert_eq!(
            m.observe(&s, [0., 0.], "origin").unwrap().costs[0].seconds,
            50.
        );
        assert_eq!(
            m.observe(&m.advance(&s, 24., &[]).unwrap(), [0., 0.], "origin")
                .unwrap()
                .costs[0]
                .seconds,
            500.
        );
        assert_eq!(
            m.observe(&s, [1000., 0.], "en_route").unwrap().costs[0].seconds,
            21.
        );
        assert!(m.advance(&s, 20., &[report(20., 1., 0.)]).is_err());
        assert_eq!(s.reports().len(), 2);
        assert!(m.advance(&s, 20., &[report(19., 1., 0.)]).is_err());
        assert!(m.advance(&s, 20., &[report(21., 1., 0.)]).is_err());
        let a = m.advance(&s, 120., &[]).unwrap();
        assert!(a.reports().is_empty());
        let b = m
            .advance(
                &m.initial(),
                20.,
                &[
                    report(10., 50., 0.),
                    report(10., 50., 0.),
                    report(19., 500., 0.),
                ],
            )
            .unwrap();
        assert_eq!(b, s);
    }
}
