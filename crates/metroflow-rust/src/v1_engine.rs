//! Whole-calendar activation from native records and marginal frontend inputs.
//! Static declarations and all dynamic road/service/journey state stay in Rust.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
use crate::v1_calendar::NativeCalendar;
use crate::v1_journey::{
    advance_owned_joint, fsum, journey_debug, journey_dense_storage_bytes, journey_storage_bytes,
    service_dense_storage_bytes, service_event_storage_bytes, Journey, NativeJourneyCore,
    NativeServiceCore, ServiceCheckpoint, SharedBusMeta, SharedFreightMeta, SharedJourneyLeg,
    SharedLaw,
};
use crate::v1_parallel::ParallelPolicy;
use crate::v1_road::{RoadState, V1Road};
use crate::v1_routing::V1RoutingGraph;
#[cfg(feature="python-extension")]
use pyo3::types::PyDict;
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{BufReader, BufWriter, Read, Write};
use std::sync::Arc;
use std::time::Instant;

const ROUTE_OVERFLOW_BIN: usize = 256 + 56 * 128;
const OBSERVATION_RESERVE: usize = 64 * 1024 * 1024;
fn buffer_bytes<T>(values: &Vec<T>) -> usize {
    values
        .capacity()
        .saturating_mul(std::mem::size_of::<T>())
        .saturating_add(if values.capacity() == 0 { 0 } else { 128 })
}
fn string_bytes(value: &String) -> usize {
    value
        .capacity()
        .saturating_add(if value.capacity() == 0 { 0 } else { 128 })
}
/// Explicit conservative bucket/control and growth allowance, not an allocator
/// or RSS theorem. Vec/String payload capacities are counted separately.
fn map_workspace<K, V>(entries: usize) -> usize {
    if entries == 0 {
        return 0;
    }
    entries
        .saturating_mul(4)
        .saturating_mul(std::mem::size_of::<(K, V)>().saturating_add(1))
        .saturating_add(256)
}
#[derive(Default)]
struct RuntimeStorage {
    owned_static: usize,
    initial_road: usize,
    journey_dense: usize,
    service_dense: usize,
    call_binding: usize,
    worker_scratch: usize,
    service_prepare_scratch: usize,
    fixed_charge: usize,
}
impl RuntimeStorage {
    fn base(&self) -> usize {
        self.owned_static
            .saturating_add(self.initial_road)
            .saturating_add(self.journey_dense.saturating_mul(4))
            .saturating_add(self.service_dense.saturating_mul(6))
            .saturating_add(OBSERVATION_RESERVE)
            .saturating_add(self.worker_scratch)
            .saturating_add(self.service_prepare_scratch)
    }
}
struct NativeRouteMetrics {
    counts: Vec<usize>,
    calls: usize,
    failed: usize,
    cache_hits: usize,
    minimum_ns: Option<u128>,
    maximum_ns: Option<u128>,
}
impl NativeRouteMetrics {
    fn new() -> Self {
        Self {
            counts: vec![0; ROUTE_OVERFLOW_BIN + 1],
            calls: 0,
            failed: 0,
            cache_hits: 0,
            minimum_ns: None,
            maximum_ns: None,
        }
    }
    fn record(&mut self, ns: u128, failed: bool) {
        let index = if ns < 256 {
            ns as usize
        } else if ns >= 1u128 << 64 {
            ROUTE_OVERFLOW_BIN
        } else {
            let shift = (128 - ns.leading_zeros()) as usize - 8;
            256 + (shift - 1) * 128 + (ns >> shift) as usize - 128
        };
        self.counts[index] += 1;
        self.calls += 1;
        self.failed += usize::from(failed);
        self.minimum_ns = Some(self.minimum_ns.map_or(ns, |old| old.min(ns)));
        self.maximum_ns = Some(self.maximum_ns.map_or(ns, |old| old.max(ns)));
    }
    #[cfg(feature="python-extension")]
    fn report(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item(
            "status",
            if self.calls == 0 {
                "NOT_MEASURED"
            } else {
                "MEASURED_INTERVAL"
            },
        )?;
        out.set_item("observed_calls", self.calls)?;
        out.set_item("failed_calls", self.failed)?;
        out.set_item("pair_cache_hits", self.cache_hits)?;
        out.set_item("search_calls", self.calls - self.cache_hits)?;
        out.set_item("min_ns", self.minimum_ns)?;
        out.set_item("max_ns", self.maximum_ns)?;
        if self.calls > 0 {
            let rank = (99u128 * self.calls as u128 + 99) / 100;
            let mut cumulative = 0u128;
            let index = self
                .counts
                .iter()
                .position(|&count| {
                    cumulative += count as u128;
                    cumulative >= rank
                })
                .expect("nonempty route histogram");
            let (lower, upper) = if index < 256 {
                (index as u128, index as u128)
            } else if index == ROUTE_OVERFLOW_BIN {
                (1u128 << 64, self.maximum_ns.unwrap())
            } else {
                let shift = (index - 256) / 128 + 1;
                let offset = (index - 256) % 128;
                (
                    ((128 + offset) as u128) << shift,
                    (((129 + offset) as u128) << shift) - 1,
                )
            };
            let interval = PyDict::new(py);
            interval.set_item("lower", lower.max(self.minimum_ns.unwrap()))?;
            interval.set_item("upper", upper.min(self.maximum_ns.unwrap()))?;
            out.set_item("p99_ns", interval)?;
        } else {
            out.set_item("p99_ns", py.None())?;
        }
        out.set_item("histogram_bins", self.counts.len())?;
        out.set_item("overflow_samples", self.counts[ROUTE_OVERFLOW_BIN])?;
        out.set_item("nonsaturated_relative_bin_width_bound", 1.0 / 128.0)?;
        out.set_item(
            "quantile",
            "nearest rank ceil(0.99 * observed_calls), including failed requests",
        )?;
        out.set_item(
            "clock",
            "Rust std::time::Instant nanoseconds; timer overhead not subtracted",
        )?;
        out.set_item("source", "native_whole_router.route")?;
        out.set_item("scope", "native OD route API requests during successful whole-engine construction, including pair-cache hits; excludes frontend fixed-fleet routing and declared corridor paths")?;
        Ok(out.unbind())
    }
}

/// Per-leg stage mass, fed to `Sum` in the original row order (j.1, j.2, j.3).
/// Sorting the key (leg << 32 | global row index) in place groups rows by leg
/// while keeping their original order within each leg, so every leg receives
/// exactly the same `Sum::add` sequence as the former per-key HashMap entry.
/// Workspace: 16 bytes per stage row plus one dense f64 per leg; no map growth.
pub(crate) const STAGE_SUM_ROW_BYTES: usize = std::mem::size_of::<(u64, f64)>();
fn stage_sums(j: &Journey, legs: usize) -> CoreResult<Vec<f64>> {
    let rows = j.1.len() + j.2.len() + j.3.len();
    if legs > u32::MAX as usize || rows > u32::MAX as usize {
        return Err(bad("native stage validation index exceeds u32"));
    }
    let mut keyed: Vec<(u64, f64)> = Vec::new();
    keyed
        .try_reserve_exact(rows)
        .map_err(|_| CoreError::resource("native stage validation allocation failed"))?;
    let mut mass: Vec<f64> = Vec::new();
    mass.try_reserve_exact(legs)
        .map_err(|_| CoreError::resource("native stage validation allocation failed"))?;
    mass.resize(legs, 0.0);
    let mut row = 0u64;
    for part in [&j.1, &j.2, &j.3] {
        for a in part {
            if a.0 >= legs {
                return Err(bad("native stage row leg index differs"));
            }
            keyed.push((((a.0 as u64) << 32) | row, a.1));
            row += 1;
        }
    }
    keyed.sort_unstable_by_key(|e| e.0);
    let mut start = 0;
    while start < keyed.len() {
        let leg = (keyed[start].0 >> 32) as usize;
        let mut sum = Sum::default();
        let mut end = start;
        while end < keyed.len() && (keyed[end].0 >> 32) as usize == leg {
            sum.add(keyed[end].1);
            end += 1;
        }
        mass[leg] = sum.finish();
        start = end;
    }
    Ok(mass)
}

// Streaming expansion summation: retain exact low-order components until the
// final fsum rounding, without a vector per pending calendar record.
#[derive(Default)]
struct Sum {
    partials: Vec<f64>,
}
impl Sum {
    fn add(&mut self, mut x: f64) {
        let mut i = 0;
        for j in 0..self.partials.len() {
            let mut y = self.partials[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                self.partials[i] = lo;
                i += 1;
            }
            x = hi;
        }
        self.partials.truncate(i);
        if x != 0.0 {
            self.partials.push(x);
        }
    }
    fn finish(self) -> f64 {
        fsum(self.partials)
    }
}

