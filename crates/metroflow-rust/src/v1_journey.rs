//! Native B01 service scheduling and whole-journey ledgers.
//! Road evolution is supplied by the sole road owner between prepare/finish.
//! Each transition is transactional: errors leave the last committed state intact.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
use crate::v1_history::{ReceiptHistory,GridWorkspace,ReceiptAccumulator};
use crate::v1_parallel::ordered_map;
use crate::v1_road::{
    checkpoint_vec, read_exact_len, read_f64, read_len, read_u64, write_f64, write_len, write_u64,
    ChunkedEvents, EventRow, RoadState, V1Road,
};
use crate::v1_stage::{Access, StageQueue};
use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::sync::Arc;
use std::time::Instant;

type Offer = (String, f64, f64);
type Sink = (String, f64, f64);
pub(crate) type Bus = (String, Vec<f64>, f64, f64);
pub(crate) type Person = (usize, usize, usize, f64, f64);
pub(crate) type Source = (String, f64, f64);
type Run = (usize, u8, f64, f64, f64); // stop index, STOP/ROAD/DONE, ready, partial sink, delay
type People = (f64, f64, f64, f64, f64);
pub(crate) type Service = (Vec<Run>, Vec<People>, Vec<bool>, Vec<f64>, Vec<bool>);
pub(crate) type ServiceCheckpoint = (Service, Arc<ChunkedEvents>);
type Profile = Vec<(f64, f64, f64)>;
type Law = Vec<(f64, f64)>;
pub(crate) type JourneyLeg = (String, f64, Option<usize>, f64, Profile, u8, Law, Law);
pub(crate) type BusMeta = (usize, f64, f64, f64, f64, Law); // leg, calendar persons, window persons, birth moment, required CDF, egress
pub(crate) type FreightMeta = (usize, f64, f64, Law);
pub(crate) type SharedProfile = Arc<Profile>;
pub(crate) type SharedLaw = Arc<Law>;
pub(crate) type SharedJourneyLeg = (
    String,
    f64,
    Option<usize>,
    f64,
    SharedProfile,
    u8,
    SharedLaw,
    SharedLaw,
);
pub(crate) type SharedBusMeta = (usize, f64, f64, f64, f64, SharedLaw);
pub(crate) type SharedFreightMeta = (usize, f64, f64, SharedLaw);
pub(crate) type Journey = (
    f64,
    StageQueue,
    StageQueue,
    StageQueue,
    Vec<f64>,
    Vec<f64>,
    Vec<ReceiptHistory>,
    Vec<f64>,
);

// Structural retained-allocation estimates, separate from constructor peak
// admission. Inline core/Vec headers belong to the enclosing owner; these
// helpers charge heap capacity and conservative allocator/control padding.
const RETAINED_ALLOCATION_PADDING: usize = 128;
fn capacity_storage_bytes<T>(capacity: usize) -> usize {
    if capacity == 0 {
        0
    } else {
        capacity
            .saturating_mul(std::mem::size_of::<T>())
            .saturating_add(RETAINED_ALLOCATION_PADDING)
    }
}
fn vec_storage_bytes<T>(values: &Vec<T>) -> usize {
    capacity_storage_bytes::<T>(values.capacity())
}
fn string_storage_bytes(value: &String) -> usize {
    capacity_storage_bytes::<u8>(value.capacity())
}
fn hash_capacity_storage_bytes<K, V>(capacity: usize) -> usize {
    if capacity == 0 {
        0
    } else {
        // Public HashMap::capacity excludes control bytes and is less than
        // its bucket count. Two buckets per usable entry bounds the current
        // standard table layout, with fixed padding for group/control tails.
        capacity
            .saturating_mul(2)
            .saturating_mul(std::mem::size_of::<(K, V)>().saturating_add(1))
            .saturating_add(RETAINED_ALLOCATION_PADDING)
    }
}
fn hash_entries_upper_bytes<K, V>(entries: usize) -> usize {
    // A growing table can retain capacity above its live entry count. Four
    // buckets per requested entry also covers the small-table minimum.
    hash_capacity_storage_bytes::<K, V>(entries.saturating_mul(2))
}
fn shared_vec_storage_bytes<T>(values: &Arc<Vec<T>>) -> usize {
    std::mem::size_of::<Vec<T>>()
        .saturating_add(2 * std::mem::size_of::<usize>())
        .saturating_add(RETAINED_ALLOCATION_PADDING)
        .saturating_add(vec_storage_bytes(values.as_ref()))
}

/// One journey state's dense heap buffers, excluding shared stage/history
/// payloads (charged separately by journey_storage_bytes).
pub(crate) fn journey_dense_storage_bytes(state: &Journey) -> usize {
    vec_storage_bytes(&state.4)
        .saturating_add(vec_storage_bytes(&state.5))
        .saturating_add(vec_storage_bytes(&state.6))
        .saturating_add(vec_storage_bytes(&state.7))
}

/// One service state's dense heap buffers, excluding retained road events.
pub(crate) fn service_dense_storage_bytes(state: &Service) -> usize {
    vec_storage_bytes(&state.0)
        .saturating_add(vec_storage_bytes(&state.1))
        .saturating_add(vec_storage_bytes(&state.2))
        .saturating_add(vec_storage_bytes(&state.3))
        .saturating_add(vec_storage_bytes(&state.4))
}

pub(crate) fn service_event_storage_bytes(state: &ServiceCheckpoint) -> usize {
    state.1.retained_storage_bytes()
}

/// Debug counters are observational metadata, never serialized physical state.
#[derive(Clone, Debug, Default)]
pub(crate) struct JourneyDebug {
    pub counts: [usize; 4],
    pub stage_capacity: [usize; 3],
    pub dense_capacity_bytes: usize,
    pub stage_mass: [f64; 3],
    pub ready_now: [usize; 3],
    pub nonempty_histories: usize,
}

pub(crate) fn journey_debug(s: &Journey) -> JourneyDebug {
    let stages = [&s.1, &s.2, &s.3];
    JourneyDebug {
        counts: [
            s.1.len(),
            s.2.len(),
            s.3.len(),
            s.6.iter().map(ReceiptHistory::len).sum(),
        ],
        stage_capacity: stages.map(|rows| rows.capacity()),
        dense_capacity_bytes: (s.4.capacity() + s.5.capacity() + s.7.capacity())
            * std::mem::size_of::<f64>()
            + s.6.capacity() * std::mem::size_of::<ReceiptHistory>(),
        stage_mass: stages.map(|rows| fsum(rows.iter().map(|a| a.1))),
        ready_now: stages.map(|rows| rows.iter().filter(|a| a.2 + a.3 <= s.0 + 1e-10).count()),
        nonempty_histories: s.6.iter().filter(|rows| rows.len() != 0).count(),
    }
}

#[derive(Clone, Debug)]
pub(crate) struct JourneyAttempt {
    pub start_s: f64,
    pub end_s: f64,
    pub before: [usize; 4],
    pub after_prepare: [usize; 4],
    pub candidate: [usize; 4],
    pub generated: [usize; 3],
    pub retired: [usize; 3],
    pub receipts_added: usize,
    pub emitted_offers: usize,
    pub committed: bool,
    pub phase: &'static str,
}

/// Aggregate wall time within one coupled advance call. Timings are diagnostic
/// only: they do not enter snapshots, model identity or any numerical branch.
#[derive(Clone, Copy, Debug, Default)]
pub(crate) struct JourneyPhaseMetrics {
    pub prepare_s: f64,
    pub service_prepare_s: f64,
    pub road_step_s: f64,
    pub service_finish_s: f64,
    pub journey_finish_s: f64,
    pub other_tick_s: f64,
    pub binding_s: f64,
    pub successful_ticks: usize,
    pub failed_ticks: usize,
}
impl JourneyPhaseMetrics {
    fn phase_sum(&self) -> f64 {
        self.prepare_s
            + self.service_prepare_s
            + self.road_step_s
            + self.service_finish_s
            + self.journey_finish_s
    }
}

const LEG_CHUNK: usize = 1024;

fn release_unused_stage_capacity(stage: &mut StageQueue) {
    stage.compact_registry();
}

/// Dynamic allocations only; dense per-leg arrays are part of the static
/// constructor accounting. Each live history is charged with its shared prefix.
pub(crate) fn journey_storage_bytes(s: &Journey) -> usize {
    s.1.storage_bytes()
        .saturating_add(s.2.storage_bytes())
        .saturating_add(s.3.storage_bytes())
        .saturating_add(s.6.iter().map(ReceiptHistory::storage_bytes).sum::<usize>())
}
pub(crate) fn journey_decoded_storage_upper_bytes(s: &Journey) -> usize {
    let (final_bytes, extra) =
        s.6.iter()
            .fold((0usize, 0usize), |(total, extra), history| {
                let final_bytes = history.decoded_final_storage_upper_bytes();
                (
                    total.saturating_add(final_bytes),
                    extra.max(
                        history
                            .decoded_storage_upper_bytes()
                            .saturating_sub(final_bytes),
                    ),
                )
            });
    stage_decoded_storage_upper_bytes(s)
        .saturating_add(final_bytes)
        .saturating_add(extra)
}
fn stage_decoded_storage_upper_bytes(s: &Journey) -> usize {
    s.1.decoded_storage_upper_bytes()
        .saturating_add(s.2.decoded_storage_upper_bytes())
        .saturating_add(s.3.decoded_storage_upper_bytes())
}
const WORKING_COPIES: usize = 3;
const STORAGE_SCRATCH_RESERVE: usize = 64 * 1024;
fn stage_storage_bytes(s: &Journey) -> usize {
    s.1.storage_bytes()
        .saturating_add(s.2.storage_bytes())
        .saturating_add(s.3.storage_bytes())
}
fn check_storage_limit(
    limit: Option<usize>,
    retained: usize,
    dynamic: usize,
    scratch: usize,
) -> CoreResult<()> {
    let required = dynamic
        .max(retained)
        .saturating_mul(WORKING_COPIES)
        .saturating_add(scratch)
        .saturating_add(STORAGE_SCRATCH_RESERVE);
    if let Some(cap) = limit {
        if crate::v1_trace::guard(
            "journey_store",
            "stored/working",
            required,
            cap,
            &[
                ("retained", retained),
                ("dynamic", dynamic),
                ("scratch", scratch),
            ],
        ) {
            return Ok(());
        }
    }
    if limit.is_some_and(|cap| required > cap) {
        return Err(CoreError::resource(format!("native journey stored/working byte budget: required_bytes={required}, budget_bytes={}, retained_bytes={retained}, dynamic_bytes={dynamic}, scratch_bytes={scratch}",limit.unwrap())));
    }
    Ok(())
}

/// Source-bound original whole-engine checkpoint lifetime. At commit the
/// input, committed and new candidate owners coexist. At a later reload,
/// the third slot is the freshly decoded checkpoint instead. Candidate and
/// future decoded state are never both the third simultaneously live owner.
///
/// Charge ALL individually known first two owners even when Arc pointer
/// aliases share payload. Charge the *larger* of candidate and future decode
/// as the distinct third owner, and charge the maximum physical scratch of
/// the separate phases. This is not a reduction of the original cap and does
/// not change the old checkpoint wire or physical integration.
#[derive(Clone,Copy)]
struct CheckpointabilityTerms {
    input_road:usize,
    current_road:usize,
    road_pair_credit:usize,
    candidate_road:usize,
    decoded_road:usize,
    journey_input:usize,
    journey_old:usize,
    journey_new:usize,
    journey_decoded:usize,
    event_input:usize,
    event_current:usize,
    event_candidate:usize,
    validation_scratch:usize,
    call_binding_reserve:usize,
    road_decode_scratch:usize,
}

fn checkpointability_phase_lifetime_bytes(t:CheckpointabilityTerms)->usize {
    t.input_road
        .saturating_add(t.current_road.saturating_sub(t.road_pair_credit.min(t.input_road).min(t.current_road)))
        .saturating_add(t.candidate_road.max(t.decoded_road))
        .saturating_add(t.journey_input)
        .saturating_add(t.journey_old)
        .saturating_add(t.journey_new.max(t.journey_decoded))
        .saturating_add(t.event_input)
        .saturating_add(t.event_current)
        .saturating_add(t.event_candidate)
        .saturating_add(
            t.validation_scratch
                .saturating_sub(t.call_binding_reserve)
                .max(t.road_decode_scratch)
                .max(STORAGE_SCRATCH_RESERVE)
        )
}

fn phase_storage_allowance(total: usize, other_live: usize, phase: &str) -> CoreResult<usize> {
    if crate::v1_trace::guard("phase_allowance", phase, other_live, total, &[]) {
        // Diagnostic observe build only: continue with a nominal allowance.
        return Ok(total.max(1));
    }
    total.checked_sub(other_live).filter(|bytes| *bytes > 0).ok_or_else(|| {
        CoreError::resource(format!(
            "native coupled storage budget exceeded before {phase}: other_live_bytes={other_live}, budget_bytes={total}"
        ))
    })
}

type JourneyRow = (
    f64,
    Vec<Access>,
    Vec<Access>,
    Vec<Access>,
    Vec<f64>,
    Vec<f64>,
    Vec<Vec<(f64, f64)>>,
    Vec<f64>,
);

