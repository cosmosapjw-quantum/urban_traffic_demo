//! Native B01 service scheduling and whole-journey ledgers.
//! Road evolution is supplied by the sole road owner between prepare/finish.
//! Each transition is transactional: errors leave the last committed state intact.
use crate::v1_history::ReceiptHistory;
use crate::v1_parallel::ordered_map;
use crate::v1_road::{
    checkpoint_vec, read_exact_len, read_f64, read_len, read_u64, write_f64, write_len, write_u64,
    ChunkedEvents, EventRow, V1Road,
};
use crate::v1_stage::{Access, StageQueue};
use pyo3::exceptions::{PyMemoryError, PyValueError};
use pyo3::prelude::*;
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
    state.1.storage_bytes()
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

/// The joint transition holds three specifically known original owners:
/// caller input, committed state, and new uncommitted candidate. They are
/// not three full copies of the largest post-road candidate. Sum all three
/// true source-retained sizes without claiming any Arc alias credit.
fn three_concrete_owner_bytes(input:usize,current:usize,candidate:usize)->usize {
    input.saturating_add(current).saturating_add(candidate)
}
/// Under a source-verified Arc identity, caller input events and the
/// currently committed service.last_events are two handles of one immutable
/// payload. Count that payload ONCE, plus the new independent road EventRow
/// Vec. Without the exact same Arc backing, count all three separately.
fn concrete_service_event_owner_bytes(
    input:usize,current:usize,candidate:usize,input_current_arc_shared:bool,
)->usize {
    if input_current_arc_shared {
        input.max(current).saturating_add(candidate)
    } else {
        three_concrete_owner_bytes(input,current,candidate)
    }
}
/// Only the same live Arc backing can be subtracted at this commit gate.
/// Equality of payload content or size is NOT enough. On an unexpected
/// mismatch in byte accounting retain the old current-owner charge.
fn verified_current_event_bytes_with_input_arc(
    input:usize,current:usize,input_current_arc_shared:bool,
)->usize {
    if input_current_arc_shared && input==current {0} else {current}
}
const STORAGE_SCRATCH_RESERVE: usize = 64 * 1024;
fn stage_storage_bytes(s: &Journey) -> usize {
    s.1.storage_bytes()
        .saturating_add(s.2.storage_bytes())
        .saturating_add(s.3.storage_bytes())
}
/// Exact pointer intersection across all three StageQueue owners. One
/// immutable Arc<Block> payload is counted only once, even when the same
/// allocation appears in two different route-stage registries. Block
/// headers, Arc control, pointer Vec registry, ReceiptHistory and metadata
/// stay fully charged in each owner. The temporary pointer HashMap's
/// measured capacity is included as separate source census scratch.
#[derive(Default,Clone,Copy)]
struct JourneyStageArcOverlap {
    shared_payload_bytes:usize,
    temporary_census_scratch_bytes:usize,
}
fn journey_shared_stage_payload_census(
    left:&Journey,right:&Journey,
)->JourneyStageArcOverlap {
    let mut witness=HashMap::<usize,usize>::new();
    for queue in [&left.1,&left.2,&left.3] {
        queue.visit_immutable_row_payloads(|ptr,bytes|{
            witness.entry(ptr).or_insert(bytes);
        });
    }
    let scratch=hash_capacity_storage_bytes::<usize,usize>(witness.capacity());
    let mut shared=0usize;
    for queue in [&right.1,&right.2,&right.3] {
        queue.visit_immutable_row_payloads(|ptr,_|{
            if let Some(bytes)=witness.remove(&ptr) {
                shared=shared.saturating_add(bytes);
            }
        });
    }
    JourneyStageArcOverlap{
        shared_payload_bytes:shared,
        temporary_census_scratch_bytes:scratch,
    }
}
/// Before road prediction there is no road candidate: only the supplied
/// input and committed road allocations are live. The restore-time pointer
/// witness expires on the first changed road clock, exactly as in the road
/// owner's existing post-proposal accounting.
fn preproposal_road_source_owner_bytes(
    input:usize,current:usize,current_clock:f64,
    verified_input_shared:Option<(f64,usize)>,
)->(usize,usize) {
    let credit=verified_input_shared.map_or(0,|(clock,bytes)|{
        if clock==current_clock {bytes.min(input).min(current)} else {0}
    });
    (input.saturating_add(current).saturating_sub(credit),credit)
}

/// The census inserts at most one key per source block. The existing helper
/// grows a HashMap, so cover BOTH old and new tables during reallocation,
/// including each table's conservative control/allocator padding. Two pair
/// censuses run sequentially; their maps are dropped before either returns.
fn stage_census_table_upper_bytes(state:&Journey)->usize {
    let blocks=state.1.block_count()
        .saturating_add(state.2.block_count())
        .saturating_add(state.3.block_count());
    if blocks==0 {return 0;}
    // A one-entry HashMap already has usable capacity 3. The generic
    // 2*entries capacity envelope must include that minimum allocation.
    hash_entries_upper_bytes::<usize,usize>(blocks.max(2))
}
fn stage_census_scratch_upper_bytes(state:&Journey)->usize {
    stage_census_table_upper_bytes(state).saturating_mul(2)
}

fn check_stage_census_actual_scratch(actual:usize,upper:usize)->PyResult<()> {
    if actual>upper {
        return Err(PyMemoryError::new_err(format!(
            "native journey stage census capacity exceeds preflight: actual_bytes={actual}, reserved_bytes={upper}"
        )));
    }
    Ok(())
}

/// The whole-engine snapshot census has a source-exact Clone target.
#[derive(Default,Clone,Copy)]
pub(crate) struct SnapshotJourneyArcWitness {
    pub(crate) input_current_stage_payload_bytes:usize,
    pub(crate) clone_stage_payload_bytes:usize,
    pub(crate) clone_history_bytes:usize,
    pub(crate) actual_census_bytes:usize,
}
pub(crate) fn snapshot_journey_census_upper_bytes(target:&Journey)->usize {
    stage_census_scratch_upper_bytes(target)
}
pub(crate) fn snapshot_journey_arc_witness(
    target:&Journey,other:&Journey,
)->PyResult<SnapshotJourneyArcWitness> {
    let pair=journey_shared_stage_payload_census(target,other);
    check_stage_census_actual_scratch(
        pair.temporary_census_scratch_bytes,stage_census_table_upper_bytes(target))?;
    let mut cloned_stages=0usize;
    for queue in [&target.1,&target.2,&target.3] {
        queue.visit_immutable_row_payloads(|_,bytes|{
            cloned_stages=cloned_stages.saturating_add(bytes);
        });
    }
    // StageQueue::clone shares immutable blocks but allocates its registry:
    // credit only row payloads, conservatively retaining every block header.
    // ReceiptHistory::clone is exactly an Option<Arc<Block>> clone. All its
    // measured dynamic storage stays in the same persistent chain; the outer
    // Vec<ReceiptHistory> is already in the fixed dense reserve. No credit
    // for cross-source history prefixes is inferred from equal values.
    Ok(SnapshotJourneyArcWitness{
        input_current_stage_payload_bytes:pair.shared_payload_bytes,
        clone_stage_payload_bytes:cloned_stages,
        clone_history_bytes:target.6.iter().map(ReceiptHistory::storage_bytes).sum(),
        actual_census_bytes:pair.temporary_census_scratch_bytes,
    })
}

#[derive(Default,Clone,Copy)]
struct RoadPhaseJourneyOwners {
    uncredited_bytes:usize,
    charged_bytes:usize,
    input_current_payload_credit:usize,
    current_pending_payload_credit:usize,
    census_scratch_upper_bytes:usize,
    census_actual_scratch_bytes:usize,
}

/// Input/current/pending Journey states remain immutable throughout the
/// road proposal. Retain every history and stage shell/registry allocation;
/// only the two actually witnessed immutable row-payload intersections are
/// credits. Dense per-leg copies remain in the unchanged engine fixed reserve.
/// Missing source references retain the original conservative 3*max policy.
fn road_phase_journey_owner_bytes(
    input:Option<&Journey>,current:&Journey,pending:Option<&Journey>,
    input_bytes:usize,current_bytes:usize,pending_bytes:usize,
    other_live:usize,total:usize,
)->PyResult<RoadPhaseJourneyOwners> {
    let (Some(input),Some(pending))=(input,pending) else {
        let conservative=input_bytes.max(current_bytes).max(pending_bytes)
            .saturating_mul(WORKING_COPIES);
        return Ok(RoadPhaseJourneyOwners{
            uncredited_bytes:conservative,charged_bytes:conservative,
            ..RoadPhaseJourneyOwners::default()
        });
    };
    let uncredited=three_concrete_owner_bytes(input_bytes,current_bytes,pending_bytes);
    let scratch_upper=stage_census_scratch_upper_bytes(input)
        .max(stage_census_scratch_upper_bytes(current));
    // Admission precedes either HashMap allocation and uses NO Journey
    // overlap credit. other_live contains only actual old road/event owners
    // plus the already allocated physical offers; no future road candidate.
    let required=other_live.saturating_add(uncredited)
        .saturating_add(scratch_upper)
        .saturating_add(STORAGE_SCRATCH_RESERVE);
    crate::v1_trace::guard(
        "journey_stage_census","road preproposal",required,total,&[
            ("known_other_live",other_live),
            ("journey_input",input_bytes),
            ("journey_current",current_bytes),
            ("journey_pending",pending_bytes),
            ("journey_uncredited_sum",uncredited),
            ("census_growth_scratch_upper",scratch_upper),
            ("scratch_original",STORAGE_SCRATCH_RESERVE),
        ],
    );
    if required>total {
        return Err(PyMemoryError::new_err(format!(
            "native journey stage census preflight budget exceeded: required_bytes={required}, budget_bytes={total}"
        )));
    }
    let source_current=journey_shared_stage_payload_census(input,current);
    check_stage_census_actual_scratch(
        source_current.temporary_census_scratch_bytes,stage_census_table_upper_bytes(input))?;
    let current_pending=journey_shared_stage_payload_census(current,pending);
    check_stage_census_actual_scratch(
        current_pending.temporary_census_scratch_bytes,stage_census_table_upper_bytes(current))?;
    // Each helper has already dropped its HashMap. The simultaneous three
    // owners may share one allocation: then subtracting its payload in BOTH
    // pairs leaves exactly one payload charge, while all metadata remains.
    let input_credit=source_current.shared_payload_bytes
        .min(input_bytes).min(current_bytes);
    let pending_credit=current_pending.shared_payload_bytes
        .min(current_bytes).min(pending_bytes);
    Ok(RoadPhaseJourneyOwners{
        uncredited_bytes:uncredited,
        charged_bytes:uncredited.saturating_sub(input_credit).saturating_sub(pending_credit),
        input_current_payload_credit:input_credit,
        current_pending_payload_credit:pending_credit,
        census_scratch_upper_bytes:scratch_upper,
        census_actual_scratch_bytes:source_current.temporary_census_scratch_bytes
            .max(current_pending.temporary_census_scratch_bytes),
    })
}