type ActivityRow = (
    String,
    String,
    Option<String>,
    Option<String>,
    Vec<(f64, f64)>,
    Vec<(f64, f64)>,
    f64,
);
type Corridor = (String, String, String, f64, f64, f64);
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
fn io(e: std::io::Error) -> CoreError {
    CoreError::io(e.to_string())
}
#[cfg(feature="python-extension")]
fn field<'py, T: FromPyObject<'py>>(p: &Bound<'py, PyDict>, key: &str) -> PyResult<T> {
    p.get_item(key)?
        .ok_or_else(|| bad(format!("missing static field {key}")))?
        .extract()
}
#[cfg(feature="python-extension")]
fn stage_counts<'py>(py: Python<'py>, counts: &[usize; 4]) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    for (name, value) in ["entering", "egress", "internal", "receipts"]
        .into_iter()
        .zip(counts)
    {
        out.set_item(name, *value)?;
    }
    out.set_item("total_records", counts.iter().sum::<usize>())?;
    Ok(out)
}
#[cfg(feature="python-extension")]
fn stage_values<'py, T>(py: Python<'py>, values: [T; 3]) -> PyResult<Bound<'py, PyDict>>
where
    T: IntoPyObject<'py>,
    PyErr: From<T::Error>,
{
    let out = PyDict::new(py);
    for (name, value) in ["entering", "egress", "internal"].into_iter().zip(values) {
        out.set_item(name, value)?;
    }
    Ok(out)
}
#[derive(Clone)]
struct Activity {
    block: String,
    car: Option<String>,
    service: Option<String>,
    car_law: SharedLaw,
    service_law: SharedLaw,
    maximum: f64,
}
#[cfg_attr(feature = "native-cli", derive(serde::Deserialize))]
struct Static {
    identity: String,
    #[cfg_attr(feature = "native-cli", serde(rename = "city_identity"))]
    city: String,
    #[cfg_attr(feature = "native-cli", serde(rename = "schedule_identity"))]
    schedule: String,
    #[cfg_attr(feature = "native-cli", serde(rename = "step_s"))]
    step: f64,
    #[cfg_attr(feature = "native-cli", serde(rename = "record_budget"))]
    budget: usize,
    max_service_runs: usize,
    event_budget: Option<usize>,
    #[cfg_attr(feature = "native-cli", serde(rename = "preserve_entry_intervals"))]
    intervals: bool,
    activities: Vec<ActivityRow>,
    #[cfg_attr(feature = "native-cli", serde(rename = "intrazonal_laws"))]
    laws: Vec<(String, Vec<(f64, f64)>)>,
    groups: Vec<Vec<f64>>,
    signals: Vec<Option<(f64, f64, f64)>>,
    classes: Vec<Vec<f64>>,
    #[cfg_attr(feature = "native-cli", serde(rename = "class_names"))]
    names: Vec<String>,
    incoming: Vec<Vec<usize>>,
    windows: Vec<(usize, f64, f64, f64)>,
    #[cfg_attr(feature = "native-cli", serde(rename = "link_ids"))]
    links: Vec<String>,
    #[cfg_attr(feature = "native-cli", serde(rename = "route_arcs"))]
    arcs: Vec<(String, String, String)>,
    #[cfg_attr(feature = "native-cli", serde(rename = "route_costs"))]
    costs: Vec<(String, f64)>,
    #[cfg_attr(feature = "native-cli", serde(rename = "allowed_turns"))]
    turns: Vec<(String, String)>,
    corridors: Vec<Corridor>,
    corridor_routes: Vec<(String, Vec<String>)>,
    #[cfg_attr(feature = "native-cli", serde(rename = "depot_block_id"))]
    depot: Option<String>,
    #[cfg_attr(feature = "native-cli", serde(rename = "depot_node_or_None"))]
    depot_node: Option<String>,
}
impl Static {
    #[cfg(feature="python-extension")]
    fn read(p: &Bound<'_, PyDict>) -> PyResult<Self> {
        if field::<String>(p, "schema")? != "native_calendar_static_v1" {
            return Err(bad("static schema differs").into());
        }
        Ok(Self {
            identity: field(p, "identity")?,
            city: field(p, "city_identity")?,
            schedule: field(p, "schedule_identity")?,
            step: field(p, "step_s")?,
            budget: field(p, "record_budget")?,
            max_service_runs: field(p, "max_service_runs")?,
            event_budget: field(p, "event_budget")?,
            intervals: field(p, "preserve_entry_intervals")?,
            activities: field(p, "activities")?,
            laws: field(p, "intrazonal_laws")?,
            groups: field(p, "groups")?,
            signals: field(p, "signals")?,
            classes: field(p, "classes")?,
            names: field(p, "class_names")?,
            incoming: field(p, "incoming")?,
            windows: field(p, "windows")?,
            links: field(p, "link_ids")?,
            arcs: field(p, "route_arcs")?,
            costs: field(p, "route_costs")?,
            turns: field(p, "allowed_turns")?,
            corridors: field(p, "corridors")?,
            corridor_routes: field(p, "corridor_routes")?,
            depot: field(p, "depot_block_id")?,
            depot_node: field(p, "depot_node_or_None")?,
        })
    }
}
struct Router {
    metrics: NativeRouteMetrics,
    graph: V1RoutingGraph,
    link_indices: HashMap<String, usize>,
    pairs: HashMap<(String, String), Option<usize>>,
    paths: Vec<Vec<usize>>,
    path_indices: HashMap<Vec<usize>, usize>,
    estimated: usize,
    budget: usize,
}
impl Router {
    fn intern(&mut self, path: Vec<usize>) -> CoreResult<usize> {
        if let Some(&i) = self.path_indices.get(&path) {
            return Ok(i);
        }
        self.estimated = self.estimated.saturating_add(path.len() * 16 + 256);
        if self.estimated > self.budget {
            return Err(CoreError::resource(
                "whole-calendar route storage budget exceeded; no demand omitted",
            ));
        }
        let i = self.paths.len();
        self.path_indices.insert(path.clone(), i);
        self.paths.push(path);
        Ok(i)
    }
    fn declared(&mut self, links: &[String]) -> CoreResult<usize> {
        let path = links
            .iter()
            .map(|x| {
                self.link_indices
                    .get(x)
                    .copied()
                    .ok_or_else(|| bad("unknown route link"))
            })
            .collect::<CoreResult<Vec<_>>>()?;
        if path.is_empty() {
            return Err(bad("empty registered route"));
        }
        self.intern(path)
    }
    fn route(&mut self, a: &str, b: &str) -> CoreResult<Option<usize>> {
        let started = Instant::now();
        let result = self.route_inner(a, b);
        self.metrics
            .record(started.elapsed().as_nanos(), result.is_err());
        result
    }
    fn route_inner(&mut self, a: &str, b: &str) -> CoreResult<Option<usize>> {
        let key = (a.to_owned(), b.to_owned());
        if let Some(v) = self.pairs.get(&key) {
            self.metrics.cache_hits += 1;
            return Ok(*v);
        }
        let (found, _, _) = self.graph.search_inner(a, b, 1, 2000).map_err(bad)?;
        let value = if let Some(path) = found.first().filter(|p| !p.is_empty()) {
            Some(self.declared(path)?)
        } else {
            None
        };
        self.estimated = self.estimated.saturating_add(a.len() + b.len() + 128);
        if self.estimated > self.budget {
            return Err(CoreError::resource(
                "whole-calendar route cache budget exceeded; no demand omitted",
            ));
        }
        self.pairs.insert(key, value);
        Ok(value)
    }
}
#[derive(Clone)]
struct Bundle {
    road: RoadState,
    service: ServiceCheckpoint,
    journey: Journey,
}
#[cfg_attr(feature="python-extension", pyclass(frozen))]
#[derive(Clone)]
pub struct NativeWholeState {
    identity: String,
    value: Arc<Bundle>,
}
crate::optional_binding::optional_pymethods!(NativeWholeState,
    [
    #[getter]
    ] {
    fn time_s(&self) -> f64 {
        self.value.journey.0
    }
    }
    [
    #[getter]
    ] {

    fn model_identity(&self) -> String {
        self.identity.clone()
    }
    }
);
#[cfg_attr(feature="python-extension", pyclass)]
pub struct NativeWholeEngine {
    parallel: ParallelPolicy,
    route_metrics: NativeRouteMetrics,
    storage_policy: String,
    road_storage_bytes: Option<usize>,
    journey_storage_bytes: Option<usize>,
    runtime_storage: Option<RuntimeStorage>,
    identity: String,
    city: String,
    schedule: String,
    step: f64,
    road: V1Road,
    service: NativeServiceCore,
    journey: NativeJourneyCore,
    tags: Vec<String>,
    amounts: Vec<[f64; 3]>,
    profile_ids: Vec<usize>,
    profiles: Vec<Arc<Vec<(f64, f64, f64)>>>,
    totals: [f64; 3],
    unassigned: [f64; 3],
    unsupported: usize,
    supported: [usize; 3],
    passenger_available: Vec<f64>,
    freight_cargo: Vec<f64>,
    freight_vehicles: Vec<f64>,
    class_names: Vec<String>,
    initial_state: Arc<Bundle>,
    estimated_bytes: usize,
    byte_budget: usize,
    unique_paths: usize,
    event_limit: usize,
    group_count: usize,
    car_tag_legs: Vec<Option<usize>>,
}
fn fraction(profile: &[(f64, f64, f64)], end: f64) -> f64 {
    fsum(
        profile
            .iter()
            .map(|&(a, b, p)| p * (end.min(b) - a.max(0.0)).max(0.0) / (b - a)),
    )
}
fn moment(profile: &[(f64, f64, f64)], start: f64, end: f64) -> f64 {
    fsum(profile.iter().map(|&(a, b, p)| {
        let lo = a.max(start);
        let hi = b.min(end);
        if hi > lo {
            p * (hi - lo) * (lo + hi) / (2.0 * (b - a))
        } else {
            0.0
        }
    }))
}
/// A planned road capture only allocates a new outer RoadState shell;
/// all its immutable Arc<Vec<_>> packet row payload allocations remain
/// physically pointer-shared with the current committed road state.
/// This credits only one physically omitted copy of the same unique rows
/// inside the preexisting 3*max owner envelope, never metadata or old source.
fn capture_road_clone_credit(
    current_retained:usize,unique_immutable_payload:usize,
    validates_future_capture:bool,has_original_input:bool,
)->usize {
    if validates_future_capture && has_original_input {
        unique_immutable_payload.min(current_retained)
    } else {0}
}