fn bad(message: &str) -> CoreError {
    CoreError::value(message.to_owned())
}
fn nonnegative(values: impl IntoIterator<Item = f64>) -> bool {
    values.into_iter().all(|x| x.is_finite() && x >= 0.0)
}
fn service_observer_group_bound(rows:usize,legs:usize,bus:usize,freight:usize)->usize{
    rows.min(legs).min(bus.saturating_add(freight))
}
fn service_egress_rows(
    stage: &StageQueue,
    bus: &HashMap<usize, [f64;3]>,
    freight: &HashMap<usize, [f64;3]>,
)->HashMap<usize, Vec<f64>>{
    let mut observed = HashMap::<usize,Vec<f64>>::new();
    if bus.is_empty() && freight.is_empty(){return observed}
    for a in stage{
        if bus.contains_key(&a.0) || freight.contains_key(&a.0){
            observed.entry(a.0).or_default().push(a.1);
        }
    }
    observed
}
// Non-overlapping partials, with the final half-even adjustment of math.fsum.
pub(crate) fn fsum(values: impl IntoIterator<Item = f64>) -> f64 {
    let mut partials: smallvec::SmallVec<[f64; 4]> = smallvec::SmallVec::new();
    for mut x in values {
        let mut i = 0;
        for j in 0..partials.len() {
            let mut y = partials[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            if !hi.is_finite() {
                return hi;
            }
            let lo = y - (hi - x);
            if lo != 0.0 {
                partials[i] = lo;
                i += 1;
            }
            x = hi;
        }
        partials.truncate(i);
        if x != 0.0 {
            partials.push(x);
        }
    }
    let Some(mut hi) = partials.pop() else {
        return 0.0;
    };
    let mut lo = 0.0;
    while let Some(y) = partials.pop() {
        let x = hi;
        hi = x + y;
        lo = y - (hi - x);
        if lo != 0.0 {
            break;
        }
    }
    if let Some(last) = partials.last() {
        if (lo < 0.0 && *last < 0.0) || (lo > 0.0 && *last > 0.0) {
            let y = lo * 2.0;
            let x = hi + y;
            if y == x - hi {
                hi = x;
            }
        }
    }
    hi
}

#[cfg_attr(feature="python-extension", pyclass)]
pub struct NativeServiceCore {
    buses: Vec<Bus>,
    people: Vec<Person>,
    freight: Vec<Source>,
    cars: Vec<Source>,
    people_by_run: Vec<Vec<usize>>,
    last_events: Arc<ChunkedEvents>,
    state: Service,
    pending: Option<(f64, Service)>,
}
impl NativeServiceCore {
    /// Owned immutable heap allocations only. Dense states, event buffers and
    /// the inline NativeServiceCore object are accounted by their own owners.
    pub(crate) fn static_storage_bytes(&self) -> usize {
        let mut bytes = vec_storage_bytes(&self.buses)
            .saturating_add(vec_storage_bytes(&self.people))
            .saturating_add(vec_storage_bytes(&self.freight))
            .saturating_add(vec_storage_bytes(&self.cars))
            .saturating_add(vec_storage_bytes(&self.people_by_run));
        for bus in &self.buses {
            bytes = bytes
                .saturating_add(string_storage_bytes(&bus.0))
                .saturating_add(vec_storage_bytes(&bus.1));
        }
        for source in self.freight.iter().chain(&self.cars) {
            bytes = bytes.saturating_add(string_storage_bytes(&source.0));
        }
        for indices in &self.people_by_run {
            bytes = bytes.saturating_add(vec_storage_bytes(indices));
        }
        bytes
    }
    pub(crate) fn event_backing_matches(&self,other:&ServiceCheckpoint)->bool{Arc::ptr_eq(&self.last_events,&other.1)}
    pub(crate) fn event_storage_bytes(&self) -> usize {
        self.last_events.retained_storage_bytes()
    }
    /// Fixed-count source preparation workspace: one offer per bus/source,
    /// generated labels, geometric offer-buffer growth/physical conversion,
    /// eligibility flags and one run's boarding keys/fsum workspace.
    pub(crate) fn prepare_scratch_bytes(&self) -> usize {
        let count = self
            .buses
            .len()
            .saturating_add(self.freight.len())
            .saturating_add(self.cars.len());
        let buffer_per_offer =
            4 * std::mem::size_of::<Offer>() + std::mem::size_of::<crate::v1_road::Offer>();
        let mut bytes = count
            .saturating_mul(buffer_per_offer)
            .saturating_add(self.people.len())
            .saturating_add(4 * RETAINED_ALLOCATION_PADDING);
        for id in self
            .buses
            .iter()
            .map(|row| &row.0)
            .chain(self.freight.iter().map(|row| &row.0))
            .chain(self.cars.iter().map(|row| &row.0))
        {
            // Prefix/separators and at most 20 decimal digits for a stop
            // index; formatting growth can reserve twice the final length.
            bytes = bytes
                .saturating_add(id.len().saturating_add(28).saturating_mul(2))
                .saturating_add(RETAINED_ALLOCATION_PADDING);
        }
        let boarding = self.people_by_run.iter().map(Vec::len).max().unwrap_or(0);
        bytes.saturating_add(
            boarding
                .saturating_mul(2 * (std::mem::size_of::<usize>() + std::mem::size_of::<f64>())),
        )
    }
    pub(crate) fn state(&self) -> &Service {
        &self.state
    }
    pub(crate) fn sources(&self) -> (&[Source], &[Source]) {
        (&self.freight, &self.cars)
    }
    pub(crate) fn checkpoint(&self) -> ServiceCheckpoint {
        (self.state.clone(), self.last_events.clone())
    }
    pub(crate) fn rollback(&mut self, state: ServiceCheckpoint) {
        self.state = state.0;
        self.last_events = state.1;
        self.pending = None;
    }
    pub(crate) fn install_state(&mut self, state: ServiceCheckpoint) {
        self.rollback(state);
    }
    pub(crate) fn write_state<W: Write>(&self, w: &mut W) -> CoreResult<()> {
        if self.pending.is_some() {
            return Err(bad("cannot checkpoint pending native service transition"));
        }
        Self::write_snapshot(w,&self.state,&self.last_events)
    }
    pub(crate) fn write_snapshot<W:Write>(w:&mut W,s:&Service,events:&ChunkedEvents)->CoreResult<()> {Self::write_snapshot_codec(w,s,events,false)}
    pub(crate) fn write_snapshot_codec<W:Write>(w:&mut W,s:&Service,events:&ChunkedEvents,event_runs:bool)->CoreResult<()> {
        write_len(w, s.0.len())?;
        for v in &s.0 {
            write_len(w, v.0)?;
            write_u64(w, v.1 as u64)?;
            for x in [v.2, v.3, v.4] {
                write_f64(w, x)?;
            }
        }
        write_len(w, s.1.len())?;
        for v in &s.1 {
            for x in [v.0, v.1, v.2, v.3, v.4] {
                write_f64(w, x)?;
            }
        }
        write_len(w, s.2.len())?;
        for &v in &s.2 {
            write_u64(w, u64::from(v))?;
        }
        write_len(w, s.3.len())?;
        for &v in &s.3 {
            write_f64(w, v)?;
        }
        write_len(w, s.4.len())?;
        for &v in &s.4 {
            write_u64(w, u64::from(v))?;
        }
        write_len(w, events.len())?;
        if event_runs{let packed=events.can_write_runs();write_u64(w,u64::from(packed))?;if packed{return events.write_runs(w)}}
        for e in events.iter() {
            write_len(w, e.0)?;
            write_len(w, e.1)?;
            write_u64(w, u64::from(e.2.is_some()))?;
            if let Some(v) = e.2 {
                write_len(w, v)?;
            }
            for v in [e.3, e.4, e.5, e.6] {
                write_f64(w, v)?;
            }
        }
        Ok(())
    }
    pub(crate) fn read_state<R: Read>(
        &self,
        r: &mut R,
        event_limit: usize,
        event_byte_limit: Option<usize>,
        compressed: bool,
    ) -> CoreResult<ServiceCheckpoint> {self.read_state_codec(r,event_limit,event_byte_limit,compressed,false)}
    pub(crate) fn read_state_codec<R:Read>(&self,r:&mut R,event_limit:usize,event_byte_limit:Option<usize>,compressed:bool,event_runs:bool)->CoreResult<ServiceCheckpoint>{
        fn flag<R: Read>(r: &mut R) -> CoreResult<bool> {
            match read_u64(r)? {
                0 => Ok(false),
                1 => Ok(true),
                _ => Err(bad("invalid checkpoint boolean")),
            }
        }
        read_exact_len(r, self.buses.len())?;
        let mut runs = checkpoint_vec(self.buses.len())?;
        for b in &self.buses {
            runs.push((
                read_len(r, b.1.len())?,
                read_len(r, 2)? as u8,
                read_f64(r)?,
                read_f64(r)?,
                read_f64(r)?,
            ));
        }
        read_exact_len(r, self.people.len())?;
        let mut people = checkpoint_vec(self.people.len())?;
        for _ in &self.people {
            people.push((
                read_f64(r)?,
                read_f64(r)?,
                read_f64(r)?,
                read_f64(r)?,
                read_f64(r)?,
            ));
        }
        read_exact_len(r, self.freight.len())?;
        let mut released = checkpoint_vec(self.freight.len())?;
        for _ in &self.freight {
            released.push(flag(r)?);
        }
        read_exact_len(r, self.freight.len())?;
        let mut completed = checkpoint_vec(self.freight.len())?;
        for _ in &self.freight {
            completed.push(read_f64(r)?);
        }
        read_exact_len(r, self.cars.len())?;
        let mut cars = checkpoint_vec(self.cars.len())?;
        for _ in &self.cars {
            cars.push(flag(r)?);
        }
        let n = read_len(r, event_limit)?;
        if event_runs&&flag(r)?{if !compressed{return Err(bad("event run wire outside compact domain"))}let events=ChunkedEvents::read_runs(r,n,event_byte_limit)?;let state=(runs,people,released,completed,cars);self.validate(&state)?;return Ok((state,Arc::new(events)))}
        // Consume the unchanged logical wire directly into its immutable carrier.
        // No flat EventRow buffer coexists with the encoded history during load.
        let mut events = ChunkedEvents::new(compressed);
        if let Some(limit) = event_byte_limit {
            let required = events.retained_storage_bytes();
            if required > limit {
                return Err(CoreError::resource(format!(
                    "native service event decode storage budget exceeded: required_bytes={required}, budget_bytes={limit}"
                )));
            }
        }
        for _ in 0..n {
            let tag = read_len(r, usize::MAX)?;
            let origin = read_len(r, usize::MAX)?;
            let dest = if flag(r)? {
                Some(read_len(r, usize::MAX)?)
            } else {
                None
            };
            let e = (
                tag,
                origin,
                dest,
                read_f64(r)?,
                read_f64(r)?,
                read_f64(r)?,
                read_f64(r)?,
            );
            if !nonnegative([e.3, e.4, e.5, e.6]) {
                return Err(bad("invalid checkpoint road event"));
            }
            if let Some(limit) = event_byte_limit {
                // This source-derived bound includes append allocation peaks and
                // is constant-time; scanning existing pages per row is quadratic.
                let required = events.projected_append_storage_bytes(e)?;
                if required > limit {
                    return Err(CoreError::resource(format!(
                        "native service event decode storage budget exceeded: required_bytes={required}, budget_bytes={limit}"
                    )));
                }
            }
            events.push_checked(e)?;
        }
        let state = (runs, people, released, completed, cars);
        self.validate(&state)?;
        Ok((state, Arc::new(events)))
    }
    fn validate(&self, s: &Service) -> CoreResult<()> {
        if s.0.len() != self.buses.len()
            || s.1.len() != self.people.len()
            || s.2.len() != self.freight.len()
            || s.3.len() != self.freight.len()
            || s.4.len() != self.cars.len()
        {
            return Err(bad("native service state lengths differ"));
        }
        for (b, v) in self.buses.iter().zip(&s.0) {
            if v.1 > 2
                || v.0 > b.1.len()
                || (v.1 == 2) != (v.0 == b.1.len())
                || !nonnegative([v.2, v.3, v.4])
                || v.3 > 1.0 + 1e-8
            {
                return Err(bad("invalid native bus state"));
            }
        }
        for (p, v) in self.people.iter().zip(&s.1) {
            // The reference's +1e-10 boarding tolerance can give a small
            // negative waiting moment; preserve it rather than clip the law.
            if !nonnegative([v.0, v.1, v.2, v.4])
                || !v.3.is_finite()
                || (v.0 + v.1 + v.2 - p.4).abs() > 1e-8_f64.max(1e-9 * p.4)
            {
                return Err(bad("native person conservation failure"));
            }
        }
        for (i, b) in self.buses.iter().enumerate() {
            let load = fsum(self.people_by_run[i].iter().map(|k| s.1[*k].1));
            if load > b.2 + 1e-8 {
                return Err(bad("native bus overcapacity"));
            }
        }
        for (f, c) in self.freight.iter().zip(&s.3) {
            if !c.is_finite() || *c < 0.0 || *c > f.2 + 1e-8 {
                return Err(bad("native freight conservation failure"));
            }
        }
        Ok(())
    }
}
crate::optional_binding::optional_pymethods!(NativeServiceCore,
    [
    #[new]
    ] {
    pub(crate) fn new(
        buses: Vec<Bus>,
        people: Vec<Person>,
        freight: Vec<Source>,
        cars: Vec<Source>,
    ) -> CoreResult<Self> {
        let mut ids = HashSet::new();
        for b in &buses {
            if b.0.is_empty()
                || !ids.insert(b.0.clone())
                || b.1.is_empty()
                || !nonnegative(b.1.iter().copied().chain([b.2, b.3]))
                || b.2 == 0.0
                || b.1.windows(2).any(|x| x[0] > x[1])
            {
                return Err(bad("invalid native bus declaration"));
            }
        }
        for p in &people {
            if p.0 >= buses.len()
                || p.1 >= p.2
                || p.2 > buses[p.0].1.len()
                || !nonnegative([p.3, p.4])
            {
                return Err(bad("invalid native passenger declaration"));
            }
        }
        for sources in [&freight, &cars] {
            let mut ids = HashSet::new();
            if sources.iter().any(|f| {
                f.0.is_empty() || !ids.insert(&f.0) || !nonnegative([f.1, f.2]) || f.2 == 0.0
            }) {
                return Err(bad("invalid native freight/car declaration"));
            }
        }
        let state = (
            vec![(0, 0, 0.0, 0.0, 0.0); buses.len()],
            people.iter().map(|p| (p.4, 0.0, 0.0, 0.0, 0.0)).collect(),
            vec![false; freight.len()],
            vec![0.0; freight.len()],
            vec![false; cars.len()],
        );
        let mut people_by_run = vec![Vec::new(); buses.len()];
        for (k, p) in people.iter().enumerate() {
            people_by_run[p.0].push(k);
        }
        Ok(Self {
            buses,
            people,
            freight,
            cars,
            people_by_run,
            last_events: Arc::new(ChunkedEvents::new(false)),
            state,
            pending: None,
        })
    }
    }
    [

    ] {

    fn snapshot(&self) -> Service {
        self.state.clone()
    }
    }
    [

    ] {

    /// Inspection only: immutable static heap, one dense state, event buffer.
    fn storage_accounting(&self) -> (usize, usize, usize) {
        (
            self.static_storage_bytes(),
            service_dense_storage_bytes(&self.state),
            self.event_storage_bytes(),
        )
    }
    }
    [

    ] {

    fn road_events(&self) -> Vec<EventRow> {
        // Explicit publication boundary: internal consumers iterate the carrier.
        self.last_events.iter().collect()
    }
    }
    [

    ] {

    fn restore(&mut self, state: Service) -> CoreResult<()> {
        self.validate(&state)?;
        self.state = state;
        self.pending = None;
        self.last_events = Arc::new(ChunkedEvents::new(false));
        Ok(())
    }
    }
    [

    ] {

    fn abort(&mut self) {
        self.pending = None;
    }
    }
    [

    ] {

    fn prepare(&mut self, t: f64, eligible: Vec<bool>) -> CoreResult<Vec<Offer>> {
        if !nonnegative([t]) || eligible.len() != self.people.len() || self.pending.is_some() {
            return Err(bad(
                "invalid native service prepare clock/eligibility/phase",
            ));
        }
        self.validate(&self.state)?;
        let mut s = self.state.clone();
        let mut offers = Vec::new();
        for (i, b) in self.buses.iter().enumerate() {
            let v = s.0[i];
            if v.1 != 0 || t + 1e-10 < v.2.max(b.1[v.0]) {
                continue;
            }
            let load = fsum(self.people_by_run[i].iter().map(|k| s.1[*k].1));
            let keys: Vec<usize> = self.people_by_run[i]
                .iter()
                .copied()
                .filter(|k| {
                    self.people[*k].1 == v.0
                        && eligible[*k]
                        && self.people[*k].3 <= t + 1e-10
                        && s.1[*k].0 > 0.0
                })
                .collect();
            let total = fsum(keys.iter().map(|k| s.1[*k].0));
            if !total.is_finite() {
                return Err(bad("native boarding total overflow"));
            }
            let fraction = if total != 0.0 {
                1.0_f64.min((b.2 - load).max(0.0) / total)
            } else {
                0.0
            };
            for k in keys {
                let x = &mut s.1[k];
                let amount = x.0 * fraction;
                x.0 -= amount;
                x.1 += amount;
                x.3 += amount * (t - self.people[k].3);
            }
            offers.push((format!("bus:{}:{}", b.0, v.0), 1.0, t));
            s.0[i] = (v.0, 1, v.2, v.3, v.4 + (t - b.1[v.0]).max(0.0));
        }
        for (i, f) in self.freight.iter().enumerate() {
            if !s.2[i] && t + 1e-10 >= f.1 {
                offers.push((format!("freight:{}", f.0), f.2, f.2 * t));
                s.2[i] = true;
            }
        }
        for (i, c) in self.cars.iter().enumerate() {
            if !s.4[i] && t + 1e-10 >= c.1 {
                offers.push((format!("car:{}", c.0), c.2, c.2 * t));
                s.4[i] = true;
            }
        }
        self.pending = Some((t, s));
        Ok(offers)
    }
    }
    [

    ] {

    fn finish(&mut self,end:f64,events:Vec<Sink>)->CoreResult<()>{self.finish_borrowed(end,events.iter().map(|e|Ok((e.0.as_str(),e.1,e.2))),false)}
    }
);

fn fraction(profile: &Profile, t: f64) -> f64 {
    fsum(
        profile
            .iter()
            .map(|w| w.2 * (t.min(w.1) - 0.0_f64.max(w.0)).max(0.0) / (w.1 - w.0)),
    )
}
fn birth_between(profile: &Profile, lo: f64, hi: f64) -> f64 {
    let mut windows = profile.clone();
    windows.sort_by(|a, b| a.0.total_cmp(&b.0));
    let (mut total, mut moment) = (0.0, 0.0);
    for w in windows {
        let a = lo.max(total);
        let b = hi.min(total + w.2);
        if b > a {
            let x = w.0 + (a - total) * (w.1 - w.0) / w.2;
            let y = w.0 + (b - total) * (w.1 - w.0) / w.2;
            moment += (b - a) * (x + y) / 2.0;
        }
        total += w.2;
    }
    moment / (hi - lo)
}
// Profile and released fraction are checked by the journey contract.
 // Do not visit parent receipts when even the profile cap cannot release.
fn release_high(profile:f64,lo:f64,eligible:impl FnOnce()->f64)->Option<f64>{
    if profile<=lo {return None}
    let hi=profile.min(eligible());
    if hi<=lo{None}else{Some(hi)}
}
// Eligibility is a finite nonnegative subset sum of positive receipts.
fn released_eligible(released:f64, mass:f64, tol:f64, eligible:impl FnOnce()->f64)->bool{
    released<=tol || released<=mass*eligible()+tol
}
// For a private child, the profile is zero through its first window start.
// The entire old parent measure is eligible by any subsequent observation if
// its newest possible receipt plus dwell is no later than that start.
fn private_profile_hides_old_history(end:f64,dwell:f64,kind:u8,profile:&Profile)->bool{
    kind!=0&&profile.iter().map(|w|w.0).reduce(f64::min).is_some_and(|start|end+dwell<=start)
}
fn eligible(legs: &[SharedJourneyLeg], s: &Journey, i: usize) -> f64 {
    match legs[i].2 {
        None => 1.0,
        Some(parent) if parent >= legs.len() => 0.0,
        Some(parent) => s.6[parent].eligible(legs[i].3, s.0),
    }
}
fn valid_law(law: &Law) -> bool {
    !law.is_empty()
        && law.iter().all(|w| nonnegative([w.0, w.1]) && w.1 > 0.0)
        && (fsum(law.iter().map(|w| w.1)) - 1.0).abs() <= 1e-12
}
#[cfg_attr(feature="python-extension", pyclass)]
pub struct NativeJourneyCore {
    legs: Vec<SharedJourneyLeg>,
    bus: Vec<SharedBusMeta>,
    freight: Vec<SharedFreightMeta>,
    route_indices: HashMap<String, usize>,
    budget: usize,
    state: Journey,
    pending: Option<Journey>,
    defer_finish_commit: bool,
    deferred_previous: Option<(Journey, usize, usize, usize, usize)>,
    tick_times_s: Vec<f64>,
    peak_records: usize,
    history_rows: usize,
    research_receipt_period_s:Option<u64>,
    research_group_outlets:bool,
    research_receipt_grid_step:Option<f64>,
    research_schedule_receipts:bool,
    research_stream_receipts:bool,
    research_egress_buckets:bool,
    research_entry_buckets:bool,
    research_delay_calendar:bool,
    history_bytes: usize,
    history_decoded_final: usize,
    history_decode_extra_max: usize,
    storage_budget: Option<usize>,
    retained_input_bytes: usize,
    max_tag_bytes: usize,
    max_profile_rows: usize,
    last_attempt: Option<JourneyAttempt>,
    phase_metrics: JourneyPhaseMetrics,
}
impl NativeJourneyCore {
    /// Owned immutable heap allocations only. Arc<Vec> allocations are counted
    /// once by object identity across legs and bus/freight metadata, including
    /// empty Arc allocations. Engine profile pointer registries count only
    /// their own buffers, since this owner charges the shared profile payloads.
    pub(crate) fn static_storage_bytes(&self) -> usize {
        let mut bytes = vec_storage_bytes(&self.legs)
            .saturating_add(vec_storage_bytes(&self.bus))
            .saturating_add(vec_storage_bytes(&self.freight))
            .saturating_add(hash_capacity_storage_bytes::<String, usize>(
                self.route_indices.capacity(),
            ));
        let mut profiles = HashSet::new();
        let mut laws = HashSet::new();
        for leg in &self.legs {
            bytes = bytes.saturating_add(string_storage_bytes(&leg.0));
            if profiles.insert(Arc::as_ptr(&leg.4) as usize) {
                bytes = bytes.saturating_add(shared_vec_storage_bytes(&leg.4));
            }
            for law in [&leg.6, &leg.7] {
                if laws.insert(Arc::as_ptr(law) as usize) {
                    bytes = bytes.saturating_add(shared_vec_storage_bytes(law));
                }
            }
        }
        for law in self
            .bus
            .iter()
            .map(|row| &row.5)
            .chain(self.freight.iter().map(|row| &row.3))
        {
            if laws.insert(Arc::as_ptr(law) as usize) {
                bytes = bytes.saturating_add(shared_vec_storage_bytes(law));
            }
        }
        for tag in self.route_indices.keys() {
            bytes = bytes.saturating_add(string_storage_bytes(tag));
        }
        bytes
    }

    /// Parallel proposal/validation workers may each clone and sort one full
    /// departure profile. Scalar and non-overlapping expansion scratch has a
    /// separate reserve; the caller multiplies this by the actual worker count.
    pub(crate) fn per_worker_scratch_bytes(&self) -> usize {
        let profile_rows = self.max_profile_rows;
        (64usize * 1024)
            .saturating_add(profile_rows.saturating_mul(2 * std::mem::size_of::<(f64, f64, f64)>()))
            .saturating_add(4 * RETAINED_ALLOCATION_PADDING)
    }

    /// Scratch bound for cross-owner service binding: egress grouping, its
    /// per-leg Vec capacities, bus/freight maps, one profile clone/sort and one
    /// fsum expansion. Parallel validation's per-worker control reserve and
    /// dense snapshot copies are accounted by the enclosing engine.
    pub(crate) fn validation_scratch_bytes(&self, state: &Journey) -> usize {
        let rows = state.2.len();
        // service_egress_rows stores only actual bus/freight owner keys.
        // The row term remains all egress rows (worst case); the number of
        // materialized Vec/HashMap keys cannot exceed the declared support.
        let groups = service_observer_group_bound(rows,self.legs.len(),self.bus.len(),self.freight.len());
        let egress_vectors = rows
            .saturating_mul(2)
            .saturating_add(groups.saturating_mul(4))
            .saturating_mul(std::mem::size_of::<f64>())
            .saturating_add(groups.saturating_mul(RETAINED_ALLOCATION_PADDING));
        let profile_rows = self.max_profile_rows;
        hash_entries_upper_bytes::<usize, Vec<f64>>(groups)
            .saturating_add(egress_vectors)
            .saturating_add(hash_entries_upper_bytes::<usize, [f64; 3]>(
                self.bus.len().min(self.legs.len()),
            ))
            .saturating_add(hash_entries_upper_bytes::<usize, [f64; 3]>(
                self.freight.len().min(self.legs.len()),
            ))
            .saturating_add(profile_rows.saturating_mul(2 * std::mem::size_of::<(f64, f64, f64)>()))
            .saturating_add(rows.saturating_mul(2 * std::mem::size_of::<f64>()))
            .saturating_add(4 * RETAINED_ALLOCATION_PADDING)
    }

    /// Canonical cross-owner validation envelope shared by engine admission
    /// and the precommit check. Engine's Sum value contains one Vec<f64>.
    pub(crate) fn whole_validation_scratch_bytes(
        &self,
        state: &Journey,
        road_rows: usize,
        route_tags: usize,
    ) -> usize {
        fn map_bytes<K, V>(entries: usize) -> usize {
            if entries == 0 {
                return 0;
            }
            entries
                .saturating_mul(4)
                .saturating_mul(std::mem::size_of::<(K, V)>().saturating_add(1))
                .saturating_add(256)
        }
        let rows = state
            .1
            .len()
            .saturating_add(state.2.len())
            .saturating_add(state.3.len());
        // Engine `stage_sums`: one exact (key, mass) row per stage row, a
        // dense per-leg result, and one leg's `Sum` partials at a time
        // (bounded by binary64 exponent span; 2 KiB covers it with padding).
        let dense = self
            .legs
            .len()
            .saturating_mul(std::mem::size_of::<f64>())
            .saturating_add(RETAINED_ALLOCATION_PADDING);
        let stage_maps = rows
            .saturating_mul(crate::v1_engine::STAGE_SUM_ROW_BYTES)
            .saturating_add(RETAINED_ALLOCATION_PADDING)
            .saturating_add(dense)
            .saturating_add(2048);
        let active_keys = road_rows.min(route_tags);
        let active_maps = dense
            .saturating_add(map_bytes::<usize, f64>(active_keys).saturating_mul(2))
            .saturating_add(
                rows.max(self.legs.len())
                    .saturating_mul(3 * std::mem::size_of::<f64>()),
            )
            .saturating_add(128);
        self.validation_scratch_bytes(state)
            .max(stage_maps)
            .max(active_maps)
    }

    fn begin_deferred_finish(&mut self) -> CoreResult<()> {
        if self.defer_finish_commit || self.deferred_previous.is_some() {
            return Err(bad("native journey deferred transition already active"));
        }
        self.defer_finish_commit = true;
        Ok(())
    }
    fn finalize_deferred_finish(&mut self) {
        self.deferred_previous = None;
        self.defer_finish_commit = false;
        if let Some(attempt) = &mut self.last_attempt {
            attempt.committed = true;
            attempt.phase = "committed";
        }
    }
    fn rollback_deferred_finish(&mut self) {
        if let Some((
            state,
            history_rows,
            history_bytes,
            history_decoded_final,
            history_decode_extra_max,
        )) = self.deferred_previous.take()
        {
            self.state = state;
            self.history_rows = history_rows;
            self.history_bytes = history_bytes;
            self.history_decoded_final = history_decoded_final;
            self.history_decode_extra_max = history_decode_extra_max;
        }
        self.defer_finish_commit = false;
        if let Some(attempt) = &mut self.last_attempt {
            attempt.committed = false;
        }
    }

    /// Reproduce the joint oracle's cross-owner service and original-intent
    /// moment checks, including valid-looking finite checkpoint corruption.
    pub(crate) fn check_service_binding(&self, s: &Journey, service: &Service) -> CoreResult<()> {
        self.validate(s)?;
        if service.1.len() != self.bus.len()
            || service.2.len() != self.freight.len()
            || service.3.len() != self.freight.len()
        {
            return Err(bad("native journey service checkpoint shape differs"));
        }
        let mut bus: HashMap<usize, [f64; 3]> = HashMap::new();
        for (k, b) in self.bus.iter().enumerate() {
            let v = service.1[k];
            let factor = self.legs[b.0].1 / b.1;
            let count = (v.1 + v.2) * factor;
            let row = bus.entry(b.0).or_insert([0.; 3]);
            row[0] += count;
            row[1] += v.2 * factor;
            row[2] += count * b.3 / b.2;
        }
        let mut freight: HashMap<usize, [f64; 3]> = HashMap::new();
        for (k, f) in self.freight.iter().enumerate() {
            let row = freight.entry(f.0).or_insert([0.; 3]);
            if service.2[k] {
                row[0] += f.1;
                row[2] += f.2;
            }
            row[1] += service.3[k];
        }
        // Only bus/freight leg egress is observed by these service equations.
        // Full stage and road conservation is independently checked by validate_bundle.
        let egress = service_egress_rows(&s.2, &bus, &freight);
        for (i, l) in self.legs.iter().enumerate() {
            let released = s.4[i];
            let completed = s.5[i];
            let tol = 1e-9 * l.1.max(1.);
            let mut expected = if l.5 != 0 && released != 0. {
                released * birth_between(&l.4, 0., released / l.1)
            } else {
                0.
            };
            let egress = fsum(egress.get(&i).into_iter().flatten().copied());
            if let Some(v) = bus.get(&i) {
                if (released - v[0]).abs() > tol || (completed + egress - v[1]).abs() > tol {
                    return Err(bad("joint bus stage and physical service ledger differ"));
                }
                expected += v[2];
            }
            if let Some(v) = freight.get(&i) {
                if (released - v[0]).abs() > tol || (completed + egress - v[1]).abs() > tol {
                    return Err(bad(
                        "joint freight stage and physical service ledger differ",
                    ));
                }
                expected += v[2];
            }
            if l.5 == 0
                && !bus.contains_key(&i)
                && !freight.contains_key(&i)
                && (released != 0. || completed != 0.)
            {
                return Err(bad("unsupported joint leg completed or released"));
            }
            if !expected.is_finite() || (s.7[i] - expected).abs() > 1e-9 * expected.abs().max(1.) {
                return Err(bad("joint original birth moment differs"));
            }
        }
        Ok(())
    }
    pub(crate) fn state(&self) -> &Journey {
        &self.state
    }
    pub(crate) fn legs(&self) -> &[SharedJourneyLeg] {
        &self.legs
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn set_research_receipt_period(&mut self,period:u64)->CoreResult<()>{
        if !(10..=3600).contains(&period)||self.storage_budget.is_none(){return Err(bad("receipt closure period outside supported domain"))}
        self.research_receipt_period_s=Some(period);Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_group_outlets(&mut self)->CoreResult<()>{
        if self.research_receipt_period_s.is_none()||self.storage_budget.is_none(){return Err(bad("outlet grouping requires receipt research identity"))}
        self.research_group_outlets=true;Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_receipt_grid(&mut self,dt:f64)->CoreResult<()>{
        if !self.research_group_outlets||!dt.is_finite()||!(1.0..=3600.).contains(&dt)||dt.fract()!=0.{return Err(bad("receipt grid requires grouped outlet research and integral dt"))}
        self.research_receipt_grid_step=Some(dt);Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_schedule_receipts(&mut self)->CoreResult<()>{
        if self.research_receipt_grid_step.is_none(){return Err(bad("schedule receipt closure requires fixed receipt grid"))}
        self.research_schedule_receipts=true;Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_stream_receipts(&mut self)->CoreResult<()>{
        if !self.research_schedule_receipts{return Err(bad("streaming receipts require schedule receipt identity"))}
        self.research_stream_receipts=true;Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_egress_buckets(&mut self)->CoreResult<()>{
        if !self.research_stream_receipts{return Err(bad("egress buckets require streaming receipt identity"))}
        self.research_egress_buckets=true;Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_entry_buckets(&mut self)->CoreResult<()>{
        if !self.research_egress_buckets||self.research_receipt_grid_step.is_none(){return Err(bad("entry buckets require egress and fixed grid identity"))}
        self.research_entry_buckets=true;Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn enable_research_delay_calendar(&mut self)->CoreResult<()>{
        if !self.research_entry_buckets||!self.research_egress_buckets{return Err(bad("delay calendar requires both entry and egress identities"))}
        self.research_delay_calendar=true;Ok(())
    }
    pub(crate) fn owned_time(&self) -> f64 {
        self.state.0
    }
    pub(crate) fn owned_metrics(&self) -> (&[f64], usize) {
        (&self.tick_times_s, self.peak_records)
    }
    pub(crate) fn owned_phase_metrics(&self) -> &JourneyPhaseMetrics {
        &self.phase_metrics
    }
    pub(crate) fn checkpoint(&self) -> Journey {
        self.state.clone()
    }
    pub(crate) fn rollback(&mut self, state: Journey) {
        let (rows, bytes, decoded, extra) = state.6.iter().fold(
            (0usize, 0usize, 0usize, 0usize),
            |(rows, bytes, decoded, extra), history| {
                let final_bytes = history.decoded_final_storage_upper_bytes();
                (
                    rows.saturating_add(history.len()),
                    bytes.saturating_add(history.storage_bytes()),
                    decoded.saturating_add(final_bytes),
                    extra.max(
                        history
                            .decoded_storage_upper_bytes()
                            .saturating_sub(final_bytes),
                    ),
                )
            },
        );
        self.history_rows = rows;
        self.history_bytes = bytes;
        self.history_decoded_final = decoded;
        self.history_decode_extra_max = extra;
        self.retained_input_bytes = 0;
        self.state = state;
        self.pending = None;
        self.defer_finish_commit = false;
        self.deferred_previous = None;
        self.last_attempt = None;
    }
    /// Opt-in whole-engine byte accounting. Legacy direct cores retain their
    /// raw-record guard. The enclosing engine binds this policy in identity.
    pub(crate) fn configure_storage_budget(&mut self, bytes: usize) -> CoreResult<()> {
        if bytes == 0 {
            return Err(bad("positive native journey storage budget required"));
        }
        check_storage_limit(
            Some(bytes),
            self.retained_input_bytes,
            journey_storage_bytes(&self.state),
            0,
        )?;
        self.storage_budget = Some(bytes);
        Ok(())
    }
    pub(crate) fn storage_budget(&self) -> Option<usize> {
        self.storage_budget
    }
    /// The enclosing owner has already subtracted other live allocations.
    /// Updating this nonphysical allowance must not clone or validate state.
    pub(crate) fn set_phase_storage_budget(&mut self, bytes: usize) -> CoreResult<()> {
        if bytes == 0 {
            return Err(CoreError::resource(
                "native journey storage budget is empty",
            ));
        }
        self.storage_budget = Some(bytes);
        Ok(())
    }
    pub(crate) fn clear_call_storage_accounting(&mut self) {
        self.retained_input_bytes = 0;
    }
    pub(crate) fn last_attempt(&self) -> Option<&JourneyAttempt> {
        self.last_attempt.as_ref()
    }
    pub(crate) fn record_counts(&self) -> [usize; 4] {
        [
            self.state.1.len(),
            self.state.2.len(),
            self.state.3.len(),
            self.history_rows,
        ]
    }
    fn phase(&mut self, phase: &'static str) {
        if let Some(attempt) = &mut self.last_attempt {
            attempt.phase = phase;
        }
    }
    pub(crate) fn install_state(&mut self, state: Journey) {
        self.rollback(state);
    }
    pub(crate) fn write_state<W: Write>(&self, w: &mut W) -> CoreResult<()> {
        if self.pending.is_some() || self.defer_finish_commit {
            return Err(bad("cannot checkpoint pending native journey transition"));
        }
        Self::write_snapshot(w,&self.state)
    }
    pub(crate) fn write_snapshot<W:Write>(w:&mut W,s:&Journey)->CoreResult<()> {
        if cfg!(all(feature="native-cli",not(feature="python-extension")))&&std::env::var_os("METROFLOW_NATIVE_SCALAR_JOURNEY_WIRE").as_deref()!=Some(std::ffi::OsStr::new("1")){return Self::write_snapshot_batched(w,s)}
        Self::write_snapshot_scalar(w,s)
    }
    fn write_snapshot_batched<W:Write>(w:&mut W,s:&Journey)->CoreResult<()>{
        let mut b=JourneyWords::new(w);b.word(s.0.to_bits())?;
        for stage in [&s.1,&s.2,&s.3]{b.word(stage.len()as u64)?;for a in stage{b.word(a.0 as u64)?;for x in [a.1,a.2,a.3]{b.word(x.to_bits())?;}}}
        for values in [&s.4,&s.5]{b.word(values.len()as u64)?;for &v in values{b.word(v.to_bits())?;}}
        b.word(s.6.len()as u64)?;for h in &s.6{b.word(h.len()as u64)?;h.visit_ordered(|(t,v)|{b.word(t.to_bits())?;b.word(v.to_bits())})?;}
        b.word(s.7.len()as u64)?;for &v in &s.7{b.word(v.to_bits())?;}
        b.flush()
    }
    fn write_snapshot_scalar<W:Write>(w:&mut W,s:&Journey)->CoreResult<()> {
        write_f64(w, s.0)?;
        for stage in [&s.1, &s.2, &s.3] {
            write_len(w, stage.len())?;
            for a in stage {
                write_len(w, a.0)?;
                for v in [a.1, a.2, a.3] {
                    write_f64(w, v)?;
                }
            }
        }
        for values in [&s.4, &s.5] {
            write_len(w, values.len())?;
            for &v in values {
                write_f64(w, v)?;
            }
        }
        write_len(w, s.6.len())?;
        for rows in &s.6 {
            write_len(w, rows.len())?;
            for &(t, v) in rows.iter() {
                write_f64(w, t)?;
                write_f64(w, v)?;
            }
        }
        write_len(w, s.7.len())?;
        for &v in &s.7 {
            write_f64(w, v)?;
        }
        Ok(())
    }
    pub(crate) fn read_state<R: Read>(&self, r: &mut R) -> CoreResult<Journey> {
        let t = read_f64(r)?;
        let n = self.legs.len();
        let retained = self
            .retained_input_bytes
            .max(journey_storage_bytes(&self.state));
        let mut remaining = if self.storage_budget.is_some() {
            usize::MAX
        } else {
            self.budget
        };
        let mut stage_bytes = 0usize;
        let mut stages = Vec::with_capacity(3);
        for _ in 0..3 {
            let m = read_len(r, remaining)?;
            remaining -= m;
            let mut stage = StageQueue::new();
            for _ in 0..m {
                check_storage_limit(
                    self.storage_budget,
                    retained,
                    stage_bytes.saturating_add(stage.append_upper_bytes(1)),
                    0,
                )?;
                stage.push((read_len(r, n)?, read_f64(r)?, read_f64(r)?, read_f64(r)?));
            }
            stage_bytes = stage_bytes.saturating_add(stage.storage_bytes());
            stages.push(stage);
        }
        let mut values = Vec::with_capacity(2);
        for _ in 0..2 {
            read_exact_len(r, n)?;
            let mut row = checkpoint_vec(n)?;
            for _ in 0..n {
                row.push(read_f64(r)?);
            }
            values.push(row);
        }
        read_exact_len(r, n)?;
        let mut histories = checkpoint_vec(n)?;
        let mut history_bytes = 0usize;
        for _ in 0..n {
            let m = read_len(r, remaining)?;
            remaining -= m;
            let mut history = ReceiptHistory::default();
            for _ in 0..m {
                check_storage_limit(
                    self.storage_budget,
                    retained,
                    stage_bytes
                        .saturating_add(history_bytes)
                        .saturating_add(history.append_upper_bytes()),
                    0,
                )?;
                history.push((read_f64(r)?, read_f64(r)?)).map_err(bad)?;
            }
            history_bytes = history_bytes.saturating_add(history.storage_bytes());
            histories.push(history);
        }
        read_exact_len(r, n)?;
        let mut births = checkpoint_vec(n)?;
        for _ in 0..n {
            births.push(read_f64(r)?);
        }
        let internal = stages.pop().unwrap();
        let egress = stages.pop().unwrap();
        let entering = stages.pop().unwrap();
        let completed = values.pop().unwrap();
        let released = values.pop().unwrap();
        let state = (
            t, entering, egress, internal, released, completed, histories, births,
        );
        self.validate(&state)?;
        Ok(state)
    }
    fn validate(&self, s: &Journey) -> CoreResult<()> {
        let n = self.legs.len();
        if !nonnegative([s.0])
            || s.4.len() != n
            || s.5.len() != n
            || s.6.len() != n
            || s.7.len() != n
        {
            return Err(bad("native journey snapshot shape/clock differs"));
        }
        // Read-only checks are independent across leg indices. No floating
        // point reduction is parallelized and error selection stays stable.
        let valid = ordered_map(n.div_ceil(LEG_CHUNK), 2, |chunk| {
            let start = chunk * LEG_CHUNK;
            let end = (start + LEG_CHUNK).min(n);
            (start..end).all(|i| {
                let l = &self.legs[i];
                let tol = 1e-9 * l.1.max(1.0);
                nonnegative([s.4[i], s.5[i], s.7[i]])
                    && s.5[i] <= s.4[i] + tol
                    && s.4[i] <= l.1 * fraction(&l.4, s.0) + tol
                    && s.6[i].valid_at(s.0)
                    && (s.6[i].total() * l.1 - s.5[i]).abs() <= tol
                    && released_eligible(s.4[i],l.1,tol,||eligible(&self.legs,s,i))
            })
        });
        if valid.into_iter().any(|valid| !valid) {
            return Err(bad(
                "native journey conservation/receipt/eligibility failure",
            ));
        }
        for stage in [&s.1, &s.2, &s.3] {
            if !stage.valid_at(n, s.0) {
                return Err(bad("invalid native access stage"));
            }
        }
        let records =
            s.1.len() + s.2.len() + s.3.len() + s.6.iter().map(ReceiptHistory::len).sum::<usize>();
        if self.storage_budget.is_none() && records > self.budget {
            return Err(CoreError::resource("joint journey record budget"));
        }
        if self.storage_budget.is_some() {
            check_storage_limit(
                self.storage_budget,
                self.retained_input_bytes,
                journey_storage_bytes(s),
                0,
            )?;
        }
        Ok(())
    }
}

/// Coupled numerical loop: one mutable owner of road, services and journey.
/// The three owners commit one complete interval together. A failure rolls all
/// three back to the previous complete interval, not to the start of the call.
#[cfg(feature="python-extension")]
#[cfg_attr(feature="python-extension", pyfunction)]
pub fn advance_native_joint(
    py: Python<'_>,
    mut road: PyRefMut<'_, V1Road>,
    mut service: PyRefMut<'_, NativeServiceCore>,
    mut journey: PyRefMut<'_, NativeJourneyCore>,
    tags: Vec<String>,
    count: usize,
    step_s: f64,
) -> CoreResult<usize> {
    let road = &mut *road;
    let service = &mut *service;
    let journey = &mut *journey;
    py.allow_threads(move || {
        advance_owned_joint(road, service, journey, &tags, count, step_s, None, 0, None)
    })
}

// After proposal, each of the three independently retained owners is known.
// Arc::ptr_eq must be established on the actual live source and current event
// histories. Equal row counts or equal content alone never earns credit.
fn event_alias_credit(input:usize,current:usize,identical_allocation:bool)->usize {
    if identical_allocation {input.min(current)} else {0}
}
fn service_phase_owner_bytes(input:usize,current:usize,candidate:usize,exact:bool)->usize {
    if exact {input.saturating_add(current).saturating_add(candidate)}
    else {input.max(current).max(candidate).saturating_mul(3)}
}
pub(crate) fn advance_owned_joint(
    road: &mut V1Road,
    service: &mut NativeServiceCore,
    journey: &mut NativeJourneyCore,
    tags: &[String],
    count: usize,
    step_s: f64,
    dynamic_budget: Option<usize>,
    call_binding_reserve: usize,
    call_input: Option<&RoadState>,
) -> CoreResult<usize> {
    journey.phase_metrics = JourneyPhaseMetrics::default();
    // The Python input snapshot remains live throughout this call, even when
    // later ticks drain its queues. Charge that known retained owner as well.
    journey.retained_input_bytes = journey_storage_bytes(&journey.state);
    road.begin_call_storage_accounting();
    let call_input_events = Arc::clone(&service.last_events);
    road.configure_service_event_accounting(
        service.last_events.retained_storage_bytes(),
        tags.iter().map(String::capacity).max().unwrap_or(0),
        Arc::ptr_eq(&call_input_events, &service.last_events),
    );
    let stream_sinks=std::env::var("METROFLOW_NATIVE_STREAM_SINKS").as_deref()==Ok("1");
    let exact_service_lifetime=std::env::var_os("METROFLOW_EXPERIMENTAL_RECEIVING_LIFETIMES").as_deref()
        ==Some(std::ffi::OsStr::new("1"))
        && std::env::var_os("METROFLOW_EXPERIMENTAL_EVENT_INDEX_INCOMING").as_deref()
        ==Some(std::ffi::OsStr::new("1"));
    let input_road_bytes = if dynamic_budget.is_some() {
        let measured=road.owned_storage_bytes();
        if exact_service_lifetime {
            measured.max(call_input.map_or(0,|input|input.retained_storage_bytes()))
        } else {measured}
    } else {
        0
    };
    let input_event_bytes = if dynamic_budget.is_some() {
        service.event_storage_bytes()
    } else {
        0
    };
    if !step_s.is_finite()
        || step_s <= 0.0
        || service.pending.is_some()
        || journey.pending.is_some()
    {
        return Err(bad("invalid native coupled step or pending transition"));
    }
    let binding_started = Instant::now();
    let tag_indices: HashMap<String, usize> = tags
        .iter()
        .enumerate()
        .map(|(i, t)| (t.clone(), i))
        .collect();
    journey.phase_metrics.binding_s = binding_started.elapsed().as_secs_f64();
    if tag_indices.len() != tags.len() || road.owned_time() != journey.state.0 {
        return Err(bad("native coupled route labels or clocks differ"));
    }
    // Per-call observations, bounded by this requested interval count.
    // They are diagnostics, not part of a physical checkpoint.
    journey.tick_times_s = Vec::new();
    journey.peak_records = 0;
    journey.tick_times_s.try_reserve(count).map_err(|_| {
        CoreError::resource("native tick metric allocation exceeds available memory")
    })?;
    for _ in 0..count {
        let started = Instant::now();
        let phases_before = journey.phase_metrics.phase_sum();
        let service_before = service.state.clone();
        let current_road_bytes = if dynamic_budget.is_some() {
            road.owned_storage_bytes()
        } else {
            0
        };
        let road_pair_credit=if dynamic_budget.is_some() && exact_service_lifetime && cfg!(all(feature="native-cli",not(feature="python-extension"))) && std::env::var("METROFLOW_NATIVE_EXACT_RESTART").as_deref()==Ok("1"){call_input.map_or(0,|input|road.owned_paired_payload_credit(input)).min(input_road_bytes).min(current_road_bytes)}else{0};
        let charged_current_road_bytes=current_road_bytes.saturating_sub(road_pair_credit);
        let current_event_bytes = if dynamic_budget.is_some() {
            service.event_storage_bytes()
        } else {
            0
        };
        let result = (|| -> CoreResult<()> {
            let t = road.owned_time();
            if let Some(total) = dynamic_budget {
                // Before road prediction only the known input and committed
                // road/event owners coexist with the journey candidate.
                let other_live = input_road_bytes
                    .max(current_road_bytes)
                    .saturating_mul(2)
                    .saturating_add(input_event_bytes.max(current_event_bytes).saturating_mul(2));
                journey.set_phase_storage_budget(phase_storage_allowance(
                    total,
                    other_live,
                    "journey prepare",
                )?)?;
            }
            let phase_started = Instant::now();
            let result = journey.prepare();
            journey.phase_metrics.prepare_s += phase_started.elapsed().as_secs_f64();
            let (mut offers, eligible) = result?;
            journey.phase("service_prepare");
            let phase_started = Instant::now();
            let result = service.prepare(t, eligible);
            journey.phase_metrics.service_prepare_s += phase_started.elapsed().as_secs_f64();
            offers.extend(result?);
            let mut physical = Vec::with_capacity(offers.len());
            for (tag, mass, birth) in offers {
                let index = *tag_indices
                    .get(&tag)
                    .ok_or_else(|| bad("native joint offer has no physical route"))?;
                physical.push((index, mass, birth, None, None));
            }
            journey.phase("road_step");
            // The road candidate is computed from the old owner without
            // installing it. It commits only after both other owners validate.
            let phase_started = Instant::now();
            road.set_service_event_current_bytes(
                service.last_events.retained_storage_bytes(),
                Arc::ptr_eq(&call_input_events, &service.last_events),
            );
            if let Some(total) = dynamic_budget {
                let current_journey =
                    stage_storage_bytes(&journey.state).saturating_add(journey.history_bytes);
                let pending_journey = journey.pending.as_ref().map_or(0, |state| {
                    stage_storage_bytes(state).saturating_add(journey.history_bytes)
                });
                let owner_max=journey.retained_input_bytes
                    .max(current_journey).max(pending_journey);
                let other_live=owner_max.saturating_mul(WORKING_COPIES);
                if crate::v1_trace::enabled() {
                    // Read-only census at the actual owner-admission seam.
                    // Captured checkpoint bytes never imply equal Vec capacities.
                    let current_stage=[journey.state.1.storage_bytes(),
                        journey.state.2.storage_bytes(),journey.state.3.storage_bytes()];
                    let pending_stage=journey.pending.as_ref().map(|q|
                        [q.1.storage_bytes(),q.2.storage_bytes(),q.3.storage_bytes()])
                        .unwrap_or([0;3]);
                    let argmax=if journey.retained_input_bytes>=current_journey
                        && journey.retained_input_bytes>=pending_journey {0}
                        else if current_journey>=pending_journey {1} else {2};
                    crate::v1_trace::guard("journey_owner",
                        "road step input/current/pending census",other_live,total,&[
                            ("clock_bits",t.to_bits() as usize),
                            ("input",journey.retained_input_bytes),
                            ("current",current_journey),("pending",pending_journey),
                            ("current_enter",current_stage[0]),
                            ("current_egress",current_stage[1]),
                            ("current_internal",current_stage[2]),
                            ("pending_enter",pending_stage[0]),
                            ("pending_egress",pending_stage[1]),
                            ("pending_internal",pending_stage[2]),
                            ("history_bytes",journey.history_bytes),
                            ("max_owner",owner_max),("argmax_input0_current1_pending2",argmax),
                            ("working_copies",WORKING_COPIES)]);
                }
                road.set_phase_storage_budget(phase_storage_allowance(
                    total,
                    other_live,
                    "road step",
                )?)?;
            }
            let result = road.propose_owned_step(step_s, physical, call_input);
            journey.phase_metrics.road_step_s += phase_started.elapsed().as_secs_f64();
            let (road_candidate, events) = result?;
            let event_alias_credit=event_alias_credit(input_event_bytes,current_event_bytes,
                exact_service_lifetime && cfg!(all(feature="native-cli",not(feature="python-extension")))
                && std::env::var("METROFLOW_NATIVE_EXACT_RESTART").as_deref()==Ok("1")
                && Arc::ptr_eq(&call_input_events,&service.last_events));
            let charged_current_event_bytes=current_event_bytes.saturating_sub(event_alias_credit);
            let candidate_road_bytes = if dynamic_budget.is_some() {
                road_candidate.retained_storage_bytes()
            } else {
                0
            };
            let candidate_event_bytes = if dynamic_budget.is_some() {
                events.retained_storage_bytes()
            } else {
                0
            };
            if let Some(total) = dynamic_budget {
                // The road workspaces are dropped; its candidate and events
                // stay live with the journey owners while the sinks of the
                // exiting events are built and finished by the service.
                let exits = events.iter().filter(|e| e.2.is_none()).count();
                let tag_bytes = road
                    .service_sink_tag_bytes()
                    .unwrap_or_else(|| tags.iter().map(String::capacity).max().unwrap_or(0));
                let sink_bytes=if stream_sinks{
                    let service_exits=events.iter().filter(|e|e.2.is_none()).try_fold(0usize,|n,e|{
                        let tag=tags.get(e.0).ok_or_else(||bad("native road event route index differs"))?;
                        Ok::<_,CoreError>(n.saturating_add(usize::from(tag.starts_with("bus:")||tag.starts_with("freight:"))))
                    })?;
                    crate::v1_road::stream_sink_envelope_bytes(service_exits,tag_bytes)
                }else{crate::v1_road::sink_envelope_bytes(exits,tag_bytes)};
                let current_journey =
                    stage_storage_bytes(&journey.state).saturating_add(journey.history_bytes);
                let pending_journey = journey.pending.as_ref().map_or(0, |state| {
                    stage_storage_bytes(state).saturating_add(journey.history_bytes)
                });
                let journey_live = journey
                    .retained_input_bytes
                    .max(current_journey)
                    .max(pending_journey)
                    .saturating_mul(WORKING_COPIES);
                let road_live = service_phase_owner_bytes(input_road_bytes,charged_current_road_bytes,
                    candidate_road_bytes,exact_service_lifetime);
                let event_live = service_phase_owner_bytes(input_event_bytes,charged_current_event_bytes,
                    candidate_event_bytes,exact_service_lifetime);
                let required = journey_live
                    .saturating_add(road_live)
                    .saturating_add(event_live)
                    .saturating_add(sink_bytes)
                    .saturating_add(STORAGE_SCRATCH_RESERVE);
                let observed = crate::v1_trace::guard(
                    "service_sinks",
                    "service finish",
                    required,
                    total,
                    &[
                        ("journey_live", journey_live),
                        ("road_live", road_live),
                        ("event_live", event_live),
                        ("road_input",input_road_bytes),("road_current",current_road_bytes),
                        ("road_candidate",candidate_road_bytes),
                        ("road_pointer_verified_credit",road_pair_credit),
                        ("event_input",input_event_bytes),("event_current",current_event_bytes),
                        ("event_candidate",candidate_event_bytes),
                        ("event_pointer_verified_credit",event_alias_credit),
                        ("exact_owner_sum",usize::from(exact_service_lifetime)),
                        ("exit_rows", exits),
                        ("sink_envelope", sink_bytes),
                    ],
                );
                if required > total && !observed {
                    return Err(CoreError::resource(format!(
                        "native service event sink storage budget exceeded: phase=service finish, required_bytes={required}, budget_bytes={total}"
                    )));
                }
            }
            let mut sinks=Vec::new();
            if !stream_sinks {for e in events.iter() {
                if e.2.is_none() {
                    let tag = tags
                        .get(e.0)
                        .ok_or_else(|| bad("native road event route index differs"))?;
                    sinks.push((tag.clone(), e.3, e.5));
                }
            }}
            let sink_iter=||events.iter().filter(|e|e.2.is_none()).map(|e|tags.get(e.0).map(|tag|(tag.as_str(),e.3,e.5)).ok_or_else(||bad("native road event route index differs")));
            let end = road_candidate.time();
            journey.phase("service_finish");
            let phase_started = Instant::now();
            let result=if stream_sinks{service.finish_borrowed(end,sink_iter(),true)}else{service.finish(end,sinks.clone())};
            journey.phase_metrics.service_finish_s += phase_started.elapsed().as_secs_f64();
            result?;
            if let Some(total) = dynamic_budget {
                // Road workspaces and the service sink-map clone have been
                // dropped. The candidate, original events and original sinks
                // remain live until the complete joint transition commits.
                let sink_bytes = sinks.iter().fold(vec_storage_bytes(&sinks), |bytes, row| {
                    bytes.saturating_add(string_storage_bytes(&row.0))
                });
                let other_live = service_phase_owner_bytes(input_road_bytes,charged_current_road_bytes,
                    candidate_road_bytes,exact_service_lifetime)
                    .saturating_add(service_phase_owner_bytes(input_event_bytes,charged_current_event_bytes,
                        candidate_event_bytes,exact_service_lifetime))
                    .saturating_add(sink_bytes);
                journey.set_phase_storage_budget(phase_storage_allowance(
                    total,
                    other_live,
                    "journey finish",
                )?)?;
                journey.begin_deferred_finish()?;
            }
            let phase_started = Instant::now();
            let result=if stream_sinks{journey.finish_borrowed(end,sink_iter(),service_before.1.clone(),service.state.1.clone(),service_before.2.clone(),service.state.2.clone(),service_before.3.clone(),service.state.3.clone())}else{
            journey.finish(
                end,
                sinks,
                service_before.1.clone(),
                service.state.1.clone(),
                service_before.2.clone(),
                service.state.2.clone(),
                service_before.3.clone(),
                service.state.3.clone(),
            )
            };
            journey.phase_metrics.journey_finish_s += phase_started.elapsed().as_secs_f64();
            result?;
            if let Some(total) = dynamic_budget {
                journey.phase("whole_storage_validation");
                let road_counts = road_candidate.debug_stats();
                let road_rows = road_counts
                    .cell_parts
                    .saturating_add(road_counts.pending_parts);
                let scratch =
                    journey.whole_validation_scratch_bytes(&journey.state, road_rows, tags.len());
                let old_journey_bytes = journey
                    .deferred_previous
                    .as_ref()
                    .map_or(0, |(state, _, history, _, _)| {
                        stage_storage_bytes(state).saturating_add(*history)
                    });
                let new_journey_bytes =
                    stage_storage_bytes(&journey.state).saturating_add(journey.history_bytes);
                let decoded_journey = stage_decoded_storage_upper_bytes(&journey.state)
                    .saturating_add(journey.history_decoded_final)
                    .saturating_add(journey.history_decode_extra_max);
                let (decoded_road, road_decode_scratch) =
                    road_candidate.checkpoint_decode_envelope();
                // Fully sourced three-owner envelope across TWO exclusive
                // lifetimes: the joint commit candidate versus a future
                // checkpoint decode. The input and committed owners are
                // charged separately in both. The decoder is not live while
                // this new candidate is still in the current transition.
                let lifetime=CheckpointabilityTerms {
                    input_road:input_road_bytes,
                    current_road:current_road_bytes,
                    road_pair_credit,
                    candidate_road:candidate_road_bytes,
                    decoded_road,
                    journey_input:journey.retained_input_bytes,
                    journey_old:old_journey_bytes,
                    journey_new:new_journey_bytes,
                    journey_decoded:decoded_journey,
                    event_input:input_event_bytes,
                    event_current:charged_current_event_bytes,
                    event_candidate:candidate_event_bytes,
                    validation_scratch:scratch,
                    call_binding_reserve,
                    road_decode_scratch,
                };
                let required=checkpointability_phase_lifetime_bytes(lifetime);
                let observed = crate::v1_trace::guard(
                    "journey_commit",
                    "checkpointability",
                    required,
                    total,
                    &[
                        ("input_road", input_road_bytes),
                        ("current_road", current_road_bytes),
                        ("road_pointer_verified_credit",road_pair_credit),
                        ("candidate_road", candidate_road_bytes),
                        ("decoded_road", decoded_road),
                        ("journey_retained_input", journey.retained_input_bytes),
                        ("old_journey", old_journey_bytes),
                        ("new_journey", new_journey_bytes),
                        ("decoded_journey", decoded_journey),
                        ("input_event", input_event_bytes),
                        ("current_event", current_event_bytes),
                        ("event_pointer_verified_credit",event_alias_credit),
                        ("candidate_event", candidate_event_bytes),
                        ("validation_scratch", scratch),
                        ("call_binding_reserve", call_binding_reserve),
                        ("road_decode_scratch", road_decode_scratch),
                        ("phase_road_charge", input_road_bytes
                            .saturating_add(charged_current_road_bytes)
                            .saturating_add(candidate_road_bytes.max(decoded_road))),
                        ("phase_journey_charge",journey.retained_input_bytes
                            .saturating_add(old_journey_bytes)
                            .saturating_add(new_journey_bytes.max(decoded_journey))),
                        ("phase_event_charge",input_event_bytes
                            .saturating_add(charged_current_event_bytes)
                            .saturating_add(candidate_event_bytes)),
                    ],
                );
                if required > total && !observed {
                    return Err(CoreError::resource(format!(
                        "native whole checkpointability storage budget exceeded: required_bytes={required}, budget_bytes={total}"
                    )));
                }
            }
            road.rollback(road_candidate);
            service.last_events = Arc::new(events);
            if dynamic_budget.is_some() {
                journey.finalize_deferred_finish();
            }
            Ok(())
        })();
        if let Err(error) = result {
            service.state = service_before;
            service.pending = None;
            // A whole-owner finish keeps the previous journey by move until
            // its checkpointability margin passes. Roll back that stash on
            // failure; no additional dense snapshot is cloned.
            journey.rollback_deferred_finish();
            journey.pending = None;
            journey.phase_metrics.failed_ticks += 1;
            let phases = journey.phase_metrics.phase_sum() - phases_before;
            journey.phase_metrics.other_tick_s +=
                (started.elapsed().as_secs_f64() - phases).max(0.0);
            return Err(error);
        }
        let records =
            road.owned_record_count() + journey.record_counts().into_iter().sum::<usize>();
        journey.peak_records = journey.peak_records.max(records);
        let elapsed = started.elapsed().as_secs_f64();
        let phases = journey.phase_metrics.phase_sum() - phases_before;
        journey.phase_metrics.other_tick_s += (elapsed - phases).max(0.0);
        journey.phase_metrics.successful_ticks += 1;
        journey.tick_times_s.push(elapsed);
    }
    Ok(count)
}
crate::optional_binding::optional_pymethods!(NativeJourneyCore,
    [
    #[new]
    ] {
    fn new(
        legs: Vec<JourneyLeg>,
        bus: Vec<BusMeta>,
        freight: Vec<FreightMeta>,
        record_budget: usize,
    ) -> CoreResult<Self> {
        let mut profiles: HashMap<Vec<[u64; 3]>, SharedProfile> = HashMap::new();
        let mut laws: HashMap<Vec<[u64; 2]>, SharedLaw> = HashMap::new();
        fn law(v: Law, cache: &mut HashMap<Vec<[u64; 2]>, SharedLaw>) -> SharedLaw {
            let key = v.iter().map(|w| [w.0.to_bits(), w.1.to_bits()]).collect();
            cache.entry(key).or_insert_with(|| Arc::new(v)).clone()
        }
        let legs = legs
            .into_iter()
            .map(|l| {
                let key =
                    l.4.iter()
                        .map(|w| [w.0.to_bits(), w.1.to_bits(), w.2.to_bits()])
                        .collect();
                let profile = profiles.entry(key).or_insert_with(|| Arc::new(l.4)).clone();
                (
                    l.0,
                    l.1,
                    l.2,
                    l.3,
                    profile,
                    l.5,
                    law(l.6, &mut laws),
                    law(l.7, &mut laws),
                )
            })
            .collect();
        let bus = bus
            .into_iter()
            .map(|b| (b.0, b.1, b.2, b.3, b.4, law(b.5, &mut laws)))
            .collect();
        let freight = freight
            .into_iter()
            .map(|f| (f.0, f.1, f.2, law(f.3, &mut laws)))
            .collect();
        Self::new_shared(legs, bus, freight, record_budget)
    }
    }
    [

    ] {

    fn snapshot(&self) -> JourneyRow {
        let s = &self.state;
        (
            s.0,
            s.1.to_vec(),
            s.2.to_vec(),
            s.3.to_vec(),
            s.4.clone(),
            s.5.clone(),
            s.6.iter().map(ReceiptHistory::to_vec).collect(),
            s.7.clone(),
        )
    }
    }
    [

    ] {

    /// Inspection only: immutable static heap, one dense state, stage/history.
    fn storage_accounting(&self) -> (usize, usize, usize) {
        (
            self.static_storage_bytes(),
            journey_dense_storage_bytes(&self.state),
            journey_storage_bytes(&self.state),
        )
    }
    }
    [

    ] {

    fn decoded_storage_upper_bytes(&self) -> usize {
        stage_decoded_storage_upper_bytes(&self.state)
            .saturating_add(self.history_decoded_final)
            .saturating_add(self.history_decode_extra_max)
    }
    }
    [

    ] {

    fn advance_metrics(&self) -> (Vec<f64>, usize) {
        (self.tick_times_s.clone(), self.peak_records)
    }
    }
    [

    ] {

    fn queue_storage(&self) -> ([usize; 4], [usize; 3]) {
        (
            self.record_counts(),
            [
                self.state.1.capacity(),
                self.state.2.capacity(),
                self.state.3.capacity(),
            ],
        )
    }
    }
    [

    ] {

    fn restore(&mut self, row: JourneyRow) -> CoreResult<()> {
        let state = (
            row.0,
            row.1.into(),
            row.2.into(),
            row.3.into(),
            row.4,
            row.5,
            row.6
                .into_iter()
                .map(ReceiptHistory::from_rows)
                .collect::<Result<Vec<_>, _>>()
                .map_err(bad)?,
            row.7,
        );
        self.validate(&state)?;
        self.rollback(state);
        Ok(())
    }
    }
    [

    ] {

    fn abort(&mut self) {
        self.rollback_deferred_finish();
        self.pending = None;
        self.phase("aborted");
    }
    }
    [

    ] {

    fn prepare(&mut self) -> CoreResult<(Vec<Offer>, Vec<bool>)> {
        if self.pending.is_some() {
            return Err(bad("native journey already prepared"));
        }
        let t = self.state.0;
        let before = self.record_counts();
        self.last_attempt = Some(JourneyAttempt {
            start_s: t,
            end_s: t,
            before,
            after_prepare: before,
            candidate: before,
            generated: [0; 3],
            retired: [0; 3],
            receipts_added: 0,
            emitted_offers: 0,
            committed: false,
            phase: "journey_prepare",
        });
        let proposal_scratch = self
            .legs
            .len()
            .saturating_mul(2 * std::mem::size_of::<(usize, f64, f64, f64)>())
            .saturating_add(
                self.legs.len().div_ceil(LEG_CHUNK)
                    * std::mem::size_of::<Vec<(usize, f64, f64, f64)>>(),
            );
        check_storage_limit(
            self.storage_budget,
            self.retained_input_bytes,
            stage_storage_bytes(&self.state).saturating_add(self.history_bytes),
            proposal_scratch,
        )?;
        let mut s = self.state.clone();
        let entry_dt=if self.research_entry_buckets{
            Some(self.research_receipt_grid_step.ok_or_else(||bad("entry projection missing fixed grid"))?)
        }else{None};
        if let Some(dt)=entry_dt{
            if t%dt!=0.{return Err(bad("entry projection requires aligned prepare"))}
            if !self.research_delay_calendar&&self.research_receipt_period_s.is_some_and(|p|t%(p as f64)==0.){
                let n=s.1.len();
                let dynamic=stage_storage_bytes(&s).saturating_add(self.history_bytes);
                let base=dynamic.max(self.retained_input_bytes).saturating_mul(WORKING_COPIES).saturating_add(STORAGE_SCRATCH_RESERVE);
                let available=self.storage_budget.unwrap_or(usize::MAX).saturating_sub(base);
                let workspace=entry_sweep_scratch(n);
                if n>=2&&workspace<=available{
                    check_storage_limit(self.storage_budget,self.retained_input_bytes,dynamic,workspace)?;
                    if let Some(next)=compact_entry_queue(&s.1,t,dt,available)?{
                        let removed=n-next.len();
                        s.1=next;
                        crate::v1_trace::add("entry_sweep.raw",n as u64);
                        crate::v1_trace::add("entry_sweep.retained",s.1.len() as u64);
                        crate::v1_trace::add("entry_sweep.removed",removed as u64);
                        crate::v1_trace::add("entry_sweep.scratch",workspace as u64);
                    }else{crate::v1_trace::add("entry_sweep.fallback",1);}
                }else{crate::v1_trace::add("entry_sweep.skipped_budget_or_empty",1);}
            }
        }
        // Every proposal reads the same immutable pre-tick state. Indexed
        // chunks return in source order, and all additions/queue insertion
        // remain serial in exactly the original leg/law order.
        let chunks = self.legs.len().div_ceil(LEG_CHUNK);
        let proposals = ordered_map(chunks, 2, |chunk| {
            let start = chunk * LEG_CHUNK;
            let end = (start + LEG_CHUNK).min(self.legs.len());
            let mut releases = Vec::new();
            for i in start..end {
                let l = &self.legs[i];
                if l.5 == 0 || l.1 == 0.0 {
                    continue;
                }
                let lo = self.state.4[i] / l.1;
                let Some(hi)=release_high(fraction(&l.4,t),lo,||eligible(&self.legs,&self.state,i)) else{continue};
                let mass = l.1 * (hi - lo);
                let born = birth_between(&l.4, lo, hi);
                let hold = if l.2.is_some() { t - born } else { 0.0 };
                releases.push((i, mass, born, hold));
            }
            releases
        });
        // Reserve for exactly the entries due this tick, not every delayed
        // logical atom. Offers and their physical conversion can coexist.
        let due_new: usize = proposals
            .iter()
            .flatten()
            .filter(|p| self.legs[p.0].5 == 1)
            .map(|p| {
                self.legs[p.0]
                    .6
                    .iter()
                    .filter(|w| p.2 + (w.0 + p.3) <= t + 1e-10)
                    .count()
            })
            .sum();
        let offer_count = s.1.due_count(t + 1e-10).saturating_add(due_new);
        let offer_bytes = 4 * std::mem::size_of::<Offer>()
            + std::mem::size_of::<crate::v1_road::Offer>()
            + RETAINED_ALLOCATION_PADDING;
        let scratch = proposal_scratch.saturating_add(
            offer_count.saturating_mul(offer_bytes.saturating_add(self.max_tag_bytes)),
        ).saturating_add(if entry_dt.is_some(){EntryWorkspace::storage_upper()}else{0});
        check_storage_limit(
            self.storage_budget,
            self.retained_input_bytes,
            stage_storage_bytes(&s).saturating_add(self.history_bytes),
            scratch,
        )?;
        let mut entry_work=if entry_dt.is_some(){Some(EntryWorkspace::new()?)}else{None};
        let mut entry_raw=0usize;let mut entry_stored=0usize;let mut entry_reduced=0usize;
        let attempt = self.last_attempt.as_mut().unwrap();
        for (i, mass, born, hold) in proposals.into_iter().flatten() {
            let l = &self.legs[i];
            s.4[i] += mass;
            s.7[i] += mass * born;
            let stage = if l.5 == 2 { 2 } else { 0 };
            let all_stages = stage_storage_bytes(&s);
            let target = if stage == 2 { &mut s.3 } else { &mut s.1 };
            let reduced=stage==0&&entry_work.as_mut().zip(entry_dt).is_some_and(|(w,dt)|w.project(i,mass,born,hold,&l.6,t,dt));
            let n=if reduced{entry_work.as_ref().unwrap().out.len()}else{l.6.len()};
            if stage==0&&entry_dt.is_some(){
                entry_raw=entry_raw.saturating_add(l.6.len());entry_stored=entry_stored.saturating_add(n);
                entry_reduced=entry_reduced.saturating_add(usize::from(reduced));
            }
            let projected = self
                .history_bytes
                .saturating_add(all_stages - target.storage_bytes())
                .saturating_add(target.append_upper_bytes(n));
            check_storage_limit(
                self.storage_budget,
                self.retained_input_bytes,
                projected,
                scratch,
            )?;
            attempt.generated[stage] += n;
            if reduced{target.extend(entry_work.as_ref().unwrap().out.iter().copied());}
            else{target.extend(l.6.iter().map(|w| (i, mass * w.1, born, w.0 + hold)));}
        }
        if entry_dt.is_some(){
            crate::v1_trace::add("entry_projection.raw_products",entry_raw as u64);
            crate::v1_trace::add("entry_projection.stored_rows",entry_stored as u64);
            crate::v1_trace::add("entry_projection.reduced_proposals",entry_reduced as u64);
        }
        drop(entry_work);
        if self.research_delay_calendar{
            let dt=entry_dt.ok_or_else(||bad("entry delay calendar grid missing"))?;
            let dynamic=stage_storage_bytes(&s).saturating_add(self.history_bytes);
            if let Some(next)=admitted_delay_calendar(&self.state.1,&s.1,t,dt,t,None,self.storage_budget,self.retained_input_bytes,dynamic,scratch,"entry")?{s.1=next;}
        }
        let mut offers = Vec::new();
        s.1.retire_due_mode(t + 1e-10,self.research_delay_calendar, |a| {
            offers.push((self.legs[a.0].0.clone(), a.1, a.1 * a.2));
        });
        attempt.retired[0] = offers.len();
        attempt.emitted_offers = offers.len();
        attempt.after_prepare = [s.1.len(), s.2.len(), s.3.len(), self.history_rows];
        attempt.candidate = attempt.after_prepare;
        let allow = self
            .bus
            .iter()
            .map(|b| {
                self.legs[b.0].2.is_none() || eligible(&self.legs, &self.state, b.0) + 1e-10 >= b.4
            })
            .collect();
        self.pending = Some(s);
        Ok((offers, allow))
    }
    }
    [

    ] {

    fn finish(
        &mut self,
        end: f64,
        events: Vec<Sink>,
        before_people: Vec<People>,
        after_people: Vec<People>,
        before_freight: Vec<bool>,
        after_freight: Vec<bool>,
        before_completed: Vec<f64>,
        after_completed: Vec<f64>,
    ) -> CoreResult<()> {
        self.finish_borrowed(end,events.iter().map(|e|Ok((e.0.as_str(),e.1,e.2))),before_people,after_people,before_freight,after_freight,before_completed,after_completed)
    }
    }
);

impl NativeJourneyCore {
    pub(crate) fn new_shared(
        legs: Vec<SharedJourneyLeg>,
        bus: Vec<SharedBusMeta>,
        freight: Vec<SharedFreightMeta>,
        record_budget: usize,
    ) -> CoreResult<Self> {
        if record_budget == 0 {
            return Err(bad("positive native journey record budget required"));
        }
        let mut ids = HashSet::new();
        for l in &legs {
            if l.0.is_empty()
                || !ids.insert(&l.0)
                || !nonnegative([l.1, l.3])
                || l.5 > 2
                || l.2.is_some_and(|i| i > legs.len())
                || l.4.is_empty()
                || l.4.iter().any(|w| {
                    !nonnegative([w.0, w.1, w.2]) || w.0 >= w.1 || w.1 > 86400.0 || w.2 == 0.0
                })
                || (fsum(l.4.iter().map(|w| w.2)) - 1.0).abs() > 1e-12
                || (l.5 != 0 && (!valid_law(&l.6) || !valid_law(&l.7)))
            {
                return Err(bad("invalid native journey leg"));
            }
            let mut windows = l.4.as_ref().clone();
            windows.sort_by(|a, b| a.0.total_cmp(&b.0));
            if windows.windows(2).any(|w| w[0].1 > w[1].0) {
                return Err(bad("overlapping native departure windows"));
            }
        }
        for b in &bus {
            if b.0 >= legs.len()
                || !nonnegative([b.1, b.2, b.3, b.4])
                || b.1 == 0.0
                || b.2 == 0.0
                || b.4 > 1.0 + 1e-12
                || !valid_law(&b.5)
            {
                return Err(bad("invalid native bus journey mapping"));
            }
        }
        for f in &freight {
            if f.0 >= legs.len() || !nonnegative([f.1, f.2]) || f.1 == 0.0 || !valid_law(&f.3) {
                return Err(bad("invalid native freight journey mapping"));
            }
        }
        let n = legs.len();
        let max_tag_bytes = legs.iter().map(|l| l.0.len()).max().unwrap_or(0);
        let max_profile_rows = legs.iter().map(|leg| leg.4.len()).max().unwrap_or(0);
        let route_indices = legs
            .iter()
            .enumerate()
            .filter(|(_, l)| l.5 == 1)
            .map(|(i, l)| (l.0.clone(), i))
            .collect();
        Ok(Self {
            legs,
            bus,
            freight,
            route_indices,
            budget: record_budget,
            state: (
                0.0,
                StageQueue::new(),
                StageQueue::new(),
                StageQueue::new(),
                vec![0.0; n],
                vec![0.0; n],
                vec![ReceiptHistory::default(); n],
                vec![0.0; n],
            ),
            pending: None,
            defer_finish_commit: false,
            deferred_previous: None,
            tick_times_s: Vec::new(),
            peak_records: 0,
            history_rows: 0,
            research_receipt_period_s:None,
            research_group_outlets:false,
            research_receipt_grid_step:None,
            research_schedule_receipts:false,
            research_stream_receipts:false,
            research_egress_buckets:false,
            research_entry_buckets:false,
            research_delay_calendar:false,
            history_bytes: 0,
            history_decoded_final: 0,
            history_decode_extra_max: 0,
            storage_budget: None,
            retained_input_bytes: 0,
            max_tag_bytes,
            max_profile_rows,
            last_attempt: None,
            phase_metrics: JourneyPhaseMetrics::default(),
        })
    }
}

#[cfg(test)]
mod event_snapshot_arc_ownership_tests {
    use super::*;

    fn event_history(rows: impl IntoIterator<Item = EventRow>) -> ChunkedEvents {
        // These test rows have explicitly bounded u32 indices.
        let mut events = ChunkedEvents::new(true);
        for row in rows {
            events.push_checked(row).unwrap();
        }
        events
    }

    fn fixture() -> NativeServiceCore {
        NativeServiceCore {
            buses: vec![], people: vec![], freight: vec![], cars: vec![],
            people_by_run: vec![],
            last_events: Arc::new(event_history([
                (7, 1, None, 0.25, 100., 101., 3.125),
                (8, 1, Some(2), 0.75, 101., 102., 6.25),
            ])),
            state: (vec![], vec![], vec![], vec![], vec![]),
            pending: None,
        }
    }

    #[test]
    fn captured_snapshots_and_committed_service_share_event_backing() {
        let core = fixture();
        let a = core.checkpoint();
        let b = core.checkpoint();
        assert!(Arc::ptr_eq(&a.1, &b.1));
        assert!(Arc::ptr_eq(&a.1, &core.last_events));
        assert_eq!(a.1.iter().next().unwrap().3.to_bits(), 0.25f64.to_bits());
    }

    #[test]
    fn replacing_event_backing_preserves_previous_immutable_snapshot() {
        let mut core = fixture();
        let historical = core.checkpoint();
        core.last_events = Arc::new(event_history([(9, 3, None, 0.5, 102., 103., 3.75)]));
        assert!(!Arc::ptr_eq(&historical.1, &core.last_events));
        assert_eq!(historical.1.len(), 2);
        assert_eq!(historical.1.iter().nth(1).unwrap().6.to_bits(), 6.25f64.to_bits());
        let new_cp = core.checkpoint();
        assert_eq!(new_cp.1.len(), 1);
        core.rollback(historical.clone());
        assert!(Arc::ptr_eq(&core.last_events, &historical.1));
        assert_eq!(core.last_events.iter().next().unwrap().0, 7);
    }
}

#[cfg(test)]
mod exact_checkpointability_lifetime_phase_tests {
    use super::*;

    fn original_valley_100k_terms()->CheckpointabilityTerms {
        CheckpointabilityTerms {
            input_road:545136024,current_road:545136024,road_pair_credit:0,
            candidate_road:635238976,decoded_road:635282176,
            journey_input:228929368,journey_old:228929368,
            journey_new:260270208,journey_decoded:263109816,
            event_input:795376576,event_current:795376576,
            event_candidate:923664576,
            validation_scratch:393211568,call_binding_reserve:82704900,
            road_decode_scratch:574020704,
        }
    }
    #[test]
    fn original_100k_checkpoint_future_decoder_never_coexists_with_new_candidate() {
        let t=original_valley_100k_terms();
        assert_eq!(checkpointability_phase_lifetime_bytes(t),5534961208);
        assert_eq!(6040190408-checkpointability_phase_lifetime_bytes(t),505229200);
        assert_eq!(5789366871-checkpointability_phase_lifetime_bytes(t),254405663);
    }
    #[test]
    fn verified_input_current_road_pair_must_not_be_charged_twice(){
        let mut t=original_valley_100k_terms();
        let full=checkpointability_phase_lifetime_bytes(t);
        t.road_pair_credit=300_000_000;
        assert_eq!(checkpointability_phase_lifetime_bytes(t),full-300_000_000);
        t.road_pair_credit=usize::MAX;
        assert_eq!(checkpointability_phase_lifetime_bytes(t),full-t.input_road.min(t.current_road));
    }
    #[test]
    fn individually_real_three_owner_cases_are_still_charged_not_aliased() {
        let mut t=original_valley_100k_terms();
        t.input_road=7;t.current_road=13;t.candidate_road=17;t.decoded_road=19;
        t.journey_input=3;t.journey_old=5;t.journey_new=11;t.journey_decoded=13;
        t.event_input=17;t.event_current=23;t.event_candidate=29;
        t.validation_scratch=0;t.call_binding_reserve=0;t.road_decode_scratch=0;
        let required=checkpointability_phase_lifetime_bytes(t);
        assert_eq!(required,(7+13+19)+(3+5+13)+(17+23+29)+STORAGE_SCRATCH_RESERVE);
        // Requiring an arbitrarily large physically live source still fails.
        t.input_road=6_000_000_000;
        assert!(checkpointability_phase_lifetime_bytes(t)>5789366871);
    }
}

#[cfg(test)]
#[path = "v1_journey_retained_event_tests.rs"]
mod retained_timed_event_history_contract_tests;

#[cfg(test)]
mod service_phase_actual_owner_tests {
    use super::*;
    #[test]
    fn same_arc_credit_requires_pointer_equality(){
        let a=Arc::new(ChunkedEvents::new(true));let b=a.clone();let c=Arc::new(ChunkedEvents::new(true));
        assert_eq!(event_alias_credit(100,100,Arc::ptr_eq(&a,&b)),100);
        assert_eq!(event_alias_credit(100,100,Arc::ptr_eq(&a,&c)),0);
        assert_eq!(service_phase_owner_bytes(100,100-event_alias_credit(100,100,true),150,true),250);
    }
    #[test]
    fn three_unequal_live_owners_are_all_charged_without_fictitious_largest_copies(){
        assert_eq!(service_phase_owner_bytes(20,30,40,true),90);
        assert_eq!(service_phase_owner_bytes(20,30,40,false),120);
        assert_eq!(service_phase_owner_bytes(20,20,20,true),60);
        assert_eq!(service_phase_owner_bytes(usize::MAX,1,2,true),usize::MAX);
    }
}

impl NativeServiceCore {
    fn finish_borrowed<'a>(&mut self,end:f64,events:impl Iterator<Item=CoreResult<(&'a str,f64,f64)>>,service_only:bool)->CoreResult<()>{
        // Finish consumes its uncommitted candidate. On any failure the
        // committed state remains intact and the transaction is aborted.
        let (t, mut s) = self
            .pending
            .take()
            .ok_or_else(|| bad("native service finish without prepare"))?;
        if !end.is_finite()||end<=t{
            return Err(bad("invalid native service sink/clock"));
        }
        let mut sink_mass: HashMap<&str, Vec<f64>> = HashMap::new();
        for e in events {let (tag,mass,stamp)=e?;
            if !nonnegative([mass,stamp])||stamp>end+1e-8{return Err(bad("invalid native service sink/clock"))}
            if !service_only||tag.starts_with("bus:")||tag.starts_with("freight:"){sink_mass.entry(tag).or_default().push(mass);}
        }
        for (i, b) in self.buses.iter().enumerate() {
            let v = s.0[i];
            if v.1 != 1 {
                continue;
            }
            let tag = format!("bus:{}:{}", b.0, v.0);
            let mass = v.3 + fsum(sink_mass.get(tag.as_str()).into_iter().flatten().copied());
            if mass < 1.0 - 1e-9 {
                s.0[i].3 = mass;
                continue;
            }
            let stop = v.0 + 1;
            for &k in &self.people_by_run[i] {
                let x = &mut s.1[k];
                if self.people[k].2 == stop {
                    x.2 += x.1;
                    x.4 += x.1 * end;
                    x.1 = 0.0;
                }
            }
            s.0[i] = (
                stop,
                if stop == b.1.len() { 2 } else { 0 },
                end + b.3,
                0.0,
                v.4,
            );
        }
        for (i, f) in self.freight.iter().enumerate() {
            let tag = format!("freight:{}", f.0);
            s.3[i] += fsum(sink_mass.get(tag.as_str()).into_iter().flatten().copied());
        }
        self.validate(&s)?;
        self.state = s;
        self.pending = None;
        Ok(())
    }
}
impl NativeJourneyCore {
    fn finish_borrowed<'a>(
        &mut self,
        end: f64,
        events: impl Iterator<Item=CoreResult<(&'a str,f64,f64)>>,
        before_people: Vec<People>,
        after_people: Vec<People>,
        before_freight: Vec<bool>,
        after_freight: Vec<bool>,
        before_completed: Vec<f64>,
        after_completed: Vec<f64>,
    ) -> CoreResult<()> {
        // The committed state remains available throughout finish. Consume
        // the candidate instead of duplicating all active queues a third time.
        let mut s = self
            .pending
            .take()
            .ok_or_else(|| bad("native journey finish without prepare"))?;
        if let Some(attempt) = &mut self.last_attempt {
            attempt.phase = "journey_finish";
            attempt.end_s = end;
        }
        let mut generated_egress = 0usize;
        let t = s.0;
        if !end.is_finite()
            || end <= t
            || before_people.len() != self.bus.len()
            || after_people.len() != self.bus.len()
            || before_freight.len() != self.freight.len()
            || after_freight.len() != self.freight.len()
            || before_completed.len() != self.freight.len()
            || after_completed.len() != self.freight.len()
        {
            return Err(bad("invalid native journey service shape/clock"));
        }
        if self.research_group_outlets{
            let mut rows:Vec<OutletAtom>=Vec::new();
            let size=std::mem::size_of::<OutletAtom>();
            for e in events{let e=e?;if !nonnegative([e.1,e.2])||e.2>end+1e-8{return Err(bad("invalid native grouped road sink"))}
                if let Some(&i)=self.route_indices.get(e.0){
                    if rows.len()==rows.capacity(){let next=rows.capacity().saturating_mul(2).max(4);let scratch=next.saturating_add(rows.capacity()).saturating_mul(size).saturating_add(128*1024);check_storage_limit(self.storage_budget,self.retained_input_bytes,stage_storage_bytes(&s).saturating_add(self.history_bytes),scratch)?;
                        let mut v=checkpoint_vec(next)?;if v.capacity()!=next{return Err(CoreError::resource("outlet grouping capacity differs"))}v.append(&mut rows);rows=v;
                    }
                    rows.push(OutletAtom{leg:i,stamp:e.2,mass:e.1,ordinal:rows.len()});
                }
            }
            let raw=rows.len();let scratch=rows.capacity().saturating_mul(size).saturating_add(128*1024);
            group_outlet_atoms(&mut rows)?;
            crate::v1_trace::add("outlet_group.raw",raw as u64);crate::v1_trace::add("outlet_group.grouped",rows.len()as u64);
            if self.research_egress_buckets{
                let n=self.legs.len();
                let extra=n.saturating_mul(std::mem::size_of::<f64>()).saturating_add(EgressWorkspace::storage_upper()).saturating_add(RETAINED_ALLOCATION_PADDING);
                let scratch=scratch.saturating_add(extra);
                check_storage_limit(self.storage_budget,self.retained_input_bytes,stage_storage_bytes(&s).saturating_add(self.history_bytes),scratch)?;
                let mut horizon=checkpoint_vec(n)?;
                if horizon.capacity()!=n{return Err(CoreError::resource("egress horizon capacity differs"))}
                horizon.resize(n,f64::INFINITY);
                for child in &self.legs{
                    if let Some(p)=child.2{
                        if p>=n{return Err(bad("invalid egress observer parent"))}
                        let h=if child.5==0{-1.}else{
                            private_hidden_horizon(child.3,&child.4)
                        };
                        horizon[p]=horizon[p].min(h);
                    }
                }
                for i in self.bus.iter().map(|b|b.0).chain(self.freight.iter().map(|f|f.0)){
                    if let Some(p)=self.legs[i].2{
                        if p>=n{return Err(bad("invalid egress service observer parent"))}
                        horizon[p]=-1.;
                    }
                }
                let dt=self.research_receipt_grid_step.ok_or_else(||bad("missing egress grid"))?;
                let mut work=EgressWorkspace::new()?;
                let mut raw_products=0usize;let mut stored=0usize;let mut reduced_legs=0usize;
                for chunk in rows.chunk_by(|a,b|a.leg==b.leg){
                    let i=chunk[0].leg;let law=&self.legs[i].7;
                    let count=chunk.len().checked_mul(law.len()).ok_or_else(||CoreError::resource("egress product count overflow"))?;
                    raw_products=raw_products.checked_add(count).ok_or_else(||CoreError::resource("egress raw count overflow"))?;
                    if work.project(chunk,law,t,end,dt,horizon[i]){
                        check_storage_limit(self.storage_budget,self.retained_input_bytes,self.history_bytes.saturating_add(s.1.storage_bytes()).saturating_add(s.3.storage_bytes()).saturating_add(s.2.append_upper_bytes(work.out.len())),scratch)?;
                        generated_egress+=work.out.len();stored+=work.out.len();reduced_legs+=1;
                        s.2.extend(work.out.iter().copied());
                    }else{
                        for e in chunk{
                            check_storage_limit(self.storage_budget,self.retained_input_bytes,self.history_bytes.saturating_add(s.1.storage_bytes()).saturating_add(s.3.storage_bytes()).saturating_add(s.2.append_upper_bytes(law.len())),scratch)?;
                            generated_egress+=law.len();stored+=law.len();
                            s.2.extend(law.iter().map(|w|(i,e.mass*w.1,e.stamp,w.0)));
                        }
                    }
                }
                crate::v1_trace::add("egress_bucket.raw_products",raw_products as u64);
                crate::v1_trace::add("egress_bucket.stored_rows",stored as u64);
                crate::v1_trace::add("egress_bucket.reduced_legs",reduced_legs as u64);
            }else{
                for e in rows{let i=e.leg;check_storage_limit(self.storage_budget,self.retained_input_bytes,self.history_bytes.saturating_add(s.1.storage_bytes()).saturating_add(s.3.storage_bytes()).saturating_add(s.2.append_upper_bytes(self.legs[i].7.len())),scratch)?;
                    generated_egress+=self.legs[i].7.len();s.2.extend(self.legs[i].7.iter().map(|w|(i,e.mass*w.1,e.stamp,w.0)));
                }
            }
        }else{
        for e in events {let e=e?;
            if !nonnegative([e.1, e.2]) || e.2 > end + 1e-8 {
                return Err(bad("invalid native journey road sink"));
            }
            if let Some(&i) = self.route_indices.get(e.0) {
                check_storage_limit(
                    self.storage_budget,
                    self.retained_input_bytes,
                    self.history_bytes
                        .saturating_add(s.1.storage_bytes())
                        .saturating_add(s.3.storage_bytes())
                        .saturating_add(s.2.append_upper_bytes(self.legs[i].7.len())),
                    0,
                )?;
                generated_egress += self.legs[i].7.len();
                s.2.extend(self.legs[i].7.iter().map(|w| (i, e.1 * w.1, e.2, w.0)));
            }
        }
        }
        for (k, b) in self.bus.iter().enumerate() {
            let before = before_people[k];
            let after = after_people[k];
            if !nonnegative([before.0, before.1, before.2, after.0, after.1, after.2]) {
                return Err(bad("invalid native journey passenger update"));
            }
            let boarded = (after.1 + after.2) - (before.1 + before.2);
            let arrived = after.2 - before.2;
            let factor = self.legs[b.0].1 / b.1;
            if boarded < 0.0 || arrived < 0.0 {
                return Err(bad("native passenger totals decreased"));
            }
            s.4[b.0] += boarded * factor;
            s.7[b.0] += boarded * factor * b.3 / b.2;
            if arrived != 0.0 {
                check_storage_limit(
                    self.storage_budget,
                    self.retained_input_bytes,
                    self.history_bytes
                        .saturating_add(s.1.storage_bytes())
                        .saturating_add(s.3.storage_bytes())
                        .saturating_add(s.2.append_upper_bytes(b.5.len())),
                    0,
                )?;
                generated_egress += b.5.len();
                s.2.extend(b.5.iter().map(|w| (b.0, arrived * factor * w.1, end, w.0)));
            }
        }
        for (k, f) in self.freight.iter().enumerate() {
            if before_freight[k] && !after_freight[k] {
                return Err(bad("native freight release reversed"));
            }
            if after_freight[k] && !before_freight[k] {
                s.4[f.0] += f.1;
                s.7[f.0] += f.2;
            }
            let arrival = after_completed[k] - before_completed[k];
            if !nonnegative([arrival]) {
                return Err(bad("native freight arrival decreased"));
            }
            if arrival != 0.0 {
                check_storage_limit(
                    self.storage_budget,
                    self.retained_input_bytes,
                    self.history_bytes
                        .saturating_add(s.1.storage_bytes())
                        .saturating_add(s.3.storage_bytes())
                        .saturating_add(s.2.append_upper_bytes(f.3.len())),
                    0,
                )?;
                generated_egress += f.3.len();
                s.2.extend(f.3.iter().map(|w| (f.0, arrival * w.1, end, w.0)));
            }
        }
        if self.research_delay_calendar{
            let dt=self.research_receipt_grid_step.ok_or_else(||bad("egress delay calendar grid missing"))?;
            if end-t!=dt||t%dt!=0.||end%dt!=0.{return Err(bad("egress delay calendar requires aligned ticks"))}
            let n=self.legs.len();
            let horizon_bytes=n.saturating_mul(std::mem::size_of::<f64>()).saturating_add(RETAINED_ALLOCATION_PADDING);
            let dynamic=stage_storage_bytes(&s).saturating_add(self.history_bytes);
            let base=dynamic.max(self.retained_input_bytes).saturating_mul(WORKING_COPIES).saturating_add(STORAGE_SCRATCH_RESERVE);
            if self.storage_budget.unwrap_or(usize::MAX).saturating_sub(base)>=horizon_bytes{
                check_storage_limit(self.storage_budget,self.retained_input_bytes,dynamic,horizon_bytes)?;
                let mut horizon=checkpoint_vec(n)?;
                if horizon.capacity()!=n{return Err(CoreError::resource("delay calendar horizon capacity differs"))}
                horizon.resize(n,f64::INFINITY);
                for (i,l) in self.legs.iter().enumerate(){
                    // Service egress owners are never projected.
                    if l.5!=1{horizon[i]=-1.;}
                    if let Some(p)=l.2{
                        if p>=n{return Err(bad("invalid delay calendar parent index"))}
                        let h=if l.5==0{-1.}else{private_hidden_horizon(l.3,&l.4)};
                        horizon[p]=horizon[p].min(h);
                    }
                }
                for i in self.bus.iter().map(|b|b.0).chain(self.freight.iter().map(|f|f.0)){
                    if i>=n{return Err(bad("invalid delay calendar service index"))}
                    horizon[i]=-1.;
                    if let Some(p)=self.legs[i].2{
                        if p>=n{return Err(bad("invalid delay calendar service parent index"))}
                        horizon[p]=-1.;
                    }
                }
                if let Some(next)=admitted_delay_calendar(&self.state.2,&s.2,t,dt,end+1e-8,Some(&horizon),self.storage_budget,self.retained_input_bytes,dynamic,horizon_bytes,"egress")?{s.2=next;}
            }else{crate::v1_trace::add("delay_calendar.egress_fallback",1);}
        }
        let mut retired = [0usize; 2];
        let before_retirement_bytes = stage_storage_bytes(&s);
        let mut history_bytes = self.history_bytes;
        let mut history_decoded_final = self.history_decoded_final;
        let mut history_decode_extra_max = self.history_decode_extra_max;
        // Candidate-only workspace. Bound scratch before allocation by the
        // number of due rows and legs; no raw receipt array per due event.
        let mut stream_hidden:Vec<u8>=Vec::new();
        let mut stream_slots:Vec<u32>=Vec::new();
        let mut stream_acc:Vec<(usize,ReceiptAccumulator)>=Vec::new();
        let mut stream_scratch=0usize;
        if self.research_stream_receipts{
            let n=self.legs.len();
            if n>=u32::MAX as usize{return Err(bad("streaming receipt leg count"))}
            let due=s.2.due_count(end+1e-10).saturating_add(s.3.due_count(end+1e-10));
            let cap=n.min(due);
            stream_scratch=n.saturating_mul(std::mem::size_of::<u8>()+std::mem::size_of::<u32>())
                .saturating_add(cap.saturating_mul(std::mem::size_of::<(usize,ReceiptAccumulator)>()))
                .saturating_add(3*RETAINED_ALLOCATION_PADDING);
            check_storage_limit(self.storage_budget,self.retained_input_bytes,before_retirement_bytes.saturating_add(history_bytes),stream_scratch)?;
            stream_hidden=checkpoint_vec(n)?;stream_slots=checkpoint_vec(n)?;stream_acc=checkpoint_vec(cap)?;
            if stream_hidden.capacity()!=n||stream_slots.capacity()!=n||stream_acc.capacity()!=cap{return Err(CoreError::resource("streaming receipt workspace capacity differs"))}
            stream_hidden.resize(n,1);stream_slots.resize(n,u32::MAX);
            for child in &self.legs{
                if let Some(p)=child.2{
                    if p>=n{return Err(bad("invalid parent receipt index"))}
                    if !private_profile_hides_old_history(end,child.3,child.5,&child.4){stream_hidden[p]=0;}
                }
            }
            for i in self.bus.iter().map(|b|b.0).chain(self.freight.iter().map(|f|f.0)){
                if let Some(p)=self.legs[i].2{
                    if p>=n{return Err(bad("invalid service parent receipt index"))}
                    stream_hidden[p]=0;
                }
            }
        }
        for (kind, stage) in [&mut s.2, &mut s.3].into_iter().enumerate() {
            let mut receipt_error = None;
            retired[kind] = stage.retire_due_mode(end + 1e-10,self.research_delay_calendar&&kind==0, |a| {
                if receipt_error.is_some() {
                    return;
                }
                let history = &mut s.6[a.0];
                if self.research_stream_receipts&&stream_hidden[a.0]!=0{
                    let result=(||->CoreResult<()>{
                        let mut slot=stream_slots[a.0];
                        if slot==u32::MAX{
                            if stream_acc.len()==stream_acc.capacity(){return Err(CoreError::resource("streaming receipt slot capacity"))}
                            slot=stream_acc.len() as u32;
                            let mut acc=ReceiptAccumulator::default();
                            acc.seed(history,end)?;
                            stream_acc.push((a.0,acc));stream_slots[a.0]=slot;
                        }
                        stream_acc[slot as usize].1.add(t.max(a.2+a.3),a.1/self.legs[a.0].1,end)?;
                        s.5[a.0]+=a.1;
                        Ok(())
                    })();
                    if let Err(error)=result{receipt_error=Some(error)}
                    return
                }
                let previous_bytes = history.storage_bytes();
                let previous_decoded = history.decoded_final_storage_upper_bytes();
                let projected = before_retirement_bytes
                    .saturating_add(history_bytes - previous_bytes)
                    .saturating_add(history.append_upper_bytes());
                if let Err(error) = check_storage_limit(
                    self.storage_budget,
                    self.retained_input_bytes,
                    projected,
                    stream_scratch,
                ) {
                    receipt_error = Some(error);
                    return;
                }
                s.5[a.0] += a.1;
                if let Err(error) = history.push((t.max(a.2 + a.3), a.1 / self.legs[a.0].1)) {
                    receipt_error = Some(bad(error));
                    return;
                }
                history_bytes = history_bytes - previous_bytes + history.storage_bytes();
                history_decoded_final = history_decoded_final - previous_decoded
                    + history.decoded_final_storage_upper_bytes();
                // Only one history is decoded at a time. Keep a conservative
                // ever-max transient delta within this call; restore/install
                // recomputes the current maximum in the existing history pass.
                history_decode_extra_max = history_decode_extra_max.max(
                    history
                        .decoded_storage_upper_bytes()
                        .saturating_sub(history.decoded_final_storage_upper_bytes()),
                );
            });
            if let Some(error) = receipt_error {
                return Err(error);
            }
        }
        let added = retired[0] + retired[1];
        let mut stream_removed=0usize;
        if self.research_stream_receipts{
            let touched=stream_acc.len();
            let mut raw=0usize;
            for (i,acc) in stream_acc{
                let h=&mut s.6[i];
                let prior_bytes=h.storage_bytes();
                let prior_decoded=h.decoded_final_storage_upper_bytes();
                raw=raw.checked_add(acc.count().checked_sub(h.len()).ok_or_else(||bad("streaming receipt seed count differs"))?).ok_or_else(||CoreError::resource("streaming receipt count overflow"))?;
                stream_removed=stream_removed.checked_add(acc.count()-1).ok_or_else(||CoreError::resource("streaming receipt removal overflow"))?;
                let mut next=ReceiptHistory::new();
                check_storage_limit(self.storage_budget,self.retained_input_bytes,before_retirement_bytes.saturating_add(history_bytes).saturating_add(next.append_upper_bytes()),stream_scratch)?;
                next.push(acc.representative()?).map_err(bad)?;
                history_bytes=history_bytes.checked_sub(prior_bytes).and_then(|v|v.checked_add(next.storage_bytes())).ok_or_else(||CoreError::resource("streaming receipt byte census overflow"))?;
                history_decoded_final=history_decoded_final.checked_sub(prior_decoded).and_then(|v|v.checked_add(next.decoded_final_storage_upper_bytes())).ok_or_else(||CoreError::resource("streaming receipt decoded census overflow"))?;
                history_decode_extra_max=history_decode_extra_max.max(next.decoded_storage_upper_bytes().saturating_sub(next.decoded_final_storage_upper_bytes()));
                *h=next;
            }
            crate::v1_trace::add("receipt_stream.raw",raw as u64);
            crate::v1_trace::add("receipt_stream.touched",touched as u64);
            crate::v1_trace::add("receipt_stream.removed_rows",stream_removed as u64);
            crate::v1_trace::add("receipt_stream.scratch_bytes",stream_scratch as u64);
        }
        drop(stream_slots);drop(stream_hidden);
        if let Some(dt)=self.research_receipt_grid_step{if t%dt!=0.||end%dt!=0.||end-t!=dt{return Err(bad("receipt grid requires fixed aligned ticks"))}}
        let mut removed=stream_removed;
        if self.research_receipt_period_s.is_some_and(|p|(end/p as f64).floor()>(t/p as f64).floor()){
            let n=self.legs.len();let dwell_bytes=n.saturating_mul(std::mem::size_of::<f64>()+(2+usize::from(self.research_schedule_receipts))*std::mem::size_of::<u8>());
            let stage_bytes=stage_storage_bytes(&s);
            check_storage_limit(self.storage_budget,self.retained_input_bytes,stage_bytes.saturating_add(history_bytes),dwell_bytes)?;
            let mut dwell=checkpoint_vec(n)?;if dwell.capacity()!=n{return Err(CoreError::resource("receipt dwell capacity differs"))}dwell.resize(n,0.0f64);
            let mut flags:Vec<u8>=checkpoint_vec(n)?;if flags.capacity()!=n{return Err(CoreError::resource("receipt child flags capacity differs"))}flags.resize(n,0);
            let mut hidden:Vec<u8>=Vec::new();
            if self.research_schedule_receipts{
                hidden=checkpoint_vec(n)?;
                if hidden.capacity()!=n{return Err(CoreError::resource("receipt schedule capacity differs"))}
                hidden.resize(n,1);
            }
            for leg in &self.legs{if let Some(p)=leg.2{
                if p>=n{return Err(bad("invalid parent receipt index"))}
                if flags[p]!=0&&dwell[p].to_bits()!=leg.3.to_bits(){flags[p]=2;}else if flags[p]==0{flags[p]=1;}
                dwell[p]=dwell[p].max(leg.3);
                if self.research_schedule_receipts&&!private_profile_hides_old_history(end,leg.3,leg.5,&leg.4){hidden[p]=0;}
            }}
            if self.research_schedule_receipts{
                // A bus gate is a distinct observable even if its profile
                // vanishes. Freight/service eligibility is also protected.
                for i in self.bus.iter().map(|b|b.0).chain(self.freight.iter().map(|f|f.0)){
                    if let Some(p)=self.legs[i].2{
                        if p>=n{return Err(bad("invalid service parent receipt index"))}
                        hidden[p]=0;
                    }
                }
            }
            let mut schedule_touched=0usize;let mut schedule_removed=0usize;
            let mut grid_touched=0usize;let mut grid_removed=0usize;
            let mut grid_workspace=GridWorkspace::default();
            let old_history_bytes=history_bytes;let mut touched=0usize;
            for (i,h) in s.6.iter_mut().enumerate(){
                if h.len()<2{continue}
                let base=stage_bytes.saturating_add(history_bytes).max(self.retained_input_bytes).saturating_mul(WORKING_COPIES).saturating_add(STORAGE_SCRATCH_RESERVE).saturating_add(dwell_bytes);
                let scratch=self.storage_budget.unwrap_or(usize::MAX).checked_sub(base).ok_or_else(||CoreError::resource("receipt sweep owner budget"))?;
                let schedule=self.research_schedule_receipts&&flags[i]!=0&&hidden[i]!=0;
                let grid=self.research_receipt_grid_step.filter(|_|flags[i]!=2&&!schedule);
                let next=if let Some(dt)=grid{
                    h.compact_grid_buckets(end,dwell[i],dt,scratch,&mut grid_workspace)?
                }else{
                    let available=scratch.checked_sub(grid_workspace.retained_bytes()).ok_or_else(||CoreError::resource("receipt sweep retained grid workspace"))?;
                    h.compact_mature(end,if schedule{0.}else{dwell[i]},available)?
                };
                if let Some(next)=next{
                    if grid.is_some(){grid_touched+=1;grid_removed=grid_removed.saturating_add(h.len()-next.len());}
                    if schedule{schedule_touched+=1;schedule_removed=schedule_removed.saturating_add(h.len()-next.len());}
                    removed=removed.checked_add(h.len()-next.len()).ok_or_else(||CoreError::resource("receipt removed count overflow"))?;
                    history_bytes=history_bytes.checked_sub(h.storage_bytes()).and_then(|v|v.checked_add(next.storage_bytes())).ok_or_else(||CoreError::resource("receipt owner census overflow"))?;
                    *h=next;touched+=1;
                }
            }
            // Recompute decoder envelope after deletion, not an ever-max from
            // the discarded representation; all live histories are counted.
            history_decoded_final=0;history_decode_extra_max=0;
            for h in &s.6{let b=h.decoded_final_storage_upper_bytes();history_decoded_final=history_decoded_final.saturating_add(b);history_decode_extra_max=history_decode_extra_max.max(h.decoded_storage_upper_bytes().saturating_sub(b));}
            crate::v1_trace::add("receipt_closure.sweeps",1);
            crate::v1_trace::add("receipt_schedule.touched",schedule_touched as u64);
            crate::v1_trace::add("receipt_schedule.removed_rows",schedule_removed as u64);
            crate::v1_trace::add("receipt_grid.touched",grid_touched as u64);crate::v1_trace::add("receipt_grid.removed_rows",grid_removed as u64);
            crate::v1_trace::add("receipt_closure.touched",touched as u64);
            crate::v1_trace::add("receipt_closure.removed_rows",(removed-stream_removed) as u64);
            crate::v1_trace::add("receipt_closure.saved_owner_bytes",old_history_bytes.saturating_sub(history_bytes) as u64);
        }
        let final_history_rows=self.history_rows.checked_add(added).and_then(|v|v.checked_sub(removed)).ok_or_else(||CoreError::resource("receipt history row census overflow"))?;
        s.0 = end;
        if let Some(attempt) = &mut self.last_attempt {
            attempt.generated[1] = generated_egress;
            attempt.retired[1] = retired[0];
            attempt.retired[2] = retired[1];
            attempt.receipts_added = added;
            attempt.candidate = [s.1.len(), s.2.len(), s.3.len(), final_history_rows];
            attempt.phase = "journey_validation";
        }
        self.validate(&s)?;
        for stage in [&mut s.1, &mut s.2, &mut s.3] {
            release_unused_stage_capacity(stage);
        }
        if self.defer_finish_commit {
            let previous = std::mem::replace(&mut self.state, s);
            self.deferred_previous = Some((
                previous,
                self.history_rows,
                self.history_bytes,
                self.history_decoded_final,
                self.history_decode_extra_max,
            ));
        } else {
            self.state = s;
        }
        self.history_rows = final_history_rows;
        self.history_bytes = history_bytes;
        self.history_decoded_final = history_decoded_final;
        self.history_decode_extra_max = history_decode_extra_max;
        if let Some(attempt) = &mut self.last_attempt {
            attempt.committed = !self.defer_finish_commit;
            attempt.phase = if self.defer_finish_commit {
                "whole_storage_validation"
            } else {
                "committed"
            };
        }
        Ok(())
    }
}

impl NativeJourneyCore {
    pub(crate) fn bind_route_alias(&mut self,alias:String,owner:usize)->CoreResult<()> {
        if !alias.starts_with("__variant__:")||self.legs.get(owner).is_none_or(|l|l.5!=1)||self.route_indices.contains_key(&alias){return Err(bad("invalid canonical journey alias"))}
        self.route_indices.insert(alias,owner);
        Ok(())
    }
}


// Entry access atoms are observed by road only on the aligned prepare grid.
// Canonical source packet combines same route/offset and absent intervals.
const ENTRY_BUCKETS:usize=128;
fn entry_key(r:f64,t:f64,dt:f64)->Option<u32>{
    if !r.is_finite()||r<0.||!t.is_finite()||t<0.||!dt.is_finite()||dt<1.||dt.fract()!=0.||t%dt!=0.{return None}
    if r<=t+1e-10{return Some(0)}
    let raw=((r-t)/dt).ceil();
    if !raw.is_finite()||raw<1.||raw>=u32::MAX as f64-1.{return None}
    let mut k=raw as u32;
    if k>1&&r<=t+(k-1)as f64*dt+1e-10{k-=1;}
    if r>t+k as f64*dt+1e-10{k+=1;}
    if r<=t+(k-1)as f64*dt+1e-10||r>t+k as f64*dt+1e-10{return None}
    Some(k)
}
struct EntryGroup{
    key:u32,first:Access,birth:ReceiptAccumulator,ready:ReceiptAccumulator,
}
impl EntryGroup{
    fn new(key:u32,first:Access)->Self{Self{key,first,birth:ReceiptAccumulator::default(),ready:ReceiptAccumulator::default()}}
    fn add(&mut self,a:Access,t:f64,dt:f64)->bool{self.add_at(a,t,dt,t)}
    fn add_at(&mut self,a:Access,t:f64,dt:f64,birth_max:f64)->bool{
        if a.0!=self.first.0||!a.3.is_finite()||a.3<0.||entry_key(a.2+a.3,t,dt)!=Some(self.key){return false}
        self.birth.add(a.2,a.1,birth_max).is_ok()&&self.ready.add(a.2+a.3,a.1,f64::MAX).is_ok()
    }
    fn representative(&self,t:f64,dt:f64)->Option<Access>{self.representative_at(t,dt,t)}
    fn representative_at(&self,t:f64,dt:f64,birth_max:f64)->Option<Access>{
        if self.birth.count()==1{return Some(self.first)}
        let (b,m)=self.birth.representative().ok()?;
        let (r,m2)=self.ready.representative().ok()?;
        if m.to_bits()!=m2.to_bits()||r<b||b>birth_max{return None}
        let d=r-b;let actual=b+d;
        if !d.is_finite()||entry_key(actual,t,dt)!=Some(self.key)||(actual-r).abs()>1e-11*r.abs()+4.*f64::from_bits(1){return None}
        Some((self.first.0,m,b,d))
    }
}
struct EntryWorkspace{bins:Vec<EntryGroup>,out:Vec<Access>}
impl EntryWorkspace{
    fn storage_upper()->usize{
        ENTRY_BUCKETS.saturating_mul(std::mem::size_of::<EntryGroup>()+std::mem::size_of::<Access>()).saturating_add(2*RETAINED_ALLOCATION_PADDING)
    }
    fn new()->CoreResult<Self>{
        let bins=checkpoint_vec(ENTRY_BUCKETS)?;let out=checkpoint_vec(ENTRY_BUCKETS)?;
        if bins.capacity()!=ENTRY_BUCKETS||out.capacity()!=ENTRY_BUCKETS{return Err(CoreError::resource("entry projection workspace capacity differs"))}
        Ok(Self{bins,out})
    }
    fn project(&mut self,i:usize,mass:f64,born:f64,hold:f64,law:&[(f64,f64)],t:f64,dt:f64)->bool{
        self.bins.clear();self.out.clear();
        if law.len()<2||law.len()>ENTRY_BUCKETS||!born.is_finite()||born<0.||born>t{return false}
        for &(d,q) in law{
            let a=(i,mass*q,born,d+hold);
            let Some(key)=entry_key(a.2+a.3,t,dt)else{return false};
            let pos=match self.bins.iter().position(|g|g.key==key){
                Some(j)=>j,
                None=>{self.bins.push(EntryGroup::new(key,a));self.bins.len()-1}
            };
            if !self.bins[pos].add(a,t,dt){return false}
        }
        if self.bins.len()>=law.len(){return false}
        // First encounter order is deterministic. Distinct due keys never
        // feed the same prepare tick; road combine handles same-tag offers.
        for g in &self.bins{
            let Some(a)=g.representative(t,dt)else{return false};
            self.out.push(a);
        }
        true
    }
}
#[cfg(feature="native-cli")]
pub struct EntryBucketProbe(EntryWorkspace);
#[cfg(feature="native-cli")]
impl EntryBucketProbe{
    pub fn new()->CoreResult<Self>{Ok(Self(EntryWorkspace::new()?))}
    pub fn run(&mut self)->CoreResult<[f64;3]>{
        let law=[(3.,0.125),(5.,0.25),(13.,0.25),(15.,0.375)];
        if !self.0.project(3,2.,1.,9.,&law,10.,10.){return Err(bad("entry projection probe failed"))}
        Ok([self.0.out.len()as f64,self.0.out.iter().map(|a|a.1).sum(),self.0.out.iter().map(|a|a.1*a.2).sum()])
    }
}
#[cfg(feature="native-cli")]
pub fn allocation_probe_delay_cell()->CoreResult<[f64;3]>{
    let rows=std::hint::black_box([(1,0.25,1.,12.),(1,0.75,3.,13.),(1,0.5,10.,6.)]);
    let mut g=EntryGroup::new(1,rows[0]);
    for r in rows{if !delay_projectable(&r,1,10.,10.,Some(&[100.,100.]))||!g.add_at(r,10.,10.,10.){return Err(bad("delay cell probe add"))}}
    let a=g.representative_at(10.,10.,10.).ok_or_else(||bad("delay cell probe projection"))?;
    Ok([a.1,a.2,a.2+a.3])
}
// Sparse ordered calendar. Wire remains the logical row sequence; on load
// block boundaries may be lost, so normalize once, then share untouched
// immutable clock partitions. Only the append tail is sorted thereafter.
const DELAY_CALENDAR_KEYS:usize=4096;
#[derive(Default,Debug)]
struct DelayMergeStats{sorted:usize,shared:usize,removed:usize,rebuild:bool,scratch:usize}
fn delay_calendar_key(r:f64,t:f64,dt:f64)->Option<u32>{
    entry_key(r,t,dt).filter(|&k|(k as usize)<DELAY_CALENDAR_KEYS)
}
fn delay_projectable(a:&Access,key:u32,t:f64,dt:f64,horizon:Option<&[f64]>)->bool{
    if let Some(h)=horizon{
        let r=a.2+a.3;
        // Old/new overdue rows use max(t,r) at retirement. Preserve them
        // raw. Also protect epsilon-only ready beyond the committed end.
        key>0&&r<=t+key as f64*dt&&h.get(a.0).is_some_and(|&x|r<=x&&t<=x)
    }else{true}
}
fn delay_calendar_workspace(old:&StageQueue,combined:&StageQueue,t:f64,dt:f64)->Option<(bool,usize,usize)>{
    if combined.len()<old.len(){return None}
    let canonical=old.canonical_clock_order(|r|delay_calendar_key(r,t,dt));
    let n=if canonical{combined.len()-old.len()}else{combined.len()};
    let refs=n.saturating_mul(std::mem::size_of::<(u32,usize,&Access)>());
    let scratch=refs.saturating_add(StageQueue::partitioned_storage_bound(combined.len(),DELAY_CALENDAR_KEYS)).saturating_add(64*1024);
    Some((canonical,n,scratch))
}
// Caller guarantees combined is the immutable old logical prefix followed
// only by newly generated rows, and keeps both live until return.
fn merge_delay_calendar(old:&StageQueue,combined:&StageQueue,t:f64,dt:f64,birth_max:f64,horizon:Option<&[f64]>,available:usize)->CoreResult<Option<(StageQueue,DelayMergeStats)>>{
    let Some((canonical,n,scratch))=delay_calendar_workspace(old,combined,t,dt)else{return Ok(None)};
    if scratch>available{return Ok(None)}
    if combined.is_empty(){return Ok(None)}
    let mut refs=checkpoint_vec(n)?;
    if refs.capacity()!=n{return Ok(None)}
    for (ordinal,a) in combined.iter_from(if canonical{old.len()}else{0}).enumerate(){
        let Some(k)=delay_calendar_key(a.2+a.3,t,dt)else{return Ok(None)};
        if !a.1.is_finite()||a.1<=0.||!a.2.is_finite()||a.2<0.||a.2>birth_max||!a.3.is_finite()||a.3<0.{return Ok(None)}
        refs.push((k,ordinal,a));
    }
    if refs.len()!=n{return Err(bad("delay calendar append census differs"))}
    refs.sort_unstable_by_key(|x|(x.0,x.2.0,x.1));
    let blocks=if canonical{old.blocks()}else{&[]};
    let mut result=StageQueue::with_partition_capacity(combined.len(),DELAY_CALENDAR_KEYS)?;
    let mut st=DelayMergeStats{sorted:n,rebuild:!canonical,scratch,..Default::default()};
    let (mut oi,mut ni)=(0,0);
    while oi<blocks.len()||ni<refs.len(){
        let ok=blocks.get(oi).and_then(|b|delay_calendar_key(b.min_ready,t,dt));
        let nk=refs.get(ni).map(|x|x.0);
        let k=match(ok,nk){(Some(a),Some(b))=>a.min(b),(Some(a),None)=>a,(None,Some(b))=>b,(None,None)=>return Err(bad("delay calendar partition key absent"))};
        let os=oi;while oi<blocks.len()&&delay_calendar_key(blocks[oi].min_ready,t,dt)==Some(k){oi+=1}
        let ns=ni;while ni<refs.len()&&refs[ni].0==k{ni+=1}
        if ns==ni{
            st.shared+=blocks[os..oi].iter().map(|b|b.rows.len()).sum::<usize>();
            result.append_shared_blocks(&blocks[os..oi]);continue
        }
        let mut a=blocks[os..oi].iter().flat_map(|b|b.rows.iter()).peekable();
        let mut b=refs[ns..ni].iter().map(|x|x.2).peekable();
        let mut first_in_partition=true;
        while a.peek().is_some()||b.peek().is_some(){
            let first=match(a.peek(),b.peek()){
                (Some(x),Some(y))=>if x.0<=y.0{**x}else{**y},
                (Some(x),None)=>**x,(None,Some(y))=>**y,_=>unreachable!()
            };
            let leg=first.0;let mut g=EntryGroup::new(k,first);
            let aa=a.clone();let bb=b.clone();let (mut na,mut nb)=(0usize,0usize);let mut good=true;
            while a.peek().is_some_and(|x|x.0==leg){
                let r=a.next().unwrap();na+=1;
                if good{good=delay_projectable(r,k,t,dt,horizon)&&g.add_at(*r,t,dt,birth_max)}
            }
            while b.peek().is_some_and(|x|x.0==leg){
                let r=b.next().unwrap();nb+=1;
                if good{good=delay_projectable(r,k,t,dt,horizon)&&g.add_at(*r,t,dt,birth_max)}
            }
            let rep=if good&&na+nb>1{g.representative_at(t,dt,birth_max).filter(|r|delay_projectable(r,k,t,dt,horizon))}else{None};
            if let Some(r)=rep{
                result.push_partitioned(r,first_in_partition);first_in_partition=false;
                st.removed+=na+nb-1;
            }else{
                for &r in aa.take(na).chain(bb.take(nb)){
                    result.push_partitioned(r,first_in_partition);first_in_partition=false;
                }
            }
        }
    }
    if result.len()+st.removed!=combined.len()||!result.canonical_clock_order(|r|delay_calendar_key(r,t,dt)){
        return Err(bad("delay calendar output census/order differs"))
    }
    if result.storage_bytes().saturating_add(n.saturating_mul(std::mem::size_of::<(u32,usize,&Access)>())).saturating_add(64*1024)>available{
        return Err(CoreError::resource("delay calendar actual scratch exceeds preflight"))
    }
    Ok(Some((result,st)))
}
fn admitted_delay_calendar(old:&StageQueue,combined:&StageQueue,t:f64,dt:f64,birth_max:f64,horizon:Option<&[f64]>,budget:Option<usize>,retained:usize,dynamic:usize,other_scratch:usize,stage:&str)->CoreResult<Option<StageQueue>>{
    let (sorted,shared,removed,rebuild,workspace,fallback)=if stage=="entry"{
        ("delay_calendar.entry_sorted","delay_calendar.entry_shared","delay_calendar.entry_removed","delay_calendar.entry_rebuild","delay_calendar.entry_workspace","delay_calendar.entry_fallback")
    }else{
        ("delay_calendar.egress_sorted","delay_calendar.egress_shared","delay_calendar.egress_removed","delay_calendar.egress_rebuild","delay_calendar.egress_workspace","delay_calendar.egress_fallback")
    };
    if combined.is_empty(){return Ok(None)}
    let base=dynamic.max(retained).saturating_mul(WORKING_COPIES).saturating_add(STORAGE_SCRATCH_RESERVE).saturating_add(other_scratch);
    let available=budget.unwrap_or(usize::MAX).saturating_sub(base);
    let Some((_,_,need))=delay_calendar_workspace(old,combined,t,dt)else{crate::v1_trace::add(fallback,1);return Ok(None)};
    if need>available{crate::v1_trace::add(fallback,1);return Ok(None)}
    check_storage_limit(budget,retained,dynamic,other_scratch.saturating_add(need))?;
    let Some((next,st))=merge_delay_calendar(old,combined,t,dt,birth_max,horizon,available)?else{crate::v1_trace::add(fallback,1);return Ok(None)};
    crate::v1_trace::add(sorted,st.sorted as u64);crate::v1_trace::add(shared,st.shared as u64);
    crate::v1_trace::add(removed,st.removed as u64);crate::v1_trace::add(rebuild,u64::from(st.rebuild));crate::v1_trace::add(workspace,st.scratch as u64);
    Ok(Some(next))
}
#[cfg(test)]
mod persistent_delay_calendar_tests{
    use super::*;
    fn ledger(q:&StageQueue,t:f64)->std::collections::BTreeMap<(usize,u32),[f64;3]>{
        let mut m=std::collections::BTreeMap::<_,[f64;3]>::new();
        for a in q.iter(){let x=m.entry((a.0,entry_key(a.2+a.3,t,10.).unwrap())).or_default();x[0]+=a.1;x[1]+=a.1*a.2;x[2]+=a.1*(a.2+a.3);}
        m
    }
    #[test]
    fn calendar_normalizes_once_then_merges_only_tail_and_shares_other_clocks(){
        let mut old=StageQueue::new();
        for a in [(3,0.5,1.,22.),(1,0.25,1.,12.),(1,0.75,3.,13.),(2,1.,2.,42.)]{old.push(a);}
        let (q,s)=merge_delay_calendar(&old,&old,10.,10.,10.,None,usize::MAX).unwrap().unwrap();
        assert!(s.rebuild);assert_eq!(s.sorted,4);assert_eq!(s.removed,1);assert_eq!(ledger(&old,10.),ledger(&q,10.));
        let mut c=q.clone();c.push((1,0.5,10.,6.));c.push((4,1.,10.,6.));
        let (d,s)=merge_delay_calendar(&q,&c,10.,10.,10.,None,usize::MAX).unwrap().unwrap();
        assert!(!s.rebuild);assert_eq!(s.sorted,2);assert_eq!(s.shared,2);assert_eq!(s.removed,1);
        assert_eq!(ledger(&c,10.),ledger(&d,10.));assert_eq!(q.len(),3);
        assert!(merge_delay_calendar(&q,&c,10.,10.,10.,None,1).unwrap().is_none());
        let mut next=d.clone();next.retire_due_mode(20.+1e-10,true,|_|{});
        assert!(next.canonical_clock_order(|r|delay_calendar_key(r,20.,10.)));
    }
    #[test]
    fn egress_horizon_and_overdue_clamp_protect_raw_rows(){
        let mut raw=StageQueue::new();
        for a in [(0,0.5,1.,12.),(0,0.5,3.,13.),(1,0.5,1.,12.),(1,0.5,3.,13.),(2,0.5,1.,2.),(2,0.5,3.,2.)]{raw.push(a);}
        let (q,s)=merge_delay_calendar(&StageQueue::new(),&raw,10.,10.,20.,Some(&[100.,14.,100.]),usize::MAX).unwrap().unwrap();
        assert_eq!(s.removed,1);assert_eq!(q.len(),5);assert_eq!(ledger(&raw,10.),ledger(&q,10.));
        assert_eq!(q.iter().filter(|a|a.0==1).count(),2);assert_eq!(q.iter().filter(|a|a.0==2).count(),2);
    }
}

// Periodic cross-generation entry quotient. Sort only compact references
// and original ordinals; old queue remains immutable until replacement.
fn entry_sweep_scratch(rows:usize)->usize{
    rows.saturating_mul(std::mem::size_of::<(u64,usize,&Access)>())
        .saturating_add(StageQueue::new().append_upper_bytes(rows))
        .saturating_add(64*1024)
}
fn compact_entry_queue(q:&StageQueue,t:f64,dt:f64,available:usize)->CoreResult<Option<StageQueue>>{
    let n=q.len();
    if n<2||entry_sweep_scratch(n)>available{return Ok(None)}
    let mut refs=checkpoint_vec(n)?;
    if refs.capacity()!=n{return Ok(None)}
    for (ord,a) in q.iter().enumerate(){
        if a.0>u32::MAX as usize||!a.1.is_finite()||a.1<=0.||!a.2.is_finite()||a.2<0.||a.2>t||!a.3.is_finite()||a.3<0.{return Ok(None)}
        let Some(key)=entry_key(a.2+a.3,t,dt)else{return Ok(None)};
        refs.push((((a.0 as u64)<<32)|key as u64,ord,a));
    }
    if refs.len()!=n{return Err(bad("entry sweep source census"))}
    refs.sort_unstable_by_key(|a|(a.0,a.1));
    let mut result=StageQueue::new();
    for chunk in refs.chunk_by(|a,b|a.0==b.0){
        if chunk.len()==1{result.push(*chunk[0].2);continue}
        let mut group=EntryGroup::new(chunk[0].0 as u32,*chunk[0].2);
        let valid=chunk.iter().all(|r|group.add(*r.2,t,dt));
        if let Some(a)=valid.then(||group.representative(t,dt)).flatten(){
            result.push(a);
        }else{
            for r in chunk{result.push(*r.2);}
        }
    }
    if result.len()>=n{return Ok(None)}
    if result.storage_bytes().saturating_add(n.saturating_mul(std::mem::size_of::<(u64,usize,&Access)>())).saturating_add(64*1024)>available{
        return Err(CoreError::resource("entry sweep realized workspace exceeds preflight"))
    }
    Ok(Some(result))
}
#[cfg(test)]
mod entry_projection_tests{
    use super::*;
    #[test]
    fn local_access_projection_preserves_ready_ticks_and_birth_mass(){
        let mut w=EntryWorkspace::new().unwrap();
        let law=[(3.,0.125),(5.,0.25),(13.,0.25),(15.,0.375)];
        assert!(w.project(3,2.,1.,9.,&law,10.,10.));
        assert_eq!(w.out.len(),2);
        let ledger=|rows:&[Access]|{
            let mut d=std::collections::BTreeMap::<u32,[f64;2]>::new();
            for a in rows{let k=entry_key(a.2+a.3,10.,10.).unwrap();let x=d.entry(k).or_default();x[0]+=a.1;x[1]+=a.1*a.2;}
            d
        };
        let raw:Vec<Access>=law.iter().map(|&(d,q)|(3,2.*q,1.,d+9.)).collect();
        assert_eq!(ledger(&raw),ledger(&w.out));
        assert!(!w.project(3,2.,11.,9.,&law,10.,10.));
        assert!(!w.project(3,2.,1.,9.,&[(3.,0.5),(13.,0.5)],10.,10.));
    }
    #[test]
    fn sweep_projects_across_generations_without_losing_tag_or_due_tick(){
        let mut q=StageQueue::new();
        for row in [(1,0.25,1.,12.),(2,0.5,4.,10.),(1,0.75,3.,13.),(1,0.5,1.,21.),(2,0.25,6.,9.),(1,0.5,7.,17.)]{q.push(row);}
        let before=q.iter().copied().collect::<Vec<_>>();
        let cap=entry_sweep_scratch(q.len());
        assert!(compact_entry_queue(&q,10.,10.,cap-1).unwrap().is_none());
        let out=compact_entry_queue(&q,10.,10.,cap).unwrap().unwrap();
        assert_eq!(out.len(),3);
        let ledger=|q:&StageQueue|{
            let mut d=std::collections::BTreeMap::<(usize,u32),[f64;2]>::new();
            for a in q.iter(){let k=entry_key(a.2+a.3,10.,10.).unwrap();let x=d.entry((a.0,k)).or_default();x[0]+=a.1;x[1]+=a.1*a.2;}
            d
        };
        assert_eq!(ledger(&q),ledger(&out));
        assert_eq!(before,q.iter().copied().collect::<Vec<_>>());
        for u in [10.,20.,30.,40.]{
            let mut raw=q.clone();let mut reduced=out.clone();
            let by_due=|q:&mut StageQueue|{
                let mut d=std::collections::BTreeMap::<usize,[f64;2]>::new();
                q.retire_due(u+1e-10,|a|{let x=d.entry(a.0).or_default();x[0]+=a.1;x[1]+=a.1*a.2;});d
            };
            assert_eq!(by_due(&mut raw),by_due(&mut reduced));
        }
    }
    #[test]
    fn entry_key_matches_original_rounded_readiness(){
        for t in [0.,10.,29340.,86400.]{
            for k in 0..6{
                let edge=t+k as f64*10.;
                for r in [edge,edge.next_up(),edge+1e-10,(edge+1e-10).next_up(),(edge-1e-10).max(0.)]{
                    let reference=(0..=7).find(|j|r<=t+*j as f64*10.+1e-10).unwrap();
                    assert_eq!(entry_key(r,t,10.),Some(reference));
                }
            }
        }
    }
}

// Research-only linear convolution on identical (leg, outlet clock) atoms.
// Do not change physical last-tick event owner or service sink processing.
#[derive(Clone,Copy,Debug)]
struct OutletAtom { leg:usize, stamp:f64, mass:f64, ordinal:usize }
// Positive stage projection under frozen private observer horizon.
// Key 0 is already ready at tick start; key 1 retires this tick;
// larger keys distinguish all future retirement ticks. Unsupported horizons
// and floating boundary cases fall back to the original per-product stream.
const EGRESS_SLOTS:usize=512;
fn private_hidden_horizon(dwell:f64,profile:&Profile)->f64{
    let Some(start)=profile.iter().map(|w|w.0).reduce(f64::min)else{return -1.};
    if start<dwell{return -1.}
    let mut h=start-dwell;
    if h+dwell>start{h=h.next_down();}
    if h<0.||h+dwell>start{-1.}else{h}
}
fn egress_key(r:f64,t:f64,end:f64,dt:f64)->Option<usize>{
    if !r.is_finite()||r<0.||!dt.is_finite()||dt<=0.{return None}
    if r<=t{return Some(0)}
    // Keep raw near an epsilon-only completion beyond committed time.
    if r<=end+1e-10{return if r<=end{Some(1)}else{None}}
    let raw=((r-end)/dt).ceil();
    if !raw.is_finite()||raw<1.||raw>=(EGRESS_SLOTS-2)as f64{return None}
    let mut k=raw as usize;
    if k>1&&r<=end+(k-1)as f64*dt+1e-10{k-=1;}
    if r>end+k as f64*dt+1e-10{k+=1;}
    if k+1>=EGRESS_SLOTS||r<=end+(k-1)as f64*dt+1e-10||r>end+k as f64*dt+1e-10{return None}
    // A later epsilon-only retirement would also violate valid_at.
    if r>end+k as f64*dt{return None}
    Some(k+1)
}
#[derive(Default)]
struct EgressBin{birth:ReceiptAccumulator,ready:ReceiptAccumulator,first:Access}
struct EgressWorkspace{
    slots:[u16;EGRESS_SLOTS],bins:Vec<EgressBin>,out:Vec<Access>,
}
impl EgressWorkspace{
    fn storage_upper()->usize{
        std::mem::size_of::<Self>().saturating_add(EGRESS_SLOTS.saturating_mul(std::mem::size_of::<EgressBin>()+std::mem::size_of::<Access>())).saturating_add(2*RETAINED_ALLOCATION_PADDING)
    }
    fn new()->CoreResult<Self>{
        let bins=checkpoint_vec(EGRESS_SLOTS)?;let out=checkpoint_vec(EGRESS_SLOTS)?;
        if bins.capacity()!=EGRESS_SLOTS||out.capacity()!=EGRESS_SLOTS{return Err(CoreError::resource("egress workspace capacity differs"))}
        Ok(Self{slots:[u16::MAX;EGRESS_SLOTS],bins,out})
    }
    fn project(&mut self,rows:&[OutletAtom],law:&[(f64,f64)],t:f64,end:f64,dt:f64,horizon:f64)->bool{
        self.bins.clear();self.out.clear();self.slots.fill(u16::MAX);
        if rows.is_empty()||law.is_empty()||end>horizon||end-t!=dt||t%dt!=0.||end%dt!=0.{return false}
        let i=rows[0].leg;
        let Some(raw)=rows.len().checked_mul(law.len())else{return false};
        if raw<2{return false}
        let mut max_key=0;
        for e in rows{
            if e.leg!=i{return false}
            for &(d,w) in law{
                let b=e.stamp;let r=b+d;let m=e.mass*w;
                if r>horizon||b>end+1e-8{return false}
                let Some(key)=egress_key(r,t,end,dt)else{return false};
                max_key=max_key.max(key);
                if self.slots[key]==u16::MAX{
                    if self.bins.len()==self.bins.capacity(){return false}
                    self.slots[key]=self.bins.len()as u16;
                    self.bins.push(EgressBin{first:(i,m,b,d),..Default::default()});
                }
                let bin=&mut self.bins[self.slots[key]as usize];
                if bin.birth.add(b,m,end+1e-8).is_err()||bin.ready.add(r,m,f64::MAX).is_err(){return false}
            }
        }
        if self.bins.len()>=raw{return false}
        for key in 0..=max_key{
            let slot=self.slots[key];
            if slot==u16::MAX{continue}
            let bin=&self.bins[slot as usize];
            if bin.birth.count()==1{self.out.push(bin.first);continue}
            let Ok((b,m))=bin.birth.representative()else{return false};
            let Ok((r,m2))=bin.ready.representative()else{return false};
            if m.to_bits()!=m2.to_bits()||r<b{return false}
            let d=r-b;let actual=b+d;
            if egress_key(actual,t,end,dt)!=Some(key)||actual>horizon||b>end+1e-8||(actual-r).abs()>1e-11*r.abs()+4.*f64::from_bits(1){return false}
            self.out.push((i,m,b,d));
        }
        true
    }
}

#[cfg(test)]
mod egress_projection_tests{
    use super::*;
    #[test]
    fn projected_egress_preserves_retirement_ticks_and_moments(){
        let rows=[OutletAtom{leg:3,stamp:1.,mass:0.25,ordinal:0},OutletAtom{leg:3,stamp:2.,mass:0.75,ordinal:1}];
        let law=vec![(3.,0.5),(13.,0.5)];
        let mut work=EgressWorkspace::new().unwrap();
        assert!(work.project(&rows,&law,0.,10.,10.,100.));
        assert_eq!(work.out.len(),2);
        let mut expected=std::collections::BTreeMap::<usize,[f64;3]>::new();
        for e in &rows{for &(d,w) in &law{
            let k=egress_key(e.stamp+d,0.,10.,10.).unwrap();let v=expected.entry(k).or_default();let m=e.mass*w;
            v[0]+=m;v[1]+=m*e.stamp;v[2]+=m*(e.stamp+d);
        }}
        for a in &work.out{
            let k=egress_key(a.2+a.3,0.,10.,10.).unwrap();
            assert_eq!([a.1,a.1*a.2,a.1*(a.2+a.3)],expected[&k]);
        }
        assert!(!work.project(&rows,&law,0.,10.,10.,14.));
        assert_eq!(egress_key(10.+5e-11,0.,10.,10.),None);
        assert_eq!(private_hidden_horizon(80.,&vec![(100.,110.,1.)]),20.);
    }
    #[test]
    fn early_clock_clamp_and_future_boundaries_are_distinct(){
        assert_eq!(egress_key(9.,10.,20.,10.),Some(0));
        assert_eq!(egress_key(10.,10.,20.,10.),Some(0));
        assert_eq!(egress_key(10.00001,10.,20.,10.),Some(1));
        assert_eq!(egress_key(30.,10.,20.,10.),Some(2));
        assert_eq!(egress_key(30.0001,10.,20.,10.),Some(3));
    }
}
#[cfg(feature="native-cli")]
pub struct EgressBucketProbe(EgressWorkspace);
#[cfg(feature="native-cli")]
impl EgressBucketProbe{
    pub fn new()->CoreResult<Self>{Ok(Self(EgressWorkspace::new()?))}
    pub fn run(&mut self)->CoreResult<[f64;2]>{
        let rows=[OutletAtom{leg:3,stamp:1.,mass:0.25,ordinal:0},OutletAtom{leg:3,stamp:2.,mass:0.75,ordinal:1}];
        // Use a slice adapter to avoid allocating the law on each probe.
        let law=[(3.,0.5),(13.,0.5)];
        if !self.0.project(&rows,&law,0.,10.,10.,100.){return Err(bad("egress probe projection failed"))}
        Ok([self.0.out.len()as f64,self.0.out.iter().map(|a|a.1).sum()])
    }
}
fn group_outlet_atoms(rows:&mut Vec<OutletAtom>)->CoreResult<()>{let n=group_outlet_slice(rows)?;rows.truncate(n);Ok(())}
fn group_outlet_slice(rows:&mut [OutletAtom])->CoreResult<usize>{
    if rows.iter().any(|r|!nonnegative([r.stamp,r.mass])){return Err(bad("invalid grouped outlet atom"))}
    rows.sort_unstable_by_key(|r|(r.leg,r.stamp.to_bits(),r.ordinal));
    let mut read=0usize;let mut write=0usize;
    while read<rows.len(){
        let mut row=rows[read];let mut end=read+1;
        while end<rows.len()&&rows[end].leg==row.leg&&rows[end].stamp.to_bits()==row.stamp.to_bits(){end+=1}
        row.mass=fsum(rows[read..end].iter().map(|x|x.mass));
        if !row.mass.is_finite()||row.mass<0.{return Err(bad("grouped outlet sum overflow"))}
        rows[write]=row;write+=1;read=end;
    }
    Ok(write)
}
#[cfg(test)]
mod outlet_group_tests{
    use super::*;
    #[test]fn same_clock_convolution_retains_distinct_leg_and_stamp(){
        let mut a=vec![
            OutletAtom{leg:1,stamp:4.,mass:0.125,ordinal:0},
            OutletAtom{leg:2,stamp:4.,mass:0.25,ordinal:1},
            OutletAtom{leg:1,stamp:5.,mass:0.125,ordinal:2},
            OutletAtom{leg:1,stamp:4.,mass:0.375,ordinal:3}
        ];
        let law=[(1.,0.25),(2.,0.75)];
        let distribution=|rows:&[OutletAtom]|{
            let mut d=std::collections::BTreeMap::new();
            for r in rows{for &(delay,w) in &law{*d.entry((r.leg,(r.stamp+delay).to_bits())).or_insert(0.)+=r.mass*w;}}
            d
        };
        let reference=distribution(&a);group_outlet_atoms(&mut a).unwrap();
        assert_eq!(a.len(),3);assert_eq!(a[0].mass,0.5);assert_eq!(distribution(&a),reference);
        a[0].mass=f64::NAN;assert!(group_outlet_atoms(&mut a).is_err());
    }
}

// Same little-endian journey wire, only the writer call granularity changes.
struct JourneyWords<'a,W:Write>{writer:&'a mut W,buffer:[u8;8192],len:usize}
impl<'a,W:Write> JourneyWords<'a,W>{
    fn new(writer:&'a mut W)->Self{Self{writer,buffer:[0;8192],len:0}}
    fn word(&mut self,x:u64)->CoreResult<()>{
        if self.len==self.buffer.len(){self.flush()?}
        self.buffer[self.len..self.len+8].copy_from_slice(&x.to_le_bytes());self.len+=8;Ok(())
    }
    fn flush(&mut self)->CoreResult<()>{self.writer.write_all(&self.buffer[..self.len]).map_err(|e|CoreError::io(e.to_string()))?;self.len=0;Ok(())}
}
#[cfg(feature="native-cli")]
pub fn allocation_probe_outlet_and_wire()->CoreResult<[u64;2]>{
    let mut r=[OutletAtom{leg:2,stamp:1.,mass:0.125,ordinal:0},OutletAtom{leg:1,stamp:2.,mass:0.25,ordinal:1},OutletAtom{leg:2,stamp:1.,mass:0.375,ordinal:2},OutletAtom{leg:1,stamp:3.,mass:0.25,ordinal:3}];
    let n=group_outlet_slice(&mut r)?;
    let mut sink=std::io::sink();let mut w=JourneyWords::new(&mut sink);
    let mut check=0u64;
    for x in &r[..n]{w.word(x.leg as u64)?;w.word(x.stamp.to_bits())?;w.word(x.mass.to_bits())?;check=check.wrapping_add(x.mass.to_bits());}
    w.flush()?;Ok([n as u64,check])
}
#[cfg(test)]mod journey_batch_wire_tests{
 use super::*;
 #[test]fn scalar_and_batch_identical_with_long_and_short_histories(){
  let mut a=StageQueue::new();for i in 0..2049{a.push((i%3,0.125,i as f64,0.25));}
  let mut h=ReceiptHistory::new();for i in 0..1300{h.push((i as f64,0.125)).unwrap()}
  let s=(2000.,a,StageQueue::new(),StageQueue::new(),vec![1.,2.,3.],vec![0.5,1.,2.],vec![h,ReceiptHistory::from_rows(vec![(2.,0.5)]).unwrap(),ReceiptHistory::new()],vec![0.,1.,2.]);
  let(mut old,mut new)=(vec![],vec![]);NativeJourneyCore::write_snapshot_scalar(&mut old,&s).unwrap();NativeJourneyCore::write_snapshot_batched(&mut new,&s).unwrap();assert_eq!(old,new);
 }
}

#[cfg(test)]
mod observable_clock_lazy_tests{
    use super::*;
    #[test]
    fn dormant_private_and_unreleased_validator_do_not_read_parent(){
        assert_eq!(release_high(0.,0.,||panic!("dormant parent query")),None);
        assert_eq!(release_high(0.25,0.25,||panic!("saturated profile query")),None);
        assert!(released_eligible(1e-9,10.,1e-9,||panic!("zero tolerance query")));
    }
    #[test]
    fn lazy_matches_eager_for_valid_finite_domain(){
        for p in [0.,0.125,0.5,1.]{for lo in [0.,0.125,0.5,1.,1.0000000001]{
            for e in [0.,0.125,0.5,1.,1.0000000001]{
                let hi:f64=f64::min(p,e);
                assert_eq!(release_high(p,lo,||e),if hi<=lo{None}else{Some(hi)});
                for m in [0.,0.5,1.,100.]{
                    let r=lo*m;
                    let tol=1e-9*m.max(1.);
                    assert_eq!(released_eligible(r,m,tol,||e),r<=m*e+tol);
                }
            }
        }}
    }
}

#[cfg(test)]
mod schedule_receipt_tests{
    use super::*;
    #[test]
    fn schedule_closure_preserves_all_observable_queries_and_moment(){
        let profile=vec![(100.,110.,1.)];
        let h=ReceiptHistory::from_rows(vec![(1.,0.125),(5.,0.25),(20.,0.625)]).unwrap();
        let c=h.compact_mature(20.,0.,1_000_000).unwrap().unwrap();
        assert_eq!(c.len(),1);
        for d in [10.,80.]{
            assert!(private_profile_hides_old_history(20.,d,1,&profile));
            for u in (20..=130).step_by(10){
                let p=fraction(&profile,u as f64);
                assert_eq!(p.min(h.eligible(d,u as f64)),p.min(c.eligible(d,u as f64)));
            }
        }
        assert!(!private_profile_hides_old_history(20.,81.,1,&profile));
        assert!(!private_profile_hides_old_history(20.,10.,0,&profile));
        assert_eq!(h.total(),c.total());
        assert_eq!(h.iter().map(|r|r.0*r.1).sum::<f64>(),c.iter().map(|r|r.0*r.1).sum::<f64>());
    }
}

#[cfg(test)]
mod service_projection_tests{
    use super::*;
    #[test]
    fn service_observer_bound_counts_only_materializable_keys(){
        assert_eq!(service_observer_group_bound(4_000_000,918_450,0,0),0);
        assert_eq!(service_observer_group_bound(4_000_000,918_450,13,7),20);
        assert_eq!(service_observer_group_bound(2,918_450,13,7),2);
        assert_eq!(service_observer_group_bound(100,3,13,7),3);
        let mut q=StageQueue::new();
        for i in 0..100{q.push((i,1.,0.,1.));}
        let bus=HashMap::from([(2,[0.;3]),(5,[0.;3])]);
        let freight=HashMap::from([(2,[0.;3]),(7,[0.;3])]);
        let observed=service_egress_rows(&q,&bus,&freight);
        assert_eq!(observed.len(),3);
        assert!(observed.len()<=service_observer_group_bound(q.len(),100,bus.len(),freight.len()));
    }
    #[test]
    fn service_projection_retains_original_order_and_all_observed_mass(){
        let mut q=StageQueue::new();
        for (i,m) in [(0,0.125),(2,1e16),(1,3.),(2,1.),(3,7.),(2,0.5),(1,2.)]{
            q.push((i,m,0.,1.));
        }
        let bus=HashMap::from([(2,[0.;3])]);
        let freight=HashMap::from([(1,[0.;3]),(2,[0.;3])]);
        let a=service_egress_rows(&q,&bus,&freight);
        assert_eq!(a.len(),2);
        for i in [1,2]{
            assert_eq!(a[&i],q.iter().filter(|r|r.0==i).map(|r|r.1).collect::<Vec<_>>());
        }
        assert!(service_egress_rows(&q,&HashMap::new(),&HashMap::new()).is_empty());
    }
}