/// Read-only checkpoint decoder has TWO physical source lifetimes:
/// one preexisting retained Journey and one partially constructed decoded
/// Journey. The caller has already reserved original road/service owners.
 /// StageQueue::append_upper_bytes includes its one live tail/reallocation
/// transient and Vec registry growth; keep the original 64KiB scratch.
/// Do not substitute this bound for the multi-owner mutation/rollback guard.
fn check_journey_decode_source_limit(
    limit:Option<usize>,retained:usize,decoded_with_next_append:usize,
)->PyResult<()> {
    let required=retained.saturating_add(decoded_with_next_append)
        .saturating_add(STORAGE_SCRATCH_RESERVE);
    if let Some(cap)=limit {
        crate::v1_trace::guard(
            "journey_decode","source old plus one prospective decoder",
            required,cap,&[
                ("retained_old_journey",retained),
                ("prospective_one_decoder",decoded_with_next_append),
                ("scratch_original",STORAGE_SCRATCH_RESERVE),
            ]
        );
        if required>cap {
            return Err(PyMemoryError::new_err(format!(
                "native journey source decoder storage budget exceeded: required_bytes={required}, budget_bytes={cap}"
            )));
        }
    }
    Ok(())
}

fn check_storage_limit(
    limit: Option<usize>,
    retained: usize,
    dynamic: usize,
    scratch: usize,
) -> PyResult<()> {
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
        return Err(PyMemoryError::new_err(
            "native journey stored/working byte budget",
        ));
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
        .saturating_add(t.current_road)
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
/// The original joint commit candidate and its possible future checkpoint
/// decoder are two NONOVERLAPPING lifetimes. The original input and current
/// committed source packets are simultaneous, share ONLY pointer-verified
/// immutable Arc payloads, and remain charged in both phases. Current/new
/// candidate Arc overlap exists ONLY in the candidate phase: a future
/// decoded checkpoint is a distinct allocation, not eligible for that credit.
/// Keep every other original Journey, service EventRow, scratch and pool term.
fn checkpointability_source_road_arc_lifetimes(
    t:CheckpointabilityTerms,source_credit:usize,candidate_credit:usize,
)->usize {
    let old_road=t.input_road
        .saturating_add(t.current_road)
        .saturating_add(t.candidate_road.max(t.decoded_road));
    let src=source_credit.min(t.input_road).min(t.current_road);
    let cand=candidate_credit.min(t.current_road).min(t.candidate_road);
    let physical_candidate=t.input_road
        .saturating_add(t.current_road)
        .saturating_add(t.candidate_road)
        .saturating_sub(src).saturating_sub(cand);
    let independent_decode=t.input_road
        .saturating_add(t.current_road)
        .saturating_add(t.decoded_road)
        .saturating_sub(src);
    checkpointability_phase_lifetime_bytes(t)
        .saturating_sub(old_road)
        .saturating_add(physical_candidate.max(independent_decode))
}

/// NativeWholeEngine::load reads the complete RoadState first, then service
/// events, then Journey, and only then validates the decoded Bundle. Road
/// decoder workspaces have returned/dropped before a new Journey exists.
/// Keep both the full road decode scratch and the later independent Journey
/// plus whole-validation workspace, but take the maximum of these disjoint
/// phases. The caller still charges the event decode upper in every phase.
fn checkpointability_sequential_decode_phases(t:CheckpointabilityTerms)->(usize,usize) {
    let road_decode=t.decoded_road
        .saturating_add(t.road_decode_scratch.max(STORAGE_SCRATCH_RESERVE));
    let journey_validation=t.decoded_road
        .saturating_add(t.journey_decoded)
        .saturating_add(t.validation_scratch
            .saturating_sub(t.call_binding_reserve)
            .max(STORAGE_SCRATCH_RESERVE));
    (road_decode,journey_validation)
}

/// A newly constructed whole engine retains no dynamic Journey payloads and
/// only an empty event carrier before road.read_state. Static/dense owners are
/// already charged by RuntimeStorage's fixed reserve. Keep the decoder's
/// independent 3*max fallback (the decoded road dominates the empty road),
/// without adding events/Journey that have not been decoded yet. This is a
/// fresh-engine obligation; reloading after commit in the same populated
/// engine, or with unrelated user snapshots, needs its own live-owner guards.
fn checkpointability_fresh_road_decode_bytes(t:CheckpointabilityTerms)->usize {
    t.decoded_road.saturating_mul(3)
        .saturating_add(t.road_decode_scratch.max(STORAGE_SCRATCH_RESERVE))
        .saturating_add(ChunkedEvents::default().storage_bytes())
}

/// Live pre-commit source/current/candidate owners, with only the two
/// independently witnessed pointer-overlap credits. No future decoder is
/// present during this transition.
fn checkpointability_current_source_candidate_bytes(
    t:CheckpointabilityTerms,road_input_credit:usize,road_candidate_credit:usize,
    journey_input_credit:usize,journey_candidate_credit:usize,
    census_scratch:usize,
)->usize {
    let road_input_credit=road_input_credit.min(t.input_road).min(t.current_road);
    let road_candidate_credit=road_candidate_credit
        .min(t.current_road).min(t.candidate_road);
    let journey_input_credit=journey_input_credit
        .min(t.journey_input).min(t.journey_old);
    let journey_candidate_credit=journey_candidate_credit
        .min(t.journey_old).min(t.journey_new);
    t.input_road.saturating_add(t.current_road).saturating_add(t.candidate_road)
        .saturating_sub(road_input_credit).saturating_sub(road_candidate_credit)
        .saturating_add(t.journey_input).saturating_add(t.journey_old)
        .saturating_add(t.journey_new)
        .saturating_sub(journey_input_credit).saturating_sub(journey_candidate_credit)
        .saturating_add(t.event_input).saturating_add(t.event_current)
        .saturating_add(t.event_candidate)
        .saturating_add(t.validation_scratch.saturating_sub(t.call_binding_reserve)
            .max(STORAGE_SCRATCH_RESERVE))
        .saturating_add(census_scratch)
}

/// Journey.read_state ends by calling Journey.validate, whose unchanged
/// stored/working guard reserves three dynamic Journey owners plus 64 KiB.
/// The newly decoded road/events and constructor road/event owners are still
/// live. This local validator floor precedes whole-bundle validation and must
/// be retained even when the later whole-validation scratch is small.
fn checkpointability_fresh_journey_validation_bytes(
    t:CheckpointabilityTerms,initial_road_bytes:usize,decoded_event_bytes:usize,
)->usize {
    initial_road_bytes.saturating_add(ChunkedEvents::default().storage_bytes())
        .saturating_add(t.decoded_road).saturating_add(decoded_event_bytes)
        .saturating_add(t.journey_decoded.saturating_mul(WORKING_COPIES))
        .saturating_add(STORAGE_SCRATCH_RESERVE)
}

/// After fresh road decoding returns, its raw packing and streaming scratch
/// are dead. The current constructor road and empty event carrier remain
/// alongside the independent decoded road/events/Journey and real cross-owner
/// validation workspace. The engine's permanent initial snapshot, dense/static
/// owners and call binding have already been charged in the fixed reserve.
fn checkpointability_fresh_bundle_bytes(
    t:CheckpointabilityTerms,initial_road_bytes:usize,decoded_event_bytes:usize,
)->usize {
    initial_road_bytes.saturating_add(ChunkedEvents::default().storage_bytes())
        .saturating_add(t.decoded_road).saturating_add(decoded_event_bytes)
        .saturating_add(t.journey_decoded)
        .saturating_add(t.validation_scratch.saturating_sub(t.call_binding_reserve)
            .max(STORAGE_SCRATCH_RESERVE))
}

/// Historical pre-commit-owner/future-decode scenario kept solely as a
/// regression record for the previous gate. Those pre-commit owners do not
/// coexist with a fresh-process decoder, and this expression never guaranteed
/// a later populated-engine reload after the candidate replaces current.
#[cfg(test)]
fn checkpointability_source_joint_phase_bytes(
    t:CheckpointabilityTerms,road_input_credit:usize,road_candidate_credit:usize,
    journey_input_credit:usize,journey_candidate_credit:usize,
    census_scratch:usize,
)->usize {
    let road_input_credit=road_input_credit.min(t.input_road).min(t.current_road);
    let road_candidate_credit=road_candidate_credit
        .min(t.current_road).min(t.candidate_road);
    let journey_input_credit=journey_input_credit
        .min(t.journey_input).min(t.journey_old);
    let journey_candidate_credit=journey_candidate_credit
        .min(t.journey_old).min(t.journey_new);
    let fixed=t.input_road.saturating_add(t.current_road)
        .saturating_sub(road_input_credit)
        .saturating_add(t.journey_input)
        .saturating_add(t.journey_old)
        .saturating_sub(journey_input_credit)
        .saturating_add(t.event_input)
        .saturating_add(t.event_current)
        .saturating_add(t.event_candidate);
    let candidate=t.candidate_road
        .saturating_sub(road_candidate_credit)
        .saturating_add(t.journey_new.saturating_sub(journey_candidate_credit))
        .saturating_add(t.validation_scratch
            .saturating_sub(t.call_binding_reserve)
            .max(STORAGE_SCRATCH_RESERVE));
    let (road_decode,journey_validation)=checkpointability_sequential_decode_phases(t);
    let future=road_decode.max(journey_validation);
    fixed.saturating_add(candidate.max(future))
        .saturating_add(census_scratch)
}

fn phase_storage_allowance(total: usize, other_live: usize, phase: &str) -> PyResult<usize> {
    if crate::v1_trace::guard("phase_allowance", phase, other_live, total, &[]) {
        // Diagnostic observe build only: continue with a nominal allowance.
        return Ok(total.max(1));
    }
    total.checked_sub(other_live).filter(|bytes| *bytes > 0).ok_or_else(|| {
        PyMemoryError::new_err(format!(
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

fn bad(message: &str) -> PyErr {
    PyValueError::new_err(message.to_owned())
}
fn nonnegative(values: impl IntoIterator<Item = f64>) -> bool {
    values.into_iter().all(|x| x.is_finite() && x >= 0.0)
}
// Non-overlapping partials, with the final half-even adjustment of math.fsum.
pub(crate) fn fsum(values: impl IntoIterator<Item = f64>) -> f64 {
    let mut partials: Vec<f64> = Vec::new();
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

#[pyclass]
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
    pub(crate) fn event_storage_bytes(&self) -> usize {
        self.last_events.storage_bytes()
    }
    pub(crate) fn shares_event_arc(&self,other:&Arc<ChunkedEvents>)->bool {
        Arc::ptr_eq(&self.last_events,other)
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
    pub(crate) fn write_state<W: Write>(&self, w: &mut W) -> PyResult<()> {
        if self.pending.is_some() {
            return Err(bad("cannot checkpoint pending native service transition"));
        }
        let s = &self.state;
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
        write_len(w, self.last_events.len())?;
        for e in self.last_events.iter() {
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
        compact_events: bool,
    ) -> PyResult<ServiceCheckpoint> {
        fn flag<R: Read>(r: &mut R) -> PyResult<bool> {
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
        let mut events = ChunkedEvents::new(compact_events);
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
            events.push_decoded_checked(e,n)?;
        }
        let state = (runs, people, released, completed, cars);
        self.validate(&state)?;
        Ok((state, Arc::new(events)))
    }
    fn validate(&self, s: &Service) -> PyResult<()> {
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
#[pymethods]
impl NativeServiceCore {
    #[new]
    pub(crate) fn new(
        buses: Vec<Bus>,
        people: Vec<Person>,
        freight: Vec<Source>,
        cars: Vec<Source>,
    ) -> PyResult<Self> {
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
            last_events: Arc::new(ChunkedEvents::default()),
            state,
            pending: None,
        })
    }
    fn snapshot(&self) -> Service {
        self.state.clone()
    }
    /// Inspection only: immutable static heap, one dense state, event buffer.
    fn storage_accounting(&self) -> (usize, usize, usize) {
        (
            self.static_storage_bytes(),
            service_dense_storage_bytes(&self.state),
            self.event_storage_bytes(),
        )
    }
    fn road_events(&self) -> Vec<EventRow> {
        self.last_events.iter().collect()
    }
    fn restore(&mut self, state: Service) -> PyResult<()> {
        self.validate(&state)?;
        self.state = state;
        self.pending = None;
        self.last_events = Arc::new(ChunkedEvents::default());
        Ok(())
    }
    fn abort(&mut self) {
        self.pending = None;
    }
    fn prepare(&mut self, t: f64, eligible: Vec<bool>) -> PyResult<Vec<Offer>> {
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
    fn finish(&mut self, end: f64, events: Vec<Sink>) -> PyResult<()> {
        // Finish consumes its uncommitted candidate. On any failure the
        // committed state remains intact and the transaction is aborted.
        let (t, mut s) = self
            .pending
            .take()
            .ok_or_else(|| bad("native service finish without prepare"))?;
        if !end.is_finite()
            || end <= t
            || events
                .iter()
                .any(|e| !nonnegative([e.1, e.2]) || e.2 > end + 1e-8)
        {
            return Err(bad("invalid native service sink/clock"));
        }
        let mut sink_mass: HashMap<&str, Vec<f64>> = HashMap::new();
        for e in &events {
            sink_mass.entry(&e.0).or_default().push(e.1);
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
#[pyclass]
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
        let groups = rows.min(self.legs.len());
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

    fn begin_deferred_finish(&mut self) -> PyResult<()> {
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
    pub(crate) fn check_service_binding(&self, s: &Journey, service: &Service) -> PyResult<()> {
        self.validate(s)?;
        if service.1.len() != self.bus.len()
            || service.2.len() != self.freight.len()
            || service.3.len() != self.freight.len()
        {
            return Err(bad("native journey service checkpoint shape differs"));
        }
        let mut egress: HashMap<usize, Vec<f64>> = HashMap::new();
        for a in &s.2 {
            egress.entry(a.0).or_default().push(a.1);
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
    pub(crate) fn configure_storage_budget(&mut self, bytes: usize) -> PyResult<()> {
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
    pub(crate) fn set_phase_storage_budget(&mut self, bytes: usize) -> PyResult<()> {
        if bytes == 0 {
            return Err(PyMemoryError::new_err(
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
    pub(crate) fn write_state<W: Write>(&self, w: &mut W) -> PyResult<()> {
        if self.pending.is_some() || self.defer_finish_commit {
            return Err(bad("cannot checkpoint pending native journey transition"));
        }
        let s = &self.state;
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
    pub(crate) fn read_state<R: Read>(&self, r: &mut R) -> PyResult<Journey> {
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
                check_journey_decode_source_limit(
                    self.storage_budget,
                    retained,
                    stage_bytes.saturating_add(stage.append_upper_bytes(1)),
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
                check_journey_decode_source_limit(
                    self.storage_budget,
                    retained,
                    stage_bytes
                        .saturating_add(history_bytes)
                        .saturating_add(history.append_upper_bytes()),
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
    fn validate(&self, s: &Journey) -> PyResult<()> {
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
                    && s.4[i] <= l.1 * eligible(&self.legs, s, i) + tol
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
            return Err(PyMemoryError::new_err("joint journey record budget"));
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
#[pyfunction]
pub fn advance_native_joint(
    py: Python<'_>,
    mut road: PyRefMut<'_, V1Road>,
    mut service: PyRefMut<'_, NativeServiceCore>,
    mut journey: PyRefMut<'_, NativeJourneyCore>,
    tags: Vec<String>,
    count: usize,
    step_s: f64,
) -> PyResult<usize> {
    let road = &mut *road;
    let service = &mut *service;
    let journey = &mut *journey;
    py.allow_threads(move || {
        advance_owned_joint(road, service, journey, &tags, count, step_s, None, 0, 0, None, None, None)
    })
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
    fresh_initial_road_bytes: usize,
    original_input_road_shared: Option<(f64,usize)>,
    original_input_road_bytes: Option<usize>,
    original_input_journey: Option<&Journey>,
) -> PyResult<usize> {
    journey.phase_metrics = JourneyPhaseMetrics::default();
    // The Python input snapshot remains live throughout this call, even when
    // later ticks drain its queues. Charge that known retained owner as well.
    journey.retained_input_bytes = journey_storage_bytes(&journey.state);
    // The original snapshot can retain a wider registry than its restored
    // clone. Use its actual footprint for the source-concrete road phase.
    let original_input_journey_bytes=original_input_journey
        .map(journey_storage_bytes).unwrap_or(journey.retained_input_bytes);
    road.begin_call_storage_accounting();
    let call_input_events = Arc::clone(&service.last_events);
    road.configure_service_event_accounting(
        service.last_events.storage_bytes(),
        tags.iter().map(String::capacity).max().unwrap_or(0),
        Arc::ptr_eq(&call_input_events, &service.last_events),
        original_input_road_shared,
    );
    road.bind_original_input_road_storage(original_input_road_bytes);
    let input_road_bytes = if dynamic_budget.is_some() {
        original_input_road_bytes.unwrap_or_else(|| road.owned_storage_bytes())
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
        PyMemoryError::new_err("native tick metric allocation exceeds available memory")
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
        let current_event_bytes = if dynamic_budget.is_some() {
            service.event_storage_bytes()
        } else {
            0
        };
        let result = (|| -> PyResult<()> {
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
                service.last_events.storage_bytes(),
                Arc::ptr_eq(&call_input_events, &service.last_events),
            );
            if let Some(total) = dynamic_budget {
                let current_journey =
                    stage_storage_bytes(&journey.state).saturating_add(journey.history_bytes);
                let pending_journey = journey.pending.as_ref().map_or(0, |state| {
                    stage_storage_bytes(state).saturating_add(journey.history_bytes)
                });
                let (source_road_live,source_road_credit)=preproposal_road_source_owner_bytes(
                    input_road_bytes,current_road_bytes,t,original_input_road_shared);
                let old_event_arc_shared=Arc::ptr_eq(&call_input_events,&service.last_events);
                let source_event_live=concrete_service_event_owner_bytes(
                    input_event_bytes,current_event_bytes,0,old_event_arc_shared);
                let physical_offer_bytes=vec_storage_bytes(&physical);
                let census_other_live=source_road_live
                    .saturating_add(source_event_live)
                    .saturating_add(physical_offer_bytes);
                let owners=road_phase_journey_owner_bytes(
                    original_input_journey,&journey.state,journey.pending.as_ref(),
                    original_input_journey_bytes,current_journey,pending_journey,
                    census_other_live,total,
                )?;
                // Both census maps are gone. No scratch discount is carried
                // into road execution; only exact live StageQueue payload
                // aliases reduce the Journey reservation during the proposal.
                crate::v1_trace::guard(
                    "journey_road_reservation","road step",
                    census_other_live.saturating_add(owners.charged_bytes)
                        .saturating_add(STORAGE_SCRATCH_RESERVE),
                    total,&[
                        ("journey_uncredited_sum",owners.uncredited_bytes),
                        ("journey_charged",owners.charged_bytes),
                        ("input_current_stage_payload_credit",owners.input_current_payload_credit),
                        ("current_pending_stage_payload_credit",owners.current_pending_payload_credit),
                        ("source_road_live",source_road_live),
                        ("source_road_clock_verified_credit",source_road_credit),
                        ("source_event_live",source_event_live),
                        ("old_event_arc_pointer_identical",usize::from(old_event_arc_shared)),
                        ("physical_offer_bytes",physical_offer_bytes),
                        ("census_growth_scratch_upper",owners.census_scratch_upper_bytes),
                        ("census_actual_scratch_dropped",owners.census_actual_scratch_bytes),
                    ],
                );
                road.set_phase_storage_budget(phase_storage_allowance(
                    total,
                    owners.charged_bytes,
                    "road step",
                )?)?;
            }
            let result = road.propose_owned_step(step_s, physical);
            journey.phase_metrics.road_step_s += phase_started.elapsed().as_secs_f64();
            let (road_candidate, events) = result?;
            let candidate_road_bytes = if dynamic_budget.is_some() {
                road_candidate.retained_storage_bytes()
            } else {
                0
            };
            let candidate_event_bytes = if dynamic_budget.is_some() {
                events.storage_bytes()
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
                let sink_bytes = crate::v1_road::sink_envelope_bytes(exits, tag_bytes);
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
                // Source-concrete post-road owner census. No candidate
                // payload is multiplied into fictitious input snapshots.
                // Every distinct actual road/event owner remains charged.
                let (road_live,input_road_arc_credit,candidate_road_arc_credit)=
                    road.source_joint_road_owner_charge(
                        &road_candidate,input_road_bytes,original_input_road_shared);
                let old_event_arc_shared=
                    Arc::ptr_eq(&call_input_events,&service.last_events);
                let event_live = concrete_service_event_owner_bytes(
                    input_event_bytes,current_event_bytes,candidate_event_bytes,
                    old_event_arc_shared,
                );
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
                        ("source_input_shared_road_arc_payload_credit",input_road_arc_credit),
                        ("current_candidate_shared_road_arc_payload_credit",candidate_road_arc_credit),
                        ("event_live", event_live),
                        ("old_event_arc_pointer_identical",usize::from(old_event_arc_shared)),
                        ("input_event_bytes",input_event_bytes),
                        ("current_event_bytes",current_event_bytes),
                        ("candidate_event_bytes",candidate_event_bytes),
                        ("exit_rows", exits),
                        ("sink_envelope", sink_bytes),
                    ],
                );
                if required > total && !observed {
                    return Err(PyMemoryError::new_err(format!(
                        "native service event sink storage budget exceeded: phase=service finish, required_bytes={required}, budget_bytes={total}"
                    )));
                }
            }
            let mut sinks = Vec::new();
            for e in events.iter() {
                if e.2.is_none() {
                    let tag = tags
                        .get(e.0)
                        .ok_or_else(|| bad("native road event route index differs"))?;
                    sinks.push((tag.clone(), e.3, e.5));
                }
            }
            let end = road_candidate.time();
            journey.phase("service_finish");
            let phase_started = Instant::now();
            let result = service.finish(end, sinks.clone());
            journey.phase_metrics.service_finish_s += phase_started.elapsed().as_secs_f64();
            result?;
            if let Some(total) = dynamic_budget {
                // Road workspaces and the service sink-map clone have been
                // dropped. The candidate, original events and original sinks
                // remain live until the complete joint transition commits.
                let sink_bytes = sinks.iter().fold(vec_storage_bytes(&sinks), |bytes, row| {
                    bytes.saturating_add(string_storage_bytes(&row.0))
                });
                let (road_live,_,_)=road.source_joint_road_owner_charge(
                    &road_candidate,input_road_bytes,original_input_road_shared
                );
                let other_live = road_live
                    .saturating_add(concrete_service_event_owner_bytes(
                    input_event_bytes,current_event_bytes,candidate_event_bytes,
                    Arc::ptr_eq(&call_input_events,&service.last_events),
                )).saturating_add(sink_bytes);
                journey.set_phase_storage_budget(phase_storage_allowance(
                    total,
                    other_live,
                    "journey finish",
                )?)?;
                journey.begin_deferred_finish()?;
            }
            let phase_started = Instant::now();
            let result = journey.finish(
                end,
                sinks,
                service_before.1.clone(),
                service.state.1.clone(),
                service_before.2.clone(),
                service.state.2.clone(),
                service_before.3.clone(),
                service.state.3.clone(),
            );
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
                    road.checkpoint_decode_envelope(&road_candidate)?;
                // Separate source-visible lifetimes: the current
                // transition, fresh-engine road decode, the Journey decoder's
                // unchanged local validator, and later whole-bundle validation.
                // Native runtime checkpointability promises
                // fresh-runtime load/replay; populated same-engine resumption
                // remains a separate V03 acceptance experiment with its own
                // unchanged loader guards.
                let decoded_event_upper=candidate_event_bytes.max(events.decode_storage_upper_bytes());
                let old_event_arc_shared=
                    Arc::ptr_eq(&call_input_events,&service.last_events);
                let effective_current_event=verified_current_event_bytes_with_input_arc(
                    input_event_bytes,current_event_bytes,old_event_arc_shared
                );
                let lifetime=CheckpointabilityTerms {
                    input_road:input_road_bytes,
                    current_road:current_road_bytes,
                    candidate_road:candidate_road_bytes,
                    decoded_road,
                    journey_input:original_input_journey_bytes,
                    journey_old:old_journey_bytes,
                    journey_new:new_journey_bytes,
                    journey_decoded:decoded_journey,
                    event_input:input_event_bytes,
                    event_current:effective_current_event,
                    event_candidate:candidate_event_bytes,
                    validation_scratch:scratch,
                    call_binding_reserve,
                    road_decode_scratch,
                };
                let (_,source_arc_credit,candidate_arc_credit)=
                    road.source_joint_road_owner_charge(
                        &road_candidate,input_road_bytes,original_input_road_shared
                    );
                let source_old_journey=match (
                    original_input_journey,journey.deferred_previous.as_ref(),
                ){
                    (Some(input),Some((old,_,_,_,_)))=>
                        journey_shared_stage_payload_census(input,old),
                    _=>JourneyStageArcOverlap::default(),
                };
                let old_new_journey=journey.deferred_previous.as_ref().map_or(
                    JourneyStageArcOverlap::default(),
                    |(old,_,_,_,_)|journey_shared_stage_payload_census(old,&journey.state),
                );
                let exact_census_scratch=source_old_journey.temporary_census_scratch_bytes
                    .max(old_new_journey.temporary_census_scratch_bytes);
                let source_required=checkpointability_current_source_candidate_bytes(
                    lifetime,source_arc_credit,candidate_arc_credit,
                    source_old_journey.shared_payload_bytes,
                    old_new_journey.shared_payload_bytes,
                    exact_census_scratch,
                );
                let fresh_road_decode=checkpointability_fresh_road_decode_bytes(lifetime);
                let fresh_bundle=checkpointability_fresh_bundle_bytes(
                    lifetime,fresh_initial_road_bytes,decoded_event_upper);
                let fresh_journey_validation=checkpointability_fresh_journey_validation_bytes(
                    lifetime,fresh_initial_road_bytes,decoded_event_upper);
                let required=source_required.max(fresh_road_decode)
                    .max(fresh_journey_validation).max(fresh_bundle);
                let observed = crate::v1_trace::guard(
                    "journey_commit",
                    "checkpointability",
                    required,
                    total,
                    &[
                        ("input_road", input_road_bytes),
                        ("current_road", current_road_bytes),
                        ("candidate_road", candidate_road_bytes),
                        ("source_input_verified_shared_road_arcs",source_arc_credit),
                        ("committed_candidate_verified_shared_road_arcs",candidate_arc_credit),
                        ("source_old_verified_shared_stage_arc_payload",source_old_journey.shared_payload_bytes),
                        ("old_candidate_verified_shared_stage_arc_payload",old_new_journey.shared_payload_bytes),
                        ("stage_census_actual_scratch",exact_census_scratch),
                        ("decoded_road", decoded_road),
                        ("journey_retained_input", journey.retained_input_bytes),
                        ("journey_original_input_actual", original_input_journey_bytes),
                        ("old_journey", old_journey_bytes),
                        ("new_journey", new_journey_bytes),
                        ("decoded_journey", decoded_journey),
                        ("input_event", input_event_bytes),
                        ("current_event", current_event_bytes),
                        ("current_event_charged", effective_current_event),
                        ("old_event_arc_pointer_identical",usize::from(old_event_arc_shared)),
                        ("candidate_event", candidate_event_bytes),
                        ("candidate_event_with_decode_upper", decoded_event_upper),
                        ("current_source_candidate_phase",source_required),
                        ("fresh_engine_road_decode_phase",fresh_road_decode),
                        ("fresh_engine_journey_validation_phase",fresh_journey_validation),
                        ("fresh_engine_bundle_phase",fresh_bundle),
                        ("fresh_constructor_current_road",fresh_initial_road_bytes),
                        ("future_road_decode_phase",checkpointability_sequential_decode_phases(lifetime).0),
                        ("future_journey_validation_phase",checkpointability_sequential_decode_phases(lifetime).1),
                        ("validation_scratch", scratch),
                        ("call_binding_reserve", call_binding_reserve),
                        ("road_decode_scratch", road_decode_scratch),
                        ("phase_road_charge", input_road_bytes
                            .saturating_add(current_road_bytes)
                            .saturating_add(candidate_road_bytes.max(decoded_road))),
                        ("phase_journey_charge",original_input_journey_bytes
                            .saturating_add(old_journey_bytes)
                            .saturating_add(new_journey_bytes.max(decoded_journey))),
                        ("phase_event_charge",input_event_bytes
                            .saturating_add(effective_current_event)
                            .saturating_add(candidate_event_bytes)),
                    ],
                );
                if required > total && !observed {
                    return Err(PyMemoryError::new_err(format!(
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
#[pymethods]
impl NativeJourneyCore {
    #[new]
    fn new(
        legs: Vec<JourneyLeg>,
        bus: Vec<BusMeta>,
        freight: Vec<FreightMeta>,
        record_budget: usize,
    ) -> PyResult<Self> {
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
    /// Inspection only: immutable static heap, one dense state, stage/history.
    fn storage_accounting(&self) -> (usize, usize, usize) {
        (
            self.static_storage_bytes(),
            journey_dense_storage_bytes(&self.state),
            journey_storage_bytes(&self.state),
        )
    }
    fn decoded_storage_upper_bytes(&self) -> usize {
        stage_decoded_storage_upper_bytes(&self.state)
            .saturating_add(self.history_decoded_final)
            .saturating_add(self.history_decode_extra_max)
    }
    fn advance_metrics(&self) -> (Vec<f64>, usize) {
        (self.tick_times_s.clone(), self.peak_records)
    }
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
    fn restore(&mut self, row: JourneyRow) -> PyResult<()> {
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
    fn abort(&mut self) {
        self.rollback_deferred_finish();
        self.pending = None;
        self.phase("aborted");
    }
    fn prepare(&mut self) -> PyResult<(Vec<Offer>, Vec<bool>)> {
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
                let hi = fraction(&l.4, t).min(eligible(&self.legs, &self.state, i));
                if hi <= lo {
                    continue;
                }
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
        );
        check_storage_limit(
            self.storage_budget,
            self.retained_input_bytes,
            stage_storage_bytes(&s).saturating_add(self.history_bytes),
            scratch,
        )?;
        let attempt = self.last_attempt.as_mut().unwrap();
        for (i, mass, born, hold) in proposals.into_iter().flatten() {
            let l = &self.legs[i];
            s.4[i] += mass;
            s.7[i] += mass * born;
            let stage = if l.5 == 2 { 2 } else { 0 };
            let all_stages = stage_storage_bytes(&s);
            let target = if stage == 2 { &mut s.3 } else { &mut s.1 };
            let projected = self
                .history_bytes
                .saturating_add(all_stages - target.storage_bytes())
                .saturating_add(target.append_upper_bytes(l.6.len()));
            check_storage_limit(
                self.storage_budget,
                self.retained_input_bytes,
                projected,
                scratch,
            )?;
            attempt.generated[stage] += l.6.len();
            target.extend(l.6.iter().map(|w| (i, mass * w.1, born, w.0 + hold)));
        }
        let mut offers = Vec::new();
        s.1.retire_due(t + 1e-10, |a| {
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
    ) -> PyResult<()> {
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
        for e in events {
            if !nonnegative([e.1, e.2]) || e.2 > end + 1e-8 {
                return Err(bad("invalid native journey road sink"));
            }
            if let Some(&i) = self.route_indices.get(&e.0) {
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
        let mut retired = [0usize; 2];
        let before_retirement_bytes = stage_storage_bytes(&s);
        let mut history_bytes = self.history_bytes;
        let mut history_decoded_final = self.history_decoded_final;
        let mut history_decode_extra_max = self.history_decode_extra_max;
        for (kind, stage) in [&mut s.2, &mut s.3].into_iter().enumerate() {
            let mut receipt_error = None;
            retired[kind] = stage.retire_due(end + 1e-10, |a| {
                if receipt_error.is_some() {
                    return;
                }
                let history = &mut s.6[a.0];
                let previous_bytes = history.storage_bytes();
                let previous_decoded = history.decoded_final_storage_upper_bytes();
                let projected = before_retirement_bytes
                    .saturating_add(history_bytes - previous_bytes)
                    .saturating_add(history.append_upper_bytes());
                if let Err(error) = check_storage_limit(
                    self.storage_budget,
                    self.retained_input_bytes,
                    projected,
                    0,
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
        s.0 = end;
        if let Some(attempt) = &mut self.last_attempt {
            attempt.generated[1] = generated_egress;
            attempt.retired[1] = retired[0];
            attempt.retired[2] = retired[1];
            attempt.receipts_added = added;
            attempt.candidate = [s.1.len(), s.2.len(), s.3.len(), self.history_rows + added];
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
        self.history_rows += added;
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
    pub(crate) fn new_shared(
        legs: Vec<SharedJourneyLeg>,
        bus: Vec<SharedBusMeta>,
        freight: Vec<SharedFreightMeta>,
        record_budget: usize,
    ) -> PyResult<Self> {
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

    fn fixture() -> NativeServiceCore {
        NativeServiceCore {
            buses: vec![], people: vec![], freight: vec![], cars: vec![],
            people_by_run: vec![],
            last_events: Arc::new(event_fixture(vec![
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
        core.last_events = Arc::new(event_fixture(vec![(9, 3, None, 0.5, 102., 103., 3.75)]));
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
            input_road:545136024,current_road:545136024,
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
mod surgical_service_finish_concrete_lifetimes_tests {
    use super::*;
    #[test]
    fn real_100k_service_finish_charges_three_concrete_owners_not_three_new_ones() {
        let old_road=630_653_248usize;
        let current_road=630_653_248usize;
        let candidate_road=877_913_216usize;
        let old_events=461_832_224usize;
        let current_events=461_832_224usize;
        let candidate_events=1_115_458_368usize;
        let physical_road=three_concrete_owner_bytes(
            old_road,current_road,candidate_road);
        let physical_events=three_concrete_owner_bytes(
            old_events,current_events,candidate_events);
        assert_eq!(physical_road,2_139_219_712);
        assert_eq!(physical_events,2_039_122_816);
        let conservative_previous=3*candidate_road+3*candidate_events;
        let newly_sourced=physical_road+physical_events;
        assert!(conservative_previous>newly_sourced);
        assert_eq!(conservative_previous-newly_sourced,1_801_772_224);
        let source_budget=5_789_366_871usize;
        // Fixed 100k observed journey + sink + original policy scratch:
        let new_required=764_152_296+newly_sourced+155_233_792+65_536;
        assert_eq!(new_required,5_097_794_152);
        assert!(new_required<source_budget);
        assert!(6_899_566_376>source_budget);
    }
    #[test]
    fn every_distinct_owner_stays_charged_even_if_source_values_equal() {
        assert_eq!(three_concrete_owner_bytes(5,5,5),15);
        assert_eq!(three_concrete_owner_bytes(7,0,19),26);
        assert_eq!(three_concrete_owner_bytes(0,0,0),0);
    }
}

#[cfg(test)]
mod surgical_service_arc_alias_identity_tests_20261122 {
    use super::*;
    use std::sync::Arc;
    #[test]
    fn physical_event_arc_identity_removes_one_duplicate_old_allocation_only_if_shared() {
        let owner=Arc::new(vec![(3usize,1usize,None::<usize>,0.5,20.,21.,3.)]);
        let call_input=Arc::clone(&owner);
        let distinct=Arc::new((*owner).clone());
        assert!(Arc::ptr_eq(&call_input,&owner));
        assert!(!Arc::ptr_eq(&call_input,&distinct));
        let previous=923_664_448usize;
        let new=1_115_458_368usize;
        let shared=concrete_service_event_owner_bytes(
            previous,previous,new,Arc::ptr_eq(&call_input,&owner)
        );
        assert_eq!(shared,previous+new);
        assert_eq!(shared,2_039_122_816);
        let unshared=concrete_service_event_owner_bytes(
            previous,previous,new,Arc::ptr_eq(&call_input,&distinct)
        );
        assert_eq!(unshared,2*previous+new);
        assert_eq!(unshared-shared,previous);
    }
    #[test]
    fn source_recalculated_service_finish_is_under_original_unchanged_allowance() {
        let road=three_concrete_owner_bytes(630_653_248,630_653_248,877_913_216);
        let events=concrete_service_event_owner_bytes(
            923_664_448,923_664_448,1_115_458_368,true);
        let revised=road+events+764_152_296+155_233_792+65_536;
        assert_eq!(revised,5_097_794_152);
        assert!(revised<5_789_366_871);
        assert!(revised<6_021_458_856);
    }
}

#[cfg(test)]
mod surgical_checkpointability_shared_event_source_20261122_tests {
    use super::*;
    #[test]
    fn actual_original_100k_checkpoint_decode_and_candidate_never_charge_same_old_arc_twice() {
        let mut c=CheckpointabilityTerms {
            input_road:630_653_248,current_road:630_653_248,
            candidate_road:877_913_216,decoded_road:877_956_416,
            journey_input:249_753_000,journey_old:249_753_000,
            journey_new:285_239_408,journey_decoded:288_818_456,
            event_input:923_664_576,event_current:923_664_576,
            event_candidate:1_115_458_368,
            validation_scratch:411_841_968,call_binding_reserve:82_704_900,
            road_decode_scratch:675_148_032,
        };
        let old=checkpointability_phase_lifetime_bytes(c);
        assert_eq!(old,6_565_522_920);
        c.event_current=verified_current_event_bytes_with_input_arc(
            c.event_input,c.event_current,true);
        let new=checkpointability_phase_lifetime_bytes(c);
        assert_eq!(new,5_641_858_344);
        assert_eq!(old-new,923_664_576);
        assert!(new<5_789_366_871);
    }
    #[test]
    fn a_nonidentical_current_event_arc_still_occupies_all_its_bytes() {
        assert_eq!(verified_current_event_bytes_with_input_arc(17,19,false),19);
        assert_eq!(verified_current_event_bytes_with_input_arc(0,0,true),0);
    }
}

#[cfg(test)]
mod v03_source_decoder_two_live_owners_r5_20261122_tests {
    use super::*;
    #[test]
    fn original_100k_journey_replay_does_not_triplicate_a_single_decoder() {
        let decoded=75_390_656usize;
        let phase_cap=226_233_207usize;
        assert!(check_storage_limit(Some(phase_cap),0,decoded,0).is_err());
        assert!(check_journey_decode_source_limit(Some(phase_cap),0,decoded).is_ok());
    }
    #[test]
    fn source_decoder_still_checks_real_old_plus_new_with_original_scratch() {
        let old=100usize;
        let new=500usize;
        let exact=STORAGE_SCRATCH_RESERVE+old+new;
        assert!(check_journey_decode_source_limit(Some(exact),old,new).is_ok());
        assert!(check_journey_decode_source_limit(Some(exact-1),old,new).is_err());
        assert!(check_journey_decode_source_limit(Some(exact-1),0,new).is_ok());
        assert!(check_journey_decode_source_limit(None,old,new).is_ok());
    }
}

#[cfg(test)]
mod v03_joint_checkpointability_exact_arc_lifetimes_20261122_tests {
    use super::*;
    fn base()->CheckpointabilityTerms {
        CheckpointabilityTerms {
            input_road:100,current_road:100,candidate_road:150,decoded_road:160,
            journey_input:20,journey_old:20,journey_new:30,journey_decoded:50,
            event_input:40,event_current:0,event_candidate:60,
            validation_scratch:70,call_binding_reserve:0,road_decode_scratch:80,
        }
    }
    #[test]
    fn both_independent_candidate_and_future_decoder_are_never_same_live_owner() {
        let t=base();
        let ordinary=checkpointability_phase_lifetime_bytes(t);
        let exact=checkpointability_source_road_arc_lifetimes(t,40,20);
        assert_eq!(ordinary-exact,40);
        assert_eq!(exact,ordinary-(t.input_road+t.current_road+
            t.candidate_road.max(t.decoded_road))+320);
        assert_eq!(checkpointability_source_road_arc_lifetimes(t,0,0),ordinary);
    }
    #[test]
    fn current_candidate_overlap_is_not_credited_to_independent_future_decoder() {
        let mut t=base();t.candidate_road=200;
        let old=checkpointability_phase_lifetime_bytes(t);
        let corrected=checkpointability_source_road_arc_lifetimes(t,40,80);
        let real_future_road=t.input_road+t.current_road+t.decoded_road-40;
        let real_candidate_road=t.input_road+t.current_road+t.candidate_road-40-80;
        assert_eq!(real_future_road,320);
        assert_eq!(real_candidate_road,280);
        assert_eq!(old-corrected,80);
        assert!(checkpointability_source_road_arc_lifetimes(t,0,0)>=corrected);
    }
}

#[cfg(test)]
mod v03_immutable_journey_block_source_identity_20261122_tests {
    use super::*;
    fn journey()->Journey {
        let mut q=StageQueue::new();
        for i in 0..750 {
            q.push((i%3,1.0,i as f64,FIXTURE_DURATION));
        }
        (0.,q,StageQueue::new(),StageQueue::new(),
         Vec::new(),Vec::new(),Vec::new(),Vec::new())
    }
    const FIXTURE_DURATION:f64=4.0;

    #[test]
    fn actual_arc_block_clone_witnesses_payload_share_but_independent_values_do_not() {
        let input=journey();
        let old=input.clone();
        let separate=journey();
        let a=journey_shared_stage_payload_census(&input,&old);
        assert!(a.shared_payload_bytes>0);
        assert!(a.shared_payload_bytes<input.1.storage_bytes());
        assert!(a.shared_payload_bytes<old.1.storage_bytes());
        // Vec<Arc<Block>> registry capacities are independently owned,
        // and Clone may tighten the handle Vec capacity; do not equate them.
        assert!(input.1.storage_bytes()!=a.shared_payload_bytes);
        assert!(old.1.storage_bytes()!=a.shared_payload_bytes);
        let b=journey_shared_stage_payload_census(&input,&separate);
        assert_eq!(b.shared_payload_bytes,0);
        assert!(a.temporary_census_scratch_bytes>0);
        assert!(a.temporary_census_scratch_bytes<1024*1024);
    }

    #[test]
    fn moving_one_immutable_block_across_route_stage_still_counts_once() {
        let a=journey();
        let mut b=a.clone();
        // Reassign a shared block owner from one stage index to another;
        // source ordered rows are unchanged for the purpose of this audit.
        b.2=b.1.clone();
        b.1=StageQueue::new();
        let c=journey_shared_stage_payload_census(&a,&b);
        assert!(c.shared_payload_bytes>0);
        assert_eq!(c.shared_payload_bytes,
            journey_shared_stage_payload_census(&a,&a).shared_payload_bytes);
    }

    #[test]
    fn coupled_candidate_vs_future_decode_phase_max_does_not_sum_two_peaks() {
        let t=CheckpointabilityTerms{
            input_road:100,current_road:100,
            candidate_road:400,decoded_road:100,
            journey_input:100,journey_old:100,
            journey_new:100,journey_decoded:400,
            event_input:100,event_current:0,event_candidate:100,
            validation_scratch:120000,call_binding_reserve:0,
            road_decode_scratch:180000,
        };
        let generic=checkpointability_source_road_arc_lifetimes(t,0,0);
        let x=checkpointability_source_joint_phase_bytes(t,0,0,0,0,0);
        assert!(x<generic);
        let y=checkpointability_source_joint_phase_bytes(t,50,30,20,10,200);
        assert!(y<=x+200);
        assert_eq!(checkpointability_source_joint_phase_bytes(t,0,0,0,0,0),x);
    }
}

#[cfg(test)]
mod persistent_service_event_storage_20261123_tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn checkpoint_decode_retains_event_payload_below_flat_64_byte_rows() {
        let n=8193usize;
        let mut source=NativeServiceCore::new(vec![],vec![],vec![],vec![]).unwrap();
        source.last_events=Arc::new(event_fixture((0..n).map(|i|
            (i%11,i%7,if i%3==0 {None} else {Some(i%5)},1.25,2.,3.,0.5)
        ).collect()));
        let mut wire=Vec::new();
        source.write_state(&mut wire).unwrap();
        let decoded=source.read_state(&mut Cursor::new(&wire),n,true).unwrap();
        let retained=service_event_storage_bytes(&decoded);
        assert!(retained<n*56,
            "persistent service event payload still flat: retained={retained}, rows={n}");
        let mut restored=NativeServiceCore::new(vec![],vec![],vec![],vec![]).unwrap();
        restored.install_state(decoded);
        let mut roundtrip=Vec::new();
        restored.write_state(&mut roundtrip).unwrap();
        assert_eq!(wire,roundtrip);
    }
}


#[cfg(test)]
fn event_fixture(rows:Vec<EventRow>)->ChunkedEvents {
    let n=rows.len();
    let mut store=ChunkedEvents::new(true);
    for row in rows {store.push_decoded_checked(row,n).unwrap();}
    store
}


#[cfg(test)]
mod v03_road_phase_journey_source_census_20261123_tests {
    use super::*;

    fn source(rows:usize)->Journey {
        let mut queue=StageQueue::new();
        for i in 0..rows {queue.push((i%3,1.,i as f64,4.));}
        (1000.,queue,StageQueue::new(),StageQueue::new(),
         vec![1.;3],vec![0.;3],
         vec![ReceiptHistory::from_rows(vec![(0.,1.)]).unwrap()],vec![0.;3])
    }
    fn owner_charge(
        input:&Journey,current:&Journey,pending:&Journey,other:usize,cap:usize,
    )->PyResult<RoadPhaseJourneyOwners> {
        road_phase_journey_owner_bytes(
            Some(input),current,Some(pending),
            journey_storage_bytes(input),journey_storage_bytes(current),
            journey_storage_bytes(pending),other,cap,
        )
    }

    #[test]
    fn three_live_aliases_remove_two_payload_copies_but_keep_all_history_and_shells() {
        let input=source(750);
        let current=input.clone();
        let pending=current.clone();
        let expected_payload=input.1.capacity()*std::mem::size_of::<Access>();
        let uncredited=journey_storage_bytes(&input)+journey_storage_bytes(&current)
            +journey_storage_bytes(&pending);
        let result=owner_charge(&input,&current,&pending,123,usize::MAX).unwrap();
        assert_eq!(result.uncredited_bytes,uncredited);
        assert_eq!(result.input_current_payload_credit,expected_payload);
        assert_eq!(result.current_pending_payload_credit,expected_payload);
        assert_eq!(result.charged_bytes,uncredited-2*expected_payload);
        let history=input.6.iter().map(ReceiptHistory::storage_bytes).sum::<usize>();
        assert!(history>0);
        assert!(result.charged_bytes>expected_payload+3*history);
        assert!(result.census_actual_scratch_bytes>0);
        assert!(result.census_actual_scratch_bytes<=result.census_scratch_upper_bytes);
        // Census borrows only: no producer rows, clocks or dense buffers mutate.
        assert_eq!(input.1.to_vec(),current.1.to_vec());
        assert_eq!(current.1.to_vec(),pending.1.to_vec());
        assert_eq!(input.4,pending.4);
        assert_eq!(input.0,pending.0);
    }

    #[test]
    fn independent_equal_values_receive_no_stage_payload_credit() {
        let input=source(750);
        let current=source(750);
        let pending=source(750);
        assert_eq!(input.1.to_vec(),current.1.to_vec());
        let result=owner_charge(&input,&current,&pending,0,usize::MAX).unwrap();
        assert_eq!(result.input_current_payload_credit,0);
        assert_eq!(result.current_pending_payload_credit,0);
        assert_eq!(result.charged_bytes,result.uncredited_bytes);
    }

    #[test]
    fn copied_tail_is_independent_while_shared_full_blocks_keep_exact_credit() {
        let input=source(750);
        let current=input.clone();
        let mut pending=current.clone();
        pending.1.push((0,1.,750.,4.));
        let result=owner_charge(&input,&current,&pending,0,usize::MAX).unwrap();
        assert_eq!(result.input_current_payload_credit,
                   input.1.capacity()*std::mem::size_of::<Access>());
        // Two full 256-row blocks stay shared; the mutable tail is copied.
        assert_eq!(result.current_pending_payload_credit,
                   2*256*std::mem::size_of::<Access>());
        assert!(result.current_pending_payload_credit<result.input_current_payload_credit);
    }

    #[test]
    fn missing_original_reference_keeps_three_max_without_census_allocation() {
        let current=source(750);
        let pending=current.clone();
        let bytes=journey_storage_bytes(&current);
        let result=road_phase_journey_owner_bytes(
            None,&current,Some(&pending),bytes+17,bytes,
            journey_storage_bytes(&pending),0,usize::MAX,
        ).unwrap();
        assert_eq!(result.charged_bytes,3*(bytes+17));
        assert_eq!(result.input_current_payload_credit,0);
        assert_eq!(result.current_pending_payload_credit,0);
        assert_eq!(result.census_scratch_upper_bytes,0);
        assert_eq!(result.census_actual_scratch_bytes,0);
    }

    #[test]
    fn preproposal_source_road_credit_needs_the_unexpired_original_clock() {
        assert_eq!(preproposal_road_source_owner_bytes(100,150,10.,Some((10.,90))),
                   (160,90));
        assert_eq!(preproposal_road_source_owner_bytes(100,150,20.,Some((10.,90))),
                   (250,0));
        assert_eq!(preproposal_road_source_owner_bytes(100,100,10.,None),(200,0));
        assert_eq!(preproposal_road_source_owner_bytes(100,150,10.,Some((10.,999))),
                   (150,100));
    }

    #[test]
    fn census_preflight_charges_uncredited_sources_offers_and_scratch_before_credit() {
        let input=source(750);
        let current=input.clone();
        let pending=current.clone();
        let offers=Vec::<crate::v1_road::Offer>::with_capacity(4);
        let offers_bytes=vec_storage_bytes(&offers);
        assert!(offers_bytes>0); // Actual retained capacity, even at length zero.
        let (road_live,_)=preproposal_road_source_owner_bytes(100,150,10.,Some((10.,90)));
        let events=concrete_service_event_owner_bytes(80,80,0,true);
        let other=road_live+events+offers_bytes;
        let uncredited=journey_storage_bytes(&input)+journey_storage_bytes(&current)
            +journey_storage_bytes(&pending);
        let scratch=stage_census_scratch_upper_bytes(&input)
            .max(stage_census_scratch_upper_bytes(&current));
        let exact=other+uncredited+scratch+STORAGE_SCRATCH_RESERVE;
        assert!(owner_charge(&input,&current,&pending,other,exact).is_ok());
        assert!(owner_charge(&input,&current,&pending,other,exact-1).is_err());
        assert!(owner_charge(&input,&current,&pending,other+1,exact).is_err());
        // Proven sharing cannot be borrowed to fund the census that proves it.
        let payload=input.1.capacity()*std::mem::size_of::<Access>();
        assert!(owner_charge(&input,&current,&pending,other,exact-payload).is_err());
    }

    #[test]
    fn actual_census_capacity_is_checked_and_sequential_scratch_is_a_max() {
        let input=source(3*256);
        let current=source(17*256);
        let pending=current.clone();
        let first=journey_shared_stage_payload_census(&input,&current);
        let second=journey_shared_stage_payload_census(&current,&pending);
        let result=owner_charge(&input,&current,&pending,0,usize::MAX).unwrap();
        assert_eq!(result.census_actual_scratch_bytes,
                   first.temporary_census_scratch_bytes.max(second.temporary_census_scratch_bytes));
        assert!(result.census_actual_scratch_bytes<
                first.temporary_census_scratch_bytes+second.temporary_census_scratch_bytes);
        let upper=result.census_scratch_upper_bytes;
        assert!(check_stage_census_actual_scratch(upper,upper).is_ok());
        assert!(check_stage_census_actual_scratch(upper+1,upper).is_err());
        for blocks in [0usize,1,2,3,4,7,8,15,16,31,32,63,64] {
            let value=source(blocks*256);
            let copied=value.clone();
            let actual=journey_shared_stage_payload_census(&value,&copied);
            let table_upper=stage_census_table_upper_bytes(&value);
            if blocks==1 {
                println!("C8B_SINGLE_BLOCK_CENSUS actual_bytes={} table_upper_bytes={table_upper}",
                         actual.temporary_census_scratch_bytes);
            }
            assert!(check_stage_census_actual_scratch(
                actual.temporary_census_scratch_bytes,table_upper,
            ).is_ok(),"block_count={blocks}, actual_bytes={}, table_upper_bytes={table_upper}",
                      actual.temporary_census_scratch_bytes);
        }
    }
}


#[cfg(test)]
mod v03_checkpoint_decoder_sequential_lifetimes_20261123_tests {
    use super::*;

    fn frozen_48_byte_trace()->CheckpointabilityTerms {
        CheckpointabilityTerms{
            input_road:865_303_248,current_road:865_303_248,
            candidate_road:1_209_931_840,decoded_road:1_209_974_272,
            journey_input:302_233_568,journey_old:302_233_568,
            journey_new:348_545_776,journey_decoded:354_019_848,
            event_input:973_795_992,event_current:0,
            // The trace prints retained 1_168_612_200, but production takes
            // max(retained, canonical decode upper). The old 48-byte formula
            // at 24_322_678 rows gives this effective 1_168_677_032.
            event_candidate:1_168_677_032,
            validation_scratch:459_527_536,call_binding_reserve:82_704_900,
            road_decode_scratch:936_563_136,
        }
    }
    fn fixed_sources(t:CheckpointabilityTerms)->usize {
        t.input_road+t.current_road-794_297_808
            +t.journey_input+t.journey_old-242_069_504
            +t.event_input+t.event_current+t.event_candidate
    }
    fn assessed(t:CheckpointabilityTerms)->usize {
        checkpointability_source_joint_phase_bytes(
            t,794_297_808,536_987_368,242_069_504,192_962_560,1_949_824)
    }

    #[test]
    fn actual_48_byte_failure_trace_retains_actual_input_registry_and_all_validation() {
        let mut t=frozen_48_byte_trace();
        let rows=24_322_678usize;
        let pages=rows.div_ceil(4096);
        assert_eq!(360+rows*48+pages*128+(pages+1)*72+256,t.event_candidate);
        let combined=fixed_sources(t)+t.decoded_road+t.journey_decoded
            +t.road_decode_scratch+1_949_824;
        assert_eq!(combined,5_943_686_424); // Preserved actual R8b failure.
        let before_registry_correction=assessed(t);
        assert_eq!(before_registry_correction,5_589_666_576);
        t.journey_input=302_394_480; // Actual original snapshot, not clone capacity.
        let revised=assessed(t);
        assert_eq!(revised-before_registry_correction,160_912);
        assert_eq!(revised,5_589_827_488);
        assert_eq!(5_789_366_831-revised,199_539_343);
        // This is replay of frozen old-48B terms, not a new 40B physical run.
    }

    #[test]
    fn later_decoded_bundle_validation_can_dominate_and_must_not_be_omitted() {
        let mut t=frozen_48_byte_trace();
        t.validation_scratch=2_000_000_000;
        t.call_binding_reserve=0;
        t.journey_decoded=600_000_000;
        t.road_decode_scratch=100_000;
        let actual_late_phase=t.decoded_road+t.journey_decoded+t.validation_scratch;
        let required=assessed(t);
        assert_eq!(required,fixed_sources(t)+actual_late_phase+1_949_824);
    }

    #[test]
    fn independent_decoder_bytes_remain_charged_and_cap_plus_one_is_rejected() {
        let mut t=frozen_48_byte_trace();
        t.journey_input=302_394_480;
        let cap=assessed(t);
        let without_candidate_credits=checkpointability_source_joint_phase_bytes(
            t,794_297_808,0,242_069_504,0,1_949_824);
        // Road decoding dominates; a not-yet-created independent decoder
        // cannot borrow the real current/candidate payload aliases.
        assert_eq!(without_candidate_credits,cap);
        t.input_road+=1;
        assert_eq!(assessed(t),cap+1);
        assert!(assessed(t)>cap);
    }

    #[test]
    fn existing_joint_candidate_phase_is_kept_when_it_is_the_largest_peak() {
        let mut t=frozen_48_byte_trace();
        t.candidate_road=4_000_000_000;
        let current_peak=t.candidate_road-536_987_368
            +t.journey_new-192_962_560
            +(t.validation_scratch-t.call_binding_reserve).max(STORAGE_SCRATCH_RESERVE);
        assert_eq!(assessed(t),fixed_sources(t)+current_peak+1_949_824);
    }
}

#[cfg(test)]
mod v03_checkpoint_fresh_decode_20261123_tests {
    use super::*;

    #[test]
    fn fresh_road_phase_keeps_three_owner_fallback_and_only_constructor_events() {
        assert_eq!(StageQueue::new().storage_bytes(),0);
        assert_eq!(ReceiptHistory::new().storage_bytes(),0);
        let shell=ChunkedEvents::default().storage_bytes();
        let mut t=CheckpointabilityTerms {
            input_road:0,current_road:0,candidate_road:0,decoded_road:1_000_000,
            journey_input:0,journey_old:0,journey_new:0,journey_decoded:0,
            event_input:0,event_current:0,event_candidate:0,
            validation_scratch:0,call_binding_reserve:0,road_decode_scratch:128,
        };
        assert_eq!(checkpointability_fresh_road_decode_bytes(t),
            3_000_000+STORAGE_SCRATCH_RESERVE+shell);
        t.journey_decoded=4_000_000;
        t.event_candidate=8_000_000;
        t.validation_scratch=2_000_000;
        assert_eq!(checkpointability_fresh_road_decode_bytes(t),
            3_000_000+STORAGE_SCRATCH_RESERVE+shell,
            "future Journey/events are absent during road decode");
        assert_eq!(checkpointability_sequential_decode_phases(t).1,7_000_000,
            "later independent Journey plus whole validation is still charged");
    }

    #[test]
    fn fresh_bundle_keeps_every_decoded_owner_and_constructor_current_road() {
        let t=CheckpointabilityTerms {
            input_road:900,current_road:800,candidate_road:700,decoded_road:600,
            journey_input:50,journey_old:40,journey_new:30,journey_decoded:20,
            event_input:90,event_current:80,event_candidate:70,
            validation_scratch:100_000,call_binding_reserve:1_000,road_decode_scratch:200_000,
        };
        let shell=ChunkedEvents::default().storage_bytes();
        let initial=123usize;
        let event_decode=456usize;
        assert_eq!(checkpointability_fresh_bundle_bytes(t,initial,event_decode),
            initial+shell+600+event_decode+20+99_000);
        assert_eq!(checkpointability_fresh_bundle_bytes(t,initial,event_decode+1),
            checkpointability_fresh_bundle_bytes(t,initial,event_decode)+1);
        let mut later=t;
        later.journey_decoded+=1;
        assert_eq!(checkpointability_fresh_bundle_bytes(later,initial,event_decode),
            checkpointability_fresh_bundle_bytes(t,initial,event_decode)+1);
        later.validation_scratch+=1;
        assert_eq!(checkpointability_fresh_bundle_bytes(later,initial,event_decode),
            checkpointability_fresh_bundle_bytes(t,initial,event_decode)+2);
        later.road_decode_scratch=usize::MAX;
        assert_eq!(checkpointability_fresh_bundle_bytes(later,initial,event_decode),
            checkpointability_fresh_bundle_bytes(t,initial,event_decode)+2,
            "road scratch has already died before the decoded Bundle exists");
    }

    #[test]
    fn current_transition_uses_actual_events_and_never_borrows_future_sharing() {
        let mut t=CheckpointabilityTerms {
            input_road:900,current_road:800,candidate_road:700,decoded_road:600,
            journey_input:50,journey_old:40,journey_new:30,journey_decoded:20,
            event_input:90,event_current:80,event_candidate:70,
            validation_scratch:100_000,call_binding_reserve:1_000,road_decode_scratch:200_000,
        };
        let current=checkpointability_current_source_candidate_bytes(t,400,300,20,10,17);
        assert_eq!(current,900+800+700-400-300+50+40+30-20-10+90+80+70+99_000+17);
        t.decoded_road=usize::MAX;
        t.journey_decoded=usize::MAX;
        t.road_decode_scratch=usize::MAX;
        assert_eq!(checkpointability_current_source_candidate_bytes(t,400,300,20,10,17),current);
        t.event_candidate+=1;
        assert_eq!(checkpointability_current_source_candidate_bytes(t,400,300,20,10,17),current+1);
    }
}

#[cfg(test)]
mod v03_checkpoint_journey_validator_closure_20261123_tests {
    use super::*;
    use std::io::Cursor;

    fn empty()->NativeJourneyCore {
        NativeJourneyCore::new_shared(vec![(
            "receipt-leg".into(),1.0,None,0.0,
            Arc::new(vec![(0.0,1.0,1.0)]),0,Arc::new(vec![]),Arc::new(vec![]),
        )],vec![],vec![],100_000).unwrap()
    }
    fn terms(decoded:usize)->CheckpointabilityTerms {
        CheckpointabilityTerms {
            input_road:0,current_road:0,candidate_road:0,decoded_road:decoded,
            journey_input:0,journey_old:0,journey_new:0,journey_decoded:decoded,
            event_input:0,event_current:0,event_candidate:0,
            validation_scratch:STORAGE_SCRATCH_RESERVE,
            call_binding_reserve:0,road_decode_scratch:0,
        }
    }

    #[test]
    fn fresh_journey_validator_keeps_the_omitted_three_owner_floor() {
        let t=terms(1_000_000);
        let shell=ChunkedEvents::default().storage_bytes();
        let before=checkpointability_fresh_road_decode_bytes(t)
            .max(checkpointability_fresh_bundle_bytes(t,0,1_000_000));
        let required=checkpointability_fresh_journey_validation_bytes(t,0,1_000_000);
        assert_eq!(before,3_000_000+STORAGE_SCRATCH_RESERVE+shell);
        assert_eq!(required,5_000_000+STORAGE_SCRATCH_RESERVE+shell);
        assert!(required>before);
    }

    #[test]
    fn actual_fresh_journey_read_rejects_old_allowance_and_accepts_full_validator_phase() {
        pyo3::prepare_freethreaded_python();
        let mut source=empty();
        source.state.0=1.0;
        source.state.4[0]=1.0;
        source.state.5[0]=1.0;
        source.state.7[0]=0.5;
        for _ in 0..4096 {source.state.6[0].push((1.0,1.0/4096.0)).unwrap();}
        source.validate(&source.state).unwrap();
        let mut wire=Vec::new();
        source.write_state(&mut wire).unwrap();
        let mut target=empty();
        let independent=target.read_state(&mut Cursor::new(&wire)).unwrap();
        let actual=journey_storage_bytes(&independent);
        let upper=journey_decoded_storage_upper_bytes(&source.state);
        assert!(upper>=actual);
        let t=terms(upper);
        let shell=ChunkedEvents::default().storage_bytes();
        let other=2*upper+shell;
        let previous=checkpointability_fresh_road_decode_bytes(t)
            .max(checkpointability_fresh_bundle_bytes(t,0,upper));
        let old_allowance=previous-other;
        let actual_validator=actual*WORKING_COPIES+STORAGE_SCRATCH_RESERVE;
        assert!(old_allowance<actual_validator,
            "fixture must reach the omitted local validator: actual={actual}, upper={upper}");
        target.set_phase_storage_budget(old_allowance).unwrap();
        let error=target.read_state(&mut Cursor::new(&wire)).err().unwrap().to_string();
        assert!(error.contains("native journey stored/working byte budget"),"{error}");
        assert_eq!(journey_storage_bytes(&target.state),0);
        let full=checkpointability_fresh_journey_validation_bytes(t,0,upper);
        let corrected_allowance=full-other;
        assert!(corrected_allowance>=actual_validator);
        target.set_phase_storage_budget(corrected_allowance).unwrap();
        target.state=target.read_state(&mut Cursor::new(&wire)).unwrap();
        let mut restored=Vec::new();
        target.write_state(&mut restored).unwrap();
        assert_eq!(wire,restored);
        println!("actual Journey decoder closure: retained={actual} decode_upper={upper} old_allowance={old_allowance} unchanged_validator_required={actual_validator} corrected_allowance={corrected_allowance} wire_bytes={}",wire.len());
    }
}
