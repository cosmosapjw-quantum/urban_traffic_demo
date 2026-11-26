//! Persistent f64 counterpart of active_suffix.routing.candidate_paths.
//! Link IDs are ranked lexicographically; heap ordering and expansion counting
//! preserve the Python oracle, including its loopless physical-node constraint.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet, VecDeque};

#[derive(Clone)]
struct Distance(f64, usize);
impl PartialEq for Distance {
    fn eq(&self, o: &Self) -> bool {
        self.0 == o.0 && self.1 == o.1
    }
}
impl Eq for Distance {}
impl Ord for Distance {
    fn cmp(&self, o: &Self) -> Ordering {
        o.0.partial_cmp(&self.0)
            .unwrap()
            .then_with(|| o.1.cmp(&self.1))
    }
}
impl PartialOrd for Distance {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}

#[derive(Clone)]
struct Candidate {
    estimate: f64,
    cost: f64,
    path: Vec<usize>,
    visited: Vec<String>,
}
impl PartialEq for Candidate {
    fn eq(&self, o: &Self) -> bool {
        self.estimate == o.estimate
            && self.cost == o.cost
            && self.path == o.path
            && self.visited == o.visited
    }
}
impl Eq for Candidate {}
impl Ord for Candidate {
    fn cmp(&self, o: &Self) -> Ordering {
        o.estimate
            .partial_cmp(&self.estimate)
            .unwrap()
            .then_with(|| o.cost.partial_cmp(&self.cost).unwrap())
            .then_with(|| o.path.cmp(&self.path))
            .then_with(|| o.visited.cmp(&self.visited))
    }
}
impl PartialOrd for Candidate {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}

#[cfg_attr(feature="python-extension", pyclass)]
pub struct V1RoutingGraph {
    ids: Vec<String>,
    heads: Vec<String>,
    costs: Vec<f64>,
    outgoing: HashMap<String, Vec<usize>>,
    successors: Vec<Vec<usize>>,
    predecessors: Vec<Vec<usize>>,
    potentials: HashMap<String, Vec<f64>>,
    lru: VecDeque<String>,
    max_destinations: usize,
    builds: usize,
}

impl V1RoutingGraph {
    fn potential(&mut self, destination: &str) -> Vec<f64> {
        if let Some(values) = self.potentials.get(destination) {
            self.lru.retain(|d| d != destination);
            self.lru.push_back(destination.to_owned());
            return values.clone();
        }
        self.builds += 1;
        let mut values = vec![f64::INFINITY; self.ids.len()];
        let mut heap = BinaryHeap::new();
        for (i, head) in self.heads.iter().enumerate() {
            if head == destination && self.costs[i].is_finite() {
                values[i] = self.costs[i];
                heap.push(Distance(values[i], i));
            }
        }
        while let Some(Distance(value, j)) = heap.pop() {
            if value != values[j] {
                continue;
            }
            for &i in &self.predecessors[j] {
                let alt = self.costs[i] + value;
                if alt < values[i] {
                    values[i] = alt;
                    heap.push(Distance(alt, i));
                }
            }
        }
        if self.max_destinations > 0 {
            if self.lru.len() == self.max_destinations {
                if let Some(old) = self.lru.pop_front() {
                    self.potentials.remove(&old);
                }
            }
            self.lru.push_back(destination.to_owned());
            self.potentials
                .insert(destination.to_owned(), values.clone());
        }
        values
    }
}

impl V1RoutingGraph {
    pub(crate) fn search_inner(
        &mut self,
        origin: &str,
        destination: &str,
        k: usize,
        expansion_budget: usize,
    ) -> Result<(Vec<Vec<String>>, usize, bool), String> {
        if k == 0 {
            return Err("invalid route search budget".to_owned());
        }
        let values = self.potential(destination);
        let mut heap = BinaryHeap::new();
        for &i in self.outgoing.get(origin).into_iter().flatten() {
            if values[i].is_finite() {
                heap.push(Candidate {
                    estimate: values[i],
                    cost: self.costs[i],
                    path: vec![i],
                    visited: vec![origin.to_owned(), self.heads[i].clone()],
                });
            }
        }
        let mut found = Vec::new();
        let mut expanded = 0;
        while !heap.is_empty() && expanded < expansion_budget && found.len() < k {
            let current = heap.pop().unwrap();
            expanded += 1;
            let i = *current.path.last().unwrap();
            if self.heads[i] == destination {
                found.push(current.path.iter().map(|&n| self.ids[n].clone()).collect());
                continue;
            }
            for &j in &self.successors[i] {
                if current.visited.contains(&self.heads[j]) || !values[j].is_finite() {
                    continue;
                }
                let mut path = current.path.clone();
                path.push(j);
                let mut visited = current.visited.clone();
                visited.push(self.heads[j].clone());
                heap.push(Candidate {
                    estimate: current.cost + values[j],
                    cost: current.cost + self.costs[j],
                    path,
                    visited,
                });
            }
        }
        let truncated = !heap.is_empty() && expanded >= expansion_budget && found.len() < k;
        Ok((found, expanded, truncated))
    }
}