impl NativeWholeEngine {
    fn build(
        calendar: &NativeCalendar,
        s: Static,
        byte_budget: usize,
        parallel: ParallelPolicy,
        storage_policy: String,
    ) -> CoreResult<Self> {
        let (city, schedule) = calendar.owned_binding();
        if city != s.city
            || schedule != s.schedule
            || !s.step.is_finite()
            || s.step <= 0.0
            || s.budget == 0
            || s.max_service_runs == 0
        {
            return Err(bad("whole-calendar binding or step differs"));
        }
        let n = calendar.owned_legs().len();
        // Conservative persistent+construction/snapshot allowance, not an RSS cap.
        // The runner must additionally enforce a process address-space bound.
        let estimate = n
            .saturating_mul(896)
            .saturating_add(calendar.owned_bytes())
            .saturating_add(64 * 1024 * 1024);
        if estimate > byte_budget {
            return Err(CoreError::resource(format!(
            "whole-calendar native preflight needs at least {estimate} accounting bytes, budget {byte_budget}; no demand omitted")));
        }
        let labels: HashMap<&str, usize> = calendar
            .owned_labels()
            .iter()
            .enumerate()
            .map(|(i, x)| (x.as_str(), i))
            .collect();
        let empty = Arc::new(Vec::new());
        let zero = Arc::new(vec![(0.0, 1.0)]);
        let mut activities: HashMap<usize, Activity> = HashMap::new();
        for (label, block, car, service, car_law, service_law, maximum) in s.activities {
            if let Some(&id) = labels.get(label.as_str()) {
                activities.insert(
                    id,
                    Activity {
                        block,
                        car,
                        service,
                        car_law: Arc::new(car_law),
                        service_law: Arc::new(service_law),
                        maximum,
                    },
                );
            }
        }
        let mut laws: HashMap<usize, SharedLaw> = HashMap::new();
        for (label, law) in s.laws {
            if let Some(&id) = labels.get(label.as_str()) {
                laws.insert(id, Arc::new(law));
            }
        }
        let profiles: Vec<_> = calendar
            .owned_profiles()
            .iter()
            .cloned()
            .map(Arc::new)
            .collect();
        let indices: HashMap<_, _> = s
            .links
            .iter()
            .enumerate()
            .map(|(i, x)| (x.clone(), i))
            .collect();
        let costs: HashMap<_, _> = s.costs.into_iter().collect();
        let ordered_costs = s
            .arcs
            .iter()
            .map(|a| {
                costs
                    .get(&a.0)
                    .copied()
                    .ok_or_else(|| bad("route cost missing"))
            })
            .collect::<CoreResult<Vec<_>>>()?;
        let mut router = Router {
            metrics: NativeRouteMetrics::new(),
            graph: V1RoutingGraph::new(s.arcs, ordered_costs, Some(s.turns), 8)?,
            link_indices: indices,
            pairs: HashMap::new(),
            paths: Vec::new(),
            path_indices: HashMap::new(),
            estimated: estimate,
            budget: byte_budget,
        };
        let class_index: HashMap<_, _> = s
            .names
            .iter()
            .enumerate()
            .map(|(i, x)| (x.as_str(), i))
            .collect();
        let car_class = *class_index
            .get("car")
            .ok_or_else(|| bad("car class missing"))?;
        let bus_class = *class_index
            .get("scheduled_bus")
            .ok_or_else(|| bad("bus class missing"))?;
        let freight_class = *class_index
            .get("freight")
            .ok_or_else(|| bad("freight class missing"))?;
        let corridor_paths: HashMap<_, _> = s.corridor_routes.into_iter().collect();
        let mut routes: Vec<(String, usize, usize, Option<usize>)> = Vec::new();
        let mut buses = Vec::new();
        let mut corridors_by_blocks: HashMap<(String, String), Vec<usize>> = HashMap::new();
        if s.corridors.len() > s.max_service_runs {
            return Err(CoreError::resource(
                "fixed fleet run budget exceeded; no demand omitted",
            ));
        }
        for (k, b) in s.corridors.iter().enumerate() {
            let path = router.declared(
                corridor_paths
                    .get(&b.0)
                    .ok_or_else(|| bad("corridor route missing"))?,
            )?;
            routes.push((format!("bus:{}:0", b.0), path, bus_class, None));
            buses.push((b.0.clone(), vec![b.3], b.4, b.5));
            corridors_by_blocks
                .entry((b.1.clone(), b.2.clone()))
                .or_default()
                .push(k);
        }
        let mut legs: Vec<SharedJourneyLeg> = Vec::with_capacity(n);
        let mut bus_meta: Vec<SharedBusMeta> = Vec::new();
        let mut freight_meta: Vec<SharedFreightMeta> = Vec::new();
        let mut people = Vec::new();
        let mut freight = Vec::new();
        let mut freight_cargo = Vec::new();
        let mut freight_vehicles = Vec::new();
        let mut passenger_available = Vec::new();
        let mut amounts = Vec::with_capacity(n);
        let mut profile_ids = Vec::with_capacity(n);
        let mut totals = [0.0; 3];
        let mut unassigned = [0.0; 3];
        let mut unsupported = 0;
        let mut supported = [0usize; 3];
        let mut convolution: HashMap<(usize, usize), SharedLaw> = HashMap::new();
        let mut helper_required = false;
        let mut pending_sums = [Sum::default(), Sum::default(), Sum::default()];
        for (i, leg) in calendar.owned_legs().iter().enumerate() {
            let id = calendar
                .text(leg.id)
                .ok_or_else(|| bad("calendar leg ID absent"))?;
            if id == "__joint_clock__" {
                return Err(bad("reserved joint clock route label"));
            }
            let m = leg.metadata;
            let mode = calendar.owned_labels()[m[3] as usize].as_str();
            let endpoint = calendar.owned_labels()[m[7] as usize].as_str();
            helper_required |=
                mode == "\"car\"" || (mode == "\"noncar\"" && endpoint == "\"intrazonal\"");
            let origin = activities.get(&(m[0] as usize));
            let destination = activities.get(&(m[1] as usize));
            if (origin.is_none() && calendar.owned_labels()[m[0] as usize] != "null")
                || (destination.is_none() && calendar.owned_labels()[m[1] as usize] != "null")
            {
                return Err(bad(
                    "calendar activity missing from marginal payload; no demand omitted",
                ));
            }
            let profile = profiles
                .get(m[5] as usize)
                .ok_or_else(|| bad("calendar profile missing"))?;
            let mut kind = 0;
            let mut origin_law = empty.clone();
            let mut destination_law = empty.clone();
            if endpoint == "\"intrazonal\"" && (mode == "\"car\"" || mode == "\"noncar\"") {
                kind = 2;
                origin_law = laws
                    .get(&(m[6] as usize))
                    .ok_or_else(|| bad("intrazonal law missing from marginal payload"))?
                    .clone();
                destination_law = zero.clone();
            } else if mode == "\"car\"" && endpoint == "\"interzonal\"" {
                if let (Some(a), Some(b)) = (origin, destination) {
                    if let (Some(an), Some(bn)) = (&a.car, &b.car) {
                        if an == bn {
                            let key = (m[0] as usize, m[1] as usize);
                            if let Some(law) = convolution.get(&key) {
                                origin_law = law.clone();
                            } else {
                                let mut atoms: Vec<(f64, f64)> = Vec::new();
                                for &(x, wx) in a.car_law.iter() {
                                    for &(y, wy) in b.car_law.iter() {
                                        if let Some(v) = atoms.iter_mut().find(|v| v.0 == x + y) {
                                            v.1 += wx * wy;
                                        } else {
                                            atoms.push((x + y, wx * wy));
                                        }
                                    }
                                }
                                atoms.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
                                if atoms.len() > s.budget {
                                    return Err(CoreError::resource(
                                        "co-located access law exceeds budget",
                                    ));
                                }
                                origin_law = Arc::new(atoms);
                                convolution.insert(key, origin_law.clone());
                            }
                            kind = 2;
                            destination_law = zero.clone();
                        } else if let Some(path) = router.route(an, bn)? {
                            kind = 1;
                            origin_law = a.car_law.clone();
                            destination_law = b.car_law.clone();
                            routes.push((id.clone(), path, car_class, Some(i)));
                        }
                    }
                }
            }
            let mut assigned = false;
            let mut pending_fractions = Vec::new();
            if leg.parent.is_some() && mode != "\"bus\"" {
                pending_fractions.push(1.0);
            } else if mode == "\"bus\"" && origin.is_some() && destination.is_some() {
                let a = origin.unwrap();
                let b = destination.unwrap();
                if a.service.is_none() || b.service.is_none() {
                    pending_fractions.push(1.0);
                } else {
                    let candidates = corridors_by_blocks.get(&(a.block.clone(), b.block.clone()));
                    for &(start, end, p) in profile.iter() {
                        let ready = end + a.maximum;
                        let earliest = candidates
                            .into_iter()
                            .flatten()
                            .filter(|&&k| s.corridors[k].3 >= ready)
                            .map(|&k| s.corridors[k].3)
                            .fold(f64::INFINITY, f64::min);
                        let tied: Vec<usize> = candidates
                            .into_iter()
                            .flatten()
                            .copied()
                            .filter(|&k| s.corridors[k].3 == earliest)
                            .collect();
                        if tied.is_empty() {
                            pending_fractions.push(p);
                            continue;
                        }
                        let persons = leg.amounts[0] * p / tied.len() as f64;
                        for k in tied.iter().copied() {
                            if people.len() + freight.len() + buses.len() >= s.max_service_runs {
                                return Err(CoreError::resource(
                                    "service record budget exceeded; no demand omitted",
                                ));
                            }
                            people.push((k, 0, 1, ready, persons));
                            passenger_available.push(ready);
                            bus_meta.push((
                                i,
                                leg.amounts[0],
                                persons,
                                leg.amounts[0] * moment(profile, start, end) / tied.len() as f64,
                                fraction(profile, end),
                                b.service_law.clone(),
                            ));
                            assigned = true;
                        }
                    }
                }
            } else if mode == "\"freight\"" && destination.is_some() {
                let b = destination.unwrap();
                let path = match (&s.depot, &s.depot_node, &b.service) {
                    (Some(block), Some(a), Some(node)) if block != &b.block => {
                        router.route(a, node)?
                    }
                    _ => None,
                };
                if let Some(path) = path {
                    for (window, &(start, end, p)) in profile.iter().enumerate() {
                        let vehicles = leg.amounts[1] * p;
                        let cargo = leg.amounts[2] * p;
                        if vehicles == 0.0 {
                            if cargo != 0.0 {
                                return Err(bad("cargo requires positive freight vehicle amount"));
                            }
                            continue;
                        }
                        if cargo > 2000.0 * vehicles {
                            return Err(bad("freight payload capacity exceeded"));
                        }
                        if people.len() + freight.len() + buses.len() >= s.max_service_runs {
                            return Err(CoreError::resource(
                                "service record budget exceeded; no demand omitted",
                            ));
                        }
                        let name = format!("{id}:{window}");
                        routes.push((format!("freight:{name}"), path, freight_class, None));
                        freight.push((name, end, vehicles));
                        freight_cargo.push(cargo);
                        freight_vehicles.push(vehicles);
                        freight_meta.push((
                            i,
                            vehicles,
                            leg.amounts[1] * moment(profile, start, end),
                            b.service_law.clone(),
                        ));
                        assigned = true;
                    }
                } else {
                    pending_fractions.push(1.0);
                }
            } else {
                pending_fractions.push(1.0);
            }
            for p in pending_fractions {
                for j in 0..3 {
                    pending_sums[j].add(leg.amounts[j] * p);
                }
            }
            if kind == 0 && !assigned {
                unsupported += 1;
            }
            supported[kind as usize] += 1;
            let carrier = if leg.amounts[1] != 0.0 {
                leg.amounts[1]
            } else {
                leg.amounts[0]
            };
            legs.push((
                id,
                carrier,
                leg.parent.map(|p| p as usize),
                leg.dwell,
                profile.clone(),
                kind,
                origin_law,
                destination_law,
            ));
            amounts.push(leg.amounts);
            profile_ids.push(m[5] as usize);
            // Both declared service-record and native byte budgets apply.
            if (people.len() + freight.len())
                .saturating_mul(512)
                .saturating_add(router.estimated)
                > byte_budget
            {
                return Err(CoreError::resource(
                    "whole-calendar service allocation budget exceeded; no demand omitted",
                ));
            }
        }
        if helper_required && supported[1] + supported[2] == 0 {
            return Err(bad("no supported route or internal delay in bounded set; BLOCKED_IMPLEMENTATION_DEPENDENCY"));
        }
        for j in 0..3 {
            totals[j] = fsum(amounts.iter().map(|a| a[j]));
        }
        for (j, sum) in pending_sums.into_iter().enumerate() {
            unassigned[j] = sum.finish();
        }
        if routes.is_empty() {
            let path = router.intern(vec![0])?;
            routes.push(("__joint_clock__".to_owned(), path, car_class, None));
        }
        routes.sort_by(|a, b| a.0.cmp(&b.0));
        if routes.windows(2).any(|r| r[0].0 == r[1].0) {
            return Err(bad("duplicate native physical route tag"));
        }
        let mut tags = Vec::with_capacity(routes.len());
        let mut road_routes = Vec::with_capacity(routes.len());
        let mut car_tag_legs = Vec::with_capacity(routes.len());
        for (tag, path, class, leg) in routes {
            tags.push(tag);
            road_routes.push((path, class));
            car_tag_legs.push(leg);
        }
        let unique_paths = router.paths.len();
        let estimated_bytes = router.estimated + (people.len() + freight.len()) * 512;
        let mut identity = format!("native-whole-v1:{}:{}", s.identity, byte_budget);
        let group_count = s.groups.len();
        let mut road = V1Road::new_shared_routes(
            identity.clone(),
            s.step,
            s.groups,
            s.signals,
            router.paths,
            road_routes,
            s.classes,
            s.incoming,
            s.windows,
            s.budget,
            s.event_budget,
            s.intervals,
        )?;
        let service = NativeServiceCore::new(buses, people, freight, Vec::new())?;
        let mut journey = NativeJourneyCore::new_shared(legs, bus_meta, freight_meta, s.budget)?;
        let runtime_storage = if storage_policy == "bounded_bytes_v1" {
            let strings = |values: &Vec<String>| {
                values.iter().fold(buffer_bytes(values), |bytes, value| {
                    bytes.saturating_add(string_bytes(value))
                })
            };
            // Journey accounts shared laws/profiles reachable from its legs.
            // The engine also retains unused interned calendar profiles.
            let mut unused: HashSet<usize> =
                profiles.iter().map(|p| Arc::as_ptr(p) as usize).collect();
            for leg in journey.legs() {
                unused.remove(&(Arc::as_ptr(&leg.4) as usize));
            }
            let unused_profiles = profiles
                .iter()
                .filter(|p| unused.contains(&(Arc::as_ptr(p) as usize)))
                .fold(0usize, |bytes, p| {
                    bytes.saturating_add(buffer_bytes(p)).saturating_add(
                        std::mem::size_of::<Vec<(f64, f64, f64)>>()
                            + 2 * std::mem::size_of::<usize>()
                            + 128,
                    )
                });
            let owned_static = std::mem::size_of::<Self>()
                .saturating_add(
                    std::mem::size_of::<Bundle>() + 2 * std::mem::size_of::<usize>() + 128,
                )
                .saturating_add(road.static_storage_bytes())
                .saturating_add(journey.static_storage_bytes())
                .saturating_add(service.static_storage_bytes())
                .saturating_add(strings(&tags))
                .saturating_add(strings(&s.names))
                .saturating_add(buffer_bytes(&amounts))
                .saturating_add(buffer_bytes(&profile_ids))
                .saturating_add(buffer_bytes(&profiles))
                .saturating_add(unused_profiles)
                .saturating_add(buffer_bytes(&car_tag_legs))
                .saturating_add(buffer_bytes(&passenger_available))
                .saturating_add(buffer_bytes(&freight_cargo))
                .saturating_add(buffer_bytes(&freight_vehicles))
                .saturating_add(buffer_bytes(&router.metrics.counts))
                .saturating_add(string_bytes(&s.city))
                .saturating_add(string_bytes(&s.schedule))
                .saturating_add(string_bytes(&storage_policy))
                // Final policy suffix and known snapshot identity strings can
                // grow after the empty owners have been constructed.
                .saturating_add(identity.len().saturating_mul(8).saturating_add(1024));
            let call_binding = tags
                .iter()
                .fold(map_workspace::<String, usize>(tags.len()), |bytes, tag| {
                    bytes.saturating_add(tag.capacity()).saturating_add(128)
                });
            let mut accounting = RuntimeStorage {
                owned_static,
                initial_road: road.owned_storage_bytes(),
                journey_dense: journey_dense_storage_bytes(journey.state()),
                service_dense: service_dense_storage_bytes(service.state()),
                call_binding,
                worker_scratch: journey
                    .per_worker_scratch_bytes()
                    .saturating_mul(parallel.threads()),
                service_prepare_scratch: service.prepare_scratch_bytes(),
                fixed_charge: 0,
            };
            accounting.fixed_charge = accounting.base().saturating_add(call_binding);
            Some(accounting)
        } else {
            None
        };
        let (road_storage_bytes, journey_storage_bytes) = if let Some(accounting) = &runtime_storage
        {
            let available = byte_budget.checked_sub(accounting.fixed_charge).ok_or_else(||
                CoreError::resource("native retained storage and concurrent dense reserve exceed accounting budget"))?;
            // These are ceilings on a shared pool, never additive reservations.
            // advance_owned_joint subtracts the other owners at each phase.
            (Some(available), Some(available))
        } else {
            (None, None)
        };
        if let (Some(road_bytes), Some(journey_bytes)) = (road_storage_bytes, journey_storage_bytes)
        {
            identity.push_str(":bounded_bytes_v1:retained_capacity_v3");
            road.bind_storage_identity(identity.clone())?;
            road.configure_storage_budget(road_bytes)?;
            journey.configure_storage_budget(journey_bytes)?;
        }
        let event_limit = road.checkpoint_event_limit();
        let initial_state = Arc::new(Bundle {
            road: road.checkpoint(),
            service: service.checkpoint(),
            journey: journey.checkpoint(),
        });
        Ok(Self {
            parallel,
            route_metrics: router.metrics,
            storage_policy,
            road_storage_bytes,
            journey_storage_bytes,
            runtime_storage,
            identity,
            city: s.city,
            schedule: s.schedule,
            step: s.step,
            road,
            service,
            journey,
            tags,
            amounts,
            profile_ids,
            profiles,
            totals,
            unassigned,
            unsupported,
            supported,
            passenger_available,
            freight_cargo,
            freight_vehicles,
            class_names: s.names,
            initial_state,
            estimated_bytes,
            byte_budget,
            unique_paths,
            event_limit,
            group_count,
            car_tag_legs,
        })
    }
    fn reset_phase_ceilings(&mut self) -> CoreResult<()> {
        if let Some(pool) = self.road_storage_bytes {
            self.road.set_phase_storage_budget(pool)?;
            self.journey.set_phase_storage_budget(pool)?;
            self.road.clear_call_storage_accounting();
            self.journey.clear_call_storage_accounting();
        }
        Ok(())
    }
    fn pool_after(&self, reserved: usize, phase: &str) -> CoreResult<usize> {
        let pool = self.road_storage_bytes.unwrap_or(usize::MAX);
        pool.checked_sub(reserved).filter(|n| *n > 0).ok_or_else(||
            CoreError::resource(format!("native shared storage budget exhausted before {phase}: reserved_bytes={reserved}, pool_bytes={pool}")))
    }
    fn validation_scratch(&self, j: &Journey, road_rows: usize) -> usize {
        self.journey
            .whole_validation_scratch_bytes(j, road_rows, self.tags.len())
    }
    fn storage_admission(
        &self,
        j: &Journey,
        road_bytes: usize,
        road_rows: usize,
        event_bytes: usize,
        input: Option<&Bundle>,
        validate: bool,
    ) -> CoreResult<()> {
        let Some(accounting) = &self.runtime_storage else {
            return Ok(());
        };
        let mut r = road_bytes.max(self.road.owned_storage_bytes());
        let mut d = journey_storage_bytes(j).max(journey_storage_bytes(self.journey.state()));
        let mut e = event_bytes.max(self.service.event_storage_bytes());
        if let Some(input) = input {
            r = r.max(input.road.retained_storage_bytes());
            d = d.max(journey_storage_bytes(&input.journey));
            e = e.max(service_event_storage_bytes(&input.service));
        }
        let scratch = if validate {
            self.validation_scratch(j, road_rows)
        } else {
            0
        };
        let captured_arc_credit=capture_road_clone_credit(
            self.road.owned_storage_bytes(),
            if validate && input.is_some() {
                self.road.owned_unique_immutable_arc_payload_bytes()
            }else{0},
            validate,input.is_some(),
        );
        crate::v1_trace::add("engine_admission.verified_future_capture_arc_credit",
            captured_arc_credit as u64);
        let required = accounting
            .base()
            .saturating_add(accounting.call_binding.max(scratch))
            .saturating_add(r.saturating_mul(3))
            .saturating_sub(captured_arc_credit)
            .saturating_add(d.saturating_mul(3))
            .saturating_add(e.saturating_mul(3));
        let observed = crate::v1_trace::guard(
            "engine_admission",
            if validate {
                "capture/validation"
            } else {
                "capture"
            },
            required,
            self.byte_budget,
            &[
                ("fixed_base", accounting.base()),
                ("call_binding", accounting.call_binding),
                ("validation_scratch", scratch),
                ("road", r),
                ("verified_future_capture_arc_credit",captured_arc_credit),
                ("road_3max_without_credit",r.saturating_mul(3)),
                ("journey", d),
                ("events", e),
            ],
        );
        if required > self.byte_budget && !observed {
            return Err(CoreError::resource(format!(
                "native capture/validation storage budget exceeded: required_bytes={required}, budget_bytes={}",self.byte_budget)));
        }
        Ok(())
    }
    fn load_validation_admission(&self, decoded: &Bundle, road_rows: usize) -> CoreResult<()> {
        let Some(accounting) = &self.runtime_storage else {
            return Ok(());
        };
        let current_bytes = self.road.owned_storage_bytes()
            .saturating_add(journey_storage_bytes(self.journey.state()))
            .saturating_add(self.service.event_storage_bytes());
        let decoded_bytes = decoded.road.retained_storage_bytes()
            .saturating_add(journey_storage_bytes(&decoded.journey))
            .saturating_add(service_event_storage_bytes(&decoded.service));
        let scratch = self.validation_scratch(&decoded.journey, road_rows);
        // Validation borrows the decoded owners. The install clone is only
        // admitted after validation drops scratch, using restore's own guard.
        let required = accounting.base()
            .saturating_add(accounting.call_binding.max(scratch))
            .saturating_add(current_bytes)
            .saturating_add(decoded_bytes);
        let observed = crate::v1_trace::guard(
            "engine_admission",
            "load validation",
            required,
            self.byte_budget,
            &[
                ("fixed_base", accounting.base()),
                ("call_binding", accounting.call_binding),
                ("validation_scratch", scratch),
                ("current_dynamic", current_bytes),
                ("decoded_dynamic", decoded_bytes),
            ],
        );
        if required > self.byte_budget && !observed {
            return Err(CoreError::resource(format!(
                "native load validation storage budget exceeded: required_bytes={required}, budget_bytes={}", self.byte_budget
            )));
        }
        Ok(())
    }
    fn validate_bundle(&self, b: &Bundle) -> CoreResult<()> {
        if b.road.time() != b.journey.0 {
            return Err(bad("checkpoint owner clocks differ"));
        }
        self.journey
            .check_service_binding(&b.journey, &b.service.0)?;
        let time = b.journey.0;
        for e in b.service.1.iter() {
            if e.0 >= self.tags.len()
                || e.1 >= self.group_count
                || e.2.is_some_and(|i| i >= self.group_count)
                || e.3 <= 0.0
                || e.4 > e.5
                || e.5 > time + 1e-8
            {
                return Err(bad("native checkpoint road event binding differs"));
            }
        }
        let j = &b.journey;
        let service = &b.service.0;
        let stages = stage_sums(j, self.journey.legs().len())?;
        let mut active: HashMap<usize, f64> = HashMap::new();
        for (tag, mass) in b.road.active_by_tag() {
            if let Some(i) = self.car_tag_legs[tag] {
                active.insert(i, mass);
            }
        }
        for (i, leg) in self.journey.legs().iter().enumerate() {
            if leg.5 == 1 || leg.5 == 2 {
                let mass = stages[i] + active.get(&i).copied().unwrap_or(0.0);
                if (j.4[i] - j.5[i] - mass).abs() > 1e-9 * leg.1.max(1.0) {
                    return Err(bad("joint calendar stage and physical ledger differ"));
                }
            }
        }
        let (_, classes) = b.road.summary();
        let check_class = |name: &str, admitted: f64, outlet: f64| -> CoreResult<()> {
            let k = self
                .class_names
                .iter()
                .position(|n| n == name)
                .ok_or_else(|| bad("native physical class missing"))?;
            if (admitted - classes[k][0]).abs() > 1e-9 * classes[k][0].max(1.0)
                || (outlet - classes[k][1]).abs() > 1e-9 * classes[k][1].max(1.0)
            {
                return Err(bad(format!(
                    "joint {name} calendar and physical class ledger differ"
                )));
            }
            Ok(())
        };
        let legs = self.journey.legs();
        let car_released = fsum(
            legs.iter()
                .enumerate()
                .filter(|(_, l)| l.5 == 1)
                .map(|(i, _)| j.4[i]),
        ) - fsum(j.1.iter().map(|a| a.1));
        let car_completed = fsum(
            legs.iter()
                .enumerate()
                .filter(|(_, l)| l.5 == 1)
                .map(|(i, _)| j.5[i]),
        ) + fsum(j.2.iter().filter(|a| legs[a.0].5 == 1).map(|a| a.1));
        check_class("car", car_released, car_completed)?;
        check_class(
            "freight",
            fsum(
                self.freight_vehicles
                    .iter()
                    .zip(&service.2)
                    .filter(|(_, released)| **released)
                    .map(|(v, _)| *v),
            ),
            fsum(service.3.iter().copied()),
        )?;
        check_class(
            "scheduled_bus",
            fsum(
                service
                    .0
                    .iter()
                    .map(|r| r.0 as f64 + if r.1 == 1 { 1.0 } else { 0.0 }),
            ),
            fsum(
                service
                    .0
                    .iter()
                    .map(|r| r.0 as f64 + if r.1 == 1 { r.3 } else { 0.0 }),
            ),
        )?;
        Ok(())
    }
    fn checked(&self, state: &NativeWholeState) -> CoreResult<()> {
        if state.identity != self.identity {
            Err(bad("native whole checkpoint model binding differs"))
        } else {
            Ok(())
        }
    }
    fn restore(&mut self, state: &NativeWholeState) -> CoreResult<()> {
        self.checked(state)?;
        self.reset_phase_ceilings()?;
        self.storage_admission(
            &state.value.journey,
            state.value.road.retained_storage_bytes(),
            0,
            service_event_storage_bytes(&state.value.service),
            None,
            false,
        )?;
        self.road.rollback(state.value.road.clone());
        self.service.rollback(state.value.service.clone());
        self.journey.rollback(state.value.journey.clone());
        Ok(())
    }
    fn capture(&self) -> NativeWholeState {
        NativeWholeState {
            identity: self.identity.clone(),
            value: Arc::new(Bundle {
                road: self.road.checkpoint(),
                service: self.service.checkpoint(),
                journey: self.journey.checkpoint(),
            }),
        }
    }
}
crate::optional_binding::optional_pymethods!(NativeWholeEngine,
    [
    #[new]
    #[pyo3(signature = (calendar, payload, byte_budget, native_threads=1, storage_policy="legacy_records"))]
    ] {
    #[cfg(feature="python-extension")]
    fn new(
        py: Python<'_>,
        calendar: PyRef<'_, NativeCalendar>,
        payload: &Bound<'_, PyDict>,
        byte_budget: usize,
        native_threads: usize,
        storage_policy: &str,
    ) -> PyResult<Self> {
        if !["legacy_records", "bounded_bytes_v1"].contains(&storage_policy) {
            return Err(bad("unknown native storage_policy").into());
        }
        let s = Static::read(payload)?;
        let parallel = ParallelPolicy::new(native_threads).map_err(bad)?;
        let source: &NativeCalendar = &calendar;
        py.allow_threads(|| {
            Self::build(source, s, byte_budget, parallel, storage_policy.to_owned())
        }).map_err(Into::into)
    }
    }
    [
    #[getter]
    ] {

    fn identity(&self) -> String {
        self.identity.clone()
    }
    }
    [
    #[getter]
    ] {

    fn native_threads(&self) -> usize {
        self.parallel.threads()
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn routing_metrics(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        self.route_metrics.report(py)
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn event_resolution_diagnostics(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let (count, processed_time, roundoff, mass) = self.road.event_resolution_stats();
        let out = PyDict::new(py);
        out.set_item("subulp_events", count)?;
        out.set_item("processed_subulp_time_upper_s", processed_time)?;
        out.set_item("clock_roundoff_upper_s", roundoff)?;
        out.set_item("nominal_subulp_service_mass_upper", mass)?;
        out.set_item("mass_bound_scope", "outward sum of rate * duration for sub-ULP service events; a nominal served-amount bound, not a total numerical mass-error bound; excludes fraction approximation, fraction snapping and packet-part rounding")?;
        out.set_item("scope", "cumulative validated proposed road transitions in this runtime; may include later coupled service/journey rollbacks, branches and replays; not committed physical counts or supplied snapshot metadata")?;
        out.set_item("checkpointed", false)?;
        Ok(out.unbind())
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn storage_config(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("policy", &self.storage_policy)?;
        out.set_item("total_accounting_budget_bytes", self.byte_budget)?;
        out.set_item("conservative_static_accounting_bytes", self.estimated_bytes)?;
        out.set_item("static_accounting_scope", "unchanged constructor preflight estimate; retained_capacity_v3 does not subtract it from runtime storage")?;
        if let Some(accounting) = &self.runtime_storage {
            out.set_item("resource_binding", "retained_capacity_v3")?;
            out.set_item("retained_static_payload_bytes", accounting.owned_static)?;
            out.set_item("initial_road_reserve_bytes", accounting.initial_road)?;
            out.set_item("journey_dense_one_copy_bytes", accounting.journey_dense)?;
            out.set_item("journey_dense_copies", 4)?;
            out.set_item("service_dense_one_copy_bytes", accounting.service_dense)?;
            out.set_item("service_dense_copies", 6)?;
            out.set_item("call_binding_reserve_bytes", accounting.call_binding)?;
            out.set_item("per_worker_scratch_total_bytes", accounting.worker_scratch)?;
            out.set_item(
                "service_prepare_scratch_bytes",
                accounting.service_prepare_scratch,
            )?;
            out.set_item("observation_reserve_bytes", OBSERVATION_RESERVE)?;
            out.set_item("runtime_fixed_reserve_bytes", accounting.fixed_charge)?;
            out.set_item("dynamic_shared_pool_bytes", self.road_storage_bytes)?;
            out.set_item("footprint_scope", "owned Vec/String capacities, unique shared law/profile allocations and explicit allocator/map allowances; includes known dense clones, per-call binding, worker/profile and service-offer scratch; excludes Python frontend, opaque Rayon/allocator internals and unrelated caller-retained snapshots, which require the process limit")?;
        }
        out.set_item("road_dynamic_allowance_bytes", self.road_storage_bytes)?;
        out.set_item(
            "journey_dynamic_allowance_bytes",
            self.journey_storage_bytes,
        )?;
        out.set_item("service_event_record_ceiling", self.event_limit)?;
        out.set_item("allocation_rationale", if self.road_storage_bytes.is_some() {
            "road/journey values are non-additive ceilings on one shared dynamic pool; each phase subtracts other known live owners before allocation; capture/decode/validation have separate global admission; policy and total are checkpoint-bound, ephemeral quotas and worker counts are not"
        } else {
            "legacy record limits; no dynamic byte-quota split"
        })?;
        out.set_item("scope", "owner storage guards; total process address-space/RSS limit must cover caller-retained immutable snapshots and allocation overhead")?;
        Ok(out.unbind())
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn execution_config(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("native_threads", self.parallel.threads())?;
        out.set_item(
            "scheduler",
            if self.parallel.threads() == 1 {
                "serial"
            } else {
                "private_rayon_pool"
            },
        )?;
        out.set_item("float_reductions", "original serial order")?;
        out.set_item("thread_count_in_scientific_identity", false)?;
        out.set_item(
            "parallel_scope",
            "independent indexed work above per-kernel size thresholds",
        )?;
        Ok(out.unbind())
    }
    }
    [

    ] {

    fn initial(&self) -> NativeWholeState {
        NativeWholeState {
            identity: self.identity.clone(),
            value: self.initial_state.clone(),
        }
    }
    }
    [

    ] {

    fn snapshot(&self) -> NativeWholeState {
        self.capture()
    }
    }
    [

    ] {

    fn check(&self, state: &NativeWholeState) -> CoreResult<()> {
        self.checked(state)
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn advance(
        &mut self,
        py: Python<'_>,
        state: &NativeWholeState,
        end_s: f64,
    ) -> CoreResult<NativeWholeState> {
        py.allow_threads(|| self.advance_owned(state, end_s))
    }
    }
    [

    ] {

    fn advance_metrics(&self) -> (Vec<f64>, usize) {
        let (t, n) = self.journey.owned_metrics();
        (t.to_vec(), n)
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn phase_metrics(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let m = self.journey.owned_phase_metrics();
        let phases = PyDict::new(py);
        for (name, seconds) in [
            ("journey_prepare", m.prepare_s),
            ("service_prepare", m.service_prepare_s),
            ("road_step", m.road_step_s),
            ("service_finish", m.service_finish_s),
            ("journey_finish", m.journey_finish_s),
            ("other_tick", m.other_tick_s),
        ] {
            phases.set_item(name, seconds)?;
        }
        let out = PyDict::new(py);
        out.set_item("phase_wall_s", phases)?;
        out.set_item("binding_s", m.binding_s)?;
        out.set_item("successful_ticks", m.successful_ticks)?;
        out.set_item("failed_ticks", m.failed_ticks)?;
        out.set_item("native_threads", self.parallel.threads())?;
        out.set_item("scope", "latest native coupled call; includes failed phase and rollback; excludes engine restore, capture and postvalidation")?;
        out.set_item(
            "road_event_resolution",
            self.event_resolution_diagnostics(py)?,
        )?;
        Ok(out.unbind())
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn debug_state(&self, py: Python<'_>, state: &NativeWholeState) -> PyResult<Py<PyDict>> {
        self.checked(state)?;
        let j = journey_debug(&state.value.journey);
        let journey = stage_counts(py, &j.counts)?;
        journey.set_item("stage_capacity", stage_values(py, j.stage_capacity)?)?;
        journey.set_item("dense_capacity_bytes", j.dense_capacity_bytes)?;
        journey.set_item(
            "dynamic_storage_bytes",
            journey_storage_bytes(&state.value.journey),
        )?;
        journey.set_item(
            "stage_blocks",
            stage_values(
                py,
                [
                    state.value.journey.1.block_count(),
                    state.value.journey.2.block_count(),
                    state.value.journey.3.block_count(),
                ],
            )?,
        )?;
        journey.set_item("stage_carrier_sum", stage_values(py, j.stage_mass)?)?;
        journey.set_item(
            "carrier_sum_units",
            "heterogeneous per-leg carrier units; not a physical total",
        )?;
        journey.set_item("ready_now", stage_values(py, j.ready_now)?)?;
        journey.set_item("nonempty_histories", j.nonempty_histories)?;
        journey.set_item(
            "capacity_scope",
            "dense_capacity_bytes excludes stage/history blocks; dynamic_storage_bytes counts persistent stage/history allocation estimates with shared prefixes counted per owner, not process RSS",
        )?;
        let r = state.value.road.debug_stats();
        let road = PyDict::new(py);
        for (name, value) in [
            ("cell_packets", r.cell_packets),
            ("pending_packets", r.pending_packets),
            ("cell_parts", r.cell_parts),
            ("pending_parts", r.pending_parts),
            ("uniform_packets", r.uniform_packets),
            ("mixed_packets", r.mixed_packets),
            ("uniform_parts", r.uniform_parts),
            ("mixed_parts", r.mixed_parts),
            ("packet_capacity", r.packet_capacity),
            ("part_capacity", r.part_capacity),
            ("vector_capacity_bytes", r.vector_capacity_bytes),
            ("latent_entries", r.latent_entries),
            ("max_cell_parts", r.max_cell_parts),
            ("max_pending_parts", r.max_pending_parts),
        ] {
            road.set_item(name, value)?;
        }
        road.set_item("total_records", r.cell_parts + r.pending_parts)?;
        // Read-only diagnostic, evaluated only on an explicit debug_state
        // request. The original road-work admission/physics are unchanged.
        let arc_census=state.value.road.arc_backing_census();
        let shared=PyDict::new(py);
        for (name,value) in [
            ("owner_count",arc_census.owner_count),
            ("unique_backing_count",arc_census.unique_backing_count),
            ("owner_payload_bytes",arc_census.owner_payload_bytes),
            ("unique_payload_bytes",arc_census.unique_payload_bytes),
            ("duplicate_payload_bytes",arc_census.duplicate_payload_bytes),
            ("unique_arc_control_allowance_bytes",arc_census.unique_arc_control_allowance_bytes),
        ] {
            shared.set_item(name,value)?;
        }
        shared.set_item("scope","unique Arc<Vec> backing payloads within ONE stored RoadState; diagnostic only, not live process RSS or admission")?;
        road.set_item("arc_backing_census",shared)?;
        // Source-specific content-equal ordered route-key sequences. Report
        // only: never authorize work from hash equality or potential savings.
        let k=state.value.road.ordered_keyset_census();
        let kc=PyDict::new(py);
        for (name,value) in [
            ("uniform_packet_owners",k.uniform_packet_owners),
            ("distinct_uniform_backings",k.distinct_uniform_backings),
            ("distinct_keysets",k.distinct_keysets),
            ("repeated_key_packets",k.repeated_key_packets),
            ("repeated_key_rows",k.repeated_key_rows),
            ("potential_saved_key_payload_bytes",k.potential_saved_key_payload_bytes),
            ("keyset_len_ge_8_repeat_rows",k.keyset_len_ge_8_repeat_rows),
            ("max_tag",k.max_tag),
            ("max_offset",k.max_offset),
            ("total_uniform_rows",k.total_uniform_rows),
        ] {
            kc.set_item(name,value)?;
        }
        kc.set_item("scope","exact ordered u32 tag/offset equality on independently backed Uniform packet rows within ONE state; diagnostic only, no memory admission credit")?;
        road.set_item("ordered_keyset_census",kc)?;
        // Two actually live owners: the internal committed road and the
        // supplied captured/restored snapshot. A diagnostic census only.
        // The phase also has ephemeral candidate/scratch allocations which
        // are explicitly NOT enumerated here.
        let two=self.road.arc_committed_snapshot_union(&state.value.road);
        let overlap=PyDict::new(py);
        for (name,value) in [
            ("owner_count",two.owner_count),
            ("unique_backing_count",two.unique_backing_count),
            ("owner_payload_bytes",two.owner_payload_bytes),
            ("unique_payload_bytes",two.unique_payload_bytes),
            ("duplicate_payload_bytes",two.duplicate_payload_bytes),
            ("unique_arc_control_allowance_bytes",two.unique_arc_control_allowance_bytes),
        ] {
            overlap.set_item(name,value)?;
        }
        overlap.set_item("scope","current committed plus supplied immutable snapshot only; no candidate/interval scratch; never used for admission")?;
        road.set_item("arc_committed_snapshot_union_census",overlap)?;
        road.set_item("event_resolution", self.event_resolution_diagnostics(py)?)?;
        road.set_item("capacity_scope", "owned state and Vec reserved storage; excludes tree nodes, allocator and shared static state")?;
        let out = PyDict::new(py);
        out.set_item("time_s", state.time_s())?;
        out.set_item("journey", journey)?;
        out.set_item("road", road)?;
        out.set_item("service_last_events", state.value.service.1.len())?;
        out.set_item("execution", self.execution_config(py)?)?;
        out.set_item("storage", self.storage_config(py)?)?;
        if let Some(a) = self.journey.last_attempt() {
            let attempt = PyDict::new(py);
            attempt.set_item("start_s", a.start_s)?;
            attempt.set_item("end_s", a.end_s)?;
            attempt.set_item("phase", a.phase)?;
            attempt.set_item("committed", a.committed)?;
            attempt.set_item("before", stage_counts(py, &a.before)?)?;
            attempt.set_item("after_prepare", stage_counts(py, &a.after_prepare)?)?;
            attempt.set_item("candidate", stage_counts(py, &a.candidate)?)?;
            attempt.set_item("generated", stage_values(py, a.generated)?)?;
            attempt.set_item("retired", stage_values(py, a.retired)?)?;
            attempt.set_item("receipts_added", a.receipts_added)?;
            attempt.set_item("emitted_offers", a.emitted_offers)?;
            out.set_item("last_attempt", attempt)?;
        } else {
            out.set_item("last_attempt", py.None())?;
        }
        out.set_item(
            "last_attempt_scope",
            "latest native call diagnostic, separate from supplied immutable snapshot",
        )?;
        Ok(out.unbind())
    }
    }
    [

    ] {

    fn sample_legs(
        &self,
        state: &NativeWholeState,
        indices: Vec<usize>,
    ) -> CoreResult<Vec<(String, f64, f64, f64)>> {
        self.checked(state)?;
        if indices.len() > 1024 {
            return Err(bad("at most 1024 diagnostic legs per call"));
        }
        indices
            .into_iter()
            .map(|i| {
                let leg = self
                    .journey
                    .legs()
                    .get(i)
                    .ok_or_else(|| CoreError::index("leg index"))?;
                Ok((
                    leg.0.clone(),
                    state.value.journey.4[i],
                    state.value.journey.5[i],
                    state.value.journey.7[i],
                ))
            })
            .collect()
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn report(&mut self, py: Python<'_>, state: &NativeWholeState) -> PyResult<Py<PyDict>> {
        let values=self.ledger_values(state)?;
        let t=state.time_s();
        let service=&state.value.service.0;
        let out = PyDict::new(py);
        let ledger = PyDict::new(py);
        let moments = PyDict::new(py);
        let assignment = PyDict::new(py);
        let units = PyDict::new(py);
        for (j, name) in ["persons", "vehicles", "cargo_kg"].iter().enumerate() {
            let v = values[j];
            let row = PyDict::new(py);
            for (k, x) in [
                ("requested", v[0]),
                ("released", v[1]),
                ("completed", v[2]),
                ("pending", v[0] - v[1]),
                ("active", v[1] - v[2]),
            ] {
                row.set_item(k, x)?;
            }
            ledger.set_item(name, row)?;
            moments.set_item(name, v[3])?;
            let row = PyDict::new(py);
            row.set_item("requested", self.totals[j])?;
            row.set_item("assigned", self.totals[j] - self.unassigned[j])?;
            row.set_item("unassigned", self.unassigned[j])?;
            units.set_item(name, row)?;
        }
        assignment.set_item("units", units)?;
        assignment.set_item("fixed_fleet_vehicles", service.0.len())?;
        assignment.set_item(
            "scope",
            "assignment, not trip completion; bus demand vehicles are occupancy equivalents",
        )?;
        let physical = PyDict::new(py);
        let (totals, classes) = state.value.road.summary();
        let bus_class = self
            .class_names
            .iter()
            .position(|n| n == "scheduled_bus")
            .unwrap();
        let bus_road = classes[bus_class][0] - classes[bus_class][1];
        let bus_stops = fsum(service.0.iter().map(|r| if r.1 != 1 { 1.0 } else { r.3 }));
        physical.set_item("time_s", t)?;
        physical.set_item("scheduled_bus_vehicles", service.0.len())?;
        physical.set_item("bus_road_vehicles", bus_road)?;
        physical.set_item("bus_stop_or_finished_vehicles", bus_stops)?;
        physical.set_item(
            "completed_bus_vehicles",
            service.0.iter().filter(|r| r.1 == 2).count(),
        )?;
        physical.set_item("waiting_persons", fsum(service.1.iter().map(|p| p.0)))?;
        physical.set_item("onboard_persons", fsum(service.1.iter().map(|p| p.1)))?;
        physical.set_item("arrived_persons", fsum(service.1.iter().map(|p| p.2)))?;
        physical.set_item(
            "wait_person_s",
            fsum(
                service
                    .1
                    .iter()
                    .enumerate()
                    .map(|(i, p)| p.3 + p.0 * (t - self.passenger_available[i]).max(0.0)),
            ),
        )?;
        physical.set_item(
            "freight_completed_vehicles",
            fsum(service.3.iter().copied()),
        )?;
        physical.set_item(
            "cargo_delivered_kg",
            fsum(
                service
                    .3
                    .iter()
                    .enumerate()
                    .map(|(i, v)| self.freight_cargo[i] * v / self.freight_vehicles[i]),
            ),
        )?;
        physical.set_item(
            "cargo_unfinished_kg",
            fsum(
                service
                    .3
                    .iter()
                    .enumerate()
                    .map(|(i, v)| self.freight_cargo[i] * (1.0 - v / self.freight_vehicles[i])),
            ),
        )?;
        physical.set_item("road_released_veh", totals[0])?;
        physical.set_item("road_completed_veh", totals[1])?;
        let construction = PyDict::new(py);
        construction.set_item("legs", self.amounts.len())?;
        construction.set_item("physical_routes", self.tags.len())?;
        construction.set_item("unique_paths", self.unique_paths)?;
        construction.set_item("unsupported_legs", self.unsupported)?;
        construction.set_item("road_legs", self.supported[1])?;
        construction.set_item("internal_legs", self.supported[2])?;
        construction.set_item("estimated_bytes", self.estimated_bytes)?;
        construction.set_item("byte_budget", self.byte_budget)?;
        construction.set_item("python_calendar_leg_objects", 0)?;
        construction.set_item("road_owners", 1)?;
        out.set_item("status", "WHOLE_CALENDAR_NATIVE_EXECUTION")?;
        out.set_item("time_s", t)?;
        out.set_item("ledger", ledger)?;
        out.set_item("released_intent_first_moments", moments)?;
        out.set_item("service", physical)?;
        out.set_item("assignment", assignment)?;
        out.set_item("construction", construction)?;
        out.set_item("city_identity", &self.city)?;
        out.set_item("schedule_identity", &self.schedule)?;
        out.set_item("full_release_campaign", "NOT_RUN")?;
        Ok(out.unbind())
    }
    }
    [

    ] {

    fn save(&mut self, path: String, state: &NativeWholeState) -> CoreResult<()> {
        self.restore(state)?;
        let mut f = BufWriter::new(File::create(path).map_err(io)?);
        f.write_all(b"MFWHOLE1").map_err(io)?;
        f.write_all(&(self.identity.len() as u64).to_le_bytes())
            .map_err(io)?;
        f.write_all(self.identity.as_bytes()).map_err(io)?;
        self.road.write_state(&mut f)?;
        self.service.write_state(&mut f)?;
        self.journey.write_state(&mut f)?;
        f.flush().map_err(io)
    }
    }
    [

    ] {

    fn load(&mut self, path: String) -> CoreResult<NativeWholeState> {
        let mut f = BufReader::new(File::open(path).map_err(io)?);
        let mut magic = [0u8; 8];
        f.read_exact(&mut magic).map_err(io)?;
        let compact=&magic==b"MFWHOLE2";
        if &magic!=b"MFWHOLE1"&&!compact{return Err(bad("native whole checkpoint schema differs"));}
        let mut raw = [0u8; 8];
        f.read_exact(&mut raw).map_err(io)?;
        let n = u64::from_le_bytes(raw);
        if n != self.identity.len() as u64 {
            return Err(bad("native whole checkpoint binding differs"));
        }
        let mut binding = vec![0u8; n as usize];
        f.read_exact(&mut binding).map_err(io)?;
        if binding != self.identity.as_bytes() {
            return Err(bad("native whole checkpoint binding differs"));
        }
        self.reset_phase_ceilings()?;
        let result = (|| {
            let old_journey = journey_storage_bytes(self.journey.state());
            let old_events = self.service.event_storage_bytes();
            if self.runtime_storage.is_some() {
                let road_limit = self.pool_after(
                    old_journey.saturating_add(old_events).saturating_mul(3),
                    "road decode",
                )?;
                self.road.set_phase_storage_budget(road_limit)?;
            }
            let road=self.road.read_state_codec(&mut f,compact)?;
            let road_bytes = road
                .retained_storage_bytes()
                .max(self.road.owned_storage_bytes());
            let event_byte_limit = if self.runtime_storage.is_some() {
                let remaining = self.pool_after(
                    road_bytes.saturating_add(old_journey).saturating_mul(3),
                    "service decode",
                )?;
                if old_events.saturating_mul(3) > remaining {
                    return Err(CoreError::resource(
                        "native retained service event storage budget exceeded before decode",
                    ));
                }
                Some(remaining / 3)
            } else {
                None
            };
            // Logical row count and actual retained allocation are separate
            // contracts. u32::MAX is reserved for destination=None by the codec.
            let compressed_events = self.road.can_compact_candidate_events();
            let service = self.service.read_state(
                &mut f, self.event_limit, event_byte_limit, compressed_events,
            )?;
            let events = service_event_storage_bytes(&service).max(old_events);
            if self.runtime_storage.is_some() {
                let journey_limit = self.pool_after(
                    road_bytes.saturating_add(events).saturating_mul(3),
                    "journey decode",
                )?;
                self.journey.set_phase_storage_budget(journey_limit)?;
            }
            let journey = self.journey.read_state(&mut f)?;
            let mut tail = [0u8; 1];
            if f.read(&mut tail).map_err(io)? != 0 {
                return Err(bad("trailing native checkpoint bytes"));
            }
            let stats = road.debug_stats();
            let state = NativeWholeState {
                identity: self.identity.clone(),
                value: Arc::new(Bundle {
                    road,
                    service,
                    journey,
                }),
            };
            // Nothing is installed until all sequential reserve guards and
            // cross-owner physical validation have succeeded.
            self.load_validation_admission(
                &state.value,
                stats.cell_parts.saturating_add(stats.pending_parts),
            )?;
            self.validate_bundle(&state.value)?;
            self.restore(&state)?;
            Ok(state)
        })();
        let reset = self.reset_phase_ceilings();
        match result {
            Err(error) => Err(error),
            Ok(state) => {
                reset?;
                Ok(state)
            }
        }
    }
    }
);

#[cfg(test)]
mod stage_sum_tests {
    use super::*;
    use crate::v1_stage::StageQueue;

    fn lcg(state: &mut u64) -> u64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        *state >> 11
    }

    /// The former validation map: one `Sum` per key, rows in (j.1, j.2, j.3) order.
    fn reference(j: &Journey, legs: usize) -> Vec<f64> {
        let mut stages: HashMap<usize, Sum> = HashMap::new();
        for rows in [&j.1, &j.2, &j.3] {
            for a in rows {
                stages.entry(a.0).or_default().add(a.1);
            }
        }
        let stages: HashMap<usize, f64> =
            stages.into_iter().map(|(i, v)| (i, v.finish())).collect();
        (0..legs)
            .map(|i| stages.get(&i).copied().unwrap_or(0.0))
            .collect()
    }

    #[test]
    fn stage_sums_match_former_per_key_sum_bits() {
        let legs = 97;
        let mut seed = 17u64;
        let mut queues = [StageQueue::new(), StageQueue::new(), StageQueue::new()];
        for (q, n) in queues.iter_mut().zip([1500usize, 777, 2049]) {
            for _ in 0..n {
                let leg = (lcg(&mut seed) % 61) as usize; // legs 61..97 stay absent
                let exp = (lcg(&mut seed) % 40) as i32 - 20;
                let sign = if lcg(&mut seed) % 7 == 0 { -1.0 } else { 1.0 };
                let mass = sign * (1.0 + (lcg(&mut seed) % 1000) as f64 / 7.0) * 10f64.powi(exp);
                q.push((leg, mass, 1.0, 2.0));
            }
        }
        let [a, b, c] = queues;
        let j: Journey = (0.0, a, b, c, vec![], vec![], vec![], vec![]);
        let got = stage_sums(&j, legs).unwrap();
        let want = reference(&j, legs);
        assert_eq!(got.len(), want.len());
        for (g, w) in got.iter().zip(&want) {
            assert_eq!(g.to_bits(), w.to_bits());
        }
        assert!(got[61..].iter().all(|x| x.to_bits() == 0f64.to_bits()));
    }

    #[test]
    fn stage_sums_empty_journey_is_all_zero() {
        let j: Journey = (
            0.0,
            StageQueue::new(),
            StageQueue::new(),
            StageQueue::new(),
            vec![],
            vec![],
            vec![],
            vec![],
        );
        assert_eq!(stage_sums(&j, 5).unwrap(), vec![0.0; 5]);
    }
}

#[cfg(test)]
mod capture_road_clone_owner_exact_bounds {
    use super::*;

    #[test]
    fn actual_immutable_arc_payload_is_not_allocated_twice_in_future_road_clone() {
        assert_eq!(capture_road_clone_credit(500,250,true,true),250);
        assert_eq!(capture_road_clone_credit(500,0,true,true),0);
        assert_eq!(capture_road_clone_credit(500,950,true,true),500);
        assert_eq!(3*500-capture_road_clone_credit(500,250,true,true),1250);
    }
    #[test]
    fn source_road_credit_requires_actual_input_and_future_capture_phase() {
        assert_eq!(capture_road_clone_credit(500,250,false,true),0);
        assert_eq!(capture_road_clone_credit(500,250,true,false),0);
        assert_eq!(capture_road_clone_credit(0,100,true,true),0);
    }
}

impl NativeWholeEngine {
    fn advance_owned(&mut self,state:&NativeWholeState,end_s:f64)->CoreResult<NativeWholeState>{
        self.checked(state)?;
        let count = (end_s - state.time_s()) / self.step;
        if !count.is_finite() || count < 0.0 || (count - count.round()).abs() > 1e-8 {
            return Err(bad("joint horizon must align with fixed step"));
        }
        if self.runtime_storage.is_some()
            && (count as usize).saturating_mul(2 * std::mem::size_of::<f64>()) > OBSERVATION_RESERVE
        {
            return Err(CoreError::resource("native call observation storage budget exceeded; split the requested horizon into bounded calls"));
        }
        self.restore(state)?;
        let dynamic_budget = self.road_storage_bytes;
        let call_binding_reserve = self.runtime_storage.as_ref().map_or(0, |a| a.call_binding);
        let parallel = &self.parallel;
        let road = &mut self.road;
        let service = &mut self.service;
        let journey = &mut self.journey;
        let tags = &self.tags;
        let step = self.step;
        let outcome = parallel.run(|| {
                advance_owned_joint(
                    road,
                    service,
                    journey,
                    tags,
                    count.round() as usize,
                    step,
                    dynamic_budget,
                    call_binding_reserve,
                    Some(&state.value.road),
                )
        });
        self.reset_phase_ceilings()?;
        outcome?;
        self.storage_admission(
            self.journey.state(),
            self.road.owned_storage_bytes(),
            self.road.owned_record_count(),
            self.service.event_storage_bytes(),
            Some(&state.value),
            true,
        )?;
        let result = self.capture();
        if let Err(error) = self.validate_bundle(&result.value) {
            // A failed result must not coexist with the restore clone as a
            // fifth dense journey copy.
            drop(result);
            self.restore(state)?;
            return Err(error);
        }
        Ok(result)
    }
}

impl NativeWholeEngine {
    fn ledger_values(&self,state:&NativeWholeState)->CoreResult<[[f64;4];3]>{
        self.checked(state)?;
        let t = state.time_s();
        let journey = &state.value.journey;
        let profiles: Vec<_> = self.profiles.iter().map(|p| fraction(p, t)).collect();
        let mut values = [[0.0; 4]; 3];
        for (i, a) in self.amounts.iter().enumerate() {
            let carrier = self.journey.legs()[i].1;
            for j in 0..3 {
                let ratio = if carrier != 0.0 { a[j] / carrier } else { 0.0 };
                values[j][0] += a[j] * profiles[self.profile_ids[i]];
                values[j][1] += ratio * journey.4[i];
                values[j][2] += ratio * journey.5[i];
                values[j][3] += ratio * journey.7[i];
            }
        }
        Ok(values)
    }
}

#[cfg(feature="native-cli")]
fn build_native_input(manifest:serde_json::Value,threads:usize)->CoreResult<(NativeWholeEngine,usize,(f64,f64,f64))>{
    if manifest.get("schema").and_then(|v|v.as_str())!=Some("metroflow_native_declaration_v1"){
        return Err(bad("native declaration schema differs"))
    }
    let budget=manifest.get("byte_budget").and_then(|v|v.as_u64()).and_then(|v|usize::try_from(v).ok())
        .ok_or_else(||bad("native byte budget missing"))?;
    if budget==0||budget>6*1024usize.pow(3){return Err(bad("native byte budget outside 1..6GiB"))}
    let calendar:crate::v1_calendar::FactorizedDeclaration=serde_json::from_value(
        manifest.get("calendar").cloned().ok_or_else(||bad("calendar missing"))?)
        .map_err(|e|bad(format!("calendar declaration: {e}")))?;
    let raw=manifest.get("static").cloned().ok_or_else(||bad("static missing"))?;
    if raw.get("schema").and_then(|v|v.as_str())!=Some("native_calendar_static_v1"){return Err(bad("static schema differs"))}
    let s:Static=serde_json::from_value(raw).map_err(|e|bad(format!("static declaration: {e}")))?;
    let calendar=calendar.compile(budget)?;
    let calendar_legs=calendar.owned_legs().len();
    let calendar_totals=calendar.totals();
    let parallel=ParallelPolicy::new(threads).map_err(bad)?;
    let engine=NativeWholeEngine::build(&calendar,s,budget,parallel,"bounded_bytes_v1".to_owned())?;
    drop(calendar);

    Ok((engine,calendar_legs,calendar_totals))
}

/// Strict full decoder recovery: no stepping and no acceptance credit.
#[cfg(feature="native-cli")]
pub fn recover_native_checkpoint(manifest:serde_json::Value,threads:usize,path:&str)->CoreResult<serde_json::Value>{
    use serde_json::json;
    let t=Instant::now();
    let (mut engine,calendar_legs,calendar_totals)=build_native_input(manifest,threads)?;
    let build_s=t.elapsed().as_secs_f64();let t=Instant::now();
    let state=engine.load(path.to_owned())?;
    let ledger=ledger_json(&engine,&state)?;let (totals,classes)=state.value.road.summary();
    let road=state.value.road.debug_stats();
    let mut out=json!({"schema":"metroflow_native_recovery_v1","status":"RECOVERED_CHECKPOINT_ONLY","scope":"strict complete decode, cross-owner ledger validation and original identity; no execution or elapsed-horizon claim","time_s":state.time_s(),"city_identity":engine.city,"schedule_identity":engine.schedule,"native_identity":engine.identity,"calendar_legs":calendar_legs,"calendar_totals":calendar_totals,"byte_budget":engine.byte_budget,"threads":threads,"build_s":build_s,"load_s":t.elapsed().as_secs_f64(),"ledger":ledger["ledger"],"road_totals":totals,"road_class_ledgers":classes,"class_names":engine.class_names,"road_records":{"cell_parts":road.cell_parts,"pending_parts":road.pending_parts,"cell_packets":road.cell_packets,"pending_packets":road.pending_packets,"uniform_parts":road.uniform_parts,"mixed_parts":road.mixed_parts,"retained_storage_bytes":state.value.road.retained_storage_bytes()},"completed_event_rows":state.value.service.1.len()});
    let (owner,scratch)=state.value.road.compact_decode_envelope();let (old_owner,old_scratch)=state.value.road.legacy_decode_envelope();
    out["decode_envelopes"]=json!({"compact_owner_bytes":owner,"compact_validation_scratch_bytes":scratch,"historical_legacy_owner_estimate_bytes":old_owner,"historical_legacy_validation_scratch_bytes":old_scratch});
    if crate::v1_trace::enabled(){out["budget_trace"]=crate::v1_trace::native_snapshot();}
    Ok(out)
}

/// Native host entry point, with the exact same engine build/advance/save/load
/// code as the Python binding. No Python dictionary or GIL is used on the
/// successful execution path. The existing CoreError type remains for errors.
#[cfg(feature="native-cli")]
pub fn run_native_declaration(
    manifest: serde_json::Value,
    threads:usize,end_s:f64,resume:Option<&str>,checkpoint:&str,
)->CoreResult<serde_json::Value>{
    run_native_declaration_with_plan(manifest,threads,end_s,resume,checkpoint,None,None)
}

#[cfg(feature="native-cli")]
pub fn run_native_declaration_with_plan(
    manifest: serde_json::Value,
    threads:usize,
    end_s:f64,
    resume:Option<&str>,
    checkpoint:&str,
    segment_s:Option<f64>,replay_at_s:Option<f64>,
)->CoreResult<serde_json::Value>{
    use serde_json::json;
    let start=Instant::now();
    let (mut engine,calendar_legs,calendar_totals)=build_native_input(manifest,threads)?;
    let budget=engine.byte_budget;
    let build_s=start.elapsed().as_secs_f64();
    let initial=if let Some(path)=resume{engine.load(path.to_owned())?}else{engine.initial()};
    let begin=initial.time_s();
    let clock=Instant::now();
    let mut state=initial;
    let mut checkpoint_write_s=0.;let mut initial_checkpoint_method="not_applicable";
    let mut ticks=Vec::new();let mut peak=0usize;let mut segments=0usize;let mut replay_verified=false;let mut failure=None;let mut prefix=None;
    if !end_s.is_finite()||end_s<begin||((end_s-begin)/engine.step-((end_s-begin)/engine.step).round()).abs()>1e-8{return Err(bad("invalid aligned execution horizon"))}
    if let Some(chunk)=segment_s{
        if !chunk.is_finite()||chunk<=0.||((chunk/engine.step)-(chunk/engine.step).round()).abs()>1e-8{return Err(bad("segment must align with native step"))}
        if replay_at_s.is_some_and(|x|!x.is_finite()||x<=begin||x>end_s||((x-begin)/engine.step-((x-begin)/engine.step).round()).abs()>1e-8){return Err(bad("replay must align within execution horizon"))}
        {
            let t=Instant::now();
            // Opt-in: a strictly loaded immutable source can be linked
            // without serializing it again. Later saves rename a fresh inode
            // over the output name; the input checkpoint is never modified.
            let linked=if std::env::var("METROFLOW_NATIVE_LINK_RESUME").as_deref()==Ok("1"){
                if let Some(source)=resume{
                    let source=std::fs::canonicalize(source).map_err(io)?;
                    if !std::fs::metadata(&source).map_err(io)?.is_file(){return Err(bad("resume source not regular file"))}
                    let mut magic=[0u8;8];File::open(&source).map_err(io)?.read_exact(&mut magic).map_err(io)?;
                    let wanted=if std::env::var("METROFLOW_NATIVE_COMPACT_WIRE").as_deref()==Ok("1"){b"MFWHOLE2"}else{b"MFWHOLE1"};
                    if &magic!=wanted{false}else{match std::fs::hard_link(&source,checkpoint){Ok(())=>{sync_parent_native(checkpoint)?;true},Err(e) if e.kind()==std::io::ErrorKind::AlreadyExists=>return Err(io(e)),Err(_)=>false}}
                }else{false}
            }else{false};
            if linked{initial_checkpoint_method="immutable_hardlink";}else{save_atomic_native(&mut engine,checkpoint,&state)?;initial_checkpoint_method="serialize";}
            checkpoint_write_s+=t.elapsed().as_secs_f64();
        }
        while state.time_s()<end_s{
            let mut target=(state.time_s()+chunk).min(end_s);
            if let Some(x)=replay_at_s{if state.time_s()<x{target=target.min(x)}}
            if state.time_s()<28800.&&end_s>=28800.{target=target.min(28800.)}
            let previous=state.time_s();
            match engine.advance_owned(&state,target){
                Ok(next)=>{
                    let (t,n)=engine.advance_metrics();let expected=((target-previous)/engine.step).round() as usize;
                    if t.len()!=expected||t.iter().any(|x|!x.is_finite()||*x<0.){return Err(bad("native tick timing census differs"))}
                    ticks.extend(t);peak=peak.max(n);state=next;segments+=1;
                    {let t=Instant::now();save_atomic_native(&mut engine,checkpoint,&state)?;checkpoint_write_s+=t.elapsed().as_secs_f64();}
                    if state.time_s()==28800.{prefix=Some(ledger_json(&engine,&state)?);}
                    if replay_at_s==Some(state.time_s()){
                        let before=state.time_s();drop(state);state=engine.load(checkpoint.to_owned())?;
                        if state.time_s()!=before{return Err(bad("replay clock differs"))}replay_verified=true;
                    }
                }
                Err(e)=>{failure=Some(e);break;}
            }
        }
    }else{
        state=engine.advance_owned(&state,end_s)?;
        let (t,n)=engine.advance_metrics();ticks=t;peak=n;segments=1;
    }
    let advance_s=clock.elapsed().as_secs_f64();
    let values=engine.ledger_values(&state)?;
    let mut ledger=serde_json::Map::new();
    for (name,v) in ["persons","vehicles","cargo_kg"].into_iter().zip(values){
        if v.iter().any(|x|!x.is_finite())||v[1]>v[0]+1e-8*v[0].max(1.)||v[2]>v[1]+1e-8*v[1].max(1.){
            return Err(bad("native ledger differs"))
        }
        ledger.insert(name.into(),json!({"requested":v[0],"released":v[1],"completed":v[2],
            "pending":v[0]-v[1],"active":v[1]-v[2],"released_intent_first_moment":v[3]}));
    }
    let (totals,classes)=state.value.road.summary();
    let tick_times=ticks;let peak_records=peak;
    let mut result=json!({"schema":"metroflow_native_rust_host_v1","scope":"original native engine from typed declared input; not original city construction or V03 acceptance",
        "city_identity":engine.city,"schedule_identity":engine.schedule,"native_identity":engine.identity,
        "start_s":begin,"time_s":state.time_s(),"calendar_legs":calendar_legs,"threads":threads,"byte_budget":budget,
        "build_s":build_s,"advance_s":advance_s,"ledger":ledger,"road_totals":totals,"road_class_ledgers":classes,
        "class_names":engine.class_names,"events":state.value.service.1.len(),
        "tick_times_s":tick_times,"peak_records":peak_records,"unique_paths":engine.unique_paths,
        "unsupported_legs":engine.unsupported,"calendar_totals":[calendar_totals.0,calendar_totals.1,calendar_totals.2],"native_route_latency":route_metrics_json(&engine.route_metrics),"segments":segments,"resume_verified":replay_verified,"refinement_prefix":prefix,"status":if failure.is_none(){"EXECUTED_FOR_REVIEW"}else{"BLOCKED"},"failure":failure.as_ref().map(|e|json!({"kind":format!("{:?}",e.kind),"message":e.message}))});
    let clock=Instant::now();
    if segment_s.is_none(){{let t=Instant::now();save_atomic_native(&mut engine,checkpoint,&state)?;checkpoint_write_s+=t.elapsed().as_secs_f64();}}
    result["save_s"]=json!(clock.elapsed().as_secs_f64());
    result["checkpoint_write_s"]=json!(checkpoint_write_s);
    result["initial_checkpoint_method"]=json!(initial_checkpoint_method);
    result["wire_writer"]=json!(if std::env::var("METROFLOW_NATIVE_COMPACT_WIRE").as_deref()==Ok("1"){"compact_v2"}else if std::env::var_os("METROFLOW_NATIVE_SCALAR_WIRE").is_some(){"scalar"}else{"batched_stack"});
    result["checkpoint_writer"]=json!(if std::env::var("METROFLOW_NATIVE_LEGACY_SAVE").as_deref()==Ok("1"){"legacy_restore"}else{"immutable_snapshot"});
    if let Ok(cursor)=std::env::var("METROFLOW_NATIVE_COMPLETED_SINCE_S"){
        let since:f64=cursor.parse().map_err(|_|bad("invalid completed observation cursor"))?;
        let t=Instant::now();result["completed_observations"]=completed_route_observations_native(&engine,&state,since,20000)?;
        result["completed_observation_wall_s"]=json!(t.elapsed().as_secs_f64());
    }
    if crate::v1_trace::enabled(){result["budget_trace"]=crate::v1_trace::native_snapshot();}
    Ok(result)
}

#[cfg(feature="native-cli")]
fn ledger_json(engine:&NativeWholeEngine,state:&NativeWholeState)->CoreResult<serde_json::Value>{
    use serde_json::json;
    let values=engine.ledger_values(state)?;
    let mut out=serde_json::Map::new();
    for (name,v) in ["persons","vehicles","cargo_kg"].into_iter().zip(values){
        let tol=1e-9*v[0].abs().max(v[1].abs()).max(v[2].abs()).max(1.);
        if v.iter().any(|x|!x.is_finite())||v[0]< -tol||v[1]< -tol||v[2]< -tol||v[1]>v[0]+tol||v[2]>v[1]+tol{return Err(bad("invalid conserved ledger"))}
        out.insert(name.into(),json!({"requested":v[0],"released":v[1],"completed":v[2],"pending":v[0]-v[1],"active":v[1]-v[2],"released_intent_first_moment":v[3]}));
    }
    Ok(json!({"time_s":state.time_s(),"ledger":out}))
}
#[cfg(feature="native-cli")]
fn route_metrics_json(m:&NativeRouteMetrics)->serde_json::Value{
    use serde_json::json;
    let p99=if m.calls==0{None}else{
        let rank=(99u128*m.calls as u128+99)/100;
        let mut cumulative=0u128;
        let i=m.counts.iter().position(|&n|{cumulative+=n as u128;cumulative>=rank}).unwrap();
        let (lo,hi)=if i<256{(i as u128,i as u128)}else if i==ROUTE_OVERFLOW_BIN{(1u128<<64,m.maximum_ns.unwrap())}else{let shift=(i-256)/128+1;let off=(i-256)%128;(((128+off)as u128)<<shift,(((129+off)as u128)<<shift)-1)};
        Some(json!({"lower":lo.max(m.minimum_ns.unwrap()),"upper":hi.min(m.maximum_ns.unwrap())}))
    };
    json!({"status":if m.calls==0{"NOT_MEASURED"}else{"MEASURED_INTERVAL"},"observed_calls":m.calls,"failed_calls":m.failed,"pair_cache_hits":m.cache_hits,"search_calls":m.calls-m.cache_hits,"min_ns":m.minimum_ns,"max_ns":m.maximum_ns,"p99_ns":p99,"source":"native_whole_router.route","scope":"native whole-engine OD requests including pair-cache hits"})
}
#[cfg(feature="native-cli")]
fn sync_parent_native(path:&str)->CoreResult<()>{
    let p=std::path::Path::new(path).parent().filter(|p|!p.as_os_str().is_empty()).unwrap_or_else(||std::path::Path::new("."));
    std::fs::File::open(p).map_err(io)?.sync_all().map_err(io)
}
#[cfg(feature="native-cli")]
fn save_atomic_native(engine:&mut NativeWholeEngine,path:&str,state:&NativeWholeState)->CoreResult<()>{
    // Unique scratch path, same filesystem as destination. A failed save
    // never replaces the last known-valid checkpoint.
    let tmp=format!("{path}.stage-{}",std::process::id());
    if std::path::Path::new(&tmp).exists(){return Err(CoreError::io("checkpoint staging path exists"))}
    let result=(||{
        if std::env::var("METROFLOW_NATIVE_LEGACY_SAVE").as_deref()==Ok("1"){engine.save(tmp.clone(),state)?;}else{
            // State is private, immutable and produced by build/advance/load,
            // which already validates the complete bundle. Serialize borrowed
            // committed owners directly; no restore clone or altered physics.
            engine.checked(state)?;
            let mut f=BufWriter::with_capacity(1024*1024,std::fs::OpenOptions::new().write(true).create_new(true).open(&tmp).map_err(io)?);
            let compact=std::env::var("METROFLOW_NATIVE_COMPACT_WIRE").as_deref()==Ok("1");
            f.write_all(if compact{b"MFWHOLE2"}else{b"MFWHOLE1"}).map_err(io)?;
            f.write_all(&(engine.identity.len()as u64).to_le_bytes()).map_err(io)?;
            f.write_all(engine.identity.as_bytes()).map_err(io)?;
            engine.road.write_snapshot_codec(&mut f,&state.value.road,compact)?;
            NativeServiceCore::write_snapshot(&mut f,&state.value.service.0,&state.value.service.1)?;
            NativeJourneyCore::write_snapshot(&mut f,&state.value.journey)?;
            f.flush().map_err(io)?;
        }
        std::fs::File::open(&tmp).map_err(io)?.sync_all().map_err(io)?;
        std::fs::rename(&tmp,path).map_err(io)?;
        sync_parent_native(path)?;
        Ok(())
    })();
    if result.is_err(){let _=std::fs::remove_file(&tmp);}
    result
}

/// Completed conditional route costs, using the same native outlet records.
/// Never infer per-link cost from route birth marks. Opt-in diagnostics only.
#[cfg(feature="native-cli")]
fn completed_route_observations_native(engine:&NativeWholeEngine,state:&NativeWholeState,since:f64,limit:usize)->CoreResult<serde_json::Value>{
    use serde_json::json;
    use sha2::{Sha256,Digest};
    use std::collections::BTreeMap;
    engine.checked(state)?;
    let now=state.time_s();
    if !since.is_finite()||since<0.||since>now||limit==0||limit>20000{return Err(bad("invalid observation cursor/budget"))}
    struct Acc{mass:Sum,elapsed:Sum,start:f64,end:f64,count:usize,hash:Sha256}
    let mut groups:BTreeMap<usize,Acc>=BTreeMap::new();
    for e in state.value.service.1.iter(){
        if e.2.is_some()||e.5<=since||e.5>now{continue}
        if !groups.contains_key(&e.0){
            if groups.len()==limit{return Err(CoreError::resource("completed route observation budget"))}
            groups.insert(e.0,Acc{mass:Sum::default(),elapsed:Sum::default(),start:e.4,end:e.5,count:0,hash:Sha256::new()});
        }
        let a=groups.get_mut(&e.0).unwrap();
        let elapsed=e.3*(e.4+e.5)/2.-e.6;
        if !elapsed.is_finite()||!e.3.is_finite()||e.3<=0.{return Err(bad("invalid completed outlet event"))}
        a.mass.add(e.3);a.elapsed.add(elapsed);a.start=a.start.min(e.4);a.end=a.end.max(e.5);a.count+=1;
        for v in [e.0 as u64,e.1 as u64,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits()]{a.hash.update(v.to_le_bytes());}
    }
    let mut result=Vec::with_capacity(groups.len());
    let mut rows=0usize;let mut all_mass=Sum::default();let mut all_elapsed=Sum::default();
    for (tag,a) in groups{
        let id=engine.tags.get(tag).ok_or_else(||bad("outlet route identity"))?;
        let class=engine.road.class_for_route(tag).and_then(|c|engine.class_names.get(c)).ok_or_else(||bad("outlet class identity"))?;
        let mass=a.mass.finish();let elapsed=a.elapsed.finish();if !mass.is_finite()||mass<=0.||!elapsed.is_finite()||elapsed<0.{return Err(bad("invalid completed route moment"))}
        let mut h=a.hash;h.update(engine.identity.as_bytes());h.update(id.as_bytes());
        let o=crate::causal::Observation{key:crate::causal::Key{kind:"route".into(),id:id.clone(),class:class.clone()},seconds:elapsed/mass,stamp_s:now,start_s:a.start,end_s:a.end,mass_veh:mass,sensor_xy:[0.,0.],source:"T04_completed_outlet".into(),version:engine.identity.clone(),population:format!("{:x}",h.finalize()),measure:"completed conditional birth-to-exit mean; includes all recorded holds".into()};
        o.validate()?;rows+=a.count;all_mass.add(mass);all_elapsed.add(elapsed);result.push(o);
    }
    Ok(json!({"scope":"actual native outlet records, observer coordinate explicitly fixed at [0,0]; route totals cannot be converted to link costs","since_s":since,"time_s":now,"outlet_rows":rows,"route_observations":result.len(),"mass_veh":all_mass.finish(),"elapsed_veh_s":all_elapsed.finish(),"observations":result}))
}

/// Execute original C01 phase clocks on the actual native physical owner.
/// A failed call emits no new world checkpoint. Physical route proposals
/// remain non-mutating, as in the original Python C01 contract.
#[cfg(feature="native-cli")]
pub fn run_native_phase(
    manifest:serde_json::Value,threads:usize,end_s:f64,
    config:crate::phase_runtime::Config,inputs:crate::phase_runtime::Inputs,
    resume:Option<(&str,crate::phase_runtime::Wire)>,checkpoint:&str,
)->CoreResult<serde_json::Value>{
    use serde_json::json;
    use crate::{phase_runtime::Runtime,causal_routing::Link};
    let t=Instant::now();
    let static_data:Static=serde_json::from_value(manifest["static"].clone()).map_err(|e|bad(format!("phase static input: {e}")))?;
    let lengths:std::collections::BTreeMap<_,_>=static_data.links.iter().zip(&static_data.groups).map(|(id,g)|(id.as_str(),g.first().copied())).collect();
    let links=static_data.arcs.iter().map(|(id,tail,head)|Ok(Link{id:id.clone(),tail:tail.clone(),head:head.clone(),length_m:lengths.get(id.as_str()).and_then(|x|*x).ok_or_else(||bad("phase link length"))?,toll_units:0.})).collect::<CoreResult<Vec<_>>>()?;
    let turns=static_data.turns;drop(lengths);
    let (mut engine,calendar_legs,calendar_totals)=build_native_input(manifest,threads)?;
    let runtime=Runtime::new(&engine.city,&engine.schedule,&engine.identity,engine.step,links,turns,config)?;
    let build_s=t.elapsed().as_secs_f64();
    let (mut state,mut world)=if let Some((path,wire))=resume{let state=engine.load(path.to_owned())?;let world=runtime.restore(wire,state.time_s())?;(state,world)}else{(engine.initial(),runtime.initial()?)};
    runtime.validate_input(&world,end_s,&inputs)?;
    let mut pending=inputs.reports;
    if let Some(publication)=inputs.growth{runtime.publish(&mut world,publication)?;}
    let begin=state.time_s();let t=Instant::now();
    // Use a bounded explicit Rayon pool for information processing, including
    // the single-worker comparison. Never nest it inside road parallel work.
    let pool=rayon::ThreadPoolBuilder::new().num_threads(threads).build().map_err(|e|bad(e.to_string()))?;
    let mut tick_times=vec![];
    while state.time_s()<end_s{
        let target=runtime.boundary(&world,end_s);
        let next=engine.advance_owned(&state,target)?;
        let (times,_)=engine.advance_metrics();tick_times.extend(times);
        let (totals,_)=next.value.road.summary();
        let completed=if runtime.medium(&world,target){
            let v=completed_route_observations_native(&engine,&next,world.wire.observation_cursor_s,20000)?;
            serde_json::from_value(v["observations"].clone()).map_err(|e|bad(e.to_string()))?
        }else{vec![]};
        pool.install(||runtime.transition(&mut world,target,totals[1],completed,&mut pending))?;
        state=next;
    }
    let wire=runtime.finalize(world,&pending)?;
    let growth_stock_identity=runtime.growth_stock_identity(&wire)?;
    let phase_wire=serde_json::to_value(&wire).map_err(|e|bad(e.to_string()))?;
    let wire_bytes=serde_json::to_vec(&phase_wire).map_err(|e|bad(e.to_string()))?;
    if wire_bytes.len()>16*1024*1024{return Err(CoreError::resource("phase wire byte bound"))}
    let phase_wire_sha256=crate::frozen_city::hash(&wire_bytes);
    drop(wire_bytes);
    let ledger=ledger_json(&engine,&state)?;
    let advance_s=t.elapsed().as_secs_f64();
    save_atomic_native(&mut engine,checkpoint,&state)?;
    Ok(json!({"schema":"metroflow_native_world_v1","scope":"C01 proposal-only phase semantics on actual native T04 state; explicit growth publications; no occupied suffix mutation","status":"EXECUTED_FOR_REVIEW","city_identity":engine.city,"schedule_identity":engine.schedule,"native_identity":engine.identity,"phase_model_identity":runtime.id,"start_s":begin,"time_s":state.time_s(),"calendar_legs":calendar_legs,"calendar_totals":calendar_totals,"threads":threads,"byte_budget":engine.byte_budget,"build_s":build_s,"advance_s":advance_s,"tick_times_s":tick_times,"ledger":ledger["ledger"],"phase_wire":phase_wire,"phase_wire_sha256":phase_wire_sha256,"growth_stock_identity":growth_stock_identity,"physical_suffix_applied":false}))
}
