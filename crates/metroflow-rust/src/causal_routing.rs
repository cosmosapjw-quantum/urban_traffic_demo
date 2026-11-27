//! R02: bounded K legal alternatives on delivered costs, no mutation of occupied traffic.
use crate::{
    causal::DecisionObservation,
    core_error::{CoreError, CoreResult},
    frozen_city::hash,
    v1_journey::fsum,
};
use serde::{Deserialize, Serialize};
use std::{
    cmp::Ordering,
    collections::{BTreeMap, BTreeSet, BinaryHeap},
    sync::Arc,
};
fn bad(s: &str) -> CoreError {
    CoreError::value(s)
}
fn sum(xs: impl IntoIterator<Item = f64>) -> CoreResult<f64> {
    let s = fsum(xs);
    if s.is_finite() {
        Ok(s)
    } else {
        Err(CoreError::arithmetic("route sum overflow"))
    }
}
fn near(a: f64, b: f64) -> bool {
    (a - b).abs() <= 1e-12 * a.abs().max(b.abs()).max(1.)
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Link {
    pub id: String,
    pub tail: String,
    pub head: String,
    pub length_m: f64,
    pub toll_units: f64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Preference {
    pub class: String,
    pub purpose: String,
    pub time_weight: f64,
    pub distance_s_per_m: f64,
    pub money_s_per_unit: f64,
    pub logit_scale_s: f64,
    pub path_size_beta: f64,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Commitment {
    pub graph_id: String,
    pub links: Vec<String>,
    pub position: usize,
}
#[derive(Clone, Debug)]
pub struct Boundary {
    pub time_s: f64,
    pub node: String,
    pub incoming: Option<String>,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Alternative {
    pub suffix: Vec<String>,
    pub commitment: Commitment,
    pub length_m: f64,
    pub travel_time_s: f64,
    pub generalized_cost_s: f64,
    pub path_size: f64,
    pub probability: f64,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Decision {
    pub status: String,
    pub reason: String,
    pub time_s: f64,
    pub alternatives: Vec<Alternative>,
    pub fallback: Option<Commitment>,
    pub cache_hit: bool,
    pub expanded: usize,
    pub regret_s: Option<f64>,
    pub cost_epoch: String,
}
#[derive(Clone, Debug, PartialEq)]
pub struct State {
    model: String,
    cache: Vec<(String, Arc<Vec<f64>>)>,
    pub hits: usize,
    pub misses: usize,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub(crate) struct RoutingWire {
    pub model: String,
    pub cache: Vec<(String, Vec<u64>)>,
    pub hits: usize,
    pub misses: usize,
}
pub struct Routing {
    pub graph_id: String,
    id: String,
    links: Vec<Link>,
    ids: BTreeMap<String, usize>,
    nodes: BTreeMap<String, usize>,
    tail: Vec<usize>,
    head: Vec<usize>,
    out: Vec<Vec<usize>>,
    succ: Vec<Vec<usize>>,
    pred: Vec<Vec<usize>>,
    k: usize,
    expansion: usize,
    frontier: usize,
    cache: usize,
}
#[derive(Clone, Debug)]
struct Item {
    est: f64,
    cost: f64,
    path: Vec<usize>,
    visited: Vec<usize>,
}
impl Eq for Item {}
impl PartialEq for Item {
    fn eq(&self, o: &Self) -> bool {
        self.cmp(o) == Ordering::Equal
    }
}
impl Ord for Item {
    fn cmp(&self, o: &Self) -> Ordering {
        o.est
            .total_cmp(&self.est)
            .then(o.cost.total_cmp(&self.cost))
            .then(o.path.cmp(&self.path))
            .then(o.visited.cmp(&self.visited))
    }
}
impl PartialOrd for Item {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
#[derive(Clone, Copy, Debug)]
struct Dist(f64, usize);
impl Eq for Dist {}
impl PartialEq for Dist {
    fn eq(&self, o: &Self) -> bool {
        self.cmp(o) == Ordering::Equal
    }
}
impl Ord for Dist {
    fn cmp(&self, o: &Self) -> Ordering {
        o.0.total_cmp(&self.0).then(o.1.cmp(&self.1))
    }
}
impl PartialOrd for Dist {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
fn digest<T: Serialize>(v: &T) -> CoreResult<String> {
    serde_json::to_vec(v)
        .map(|b| hash(&b))
        .map_err(|e| CoreError::value(e.to_string()))
}
impl Routing {
    pub fn new(
        mut links: Vec<Link>,
        mut turns: Vec<(String, String)>,
        version: &str,
        k: usize,
        expansion: usize,
        frontier: usize,
        graph_budget: usize,
        cache: usize,
    ) -> CoreResult<Self> {
        if !(1..=3).contains(&k)
            || frontier == 0
            || cache == 0
            || graph_budget == 0
            || version.is_empty()
        {
            return Err(bad("invalid route budgets"));
        }
        links.sort_by(|a, b| a.id.cmp(&b.id));
        turns.sort();
        turns.dedup();
        if links.len().saturating_add(turns.len()) > graph_budget {
            return Err(CoreError::resource("route graph budget"));
        }
        let ids: BTreeMap<_, _> = links
            .iter()
            .enumerate()
            .map(|(i, l)| (l.id.clone(), i))
            .collect();
        if ids.len() != links.len()
            || links.iter().any(|l| {
                l.id.is_empty()
                    || l.tail.is_empty()
                    || l.head.is_empty()
                    || l.tail == l.head
                    || !l.length_m.is_finite()
                    || l.length_m <= 0.
                    || !l.toll_units.is_finite()
                    || l.toll_units < 0.
            })
        {
            return Err(bad("invalid links"));
        }
        let ns: BTreeSet<_> = links
            .iter()
            .flat_map(|l| [l.tail.clone(), l.head.clone()])
            .collect();
        let nodes: BTreeMap<_, _> = ns.into_iter().enumerate().map(|(i, n)| (n, i)).collect();
        let tail: Vec<_> = links.iter().map(|l| nodes[&l.tail]).collect();
        let head: Vec<_> = links.iter().map(|l| nodes[&l.head]).collect();
        let mut out = vec![vec![]; nodes.len()];
        let mut succ = vec![vec![]; links.len()];
        let mut pred = succ.clone();
        for (i, &n) in tail.iter().enumerate() {
            out[n].push(i)
        }
        for (a, b) in &turns {
            let i = *ids.get(a).ok_or_else(|| bad("unknown turn link"))?;
            let j = *ids.get(b).ok_or_else(|| bad("unknown turn link"))?;
            if head[i] != tail[j] {
                return Err(bad("nonadjacent turn"));
            }
            succ[i].push(j);
            pred[j].push(i);
        }
        let graph_id = digest(&(version, &links, &turns))?;
        let id = digest(&(&graph_id, k, expansion, frontier, graph_budget, cache))?;
        Ok(Self {
            graph_id,
            id,
            links,
            ids,
            nodes,
            tail,
            head,
            out,
            succ,
            pred,
            k,
            expansion,
            frontier,
            cache,
        })
    }
    pub fn initial(&self) -> State {
        State {
            model: self.id.clone(),
            cache: vec![],
            hits: 0,
            misses: 0,
        }
    }
    pub(crate) fn export_state(&self, s: &State) -> CoreResult<RoutingWire> {
        if s.model != self.id {
            return Err(bad("routing wire model"));
        }
        Ok(RoutingWire {
            model: s.model.clone(),
            cache: s
                .cache
                .iter()
                .map(|(k, v)| (k.clone(), v.iter().map(|x| x.to_bits()).collect()))
                .collect(),
            hits: s.hits,
            misses: s.misses,
        })
    }
    pub(crate) fn import_state(&self, w: &RoutingWire) -> CoreResult<State> {
        if w.model != self.id
            || w.cache.len() > self.cache
            || w.cache.iter().any(|(k, v)| {
                k.len() != 64
                    || !k.bytes().all(|x| x.is_ascii_hexdigit())
                    || v.len() != self.links.len()
                    || v.iter().any(|&x| {
                        let x = f64::from_bits(x);
                        x.is_nan() || x < 0.
                    })
            })
            || w.cache
                .iter()
                .map(|(k, _)| k)
                .collect::<BTreeSet<_>>()
                .len()
                != w.cache.len()
        {
            return Err(bad("invalid routing cache wire"));
        }
        Ok(State {
            model: w.model.clone(),
            cache: w
                .cache
                .iter()
                .map(|(k, v)| {
                    (
                        k.clone(),
                        Arc::new(v.iter().map(|&x| f64::from_bits(x)).collect()),
                    )
                })
                .collect(),
            hits: w.hits,
            misses: w.misses,
        })
    }
    fn indices(&self, ids: &[String]) -> CoreResult<Vec<usize>> {
        ids.iter()
            .map(|s| {
                self.ids
                    .get(s)
                    .copied()
                    .ok_or_else(|| bad("unknown path link"))
            })
            .collect()
    }
    fn names(&self, p: &[usize]) -> Vec<String> {
        p.iter().map(|&i| self.links[i].id.clone()).collect()
    }
    fn legal(
        &self,
        p: &[usize],
        a: usize,
        b: usize,
        incoming: Option<usize>,
        banned: &[usize],
    ) -> bool {
        if p.is_empty() {
            return a == b;
        }
        if self.tail[p[0]] != a
            || self.head[*p.last().unwrap()] != b
            || incoming.is_some_and(|i| !self.succ[i].contains(&p[0]))
            || p.windows(2).any(|w| !self.succ[w[0]].contains(&w[1]))
        {
            return false;
        }
        let mut seen = BTreeSet::new();
        std::iter::once(a)
            .chain(p.iter().map(|&i| self.head[i]))
            .all(|n| !banned.contains(&n) && seen.insert(n))
    }
    fn potential(&self, c: &[f64], d: usize) -> CoreResult<Vec<f64>> {
        let mx = c
            .iter()
            .copied()
            .filter(|x| x.is_finite())
            .fold(1., f64::max);
        let scale = if mx > 1e250 { mx } else { 1. };
        let mut v = vec![f64::INFINITY; c.len()];
        let mut heap = BinaryHeap::new();
        for (i, &n) in self.head.iter().enumerate() {
            if n == d && c[i].is_finite() {
                v[i] = c[i] / scale;
                heap.push(Dist(v[i], i));
            }
        }
        while let Some(Dist(x, j)) = heap.pop() {
            if x != v[j] {
                continue;
            }
            for &i in &self.pred[j] {
                let z = c[i] / scale + x;
                if z < v[i] {
                    v[i] = z;
                    heap.push(Dist(z, i));
                }
            }
        }
        for x in &mut v {
            let y = *x * scale;
            if x.is_finite() && !y.is_finite() {
                return Err(CoreError::arithmetic("destination potential overflow"));
            }
            *x = y;
        }
        Ok(v)
    }
    fn search(
        &self,
        c: &[f64],
        v: &[f64],
        a: usize,
        d: usize,
        incoming: Option<usize>,
        banned: &[usize],
    ) -> CoreResult<(Vec<Vec<usize>>, usize, Option<&'static str>)> {
        if a == d {
            return Ok((vec![vec![]], 0, None));
        }
        let mut heap = BinaryHeap::new();
        for &i in &self.out[a] {
            let n = self.head[i];
            if v[i].is_finite()
                && n != a
                && !banned.contains(&n)
                && incoming.is_none_or(|j| self.succ[j].contains(&i))
            {
                heap.push(Item {
                    est: v[i],
                    cost: c[i],
                    path: vec![i],
                    visited: vec![a, n],
                })
            }
        }
        let mut found: Vec<Vec<usize>> = vec![];
        let mut expanded = 0;
        if heap.len() > self.frontier {
            return Ok((vec![], 0, Some("frontier budget")));
        }
        while let Some(top) = heap.peek() {
            if found.len() >= self.k {
                let cutoff = sum(found.last().unwrap().iter().map(|&i| c[i]))?;
                if top.est > cutoff && !near(top.est, cutoff) {
                    break;
                }
            }
            if expanded >= self.expansion {
                return Ok((
                    vec![],
                    expanded,
                    Some("expansion budget before complete tie boundary"),
                ));
            }
            let x = heap.pop().unwrap();
            expanded += 1;
            let i = *x.path.last().unwrap();
            if self.head[i] == d {
                found.push(x.path);
                if found.len() > self.k {
                    return Ok((vec![], expanded, Some("cost tie exceeds K")));
                }
                continue;
            }
            for &j in &self.succ[i] {
                let n = self.head[j];
                if x.visited.contains(&n) || banned.contains(&n) || !v[j].is_finite() {
                    continue;
                }
                if heap.len() >= self.frontier {
                    return Ok((vec![], expanded, Some("frontier budget")));
                }
                let mut path = x.path.clone();
                path.push(j);
                let mut visited = x.visited.clone();
                visited.push(n);
                heap.push(Item {
                    est: sum([x.cost, v[j]])?,
                    cost: sum([x.cost, c[j]])?,
                    path,
                    visited,
                });
            }
        }
        Ok((found, expanded, None))
    }
    pub fn decide(
        &self,
        state: &State,
        o: &DecisionObservation,
        b: &Boundary,
        p: &Preference,
        destination: &str,
        current: Option<&Commitment>,
        baseline: &[String],
    ) -> CoreResult<(State, Decision)> {
        if state.model != self.id
            || state.cache.len() > self.cache
            || !b.time_s.is_finite()
            || b.time_s < 0.
            || o.time_s != b.time_s
            || o.decision
                != if b.incoming.is_some() {
                    "en_route"
                } else {
                    "origin"
                }
        {
            return Err(bad("state/decision boundary differs"));
        }
        if p.class.is_empty()
            || p.purpose.is_empty()
            || [
                p.time_weight,
                p.distance_s_per_m,
                p.money_s_per_unit,
                p.logit_scale_s,
                p.path_size_beta,
            ]
            .iter()
            .any(|x| !x.is_finite() || *x < 0.)
            || p.time_weight == 0.
            || p.logit_scale_s == 0.
        {
            return Err(bad("invalid preference"));
        }
        let a = *self
            .nodes
            .get(&b.node)
            .ok_or_else(|| bad("unknown origin"))?;
        let d = *self
            .nodes
            .get(destination)
            .ok_or_else(|| bad("unknown destination"))?;
        let incoming = b
            .incoming
            .as_ref()
            .map(|s| {
                self.ids
                    .get(s)
                    .copied()
                    .ok_or_else(|| bad("unknown incoming"))
            })
            .transpose()?;
        let (mut prefix, mut banned) = (vec![], vec![]);
        let base;
        if let Some(i) = incoming {
            let cur = current.ok_or_else(|| bad("actual occupied commitment required"))?;
            let full = self.indices(&cur.links)?;
            if cur.graph_id != self.graph_id
                || cur.position >= full.len()
                || full[cur.position] != i
                || self.head[i] != a
                || !self.legal(
                    &full,
                    self.tail[full[0]],
                    self.head[*full.last().unwrap()],
                    None,
                    &[],
                )
            {
                return Err(bad("actual occupied commitment differs"));
            }
            prefix = full[..=cur.position].to_vec();
            banned.push(self.tail[prefix[0]]);
            banned.extend(prefix[..prefix.len() - 1].iter().map(|&j| self.head[j]));
            base = full[cur.position + 1..].to_vec();
        } else {
            if current.is_some() {
                return Err(bad("occupied route at origin"));
            }
            base = self.indices(baseline)?
        }
        let mut physical = vec![f64::NAN; self.links.len()];
        let mut epoch_rows = vec![];
        for x in o.costs.iter().filter(|x| x.key.class == p.class) {
            let i = *self
                .ids
                .get(&x.key.id)
                .ok_or_else(|| bad("unknown link cost"))?;
            if x.key.kind != "link"
                || !physical[i].is_nan()
                || x.seconds.is_nan()
                || x.seconds < 0.
                || x.measure.is_empty()
                || x.version.is_empty()
            {
                return Err(bad("one valid link cost per selected class required"));
            }
            match (x.stamp_s, x.age_s, x.delivered_s) {
                (Some(s), Some(age), Some(t))
                    if s.is_finite()
                        && s >= 0.
                        && s <= b.time_s
                        && t.is_finite()
                        && t >= s
                        && t <= b.time_s
                        && age.is_finite()
                        && (age - (b.time_s - s)).abs()
                            <= 1e-9 * age.abs().max((b.time_s - s).abs()).max(1.) => {}
                (None, None, None) if x.source == "DECLARED_PRIOR" => {}
                _ => return Err(bad("future/undelivered cost")),
            }
            physical[i] = x.seconds;
            epoch_rows.push((
                i,
                x.seconds.to_bits(),
                &x.source,
                &x.version,
                &x.measure,
                x.stamp_s.map(f64::to_bits),
                x.age_s.map(f64::to_bits),
                x.delivered_s.map(f64::to_bits),
                &x.population,
            ));
        }
        if physical.iter().any(|x| x.is_nan()) {
            return Err(bad("incomplete link cost registry"));
        }
        epoch_rows.sort_by_key(|x| x.0);
        let epoch = digest(&epoch_rows)?;
        let c: Vec<_> = self
            .links
            .iter()
            .zip(&physical)
            .map(|(l, t)| {
                p.time_weight * t
                    + p.distance_s_per_m * l.length_m
                    + p.money_s_per_unit * l.toll_units
            })
            .collect();
        if c.iter()
            .zip(&physical)
            .any(|(x, t)| t.is_finite() && !x.is_finite())
        {
            return Err(CoreError::arithmetic("generalized cost overflow"));
        }
        let fallback = if self.legal(&base, a, d, incoming, &banned)
            && base.iter().all(|&i| c[i].is_finite())
            && (!base.is_empty() || !prefix.is_empty())
        {
            Some(current.cloned().unwrap_or(Commitment {
                graph_id: self.graph_id.clone(),
                links: self.names(&base),
                position: 0,
            }))
        } else {
            None
        };
        let key = digest(&(&self.graph_id, destination, p, &epoch))?;
        let found = state.cache.iter().find(|x| x.0 == key);
        let hit = found.is_some();
        let v = if let Some(x) = found {
            x.1.clone()
        } else {
            Arc::new(self.potential(&c, d)?)
        };
        let (paths, expanded, fail) = self.search(&c, &v, a, d, incoming, &banned)?;
        let mut decision = Decision {
            status: "CANDIDATES".into(),
            reason: "delivered cost alternatives".into(),
            time_s: b.time_s,
            alternatives: vec![],
            fallback,
            cache_hit: hit,
            expanded,
            regret_s: None,
            cost_epoch: epoch,
        };
        if let Some(reason) = fail {
            decision.status = "BLOCKED_RESOURCE".into();
            decision.reason = reason.into();
            return Ok((state.clone(), decision));
        }
        let mut next = state.clone();
        next.cache.retain(|x| x.0 != key);
        next.cache.push((key, v));
        if next.cache.len() > self.cache {
            next.cache.remove(0);
        }
        next.hits += usize::from(hit);
        next.misses += usize::from(!hit);
        if paths.is_empty() {
            let topo = self.potential(&vec![1.; c.len()], d)?;
            decision.status = if self.out[a]
                .iter()
                .any(|&i| topo[i].is_finite() && incoming.is_none_or(|j| self.succ[j].contains(&i)))
            {
                "NO_PERCEIVED_PATH"
            } else {
                "PHYSICAL_UNREACHABLE"
            }
            .into();
            decision.fallback = None;
            return Ok((next, decision));
        }
        if paths[0].is_empty() {
            decision.status = if current.is_some() {
                "ARRIVED_AT_NODE"
            } else {
                "LOCAL_ACTIVITY_REQUIRED"
            }
            .into();
            decision.fallback = current.cloned();
            return Ok((next, decision));
        }
        let costs = paths
            .iter()
            .map(|p| sum(p.iter().map(|&i| c[i])))
            .collect::<CoreResult<Vec<_>>>()?;
        let lengths: Vec<_> = self.links.iter().map(|l| l.length_m).collect();
        let (sizes, prob) = path_size(&paths, &lengths, &costs, p)?;
        if decision.fallback.is_some() {
            decision.regret_s = Some(
                sum(base.iter().map(|&i| c[i]))?
                    - costs.iter().copied().fold(f64::INFINITY, f64::min),
            );
        }
        for (i, path) in paths.iter().enumerate() {
            let full: Vec<_> = prefix.iter().chain(path).copied().collect();
            let commitment = Commitment {
                graph_id: self.graph_id.clone(),
                links: self.names(&full),
                position: current.map_or(0, |x| x.position),
            };
            if current.is_some_and(|x| x.links != commitment.links) {
                decision.status = "PROPOSED_SUFFIX".into();
            }
            decision.alternatives.push(Alternative {
                suffix: self.names(path),
                commitment,
                length_m: sum(full.iter().map(|&j| lengths[j]))?,
                travel_time_s: sum(path.iter().map(|&j| physical[j]))?,
                generalized_cost_s: costs[i],
                path_size: sizes[i],
                probability: prob[i],
            });
        }
        Ok((next, decision))
    }
}
pub fn path_size(
    paths: &[Vec<usize>],
    lengths: &[f64],
    costs: &[f64],
    p: &Preference,
) -> CoreResult<(Vec<f64>, Vec<f64>)> {
    if paths.is_empty()
        || paths.len() != costs.len()
        || paths.iter().collect::<BTreeSet<_>>().len() != paths.len()
        || costs.iter().any(|x| !x.is_finite() || *x < 0.)
        || !p.logit_scale_s.is_finite()
        || p.logit_scale_s <= 0.
        || !p.path_size_beta.is_finite()
        || p.path_size_beta < 0.
    {
        return Err(bad("invalid route alternatives"));
    }
    // Sparse support census, not dense incidence matrix or Cartesian path scan.
    let mut count = BTreeMap::new();
    for path in paths {
        let mut unique = BTreeSet::new();
        if path.is_empty() {
            return Err(bad("empty path"));
        }
        for &i in path {
            if !unique.insert(i) || lengths.get(i).is_none_or(|x| !x.is_finite() || *x <= 0.) {
                return Err(bad("invalid loopless path length"));
            }
            *count.entry(i).or_insert(0usize) += 1;
        }
    }
    let sizes = paths
        .iter()
        .map(|r| {
            Ok(sum(r.iter().map(|&i| lengths[i] / count[&i] as f64))?
                / sum(r.iter().map(|&i| lengths[i]))?)
        })
        .collect::<CoreResult<Vec<_>>>()?;
    let min = costs.iter().copied().fold(f64::INFINITY, f64::min);
    let logs: Vec<_> = costs
        .iter()
        .zip(&sizes)
        .map(|(c, s)| -(c - min) / p.logit_scale_s + p.path_size_beta * s.ln())
        .collect();
    let peak = logs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let w: Vec<_> = logs.iter().map(|x| (x - peak).exp()).collect();
    let total = sum(w.iter().copied())?;
    if total <= 0. {
        return Err(bad("invalid route probabilities"));
    }
    Ok((sizes, w.iter().map(|x| x / total).collect()))
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::causal::{Information, Key, Prior};
    fn pref() -> Preference {
        Preference {
            class: "car".into(),
            purpose: "work".into(),
            time_weight: 1.,
            distance_s_per_m: 0.,
            money_s_per_unit: 0.,
            logit_scale_s: 30.,
            path_size_beta: 1.,
        }
    }
    fn model(k: usize) -> Routing {
        let l = [
            ("oa", "O", "A"),
            ("ad", "A", "D"),
            ("ob", "O", "B"),
            ("bd", "B", "D"),
            ("ab", "A", "B"),
        ]
        .into_iter()
        .map(|(i, a, b)| Link {
            id: i.into(),
            tail: a.into(),
            head: b.into(),
            length_m: 100.,
            toll_units: 0.,
        })
        .collect();
        let t = [("oa", "ad"), ("oa", "ab"), ("ab", "bd"), ("ob", "bd")]
            .into_iter()
            .map(|(a, b)| (a.into(), b.into()))
            .collect();
        Routing::new(l, t, "fixture", k, 2000, 10000, 10000, 2).unwrap()
    }
    fn obs(c: [f64; 5], time: f64, decision: &str) -> DecisionObservation {
        let p = ["oa", "ad", "ob", "bd", "ab"]
            .into_iter()
            .zip(c)
            .map(|(id, seconds)| Prior {
                key: Key {
                    kind: "link".into(),
                    id: id.into(),
                    class: "car".into(),
                },
                seconds,
                version: "prior".into(),
                measure: "link mean".into(),
            })
            .collect();
        let m = Information::new(p, vec![], 10).unwrap();
        m.observe(
            &m.advance(&m.initial(), time, &[]).unwrap(),
            [0., 0.],
            decision,
        )
        .unwrap()
    }
    #[test]
    fn choices_cache_and_occupied_suffix() {
        let m = model(3);
        let b = Boundary {
            time_s: 0.,
            node: "O".into(),
            incoming: None,
        };
        let o = obs([10., 10., 12., 12., 20.], 0., "origin");
        let (s, d) = m
            .decide(&m.initial(), &o, &b, &pref(), "D", None, &[])
            .unwrap();
        assert_eq!(d.alternatives.len(), 3);
        assert_eq!(d.alternatives[0].travel_time_s, 20.);
        assert!((fsum(d.alternatives.iter().map(|x| x.probability)) - 1.).abs() < 1e-14);
        assert!(
            m.decide(&s, &o, &b, &pref(), "D", None, &[])
                .unwrap()
                .1
                .cache_hit
        );
        let cur = Commitment {
            graph_id: m.graph_id.clone(),
            links: vec!["oa".into(), "ad".into()],
            position: 0,
        };
        let b = Boundary {
            time_s: 10.,
            node: "A".into(),
            incoming: Some("oa".into()),
        };
        let (_, d) = m
            .decide(
                &s,
                &obs([10., 100., 12., 12., 1.], 10., "en_route"),
                &b,
                &pref(),
                "D",
                Some(&cur),
                &[],
            )
            .unwrap();
        assert_eq!(d.status, "PROPOSED_SUFFIX");
        assert_eq!(d.alternatives[0].commitment.links, ["oa", "ab", "bd"]);
        assert_eq!(d.regret_s, Some(87.));
        assert_eq!(cur.links, ["oa", "ad"]);
    }
    #[test]
    fn tie_resource_and_path_size() {
        let m = model(1);
        let b = Boundary {
            time_s: 0.,
            node: "O".into(),
            incoming: None,
        };
        let s = m.initial();
        let (s2, d) = m
            .decide(
                &s,
                &obs([10., 10., 10., 10., 100.], 0., "origin"),
                &b,
                &pref(),
                "D",
                None,
                &["ob".into(), "bd".into()],
            )
            .unwrap();
        assert_eq!(s, s2);
        assert_eq!(d.status, "BLOCKED_RESOURCE");
        assert!(d.reason.contains("tie"));
        assert_eq!(d.fallback.unwrap().links, ["ob", "bd"]);
        let (s, p) = path_size(
            &[vec![0, 1], vec![0, 2], vec![3]],
            &[1.; 4],
            &[20.; 3],
            &pref(),
        )
        .unwrap();
        assert_eq!(s, [0.75, 0.75, 1.]);
        for (a, b) in p.iter().zip([0.3, 0.3, 0.4]) {
            assert!((a - b).abs() < 1e-14)
        }
    }
    #[test]
    fn unavailable_not_unreachable() {
        let m = model(3);
        let b = Boundary {
            time_s: 0.,
            node: "O".into(),
            incoming: None,
        };
        let d = m
            .decide(
                &m.initial(),
                &obs([f64::INFINITY; 5], 0., "origin"),
                &b,
                &pref(),
                "D",
                None,
                &[],
            )
            .unwrap()
            .1;
        assert_eq!(d.status, "NO_PERCEIVED_PATH");
    }
}