crate::optional_binding::optional_pymethods!(V1RoutingGraph,
    [
    #[new]
    #[pyo3(signature = (arcs, costs, allowed_turns=None, max_destinations=8))]
    ] {
    pub(crate) fn new(
        arcs: Vec<(String, String, String)>,
        costs: Vec<f64>,
        allowed_turns: Option<Vec<(String, String)>>,
        max_destinations: usize,
    ) -> CoreResult<Self> {
        if arcs.len() != costs.len() {
            return Err(CoreError::value("one cost per arc required"));
        }
        if costs.iter().any(|v| v.is_nan() || *v < 0.0) {
            return Err(CoreError::value(
                "costs must be nonnegative seconds, +infinity means unavailable",
            ));
        }
        let mut rows: Vec<_> = arcs.into_iter().zip(costs).collect();
        rows.sort_by(|a, b| a.0 .0.cmp(&b.0 .0));
        if rows.windows(2).any(|w| w[0].0 .0 == w[1].0 .0) {
            return Err(CoreError::value("duplicate links"));
        }
        let ids: Vec<_> = rows.iter().map(|r| r.0 .0.clone()).collect();
        let heads: Vec<_> = rows.iter().map(|r| r.0 .2.clone()).collect();
        let costs = rows.iter().map(|r| r.1).collect();
        let mut outgoing: HashMap<String, Vec<usize>> = HashMap::new();
        for (i, r) in rows.iter().enumerate() {
            outgoing.entry(r.0 .1.clone()).or_default().push(i);
        }
        let allowed: Option<HashSet<_>> = allowed_turns.map(|v| v.into_iter().collect());
        let mut successors = vec![Vec::new(); rows.len()];
        let mut predecessors = vec![Vec::new(); rows.len()];
        for (i, row) in rows.iter().enumerate() {
            for &j in outgoing.get(&row.0 .2).into_iter().flatten() {
                let legal = match &allowed {
                    Some(a) => a.contains(&(ids[i].clone(), ids[j].clone())),
                    None => heads[j] != row.0 .1,
                };
                if legal {
                    successors[i].push(j);
                    predecessors[j].push(i);
                }
            }
        }
        Ok(Self {
            ids,
            heads,
            costs,
            outgoing,
            successors,
            predecessors,
            potentials: HashMap::new(),
            lru: VecDeque::new(),
            max_destinations,
            builds: 0,
        })
    }
    }
    [
    #[pyo3(signature = (origin, destination, k=3, expansion_budget=2000))]
    ] {


    #[cfg(feature="python-extension")]
    fn search(
        &mut self,
        py: Python<'_>,
        origin: &str,
        destination: &str,
        k: usize,
        expansion_budget: usize,
    ) -> CoreResult<(Vec<Vec<String>>, usize, bool)> {
        py.allow_threads(|| self.search_inner(origin, destination, k, expansion_budget))
            .map_err(CoreError::value)
    }
    }
    [
    #[getter]
    ] {


    fn cached_destinations(&self) -> Vec<String> {
        self.lru.iter().cloned().collect()
    }
    }
    [
    #[getter]
    ] {

    fn potential_builds(&self) -> usize {
        self.builds
    }
    }
    [
    #[pyo3(signature = (endpoints, k=3, expansion_budget=2000))]
    ] {


    #[cfg(feature="python-extension")]
    fn search_batch(
        &mut self,
        py: Python<'_>,
        endpoints: Vec<(String, String)>,
        k: usize,
        expansion_budget: usize,
    ) -> CoreResult<Vec<(Vec<Vec<String>>, usize, bool)>> {
        if k == 0 {
            return Err(CoreError::value("invalid route search budget"));
        }
        py.allow_threads(|| {
            endpoints
                .iter()
                .map(|(origin, destination)| {
                    self.search_inner(origin, destination, k, expansion_budget)
                })
                .collect::<Result<Vec<_>, String>>()
        })
        .map_err(CoreError::value)
    }
    }
);
