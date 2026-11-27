//! Rust owner of the V1 T02/T04 finite-response FIFO packet state.
//! Registry paths are interned; tags retain independent observable ledgers.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
use crate::v1_parallel::ordered_map;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
// Shadow-only experiment; the original V03 road kernel and checkpoint layout
// remain unchanged in non-test native builds.
#[cfg(test)]
#[path = "v1_lineage_shadow.rs"]
mod lineage_shadow;
#[path = "v1_ref_blocks.rs"]
mod v1_ref_blocks;
#[path = "v1_event_blocks.rs"]
mod v1_event_blocks;
#[path = "v1_rank_projection.rs"]
mod v1_rank_projection;
#[path = "v1_ready_rank.rs"]
mod v1_ready_rank;
#[path = "v1_timed_incoming.rs"]
mod timed_incoming;
use timed_incoming::{TimedIncomingControls, TimedIncomingRows};

// Versioned by the enclosing engine header. Integers and IEEE-754 bit patterns
// have a fixed little-endian representation independent of Python objects.
pub(crate) fn write_u64<W: Write>(w: &mut W, v: u64) -> CoreResult<()> {
    w.write_all(&v.to_le_bytes())
        .map_err(|e| CoreError::io(e.to_string()))
}
pub(crate) fn read_u64<R: Read>(r: &mut R) -> CoreResult<u64> {
    let mut b = [0; 8];
    r.read_exact(&mut b)
        .map_err(|e| CoreError::io(e.to_string()))?;
    Ok(u64::from_le_bytes(b))
}
pub(crate) fn write_f64<W: Write>(w: &mut W, v: f64) -> CoreResult<()> {
    write_u64(w, v.to_bits())
}
pub(crate) fn read_f64<R: Read>(r: &mut R) -> CoreResult<f64> {
    Ok(f64::from_bits(read_u64(r)?))
}
pub(crate) fn write_len<W: Write>(w: &mut W, v: usize) -> CoreResult<()> {
    write_u64(w, v as u64)
}
pub(crate) fn read_len<R: Read>(r: &mut R, max: usize) -> CoreResult<usize> {
    let v = usize::try_from(read_u64(r)?).map_err(|_| val("native checkpoint length overflow"))?;
    if v > max {
        return Err(val("native checkpoint length exceeds configuration/budget"));
    }
    Ok(v)
}
pub(crate) fn read_exact_len<R: Read>(r: &mut R, n: usize) -> CoreResult<()> {
    if read_len(r, n)? != n {
        return Err(val("native checkpoint shape differs"));
    }
    Ok(())
}
pub(crate) fn checkpoint_vec<T>(n: usize) -> CoreResult<Vec<T>> {
    let mut v = Vec::new();
    v.try_reserve_exact(n)
        .map_err(|_| budget("native checkpoint allocation exceeds available memory"))?;
    Ok(v)
}

type PartRow = (usize, usize, f64, f64, Option<f64>, Option<f64>);
type PacketRow = (f64, Vec<PartRow>);
type CellRow = (Vec<f64>, Vec<PacketRow>, Vec<(usize, f64)>);
pub(crate) type StateRow = (
    String,
    f64,
    Vec<CellRow>,
    Vec<Vec<PacketRow>>,
    Vec<f64>,
    Vec<Vec<f64>>,
);
pub(crate) type Offer = (usize, f64, f64, Option<f64>, Option<f64>);
pub(crate) type EventRow = (usize, usize, Option<usize>, f64, f64, f64, f64);
// Exact source order correspondence: the associated incoming Part already
// contains both class (from tag) and unchanged mass. Store only independent
// dynamical values, preserving their f64 payloads without any approximation.
type Mark = (f64, f64);
fn compact_mark(speed: f64, latent: f64) -> Mark {
    (speed, latent)
}
#[cfg(test)]
fn reconstruct_mark(p: &Part, m: &Mark, class: impl Fn(&Part) -> usize) -> (usize, f64, f64, f64) {
    (class(p), p.mass, m.0, m.1)
}
/// Every admitted interval endpoint is finite. A reserved nonfinite bit pattern
/// therefore represents None without doubling each endpoint's storage. Present
/// values retain their exact IEEE payload, including the sign of zero; the
/// public row and checkpoint wire format still use the original Option<f64>.
#[derive(Clone, Copy)]
#[repr(transparent)]
struct PackedTime(u64);
impl PackedTime {
    const NONE: u64 = u64::MAX;
    fn new(value: Option<f64>) -> CoreResult<Self> {
        match value {
            None => Ok(Self(Self::NONE)),
            Some(value) if value.is_finite() => Ok(Self(value.to_bits())),
            Some(_) => Err(val("nonfinite retained boundary interval")),
        }
    }
    fn option(self) -> Option<f64> {
        (self.0 != Self::NONE).then(|| f64::from_bits(self.0))
    }
    fn is_some(self) -> bool {
        self.0 != Self::NONE
    }
    fn unwrap(self) -> f64 {
        self.option().unwrap()
    }
    fn unwrap_or(self, default: f64) -> f64 {
        self.option().unwrap_or(default)
    }
    fn map_or<T>(self, default: T, f: impl FnOnce(f64) -> T) -> T {
        self.option().map_or(default, f)
    }
    fn is_some_and(self, f: impl FnOnce(f64) -> bool) -> bool {
        self.option().is_some_and(f)
    }
}
impl PartialEq for PackedTime {
    fn eq(&self, other: &Self) -> bool {
        self.option() == other.option()
    }
}
impl PartialEq<Option<f64>> for PackedTime {
    fn eq(&self, other: &Option<f64>) -> bool {
        self.option() == *other
    }
}
impl PartialOrd for PackedTime {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        self.option().partial_cmp(&other.option())
    }
}
#[derive(Clone, Copy)]
struct Part {
    tag: usize,
    offset: usize,
    mass: f64,
    birth: f64,
    a: PackedTime,
    b: PackedTime,
}
#[derive(Clone, Copy)]
struct CorePart {
    tag: u32,
    offset: u32,
    mass: f64,
    birth: f64,
}

/// Lossless only inside the representable 32-bit integer domain.
/// Ineligible legacy source rows stay in the existing Mixed(Part) form.
fn compact_indices(tag: usize, offset: usize) -> Option<(u32, u32)> {
    Some((u32::try_from(tag).ok()?, u32::try_from(offset).ok()?))
}
fn compact_core_part(p: Part) -> CorePart {
    let (tag, offset) = compact_indices(p.tag, p.offset)
        .expect("source-checked exact compact packet indices");
    CorePart { tag, offset, mass: p.mass, birth: p.birth }
}
#[derive(Clone)]
enum PacketParts {
    Uniform {
        a: PackedTime,
        b: PackedTime,
        rows: Arc<Vec<CorePart>>,
    },
    /// Exact immutable source order of keys shared across independent
    /// physical packets; every packet retains its own mass/birth moments.
    SharedKeys {
        a: PackedTime,
        b: PackedTime,
        keys: Arc<Vec<(u32,u32)>>,
        moments: Arc<Vec<(f64,f64)>>,
    },
    Mixed(Arc<Vec<Part>>),
}
impl PacketParts {
    fn pack(
        parts: Vec<Part>,
        before_allocate: impl FnOnce(usize) -> CoreResult<()>,
    ) -> CoreResult<Self> {
        let shared = parts
            .first()
            .map(|p| (p.a, p.b))
            .filter(|&(a, b)| parts.iter().all(|p| p.a.0 == a.0 && p.b.0 == b.0
                && compact_indices(p.tag, p.offset).is_some()));
        if let Some((a, b)) = shared {
            // Both buffers coexist until conversion completes. The caller
            // charges the new CorePart allocation before it is attempted.
            before_allocate(parts.len().saturating_mul(std::mem::size_of::<CorePart>()))?;
            let mut rows = checkpoint_vec(parts.len())?;
            rows.extend(parts.into_iter().map(compact_core_part));
            // Move ownership into an immutable shared container. No new row
            // conversion/copy is performed by Arc::new.
            Ok(Self::Uniform { a, b, rows: Arc::new(rows) })
        } else {
            Ok(Self::Mixed(Arc::new(parts)))
        }
    }

    /// Directly convert an immutable source and the ORIGINAL binary64 factor
    /// to one final physical packet backing. No raw Part remainder Vec lives
    /// between source and final Uniform/Mixed allocation.
    fn pack_scaled_from(
        source:&PacketParts,f:f64,
        before_allocate:impl FnOnce(usize)->CoreResult<()>,
    )->CoreResult<Self> {
        let mut count=0usize;
        let mut endpoints:Option<(PackedTime,PackedTime)>=None;
        let mut can_uniform=true;
        // This preflight is read-only and does not evaluate birth for filtered rows.
        // A second pass uses precisely the original served_parts transform.
        for p in source.iter() {
            if p.mass*f>0.0 {
                count=count.checked_add(1)
                    .ok_or_else(||budget("scaled source row count overflow"))?;
                if compact_indices(p.tag,p.offset).is_none() {
                    can_uniform=false;
                }
                match endpoints {
                    Some((a,b)) if a.0!=p.a.0 || b.0!=p.b.0 => can_uniform=false,
                    None=>endpoints=Some((p.a,p.b)),
                    _=>{}
                }
            }
        }
        if count==0 {
            return Ok(Self::Mixed(Arc::new(Vec::new())));
        }
        if can_uniform {
            let (a,b)=endpoints.expect("nonempty source has interval bits");
            before_allocate(count.saturating_mul(std::mem::size_of::<CorePart>()))?;
            let mut rows=checkpoint_vec(count)?;
            rows.extend(served_parts(source,f).map(compact_core_part));
            debug_assert_eq!(rows.len(),count);
            Ok(Self::Uniform{a,b,rows:Arc::new(rows)})
        } else {
            before_allocate(count.saturating_mul(std::mem::size_of::<Part>()))?;
            let mut rows=checkpoint_vec(count)?;
            rows.extend(served_parts(source,f));
            debug_assert_eq!(rows.len(),count);
            Ok(Self::Mixed(Arc::new(rows)))
        }
    }
    fn clone_checked(&self) -> CoreResult<Self> {
        // PacketParts owns only immutable post-packing compositions. Existing
        // snapshots and candidates may reference the same physical row
        // storage. All operations modifying a packet replace its entire
        // PacketParts value; they never mutate the shared Vec in place.
        // The original conservative work-budget remains unchanged.
        Ok(self.clone())
    }
    fn len(&self) -> usize {
        match self {
            Self::Uniform { rows, .. } => rows.len(),
            Self::SharedKeys { moments, .. } => moments.len(),
            Self::Mixed(rows) => rows.len(),
        }
    }
    fn is_empty(&self) -> bool {
        self.len() == 0
    }
    fn capacity(&self) -> usize {
        match self {
            Self::Uniform { rows, .. } => rows.capacity(),
            Self::SharedKeys { moments, .. } => moments.capacity(),
            Self::Mixed(rows) => rows.capacity(),
        }
    }
    fn is_uniform(&self) -> bool {
        matches!(self, Self::Uniform { .. } | Self::SharedKeys { .. })
    }
    fn allocated_bytes(&self) -> usize {
        match self {
            Self::Uniform { rows, .. } => rows
                .capacity()
                .saturating_mul(std::mem::size_of::<CorePart>()),
            Self::SharedKeys { keys, moments, .. } => keys.capacity()
                .saturating_mul(std::mem::size_of::<(u32,u32)>())
                .saturating_add(moments.capacity().saturating_mul(std::mem::size_of::<(f64,f64)>())),
            Self::Mixed(rows) => rows.capacity().saturating_mul(std::mem::size_of::<Part>()),
        }
    }
    fn iter(&self) -> PartIter<'_> {
        match self {
            Self::Uniform { a, b, rows } => PartIter::Uniform {
                a: *a,
                b: *b,
                rows: rows.iter(),
            },
            Self::SharedKeys { a, b, keys, moments } => PartIter::SharedKeys {
                a: *a,b: *b, rows: keys.iter().zip(moments.iter()),
            },
            Self::Mixed(rows) => PartIter::Mixed(rows.iter()),
        }
    }
}
enum PartIter<'a> {
    Uniform {
        a: PackedTime,
        b: PackedTime,
        rows: std::slice::Iter<'a, CorePart>,
    },
    SharedKeys {
        a: PackedTime,
        b: PackedTime,
        rows: std::iter::Zip<std::slice::Iter<'a,(u32,u32)>,std::slice::Iter<'a,(f64,f64)>>,
    },
    Mixed(std::slice::Iter<'a, Part>),
}
impl Iterator for PartIter<'_> {
    type Item = Part;
    fn next(&mut self) -> Option<Part> {
        match self {
            Self::Uniform { a, b, rows } => rows.next().map(|p| Part {
                tag: usize::try_from(p.tag).expect("u32 tag always fits usize"),
                offset: usize::try_from(p.offset).expect("u32 offset always fits usize"),
                mass: p.mass,
                birth: p.birth,
                a: *a,
                b: *b,
            }),
            Self::SharedKeys { a, b, rows } => rows.next().map(|(key,moment)| Part {
                tag:key.0 as usize,offset:key.1 as usize,
                mass:moment.0,birth:moment.1,a:*a,b:*b,
            }),
            Self::Mixed(rows) => rows.next().copied(),
        }
    }
    fn size_hint(&self) -> (usize, Option<usize>) {
        let n = match self {
            Self::Uniform { rows, .. } => rows.len(),
            Self::SharedKeys { rows, .. } => rows.len(),
            Self::Mixed(rows) => rows.len(),
        };
        (n, Some(n))
    }
}
impl ExactSizeIterator for PartIter<'_> {}
impl<'a> IntoIterator for &'a PacketParts {
    type Item = Part;
    type IntoIter = PartIter<'a>;
    fn into_iter(self) -> Self::IntoIter {
        self.iter()
    }
}
#[derive(Clone)]
struct Packet {
    target: f64,
    parts: PacketParts,
}
#[derive(Clone)]
struct Cell {
    v: [f64; 8],
    packets: Vec<Packet>,
    latent: BTreeMap<usize, f64>,
}
#[derive(Clone)]
pub(crate) struct RoadState {
    t: f64,
    cells: Vec<Cell>,
    pending: Vec<Vec<Packet>>,
    totals: [f64; 7],
    ledger: Vec<[f64; 5]>,
}
#[derive(Default)]
pub(crate) struct RoadDebugStats {
    pub(crate) cell_packets: usize,
    pub(crate) pending_packets: usize,
    pub(crate) cell_parts: usize,
    pub(crate) pending_parts: usize,
    pub(crate) packet_capacity: usize,
    pub(crate) part_capacity: usize,
    pub(crate) vector_capacity_bytes: usize,
    pub(crate) latent_entries: usize,
    pub(crate) max_cell_parts: usize,
    pub(crate) max_pending_parts: usize,
    pub(crate) uniform_packets: usize,
    pub(crate) mixed_packets: usize,
    pub(crate) uniform_parts: usize,
    pub(crate) mixed_parts: usize,
}

/// Read-only allocation identity diagnostic. Payload values are NOT RSS,
/// heap metadata or a resource gate. 96 bytes per unique Arc is a conservative
/// *reporting allowance*, not an allocator-certified universal upper bound.
#[derive(Default, Debug, Clone, Copy)]
pub(crate) struct ArcBackingCensus {
    pub(crate) owner_count: usize,
    pub(crate) unique_backing_count: usize,
    pub(crate) owner_payload_bytes: usize,
    pub(crate) unique_payload_bytes: usize,
    pub(crate) duplicate_payload_bytes: usize,
    pub(crate) unique_arc_control_allowance_bytes: usize,
}

/// Source key-array repetition diagnostic; no physical admission credit.
/// An independently allocated identical key array is counted separately from
/// Arc clones already physically sharing the same entire Part backing.
#[derive(Default, Clone, Copy, Debug)]
pub(crate) struct OrderedKeysetCensus {
    pub(crate) uniform_packet_owners: usize,
    pub(crate) distinct_uniform_backings: usize,
    pub(crate) distinct_keysets: usize,
    pub(crate) repeated_key_packets: usize,
    pub(crate) repeated_key_rows: usize,
    pub(crate) potential_saved_key_payload_bytes: usize,
    pub(crate) keyset_len_ge_8_repeat_rows: usize,
    pub(crate) max_tag: usize,
    pub(crate) max_offset: usize,
    pub(crate) total_uniform_rows: usize,
}

fn same_ordered_core_keys(a: &[CorePart], b: &[CorePart]) -> bool {
    a.len()==b.len() && a.iter().zip(b).all(|(x,y)|
        x.tag==y.tag && x.offset==y.offset
    )
}

/// Canonical immutable keyset for a particular source-order sequence.
struct ExactKeyGroup {
    keys: Arc<Vec<(u32,u32)>>,
    distinct_original_backings: usize,
}
/// Conservative structural working allowance, not an allocator/RSS theorem.
/// Captures one supplied immutable snapshot, the committed owner, a candidate,
/// and the large source/transfer/splitting workspaces. Unrelated user-retained
/// snapshots and allocator metadata remain covered by the process limit.
// The source-row observation envelope was introduced with raw motion and
// junction reductions. It is not a retained state owner. The receiving
// experiment expires it only after the source frame's large temporaries
// are gone; every receiving buffer is separately charged.
fn receiving_lifetime_enabled()->bool {
    std::env::var_os("METROFLOW_EXPERIMENTAL_RECEIVING_LIFETIMES").as_deref()
        ==Some(std::ffi::OsStr::new("1"))
    && !crate::v1_trace::source_attribution_enabled()
}
fn receiving_lifetime_floor(full_base:usize,max_cell_scratch:usize,source_rows:usize,
                            max_old_owner:usize,candidate_owner:usize)->CoreResult<usize> {
    let old_observation=source_rows.checked_mul(4*std::mem::size_of::<f64>())
        .ok_or_else(||budget("source observation envelope overflow"))?;
    receiving_lifetime_floor_bytes(full_base,max_cell_scratch,old_observation,max_old_owner,candidate_owner)
}
fn receiving_lifetime_floor_bytes(full_base:usize,max_cell_scratch:usize,observation_bytes:usize,max_old_owner:usize,candidate_owner:usize)->CoreResult<usize>{
    full_base.checked_sub(max_cell_scratch)
        .and_then(|x|x.checked_sub(observation_bytes))
        .and_then(|x|x.checked_add(candidate_owner.saturating_sub(max_old_owner)))
        .ok_or_else(||arithmetic("receiving lifetime floor identity differs"))
}

struct RoadWorkBudget {
    limit: Option<usize>,
    base: usize,
    /// Two max-cell Part scratch vectors belong to later interval combination,
    /// after ALL transfer and pending remainders have been packed. Source-phase
    /// remainders charge their own actual raw and packed buffers instead.
    /// True interval combination/splitting retains the full original reserve.
    transfer_exclusive_cell_scratch:usize,
    events: usize,
    /// Projected from the actual event carrier immediately before each source
    /// serve; includes both physical row/time pages and their descriptors.
    event_candidate_live_bound: Option<usize>,
    incoming: usize,
    incoming_page_cells: usize,
    /// Per-destination exact predicted row count. Only for bounded source.
    /// Updated BEFORE each physical append, and reset only after actual
    /// Part+Mark owners have been dropped for that destination.
    incoming_cell_rows: Option<Vec<usize>>,
    incoming_live_pages:usize,
    /// Real Part+Mark page-descriptor storage after all raw appends finish.
    incoming_descriptor_live_bytes:Option<usize>,
    compact_events: bool,
    compact_incoming: bool,
    // Some only for bounded, compact-index, interval-producing sources.
    // Owns the entire append-only control table and new per-cell row shells.
    timed_incoming_control_bytes: Option<usize>,
    // Present only in the optional 12-byte event-index receiving lane. Counts
    // actual or just-preflighted non-exit payloads while their rows are live.
    timed_referenced_rows: Option<usize>,
    packed_ref_saved:Option<usize>,
    /// Packed entering-interval rows already moved into the candidate.
    interval_retained: usize,
    /// Workspace of the interval being built: edges, the selected rows,
    /// combine's index/output buffers and the output packet list.
    interval_transient: usize,
    service_events: Option<ServiceEventAccounting>,
}
#[derive(Clone, Copy)]
struct ServiceEventAccounting {
    input_bytes: usize,
    current_bytes: usize,
    // Only an actual Arc::ptr_eq of the old call-input and committed
    // event buffers permits one-copy payload accounting.
    shared_input_current: bool,
    max_tag_bytes: usize,
}
impl ServiceEventAccounting {
    /// Event buffers live during the road step: the call-input and current
    /// committed buffers (charged separately, never assumed shared) and the
    /// append-only fixed-size pages, which never reallocate old EventRows.
    /// The flat output exists only during the separately-guarded final stage.
    fn road_step_bytes(self, generated_rows: usize) -> usize {
        self.road_step_bytes_for(generated_rows,false)
    }
    fn road_step_bytes_for(self,generated_rows:usize,compressed:bool)->usize {
        self.input_bytes
            .saturating_add(if self.shared_input_current {0} else {self.current_bytes})
            .saturating_add(if compressed {
                paged_compact_event_candidate_bytes(generated_rows)
            } else {
                paged_event_candidate_bytes(generated_rows)
            })
    }
}
// The public EventRow and legacy checkpoint wire remain unchanged. Native
// candidates and immutable service history retain exact time-run pages.
const EVENT_PAGE_ROWS: usize = 4096;

/// Original tag/source/destination are small source registry indexes in V03.
/// The maximum u32 destination code is reserved solely for None.
/// Four f64 payloads (mass, t0, t1, birth) are copied without arithmetic.
#[derive(Clone,Copy)]
struct CompactEventRow {
    tag:u32,
    source:u32,
    dest:u32,
    mass:f64,
    start:f64,
    end:f64,
    birth:f64,
}
impl CompactEventRow {
    fn try_new(e:EventRow)->Option<Self> {
        Some(Self {
            tag:u32::try_from(e.0).ok()?,
            source:u32::try_from(e.1).ok()?,
            dest:match e.2 {
                None=>u32::MAX,
                Some(x) if x < u32::MAX as usize=>u32::try_from(x).ok()?,
                Some(_)=>return None,
            },
            mass:e.3,start:e.4,end:e.5,birth:e.6,
        })
    }
    fn unpack(self)->EventRow {
        (self.tag as usize,self.source as usize,
         if self.dest==u32::MAX {None} else {Some(self.dest as usize)},
         self.mass,self.start,self.end,self.birth)
    }
}

/// Consecutive source/time controls are shared by all events in a service run.
/// The bit stream identifies the first event of each run in original row order.
#[derive(Clone, Copy)]
struct EventPayload {
    tag: u32,
    dest: u32,
    mass: f64,
    birth: f64,
}
impl EventPayload {
    fn unpack(self, source: u32, time: (u64, u64)) -> EventRow {
        (self.tag as usize, source as usize,
         if self.dest == u32::MAX { None } else { Some(self.dest as usize) },
         self.mass, f64::from_bits(time.0), f64::from_bits(time.1), self.birth)
    }
}

const FLAG_WORDS_PER_PAGE: usize = EVENT_PAGE_ROWS / u64::BITS as usize;
const CONTROL_PAGE_ROWS: usize = 256;

// Reserve a complete, fixed-size payload page before changing logical contents.
// An empty page from a failed multi-stream reservation remains available on retry.
fn ensure_event_slot<T>(pages: &mut Vec<Vec<T>>, rows_per_page: usize) -> CoreResult<()> {
    if pages.last().is_none_or(|page| page.len() == rows_per_page) {
        let page = checkpoint_vec(rows_per_page)?;
        if page.capacity() != rows_per_page {
            return Err(budget("fixed event page capacity differs from projection"));
        }
        push_checked(pages, page)?;
    }
    Ok(())
}

#[derive(Default)]
pub(crate) struct ChunkedEvents {
    chunks: Vec<Vec<EventRow>>,
    compact_chunks: Vec<Vec<EventPayload>>,
    packed_payload: Option<v1_event_blocks::PackedEvents>,
    time_chunks: Vec<Vec<(u64, u64)>>,
    flag_chunks: Vec<Vec<u64>>,
    control_chunks: Vec<Vec<(u32, u32)>>,
    compressed: bool,
    len: usize,
    time_len: usize,
    control_len: usize,
    last_time: Option<(u64, u64)>,
}
impl ChunkedEvents {
    pub(crate) fn new(compressed: bool) -> Self {
        let packed=compressed && cfg!(all(feature="native-cli",not(feature="python-extension"))) && std::env::var_os("METROFLOW_NATIVE_PACKED_EVENTS").as_deref()==Some(std::ffi::OsStr::new("1"));
        Self { compressed, packed_payload:packed.then(Default::default), ..Self::default() }
    }
    pub(crate) fn len(&self) -> usize { self.len }
    fn compact_payload(&self,index:usize)->Option<EventPayload> {
        if !self.compressed || index>=self.len {return None;}
        if let Some(p)=&self.packed_payload{return p.get(index)}
        self.compact_chunks.get(index/EVENT_PAGE_ROWS)?.get(index%EVENT_PAGE_ROWS).copied()
    }
    fn capacity(&self) -> usize {
        if self.compressed {
            if let Some(p)=&self.packed_payload{p.capacity()}else{self.compact_chunks.iter().map(Vec::capacity).sum()}
        } else {
            self.chunks.iter().map(Vec::capacity).sum()
        }
    }
    fn descriptor_capacity(&self) -> usize {
        self.chunks.capacity()
            .saturating_add(self.compact_chunks.capacity())
            .saturating_add(self.packed_payload.as_ref().map_or(0,|p|p.descriptor_capacity()))
            .saturating_add(self.time_chunks.capacity())
            .saturating_add(self.flag_chunks.capacity())
            .saturating_add(self.control_chunks.capacity())
    }
    fn physical_capacity_bytes(&self) -> usize {
        fn payload<T>(pages: &[Vec<T>]) -> usize {
            pages.iter().map(Vec::capacity).sum::<usize>()
                .saturating_mul(std::mem::size_of::<T>())
        }
        payload(&self.chunks).saturating_add(payload(&self.compact_chunks))
            .saturating_add(self.packed_payload.as_ref().map_or(0,|p|p.physical_bytes()))
            .saturating_add(payload(&self.time_chunks))
            .saturating_add(payload(&self.flag_chunks))
            .saturating_add(payload(&self.control_chunks))
    }
    pub(crate) fn retained_storage_bytes(&self) -> usize {
        let pages = self.chunks.len() + self.compact_chunks.len() + self.time_chunks.len()
            + self.flag_chunks.len() + self.control_chunks.len()
            + self.packed_payload.as_ref().map_or(0,|p|p.pages()+1);
        self.physical_capacity_bytes()
            .saturating_add(self.descriptor_capacity().saturating_mul(std::mem::size_of::<Vec<EventRow>>()))
            .saturating_add(pages.saturating_mul(32))
            .saturating_add(std::mem::size_of::<Self>())
            .saturating_add(2 * std::mem::size_of::<usize>() + 128)
    }
    fn last_source(&self) -> Option<u32> {
        let i = self.control_len.checked_sub(1)?;
        Some(self.control_chunks[i / CONTROL_PAGE_ROWS][i % CONTROL_PAGE_ROWS].0)
    }
    pub(crate) fn projected_append_storage_bytes(&self, row: EventRow) -> CoreResult<usize> {
        let projected = self.projected_candidate_bytes(1, row.1, row.4, row.5)?;
        if self.compressed {
            return Ok(projected);
        }
        let rows = self.len.checked_add(1).ok_or_else(|| budget("event decode row count overflow"))?;
        Ok(projected.saturating_add(rows.div_ceil(EVENT_PAGE_ROWS).saturating_mul(32))
            .saturating_add(std::mem::size_of::<Self>())
            .saturating_add(2 * std::mem::size_of::<usize>() + 128))
    }
    /// All additional events of a source serve have the same source and time bits.
    /// The wire decoder calls this with exactly one row. Filtered rows may reduce
    /// the actual append count without increasing the projected number of controls.
    fn projected_candidate_bytes(
        &self, additional: usize, source: usize, start: f64, end: f64,
    ) -> CoreResult<usize> {
        let rows = self.len.checked_add(additional).ok_or_else(|| budget("event projection row count overflow"))?;
        if !self.compressed { return Ok(paged_event_candidate_bytes(rows)); }
        let source = u32::try_from(source).map_err(|_| arithmetic("compressed event source exceeds u32"))?;
        let different_time = self.last_time != Some((start.to_bits(), end.to_bits()));
        let new_time = additional > 0 && different_time;
        let new_control = additional > 0 && (different_time || self.last_source() != Some(source));
        let times = self.time_len.checked_add(usize::from(new_time))
            .filter(|&n| n <= u32::MAX as usize).ok_or_else(|| budget("event time index exceeds compact domain"))?;
        let controls = self.control_len.checked_add(usize::from(new_control))
            .ok_or_else(|| budget("event control count overflow"))?;
        let raw=paged_run_event_candidate_bytes(rows, controls, times);
        Ok(if let Some(p)=&self.packed_payload{raw.saturating_add(v1_event_blocks::EXTRA).saturating_sub(p.saved())}else{raw})
    }
    pub(crate) fn iter(&self) -> impl Iterator<Item=EventRow> + '_ {
        let mut controls = self.control_chunks.iter().flatten();
        let mut current = (0, (0, 0));
        let compact = (0..if self.compressed{self.len}else{0}).map(move |i| {
            let row=self.compact_payload(i).expect("event payload index");
            let word = self.flag_chunks[i / EVENT_PAGE_ROWS][(i % EVENT_PAGE_ROWS) / 64];
            if (word >> (i % 64)) & 1 != 0 {
                let &(source, time) = controls.next().expect("event run has one control");
                let time = time as usize;
                current = (source, self.time_chunks[time / EVENT_PAGE_ROWS][time % EVENT_PAGE_ROWS]);
            }
            row.unpack(current.0, current.1)
        });
        self.chunks.iter().flatten().copied().chain(compact)
    }
    pub(crate) fn push_checked(&mut self, event: EventRow) -> CoreResult<()> {
        if !self.compressed {
            ensure_event_slot(&mut self.chunks, EVENT_PAGE_ROWS)?;
            self.chunks.last_mut().unwrap().push(event);
            self.len += 1;
            return Ok(());
        }
        let packed = CompactEventRow::try_new(event)
            .ok_or_else(|| arithmetic("compressed event source-index contract differs"))?;
        let time = (event.4.to_bits(), event.5.to_bits());
        let new_time = self.last_time != Some(time);
        let new_control = new_time || self.last_source() != Some(packed.source);
        if new_time && self.time_len >= u32::MAX as usize {
            return Err(budget("event time index exceeds compact domain"));
        }
        if self.packed_payload.is_none(){ensure_event_slot(&mut self.compact_chunks, EVENT_PAGE_ROWS)?;}
        if self.len % 64 == 0 { ensure_event_slot(&mut self.flag_chunks, FLAG_WORDS_PER_PAGE)?; }
        if new_time { ensure_event_slot(&mut self.time_chunks, EVENT_PAGE_ROWS)?; }
        if new_control { ensure_event_slot(&mut self.control_chunks, CONTROL_PAGE_ROWS)?; }
        if new_time {
            self.time_chunks.last_mut().unwrap().push(time);
            self.time_len += 1;
            self.last_time = Some(time);
        }
        let flags = self.flag_chunks.last_mut().unwrap();
        if self.len % 64 == 0 { flags.push(0); }
        if new_control {
            *flags.last_mut().unwrap() |= 1u64 << (self.len % 64);
            self.control_chunks.last_mut().unwrap().push((packed.source, (self.time_len - 1) as u32));
            self.control_len += 1;
        }
        let payload=EventPayload{tag:packed.tag,dest:packed.dest,mass:packed.mass,birth:packed.birth};
        if let Some(p)=&mut self.packed_payload{p.push(payload)?;}else{self.compact_chunks.last_mut().unwrap().push(payload);}
        self.len += 1;
        Ok(())
    }
    fn into_flat_checked(self) -> CoreResult<Vec<EventRow>> {
        let mut flat = checkpoint_vec(self.len)?;
        if flat.capacity() != self.len {
            return Err(budget("flat event output reserve exceeds exact native contract"));
        }
        flat.extend(self.iter());
        debug_assert_eq!(flat.len(), self.len);
        Ok(flat)
    }
}

/// Exact source-backed row capacity for append-only, fixed-size pages.
/// ChunkedEvents::push_checked allocates exactly B slots for each newly
/// started page and checks real Vec::capacity()==B. Therefore for positive
/// n, *physically live* row slots are exactly B*ceil(n/B), not n+B-1.
/// Retain the original 3x page-descriptor growth bound and charge the actual
/// carrier metadata, including its added time-page owner even for zero rows.
fn paged_event_candidate_payload_bytes(n:usize,row_bytes:usize)->usize {
    const META:usize=std::mem::size_of::<ChunkedEvents>();
    if n==0{return META;}
    let pages=n.div_ceil(EVENT_PAGE_ROWS);
    pages.saturating_mul(EVENT_PAGE_ROWS).saturating_mul(row_bytes)
        .saturating_add(pages.saturating_add(1).saturating_mul(
            3*std::mem::size_of::<Vec<EventRow>>()
        )).saturating_add(META)
}
fn paged_event_candidate_bytes(n:usize)->usize {
    paged_event_candidate_payload_bytes(n,std::mem::size_of::<EventRow>())
}
fn paged_compact_event_candidate_bytes(n:usize)->usize {
    paged_event_candidate_payload_bytes(n,std::mem::size_of::<CompactEventRow>())
}

/// Admission includes the full last payload/flag/control/time pages, the four
/// growing header vectors (including their old and new allocations), per-page
/// allocator padding and carrier metadata. The bound uses no allocator credit.
fn paged_run_event_candidate_bytes(rows: usize, controls: usize, times: usize) -> usize {
    let row_pages = rows.div_ceil(EVENT_PAGE_ROWS);
    let control_pages = controls.div_ceil(CONTROL_PAGE_ROWS);
    let time_pages = times.div_ceil(EVENT_PAGE_ROWS);
    let pages = row_pages.saturating_mul(2).saturating_add(control_pages).saturating_add(time_pages);
    row_pages.saturating_mul(EVENT_PAGE_ROWS * std::mem::size_of::<EventPayload>())
        .saturating_add(row_pages.saturating_mul(FLAG_WORDS_PER_PAGE * std::mem::size_of::<u64>()))
        .saturating_add(control_pages.saturating_mul(CONTROL_PAGE_ROWS * std::mem::size_of::<(u32, u32)>()))
        .saturating_add(time_pages.saturating_mul(EVENT_PAGE_ROWS * std::mem::size_of::<(u64, u64)>()))
        .saturating_add(pages.saturating_add(4).saturating_mul(3 * std::mem::size_of::<Vec<EventRow>>()))
        .saturating_add(pages.saturating_mul(32))
        .saturating_add(std::mem::size_of::<ChunkedEvents>() + 2 * std::mem::size_of::<usize>() + 128)
}

/// Live owners AFTER road step temporaries have been dropped. The final
/// flat events Vec briefly coexists with its original event pages; both are
/// counted as actual separate allocations, preserving original numeric caps.
/// Source-bound peak budget for continuously interning an already finished
/// road candidate after original road transient buffers and event pages die.
/// All three road retained owners, committed service events, final EventRow
/// Vec and NEW full key/moment copies coexist temporarily. The packet term
/// is a conservative 64-bit allocator envelope; no model or cap changes.
/// Each of the three actual road state retained owners is known at the
/// postroad lifetime boundary. Summing ALL THREE distinct source byte
/// counts remains conservative even when some Arc backings are aliased;
/// unlike 3*max, it does not charge an invented additional copy of the
/// largest candidate's entire physical state.
fn postroad_continuous_owner_sum(
    committed:usize,input:usize,candidate:usize,
)->usize {
    committed.saturating_add(input).saturating_add(candidate)
}
/// Distinct immutable input and committed road owners remain alive throughout
/// keyset interning. Charge all shells/candidate storage, subtract ONLY the
/// established nonallocating lower bound for their duplicate live payload.
/// Input must be the actual charged snapshot, not a merely equal value.
fn postroad_input_payload_credit(committed:&RoadState,input:Option<&RoadState>,charged_input:usize,charged_current:usize)->usize{
    let Some(input)=input else{return 0};
    if std::ptr::eq(input,committed)||input.retained_storage_bytes()>charged_input{return 0}
    committed.paired_shared_payload_lower_bound(input).min(charged_input).min(charged_current)
}
fn postroad_continuous_keyset_peak_bytes(
    owner_sum:usize, old_events:usize,
    flat_rows:usize, core_rows:usize, packet_owners:usize,
)->usize {
    postroad_continuous_keyset_peak_event_bytes(
        owner_sum, old_events,
        flat_rows.saturating_mul(std::mem::size_of::<EventRow>()),
        core_rows, packet_owners,
    )
}

fn postroad_continuous_keyset_peak_event_bytes(
    owner_sum: usize, old_events: usize, candidate_event_bytes: usize,
    core_rows: usize, packet_owners: usize,
) -> usize {
    owner_sum
        .saturating_add(old_events)
        .saturating_add(candidate_event_bytes)
        .saturating_add(core_rows.saturating_mul(std::mem::size_of::<CorePart>()))
        .saturating_add(packet_owners.saturating_mul(512))
        .saturating_add(3*32)
}

fn postroad_event_materialization_bytes(
    road_owner_bytes:usize, old_event_bytes:usize,
    paged_payload_bytes:usize, page_header_capacity:usize, n:usize,
)->usize {
    road_owner_bytes
        .saturating_add(old_event_bytes)
        .saturating_add(paged_payload_bytes)
        .saturating_add(page_header_capacity.saturating_mul(std::mem::size_of::<Vec<EventRow>>()))
        .saturating_add(n.saturating_mul(std::mem::size_of::<EventRow>()))
        // Both owners coexist in into_flat_checked, also with empty payloads.
        .saturating_add(std::mem::size_of::<ChunkedEvents>())
        .saturating_add(std::mem::size_of::<Vec<EventRow>>())
}

/// Service-finish sink workspace for `sink_rows` exiting events. The sinks
/// are built only after the road step has returned and its workspaces have
/// been dropped, so this envelope is charged then, against the exact count.
pub(crate) fn sink_envelope_bytes(sink_rows: usize, max_tag_bytes: usize) -> usize {
    if sink_rows == 0 {
        return 0;
    }
    // Push-built sink Vec (doubling: < 3 rows during reallocation) and the
    // `sinks.clone()` handed to service.finish.
    let rows = sink_rows
        .max(4)
        .saturating_mul(3)
        .saturating_add(sink_rows)
        .saturating_mul(std::mem::size_of::<(String, f64, f64)>());
    // One tag String in the original sinks and one in the clone.
    let strings = sink_rows
        .saturating_mul(2)
        .saturating_mul(max_tag_bytes.saturating_add(32));
    // service.finish's HashMap<&str, Vec<f64>> can have one key per sink,
    // including minimum Vec capacities; also covers fsum partials and a
    // temporary formatted service tag. Structural, not an allocator theorem.
    let map = sink_rows
        .saturating_mul(256)
        .saturating_add(64)
        .saturating_add(max_tag_bytes)
        .saturating_add(32);
    rows.saturating_add(strings).saturating_add(map)
}
/// Decode guards run before each reserve, while the old owner and any known
/// call-input snapshot remain live. Validation scratch is charged as rows arrive.
struct RoadDecodeBudget {
    limit: Option<usize>,
    retained_input: usize,
    decoded: usize,
    validation: usize,
}
const EVENT_CLOCK_TOLERANCE_S: f64 = 1e-10;

/// Error-free binary64 addition under the native round-to-nearest mode.
/// Unlike FastTwoSum, this has no magnitude-ordering precondition.
fn two_sum(a: f64, b: f64) -> (f64, f64) {
    let s = a + b;
    let v = s - a;
    (s, (a - (s - v)) + (b - v))
}
fn upper_add(a: f64, b: f64) -> f64 {
    if b == 0. {
        return a;
    }
    let s = a + b;
    if s.is_finite() {
        f64::from_bits(s.to_bits() + 1)
    } else {
        s
    }
}
#[derive(Default, Clone, Copy)]
struct EventResolutionStats {
    count: u64,
    processed_time_bound: f64,
    clock_roundoff_bound: f64,
    rate_weighted_mass_bound: f64,
}
impl EventResolutionStats {
    fn merge(&mut self, other: Self) {
        self.count = self.count.saturating_add(other.count);
        self.processed_time_bound =
            upper_add(self.processed_time_bound, other.processed_time_bound);
        self.clock_roundoff_bound =
            upper_add(self.clock_roundoff_bound, other.clock_roundoff_bound);
        self.rate_weighted_mass_bound = upper_add(
            self.rate_weighted_mass_bound,
            other.rate_weighted_mass_bound,
        );
    }
}
/// The legacy single-word clock stays untouched until a positive duration
/// cannot advance it. The two-word extension retains that duration; it does
/// not enlarge h, remove a positive mass or claim exact mass-split arithmetic.
#[derive(Default)]
struct EventClock {
    hi: f64,
    lo: f64,
    active: bool,
    stats: EventResolutionStats,
}
impl EventClock {
    fn remaining(&self, boundary: f64) -> f64 {
        if self.active {
            (boundary - self.hi) - self.lo
        } else {
            boundary - self.hi
        }
    }
    fn after_ready(&self, ready: f64) -> bool {
        if self.active {
            self.remaining(ready) > EVENT_CLOCK_TOLERANCE_S
        } else {
            ready > self.hi + EVENT_CLOCK_TOLERANCE_S
        }
    }
    fn offset(&self, h: f64) -> f64 {
        if self.active {
            let (s, e) = two_sum(self.hi, h);
            s + (e + self.lo)
        } else {
            self.hi + h
        }
    }
    fn jump(&mut self, boundary: f64) {
        self.hi = boundary;
        self.lo = 0.;
    }
    fn check_bound(&self) -> CoreResult<()> {
        if self.stats.processed_time_bound + self.stats.clock_roundoff_bound
            > EVENT_CLOCK_TOLERANCE_S
        {
            return Err(arithmetic(&format!(
                "packet compensated clock roundoff budget exceeded: processed_subulp_s={:?}, clock_roundoff_s={:?}, tolerance_s={EVENT_CLOCK_TOLERANCE_S:?}",
                self.stats.processed_time_bound, self.stats.clock_roundoff_bound)));
        }
        Ok(())
    }
    fn advance(&mut self, h: f64, boundary: Option<f64>) -> CoreResult<bool> {
        if !self.active {
            self.hi += h;
            return Ok(true);
        }
        // Charge selected horizon/future subtraction rounding separately from
        // the discarded third word of compensated addition.
        if let Some(boundary) = boundary {
            let error = sum([self.hi, self.lo, h, -boundary]).abs();
            self.stats.clock_roundoff_bound = upper_add(self.stats.clock_roundoff_bound, error);
        }
        let old = (self.hi, self.lo);
        let (s, e) = two_sum(self.hi, h);
        let (v, discarded) = two_sum(self.lo, e);
        (self.hi, self.lo) = two_sum(s, v);
        self.stats.clock_roundoff_bound =
            upper_add(self.stats.clock_roundoff_bound, discarded.abs());
        self.check_bound()?;
        Ok(self.hi > old.0 || (self.hi == old.0 && self.lo > old.1))
    }
}
impl RoadDecodeBudget {
    fn pack_parts(&mut self, parts: Vec<Part>) -> CoreResult<PacketParts> {
        let raw_bytes = parts.capacity().saturating_mul(std::mem::size_of::<Part>());
        let packed = PacketParts::pack(parts, |bytes| self.reserve(bytes, 0))?;
        if packed.is_uniform() {
            self.decoded = self.decoded.saturating_sub(raw_bytes);
        }
        Ok(packed)
    }
    fn reserve(&mut self, bytes: usize, validation: usize) -> CoreResult<()> {
        self.decoded = self.decoded.saturating_add(bytes);
        self.validation = self.validation.saturating_add(validation);
        let required = self
            .decoded
            .max(self.retained_input)
            .saturating_mul(3)
            .saturating_add(self.validation);
        if let Some(limit) = self.limit {
            if crate::v1_trace::guard(
                "road_decode",
                "checkpoint decode preflight",
                required,
                limit,
                &[
                    ("decoded", self.decoded),
                    ("retained_input", self.retained_input),
                    ("validation", self.validation),
                ],
            ) {
                return Ok(());
            }
        }
        check_storage_limit(self.limit, required, "checkpoint decode preflight")
    }
}
impl RoadWorkBudget {
    fn pack_parts(&self, parts: Vec<Part>) -> CoreResult<PacketParts> {
        PacketParts::pack(parts, |bytes| {
            self.require(bytes, "packet interval packing")
        })
    }
    fn require(&self, extra: usize, phase: &str) -> CoreResult<()> {
        // In a coupled transition the road-step event buffers are charged by
        // lifetime; the sink envelope is charged after the step returns.
        let event_bytes = self.service_events.map_or_else(
            || {
                self.events
                    .saturating_mul(2 * std::mem::size_of::<EventRow>())
            },
            |service| self.event_candidate_live_bound.map_or_else(
                ||service.road_step_bytes_for(self.events,self.compact_events),
                |candidate|service.input_bytes
                    .saturating_add(if service.shared_input_current {0}else{service.current_bytes})
                    .saturating_add(candidate),
            ),
        );
        let incoming_bytes=if let Some(controls) = self.timed_incoming_control_bytes {
            let base=timed_incoming_page_charge(self.incoming_page_cells,
                self.incoming_live_pages,self.incoming_descriptor_live_bytes);
            let pages=self.timed_referenced_rows.map_or(base,|refs|
                referenced_incoming_page_charge(base,self.incoming_page_cells,refs));
            let pages=if let Some(saved)=self.packed_ref_saved{packed_reference_charge(pages,self.incoming_page_cells,saved)}else{pages};
            pages.saturating_add(controls)
        } else if self.incoming_cell_rows.is_some(){
            segmented_incoming_exact_cell_pages_charge(
                self.incoming,self.incoming_page_cells,
                self.incoming_live_pages,self.compact_incoming,
                self.incoming_descriptor_live_bytes,
            )
        } else {
            segmented_incoming_charge_for(
                self.incoming,self.incoming_page_cells,self.compact_incoming,
            )
        };
        // Source transfers and their own remainder conversions finish before
        // the first combine_chunked_parts call. The dedicated remainder path
        // charges actual raw+packed capacity; it does not borrow future max-cell
        // scratch. Ordinary packet/interval packing retains the full reserve.
        let before_cell_combination = matches!(phase,
            "transfer candidates" | "source remainder packing" |
            "source tick preflight" | "source offer packing");
        let phase_base=if before_cell_combination {
            self.base.saturating_sub(self.transfer_exclusive_cell_scratch)
        } else {self.base};
        let required =
            phase_base
                .saturating_add(event_bytes)
                .saturating_add(incoming_bytes)
                .saturating_add(self.interval_retained)
                .saturating_add(self.interval_transient)
                .saturating_add(extra);
        if let Some(limit) = self.limit {
            if crate::v1_trace::guard(
                "road_work",
                phase,
                required,
                limit,
                &[
                    ("base", phase_base),
                    ("full_source_base", self.base),
                    ("transfer_exclusive_cell_scratch",
                        if before_cell_combination {
                            self.transfer_exclusive_cell_scratch
                        }else{0}),
                    ("event_bytes", event_bytes),
                    ("event_candidate_live_bound",self.event_candidate_live_bound.unwrap_or(0)),
                    ("incoming_rows", self.incoming),
                    ("incoming_live_pages",self.incoming_live_pages),
                    ("incoming_actual_page_charge",incoming_bytes),
                    ("packed_ref_sealed_credit",self.packed_ref_saved.unwrap_or(0)),
                    ("timed_incoming_control_bytes",self.timed_incoming_control_bytes.unwrap_or(0)),
                    ("incoming_actual_descriptor_bytes",
                        self.incoming_descriptor_live_bytes.unwrap_or(0)),
                    ("incoming_descriptors_frozen",
                        usize::from(self.incoming_descriptor_live_bytes.is_some())),
                    ("interval_retained", self.interval_retained),
                    ("interval_transient", self.interval_transient),
                    ("extra", extra),
                ],
            ) {
                return Ok(());
            }
        }
        check_storage_limit(self.limit, required, phase)
    }
    /// Decrease the conservative live source-row count ONLY after actual
    /// Part and matching Mark page allocations for one destination cell have
    /// been physically dropped. Retained final packet rows are separately
    /// charged by interval_retained; no packet or source row is discarded here.
    fn release_incoming(&mut self,cell:usize,expired_rows:usize)->CoreResult<()> {
        let remaining=self.incoming.checked_sub(expired_rows).ok_or_else(||
            arithmetic("expired incoming source rows exceed prior charged rows"))?;
        if let Some(tracked)=&mut self.incoming_cell_rows {
            let prior=tracked.get_mut(cell).ok_or_else(||
                arithmetic("expired raw destination outside original cell registry"))?;
            if *prior!=expired_rows {
                return Err(arithmetic("source incoming cell row count differs from real dropped pages"));
            }
            let pages=prior.div_ceil(INCOMING_PART_CHUNK);
            let new_pages=self.incoming_live_pages.checked_sub(pages).ok_or_else(||
                arithmetic("expired source pages exceed actually predicted live pages"))?;
            *prior=0;
            self.incoming_live_pages=new_pages;
        }
        self.incoming=remaining;
        Ok(())
    }
    /// Source-bound preflight runs before actual raw Part and Mark appends.
    /// Reconstruct exactly the destination distribution from the original
    /// served immutable physical packet rows without sorting or combining.
    /// Each new page is allocated iff the cell's old length is a multiple
    /// of the physical fixed page size; no in-memory object is fabricated.
    fn transfer_indexed(
        &mut self,events:usize,destinations:impl IntoIterator<Item=usize>,
    )->CoreResult<()> {
        if self.incoming_descriptor_live_bytes.is_some() {
            return Err(arithmetic("incoming page descriptor storage frozen after last source append"));
        }
        self.events=self.events.saturating_add(events);
        if let Some(tracked)=&mut self.incoming_cell_rows {
            for i in destinations {
                let count=tracked.get_mut(i).ok_or_else(||
                    arithmetic("incoming predicted destination outside original cell registry"))?;
                if *count % INCOMING_PART_CHUNK==0 {
                    self.incoming_live_pages=self.incoming_live_pages.saturating_add(1);
                }
                *count=count.saturating_add(1);
                self.incoming=self.incoming.saturating_add(1);
            }
        } else {
            for _ in destinations{
                self.incoming=self.incoming.saturating_add(1);
            }
        }
        self.require(0,"transfer candidates")
    }
    /// The raw Part/Mark page header Vecs are *momentarily* stable during
    /// packet remainder conversion, but remain appendable on the next
    /// pending source iteration. Verify exact current lengths and capacities
    /// before allowing the no-growth-time source bound.
    fn observed_incoming_descriptor_bytes(
        &self,parts:&[ChunkedParts],marks:&[ChunkedMarks],
    )->CoreResult<usize> {
        let Some(tracked)=&self.incoming_cell_rows else {
            return Err(arithmetic("incoming source destination registry unavailable"));
        };
        if parts.len()!=tracked.len() || marks.len()!=tracked.len() {
            return Err(arithmetic("incoming Part Mark registry count mismatch"));
        }
        let mut rows=0usize;
        let mut pages=0usize;
        let mut descriptors=0usize;
        for i in 0..tracked.len() {
            let (p,m)=(&parts[i],&marks[i]);
            if p.len()!=m.len() || p.len()!=tracked[i]
                || p.capacity()!=m.capacity()
                || p.capacity()!=p.len().div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK {
                return Err(arithmetic("incoming current Part Mark fixed-page counts differ"));
            }
            rows=rows.saturating_add(p.len());
            pages=pages.saturating_add(p.capacity()/INCOMING_PART_CHUNK);
            descriptors=descriptors.saturating_add(
                p.descriptor_capacity().saturating_mul(std::mem::size_of::<Vec<Part>>())
                .saturating_add(m.chunks.capacity()
                    .saturating_mul(std::mem::size_of::<Vec<Mark>>()))
            );
        }
        if rows!=self.incoming || pages!=self.incoming_live_pages {
            return Err(arithmetic("incoming live page census differs from source preflight"));
        }
        Ok(descriptors)
    }
    /// Road-head and pending remainders finish before cell combination starts.
    /// Their conversion does not append raw Part/Mark pages. Charge current real
    /// descriptor capacities plus BOTH actual remainder buffers, without the
    /// future max-cell combine reserve. Always restore the growth-time envelope
    /// on success or error; later source appends remain permitted.
    fn pack_parts_with_live_descriptors(
        &mut self,parts:Vec<Part>,
        incoming:&[ChunkedParts],marks:&[ChunkedMarks],
    )->CoreResult<PacketParts> {
        if self.incoming_cell_rows.is_none() {
            return self.pack_parts(parts);
        }
        if self.timed_incoming_control_bytes.is_some() {
            // No legacy raw Part/Mark pages exist during the timed source
            // phase. Keep the timed page/header growth bound and charge the
            // actual raw+packed remainder coexistence before conversion.
            let raw_bytes=parts.capacity().saturating_mul(std::mem::size_of::<Part>());
            self.require(raw_bytes,"source remainder packing")?;
            return PacketParts::pack(parts,|packed_bytes| self.require(
                raw_bytes.saturating_add(packed_bytes),"source remainder packing"));
        }
        if self.incoming_descriptor_live_bytes.is_some() {
            return Err(arithmetic("pending descriptor preflight already frozen"));
        }
        let actual=self.observed_incoming_descriptor_bytes(incoming,marks)?;
        self.incoming_descriptor_live_bytes=Some(actual);
        let raw_bytes=parts.capacity().saturating_mul(std::mem::size_of::<Part>());
        let result=(|| {
            // Mixed fallback reuses the raw owner, so it also needs a guard
            // even when PacketParts::pack allocates no CorePart buffer.
            self.require(raw_bytes,"source remainder packing")?;
            PacketParts::pack(parts,|packed_bytes| {
                self.require(raw_bytes.saturating_add(packed_bytes),
                    "source remainder packing")
            })
        })();
        self.incoming_descriptor_live_bytes=None;
        result
    }

    /// Source-phase boundary: every road-service and pending original raw
    /// destination Part+Mark append has finished, no further one can grow.
    /// Both real outer Vec<Vec<T>> capacities can now be read EXACTLY for
    /// later packet interval splitting and packing preflights.
    fn lock_completed_incoming_descriptors(
        &mut self,parts:&[ChunkedParts],marks:&[ChunkedMarks],
    )->CoreResult<()> {
        let Some(tracked)=&self.incoming_cell_rows else {return Ok(())};
        if self.incoming_descriptor_live_bytes.is_some()
            || parts.len()!=tracked.len() || marks.len()!=tracked.len() {
            return Err(arithmetic("incoming descriptor fixed source registry differs"));
        }
        let mut actual_rows=0usize;
        let mut actual_pages=0usize;
        let mut descriptor_bytes=0usize;
        for i in 0..tracked.len() {
            let (p,m)=(&parts[i],&marks[i]);
            if p.len()!=m.len() || p.len()!=tracked[i]
                || p.capacity()!=m.capacity()
                || p.capacity()!=p.len().div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK {
                return Err(arithmetic("incoming Part Mark aligned source page ownership differs"));
            }
            actual_rows=actual_rows.saturating_add(p.len());
            actual_pages=actual_pages.saturating_add(p.capacity()/INCOMING_PART_CHUNK);
            descriptor_bytes=descriptor_bytes.saturating_add(
                p.descriptor_capacity().saturating_mul(std::mem::size_of::<Vec<Part>>())
                .saturating_add(m.chunks.capacity()
                    .saturating_mul(std::mem::size_of::<Vec<Mark>>()))
            );
        }
        if actual_rows!=self.incoming || actual_pages!=self.incoming_live_pages {
            return Err(arithmetic("incoming frozen physical page count differs from preflight"));
        }
        self.incoming_descriptor_live_bytes=Some(descriptor_bytes);
        crate::v1_trace::add("road_work.locked_descriptor_payload_bytes",descriptor_bytes as u64);
        Ok(())
    }
    fn interval(&mut self, transient: usize) -> CoreResult<()> {
        self.interval_transient = transient;
        self.require(0, "entry interval split")
    }
    fn retain_interval(&mut self, bytes: usize) {
        self.interval_retained = self.interval_retained.saturating_add(bytes);
    }
    fn end_interval(&mut self) {
        self.interval_transient = 0;
    }
}
fn check_storage_limit(limit: Option<usize>, required: usize, phase: &str) -> CoreResult<()> {
    if let Some(limit) = limit {
        if required > limit {
            return Err(budget(&format!(
                "native road storage budget exceeded: phase={phase}, required_bytes={required}, budget_bytes={limit}")));
        }
    }
    Ok(())
}
// Structural bound (not allocator/RSS theorem). At most three class
// expansions, all/residence, two cell accumulators and one packet
// accumulator, plus sequential finishing. Each checked expansion has
// <=4096 finite partials; 128 KiB each covers Vec growth overlap.
// 2 MiB covers these accumulators and local metadata. A key-pointer
// HashSet census needs O(packet count), not O(physical row count).
pub(crate) fn compact_checkpoint_enabled()->bool{cfg!(feature="native-cli")&&std::env::var("METROFLOW_NATIVE_COMPACT_WIRE").as_deref()==Ok("1")&&std::env::var("METROFLOW_NATIVE_LEGACY_SAVE").as_deref()!=Ok("1")}
fn road_stream_validation_bound(packets:usize,cells:usize)->usize{
    (2*1024*1024usize).saturating_add(packets.saturating_mul(64)).saturating_add(cells.saturating_mul(32))
}
impl RoadState {
    pub(crate) fn time(&self) -> f64 {
        self.t
    }
    pub(crate) fn summary(&self) -> (&[f64; 7], &[[f64; 5]]) {
        (&self.totals, &self.ledger)
    }
    pub(crate) fn active_by_tag(&self) -> HashMap<usize, f64> {
        let mut out = HashMap::new();
        for p in self
            .cells
            .iter()
            .flat_map(|c| &c.packets)
            .chain(self.pending.iter().flatten())
            .flat_map(|q| &q.parts)
        {
            *out.entry(p.tag).or_insert(0.0) += p.mass;
        }
        out
    }
    /// Canonical journey mass across multiple physical route tags. Preserve
    /// physical row encounter order; one-tag owners have identical old sums.
    pub(crate) fn active_by_owner(&self,owners:&[Option<usize>])->CoreResult<HashMap<usize,f64>>{
        let mut out=HashMap::new();
        for p in self.cells.iter().flat_map(|c|&c.packets).chain(self.pending.iter().flatten()).flat_map(|q|&q.parts){
            if let Some(i)=*owners.get(p.tag).ok_or_else(||val("route owner absent"))?{*out.entry(i).or_insert(0.)+=p.mass;}
        }Ok(out)
    }
    /// Count guaranteed redundant payload across distinct, live input and
    /// committed packet shells, without allocating before the guard.
    pub(crate) fn paired_shared_payload_lower_bound(&self, other: &RoadState) -> usize {
        if std::ptr::eq(self, other) {
            return 0;
        }
        fn matched_bytes<T>(a: &Arc<Vec<T>>, b: &Arc<Vec<T>>) -> usize {
            if !Arc::ptr_eq(a, b) {
                return 0;
            }
            // For k disjoint matching pairs of slots, both live states
            // together own at least 2k references throughout this traversal.
            // Dividing each contribution by floor(strong_count/2) credits at
            // most one payload, even for a key dictionary shared by many rows.
            let pairs = Arc::strong_count(a) / 2;
            a.capacity().saturating_mul(std::mem::size_of::<T>()) / pairs
        }
        fn packets_credit(a: &[Packet], b: &[Packet]) -> usize {
            a.iter().zip(b).fold(0usize, |sum, (a, b)| {
                let bytes = match (&a.parts, &b.parts) {
                    (PacketParts::Uniform { rows: x, .. }, PacketParts::Uniform { rows: y, .. }) =>
                        matched_bytes(x, y),
                    (PacketParts::Mixed(x), PacketParts::Mixed(y)) => matched_bytes(x, y),
                    (PacketParts::SharedKeys { keys: k, moments: m, .. },
                     PacketParts::SharedKeys { keys: l, moments: n, .. }) =>
                        matched_bytes(k, l).saturating_add(matched_bytes(m, n)),
                    _ => 0,
                };
                sum.saturating_add(bytes)
            })
        }
        let cells = self.cells.iter().zip(&other.cells).fold(0usize, |sum, (a, b)| {
            sum.saturating_add(packets_credit(&a.packets, &b.packets))
        });
        self.pending.iter().zip(&other.pending).fold(cells, |sum, (a, b)| {
            sum.saturating_add(packets_credit(a, b))
        })
    }

    /// Diagnostic-only exact Vec *payload capacity* identity census.
    /// This method is never consulted by native resource admission. ArcInner
    /// is identified by stable live Arc pointer identity, NOT equal Part data.
    /// Distinct input/candidate snapshots need a separate union census.
    pub(crate) fn arc_backing_census(&self) -> ArcBackingCensus {
        Self::arc_backing_union(&[self])
    }

    /// Only called by explicit debug_state() on a source-bound RoadState.
    /// A hash is used to *find candidates*, never to declare two keysets
    /// equivalent. Full length and elementwise tag/offset comparisons decide.
    /// No source key rows are copied, no simulations or budget guards altered.
    pub(crate) fn ordered_keyset_census(&self) -> OrderedKeysetCensus {
        let mut c=OrderedKeysetCensus::default();
        let mut seen_backings=HashSet::<usize>::new();
        let mut groups:HashMap<(usize,u64), Vec<&[CorePart]>>=HashMap::new();
        for p in self.cells.iter().flat_map(|cell|&cell.packets)
            .chain(self.pending.iter().flatten())
        {
            let PacketParts::Uniform{rows,..}=&p.parts else {continue};
            c.uniform_packet_owners+=1;
            if !seen_backings.insert(Arc::as_ptr(rows) as usize) {
                continue; // existing Arc clone is *already* physically shared
            }
            c.distinct_uniform_backings+=1;
            c.total_uniform_rows+=rows.len();
            for row in rows.iter() {
                c.max_tag=c.max_tag.max(row.tag as usize);
                c.max_offset=c.max_offset.max(row.offset as usize);
            }
            let mut h=std::collections::hash_map::DefaultHasher::new();
            rows.len().hash(&mut h);
            for row in rows.iter() {
                row.tag.hash(&mut h);
                row.offset.hash(&mut h);
            }
            let candidates=groups.entry((rows.len(),h.finish())).or_default();
            if candidates.iter().any(|old|same_ordered_core_keys(old, rows.as_slice())) {
                c.repeated_key_packets+=1;
                c.repeated_key_rows+=rows.len();
                if rows.len()>=8 {
                    c.keyset_len_ge_8_repeat_rows+=rows.len();
                }
            } else {
                candidates.push(rows.as_slice());
                c.distinct_keysets+=1;
            }
        }
        c.potential_saved_key_payload_bytes=
            c.repeated_key_rows.saturating_mul(2*std::mem::size_of::<u32>());
        c
    }
    /// Intern only FULL, ordered and elementwise identical route-key arrays.
    /// All independent mass/birth, endpoints, source index order and Mixed
    /// physical rows remain unchanged. The hash is a lookup hint, never proof.
    /// Groups with fewer than two independent owners or short lists remain in
    /// their original Arc<Vec<CorePart>> form (metadata would dominate).
    /// Only Uniform sources can allocate new canonical key rows (8 B) and
    /// moment rows (16 B). SharedKeys retain their existing moment Arc and
    /// either clone or replace a key Arc; their row payload is already in the
    /// full retained-owner sum. Count repeated Uniform owners conservatively.
    fn keyset_allocation_row_count(&self) -> usize {
        self.cells.iter().flat_map(|c|&c.packets).chain(self.pending.iter().flatten())
            .fold(0usize,|total,p|total.saturating_add(match &p.parts {
                PacketParts::Uniform{rows,..}=>rows.len(),
                PacketParts::SharedKeys{..}|PacketParts::Mixed(_)=>0,
            }))
    }
    // Nonempty ordered (tag, offset) keys identify the present physical cell
    // through path(tag)[offset]. Its road and pending queues are one partition.
    // Select the maximum JOINT row + packet charge without allocating a table.
    fn peak_cell_keyset_workspace(&self) -> CoreResult<(usize,usize)> {
        if self.cells.len()!=self.pending.len() {
            return Err(val("native keyset cell/pending shape differs"));
        }
        let mut peak=(0,0);
        let mut peak_bytes=0;
        for (cell,pending) in self.cells.iter().zip(&self.pending) {
            let rows=cell.packets.iter().chain(pending).fold(0usize,|n,p|match &p.parts {
                PacketParts::Uniform{rows,..}=>n.saturating_add(rows.len()),
                _=>n,
            });
            let packets=cell.packets.len().saturating_add(pending.len());
            let bytes=postroad_continuous_keyset_peak_event_bytes(0,0,0,rows,packets);
            if bytes>peak_bytes { peak=(rows,packets); peak_bytes=bytes; }
        }
        Ok(peak)
    }
    pub(crate) fn intern_exact_keysets(&mut self) -> CoreResult<usize> {
        if self.cells.len()!=self.pending.len() {
            return Err(val("native keyset cell/pending shape differs"));
        }
        let mut converted=0usize;
        for (cell,pending) in self.cells.iter_mut().zip(&mut self.pending) {
            converted=converted.saturating_add(Self::intern_cell_keysets(&mut cell.packets,pending)?);
        }
        Ok(converted)
    }

    // All four lookup/assignment containers and the old->new moment map drop
    // before the next cell. Finished cells never increase retained owner charge:
    // existing shared keys are preferred; for m >= 2 independent Uniform owners
    // of n >= 16 rows the extra key charge is 8n+96 <= 8mn reclaimed in moments.
    fn intern_cell_keysets(road:&mut [Packet],pending:&mut [Packet])->CoreResult<usize> {
        let mut groups:Vec<ExactKeyGroup>=Vec::new();
        let mut lookup:HashMap<(usize,u64),Vec<usize>>=HashMap::new();
        let mut assignments:Vec<Option<usize>>=Vec::new();
        let mut unique_old_backings:HashSet<(u8,usize)>=HashSet::new();
        // First pass is strictly read-only. Canonical keys are OWNED, not
        // borrowed from self, so the second mutation pass cannot invalidate
        // a representative or confuse Arc pointer identities.
        for packet in road.iter().chain(pending.iter()) {
            let (n,h,old_backing)=match &packet.parts {
                PacketParts::Uniform{rows,..}=>{
                    let mut h=std::collections::hash_map::DefaultHasher::new();
                    rows.len().hash(&mut h);
                    for r in rows.iter() {r.tag.hash(&mut h);r.offset.hash(&mut h);}
                    (rows.len(),h.finish(),(0u8,Arc::as_ptr(rows) as usize))
                },
                PacketParts::SharedKeys{keys,moments,..}=>{
                    let mut h=std::collections::hash_map::DefaultHasher::new();
                    keys.len().hash(&mut h);
                    for k in keys.iter() {k.hash(&mut h);}
                    (keys.len(),h.finish(),(1u8,Arc::as_ptr(moments) as usize))
                },
                PacketParts::Mixed(_)=>{
                    push_checked(&mut assignments,None)?;
                    continue;
                }
            };
            let bucket=lookup.entry((n,h)).or_default();
            let found=bucket.iter().copied().find(|&id|{
                let key=groups[id].keys.as_slice();
                match &packet.parts {
                    PacketParts::Uniform{rows,..}=>rows.len()==key.len()&&
                        rows.iter().zip(key).all(|(r,k)|(r.tag,r.offset)==*k),
                    PacketParts::SharedKeys{keys,..}=>keys.as_slice()==key,
                    PacketParts::Mixed(_)=>false,
                }
            });
            let id=if let Some(id)=found {
                if let PacketParts::SharedKeys{keys,..}=&packet.parts {
                    groups[id].keys=keys.clone();
                }
                id
            } else {
                let key=match &packet.parts {
                    PacketParts::Uniform{rows,..}=>{
                        let mut tmp=checkpoint_vec(rows.len())?;
                        if tmp.capacity()!=rows.len() {
                            return Err(budget("cell keyset allocator exceeded exact row capacity"));
                        }
                        tmp.extend(rows.iter().map(|r|(r.tag,r.offset)));
                        Arc::new(tmp)
                    },
                    PacketParts::SharedKeys{keys,..}=>keys.clone(),
                    PacketParts::Mixed(_)=>unreachable!(),
                };
                let id=groups.len();
                push_checked(&mut groups,ExactKeyGroup{
                    keys:key,distinct_original_backings:0,
                })?;
                bucket.push(id);
                id
            };
            if unique_old_backings.insert(old_backing) {
                groups[id].distinct_original_backings+=1;
            }
            push_checked(&mut assignments,Some(id))?;
        }
        // Existing clones of a single old CorePart Arc must remain shared
        // on the *moment* side too; do not inadvertently make two new payloads.
        let mut moments_by_old_backing:HashMap<usize,Arc<Vec<(f64,f64)>>>=HashMap::new();
        let mut converted=0usize;
        let mut index=0usize;
        for packet in road.iter_mut().chain(pending.iter_mut()) {
            let group=assignments[index];
            index+=1;
            let Some(id)=group else {continue};
            let g=&groups[id];
            if g.distinct_original_backings<2 || g.keys.len()<16 {continue;}
            match &mut packet.parts {
                PacketParts::Uniform{a,b,rows}=>{
                    let ptr=Arc::as_ptr(rows) as usize;
                    let values=if let Some(old)=moments_by_old_backing.get(&ptr) {
                        old.clone()
                    } else {
                        let mut tmp=checkpoint_vec(rows.len())?;
                        if tmp.capacity()!=rows.len() {
                            return Err(budget("cell keyset allocator exceeded exact row capacity"));
                        }
                        tmp.extend(rows.iter().map(|r|(r.mass,r.birth)));
                        let new=Arc::new(tmp);
                        moments_by_old_backing.insert(ptr,new.clone());
                        new
                    };
                    let (a,b)=(*a,*b);
                    packet.parts=PacketParts::SharedKeys{
                        a,b,keys:g.keys.clone(),moments:values,
                    };
                    converted+=1;
                },
                PacketParts::SharedKeys{keys,..}=>{
                    if !Arc::ptr_eq(keys,&g.keys) {
                        *keys=g.keys.clone();
                        converted+=1;
                    }
                },
                PacketParts::Mixed(_)=>unreachable!(),
            }
        }
        debug_assert_eq!(assignments.len(),index);
        Ok(converted)
    }

    /// Exact identity union on a specifically enumerated simultaneous set of
    /// retained native snapshots, never used to approve additional work.
    pub(crate) fn arc_backing_union(states: &[&RoadState]) -> ArcBackingCensus {
        let mut distinct: HashSet<(u8, usize)> = HashSet::new();
        let mut result = ArcBackingCensus::default();
        for state in states {
            for packet in state.cells.iter().flat_map(|cell|&cell.packets)
                .chain(state.pending.iter().flatten()) {
                result.owner_count+=1;
                let mut add=|kind:u8, allocation:usize, bytes:usize| {
                    result.owner_payload_bytes=result.owner_payload_bytes.saturating_add(bytes);
                    if distinct.insert((kind,allocation)) {
                        result.unique_backing_count+=1;
                        result.unique_payload_bytes=
                            result.unique_payload_bytes.saturating_add(bytes);
                    }
                };
                match &packet.parts {
                    PacketParts::Uniform{rows,..}=>add(
                        0,Arc::as_ptr(rows) as usize,
                        rows.capacity().saturating_mul(std::mem::size_of::<CorePart>())),
                    PacketParts::Mixed(rows)=>add(
                        1,Arc::as_ptr(rows) as usize,
                        rows.capacity().saturating_mul(std::mem::size_of::<Part>())),
                    PacketParts::SharedKeys{keys,moments,..}=>{
                        add(2,Arc::as_ptr(keys) as usize,
                            keys.capacity().saturating_mul(std::mem::size_of::<(u32,u32)>()));
                        add(3,Arc::as_ptr(moments) as usize,
                            moments.capacity().saturating_mul(std::mem::size_of::<(f64,f64)>()));
                    },
                }
            }
        }
        result.duplicate_payload_bytes=result.owner_payload_bytes
            .saturating_sub(result.unique_payload_bytes);
        result.unique_arc_control_allowance_bytes=result
            .unique_backing_count.saturating_mul(96);
        result
    }
    /// Owned vector capacity only: BTreeMap nodes, allocator overhead and the
    /// immutable model registry are deliberately excluded from this diagnostic.
    pub(crate) fn debug_stats(&self) -> RoadDebugStats {
        let mut out = RoadDebugStats::default();
        out.vector_capacity_bytes = std::mem::size_of::<Self>()
            + self.cells.capacity() * std::mem::size_of::<Cell>()
            + self.pending.capacity() * std::mem::size_of::<Vec<Packet>>()
            + self.ledger.capacity() * std::mem::size_of::<[f64; 5]>();
        for cell in &self.cells {
            out.cell_packets += cell.packets.len();
            let parts = cell.packets.iter().map(|packet| packet.parts.len()).sum();
            out.cell_parts += parts;
            out.max_cell_parts = out.max_cell_parts.max(parts);
            out.latent_entries += cell.latent.len();
        }
        for queue in &self.pending {
            out.pending_packets += queue.len();
            let parts = queue.iter().map(|packet| packet.parts.len()).sum();
            out.pending_parts += parts;
            out.max_pending_parts = out.max_pending_parts.max(parts);
        }
        // Distinct SharedKeys allocations are physically shared by pointer
        // identity. Count their key payload only once while still counting
        // every packet's independent mass/birth backing and all metadata.
        let mut seen_keys=HashSet::<usize>::new();
        for queue in self.cells.iter().map(|cell| &cell.packets).chain(&self.pending) {
            out.packet_capacity += queue.capacity();
            for packet in queue {
                out.part_capacity += packet.parts.capacity();
                match &packet.parts {
                    PacketParts::SharedKeys{keys,moments,..}=>{
                        out.vector_capacity_bytes+=moments.capacity()
                            .saturating_mul(std::mem::size_of::<(f64,f64)>());
                        if seen_keys.insert(Arc::as_ptr(keys) as usize) {
                            out.vector_capacity_bytes+=keys.capacity()
                                .saturating_mul(std::mem::size_of::<(u32,u32)>())
                                .saturating_add(96); // additional key Arc/control envelope
                        }
                    },
                    _=>out.vector_capacity_bytes+=packet.parts.allocated_bytes(),
                }
                if packet.parts.is_uniform() {
                    out.uniform_packets+=1;
                    out.uniform_parts+=packet.parts.len();
                } else {
                    out.mixed_packets+=1;
                    out.mixed_parts+=packet.parts.len();
                }
            }
        }
        out.vector_capacity_bytes += out.packet_capacity * std::mem::size_of::<Packet>();
        out
    }
    pub(crate) fn restart_metadata_scratch_bytes(&self)->usize{let packets=self.cells.iter().map(|c|c.packets.len()).chain(self.pending.iter().map(Vec::len)).fold(0usize,usize::saturating_add);road_stream_validation_bound(packets,self.cells.len())}
    pub(crate) fn retained_storage_bytes(&self) -> usize {
        let stats = self.debug_stats();
        // Current native std BTreeMap entries are tiny (<=3 classes/cell).
        // Reserve 256 bytes per live entry and an empty root per cell. Add a
        // small per-buffer allocation allowance; this remains structural
        // accounting, not an exact allocator/RSS measurement.
        let buffers = stats
            .cell_packets
            .saturating_add(stats.pending_packets)
            .saturating_add(self.cells.len().saturating_mul(2))
            .saturating_add(3);
        stats
            .vector_capacity_bytes
            .saturating_add(
                stats
                    .latent_entries
                    .saturating_add(self.cells.len())
                    .saturating_mul(256),
            )
            .saturating_add(buffers.saturating_mul(32))
    }
    /// Nonallocating envelope for decoding this state's unchanged wire rows.
    /// Fresh vector capacities are no larger than the retained capacities.
    /// RoadDecodeBudget temporarily charges raw Part rows plus new CorePart
    /// rows before releasing the raw buffer for a Uniform packet. Relative to
    /// the final decoded owner, the largest such overlap is one raw packet;
    /// all preceding packet/tree/outer-vector charges remain retained below.
    pub(crate) fn checkpoint_decode_envelope(&self)->(usize,usize){
        if compact_checkpoint_enabled(){return self.compact_decode_envelope();}
        self.legacy_decode_envelope()
    }
    /// Exact structural owner projection for the actual MFWHOLE2 decoder.
    /// Reuse is ONLY within a queue and only for the preceding shared-key
    /// allocation, exactly as write_packets_compact emits. No optimistic
    /// alias credit across an independently reconstructed snapshot.
    pub(crate) fn compact_decode_envelope(&self)->(usize,usize){
        let cells=self.cells.len();
        let mut owner=std::mem::size_of::<RoadState>().saturating_add(3*32)
            .saturating_add(cells.saturating_mul(std::mem::size_of::<Cell>()+256+2*32+std::mem::size_of::<Vec<Packet>>()))
            .saturating_add(self.ledger.len().saturating_mul(std::mem::size_of::<[f64;5]>()));
        for c in &self.cells{owner=owner.saturating_add(c.latent.len().saturating_mul(256));}
        let mut packets=0usize;
        for queue in self.cells.iter().map(|c|&c.packets).chain(&self.pending){
            let mut previous:Option<&Arc<Vec<(u32,u32)>>>=None;
            packets=packets.saturating_add(queue.len());
            owner=owner.saturating_add(queue.len().saturating_mul(std::mem::size_of::<Packet>()+32));
            for packet in queue{
                let n=packet.parts.len();
                let bytes=match &packet.parts{
                    PacketParts::Uniform{..}=>n.saturating_mul(std::mem::size_of::<CorePart>()),
                    PacketParts::Mixed(_)=>n.saturating_mul(std::mem::size_of::<Part>()),
                    PacketParts::SharedKeys{keys,..}=>{
                        let reuse=previous.is_some_and(|p|Arc::ptr_eq(p,keys));previous=Some(keys);
                        n.saturating_mul(16).saturating_add(if reuse{0}else{n.saturating_mul(8).saturating_add(96)})
                    }
                };owner=owner.saturating_add(bytes);
            }
        }
        (owner,road_stream_validation_bound(packets,cells))
    }
    pub(crate) fn legacy_decode_envelope(&self)->(usize,usize){
        let stats=self.debug_stats();
        let largest_packet = self
            .cells
            .iter()
            .map(|cell| &cell.packets)
            .chain(self.pending.iter())
            .flat_map(|queue| queue.iter())
            .map(|packet| packet.parts.len())
            .max()
            .unwrap_or(0);
        let retained_and_decode = self
            .retained_storage_bytes()
            .saturating_add(largest_packet.saturating_mul(std::mem::size_of::<Part>()));
        // These terms mirror RoadDecodeBudget::reserve's validation increments:
        // 16 per homogeneous part, 32 per packet, and 32 per cell.
        let validation = stats
            .cell_parts
            .saturating_add(stats.pending_parts)
            .saturating_mul(16)
            .saturating_add(
                stats
                    .cell_packets
                    .saturating_add(stats.pending_packets)
                    .saturating_add(self.cells.len())
                    .saturating_mul(32),
            );
        (retained_and_decode, validation)
    }
}
#[derive(Clone)]
struct Motion {
    dx: f64,
    speed: f64,
    v0: f64,
    target: f64,
    tau: f64,
    accel: f64,
    brake: f64,
    latent: BTreeMap<usize, f64>,
    initial: BTreeMap<usize, f64>,
    hazards: BTreeMap<usize, f64>,
}
#[cfg_attr(feature="python-extension", pyclass)]
pub struct V1Road {
    identity: String,
    dt: f64,
    groups: Vec<Vec<f64>>,
    signals: Vec<Option<(f64, f64, f64)>>,
    paths: Vec<Vec<usize>>,
    // Bound on distinct next cells (including terminal) for one immutable head.
    registered_successor_width: usize,
    routes: Vec<(usize, usize)>,
    classes: Vec<Vec<f64>>,
    incoming: Vec<Vec<usize>>,
    windows: Vec<(usize, f64, f64, f64)>,
    record_budget: usize,
    storage_budget: Option<usize>,
    retained_input_bytes: usize,
    service_event_accounting: Option<ServiceEventAccounting>,
    event_resolution: Mutex<EventResolutionStats>,
    event_budget: Option<usize>,
    intervals: bool,
    research_interval_bins:Option<usize>,
    research_rank_bins:Option<usize>,
    research_ready_mass_milli:Option<u64>,
    state: RoadState,
}
// Route registry is validated before this call. A terminal successor uses n.
// A bounded construction-only bitmap avoids quadratic scans and per-edge heaps.
fn registered_successor_width(paths:&[Vec<usize>],n:usize)->usize{
    let words=n.saturating_add(1).div_ceil(64);
    let Some(len)=n.checked_mul(words) else{return n.saturating_add(1)};
    if len>262144{return n.saturating_add(1)}
    let mut bits=Vec::<u64>::new();if bits.try_reserve_exact(len).is_err(){return n.saturating_add(1)}
    bits.resize(len,0);
    for path in paths{
        for pair in path.windows(2){let i=pair[0];let j=pair[1];bits[i*words+j/64]|=1u64<<(j%64);}
        if let Some(&i)=path.last(){bits[i*words+n/64]|=1u64<<(n%64);}
    }
    bits.chunks_exact(words).map(|r|r.iter().map(|w|w.count_ones() as usize).sum()).max().unwrap_or(0)
}
fn val(s: &str) -> CoreError {
    CoreError::value(s.to_owned())
}
fn arithmetic(s: &str) -> CoreError {
    CoreError::arithmetic(s.to_owned())
}
fn budget(s: &str) -> CoreError {
    CoreError::resource(s.to_owned())
}
// Streaming the same expansion, with no vector of raw class observations.
#[derive(Default)]
struct RoadExpansion { p: smallvec::SmallVec<[f64; 4]> }
impl RoadExpansion {
    fn add(&mut self, mut x: f64) {
        let p = &mut self.p;
        let mut i = 0;
        for j in 0..p.len() {
            let mut y = p[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                p[i] = lo;
                i += 1;
            }
            x = hi;
        }
        p.truncate(i);
        if x != 0.0 {
            p.push(x);
        }
    }
    // Checked finite reduction for checkpoint/state validation. The same
    // arithmetic and final rounding as add(), but malformed overflowing
    // inputs cannot manufacture an unbounded list of NaN partials.
    fn add_finite(&mut self,mut x:f64)->CoreResult<()> {
        if !x.is_finite(){return Err(arithmetic("nonfinite validation summand"))}
        let p=&mut self.p;let mut i=0;
        for j in 0..p.len(){
            let mut y=p[j];if x.abs()<y.abs(){std::mem::swap(&mut x,&mut y)}
            let hi=x+y;if !hi.is_finite(){return Err(arithmetic("validation expansion overflow"))}
            let lo=y-(hi-x);if !lo.is_finite(){return Err(arithmetic("validation expansion residual"))}
            if lo!=0.{p[i]=lo;i+=1;}x=hi;
        }
        p.truncate(i);
        if x!=0.{if p.len()==4096{return Err(budget("validation expansion exceeds finite binary64 envelope"))}p.push(x);}
        Ok(())
    }
    fn finish_finite(self)->CoreResult<f64>{let x=self.finish();if x.is_finite(){Ok(x)}else{Err(arithmetic("validation sum overflow"))}}
    fn finish(self) -> f64 {
        let mut p = self.p;
        let mut hi = 0.0;
        let mut lo = 0.0;
        if let Some(x) = p.pop() {
            hi = x;
            while let Some(x) = p.pop() {
                let y = hi;
                hi = y + x;
                lo = x - (hi - y);
                if lo != 0.0 {
                    break;
                }
            }
            if !p.is_empty()
                && ((lo < 0.0 && p[p.len() - 1] < 0.0) || (lo > 0.0 && p[p.len() - 1] > 0.0))
            {
                let y = lo * 2.0;
                let x = hi + y;
                if y == x - hi {
                    hi = x;
                }
            }
        }
        hi
    }
}
fn sum<I: IntoIterator<Item = f64>>(values: I) -> f64 {
    let mut acc = RoadExpansion::default();
    for x in values { acc.add(x); }
    acc.finish()
}
#[derive(Default)]
struct ClassMoments {
    mass: RoadExpansion,
    latent_mass: RoadExpansion,
}
impl ClassMoments {
    fn add(&mut self, mass: f64, latent: f64) {
        self.mass.add(mass);
        self.latent_mass.add(mass * latent);
    }
    fn mean(self) -> f64 { self.latent_mass.finish() / self.mass.finish() }
}
fn finite_nonnegative(x: f64) -> bool {
    x.is_finite() && x >= 0.0
}
fn mass(p: &Packet) -> f64 {
    sum(p.parts.iter().map(|p| p.mass))
}
fn push_checked<T>(rows: &mut Vec<T>, row: T) -> CoreResult<()> {
    if rows.len() == rows.capacity() {
        rows.try_reserve(1)
            .map_err(|_| budget("native road allocation unavailable"))?;
    }
    rows.push(row);
    Ok(())
}
fn clone_packet(packet: &Packet) -> CoreResult<Packet> {
    Ok(Packet {
        target: packet.target,
        parts: packet.parts.clone_checked()?,
    })
}
fn clone_packets(packets: &[Packet]) -> CoreResult<Vec<Packet>> {
    let mut result = checkpoint_vec(packets.len())?;
    for packet in packets {
        result.push(clone_packet(packet)?);
    }
    Ok(result)
}
/// Exact original Part-by-Part served view without allocating the temporary
/// served Vec. The caller must retain original per-row order and sum order.
/// In particular do NOT replace sum(rounded_m_i) by f * sum(m_i).
fn served_parts(parts: &PacketParts, f: f64) -> impl Iterator<Item = Part> + '_ {
    parts.iter().filter_map(move |p| {
        let m = p.mass * f;
        if m > 0.0 {
            let mut q = p;
            q.mass = m;
            q.birth *= f;
            Some(q)
        } else {
            None
        }
    })
}
fn portion(parts: &PacketParts, f: f64) -> CoreResult<Vec<Part>> {
    let mut result = checkpoint_vec(if f == 0.0 { 0 } else { parts.len() })?;
    for p in parts {
        let m = p.mass * f;
        if m > 0.0 {
            let mut q = p.clone();
            q.mass = m;
            q.birth *= f;
            result.push(q);
        }
    }
    Ok(result)
}
/// Two-level bitset of active **source indices**. Its iterator yields exactly
/// the increasing index order formerly provided by a BTreeSet, preserving
/// original per-row floating-point transform and combine reduction order.
///
/// Storage: n/64 words plus n/4096 summary words; operations insert/remove O(1).
/// Iteration O(number of active + ceil(n/4096)) and never allocates.
struct ActiveIndexBits {
    words: Vec<u64>,
    summary: Vec<u64>,
    count: usize,
    universe: usize,
}
struct SetOneBits(u64);
impl Iterator for SetOneBits {
    type Item = usize;
    fn next(&mut self) -> Option<Self::Item> {
        if self.0 == 0 {
            return None;
        }
        let bit = self.0.trailing_zeros() as usize;
        self.0 &= self.0 - 1;
        Some(bit)
    }
}
impl ActiveIndexBits {
    fn new(universe: usize) -> CoreResult<Self> {
        let word_count = universe.div_ceil(64);
        let summary_count = word_count.div_ceil(64);
        let mut words = checkpoint_vec(word_count)?;
        words.resize(word_count, 0);
        let mut summary = checkpoint_vec(summary_count)?;
        summary.resize(summary_count, 0);
        Ok(Self { words, summary, count: 0, universe })
    }
    fn capacity_bytes(&self) -> usize {
        self.words.capacity().saturating_mul(std::mem::size_of::<u64>())
            .saturating_add(self.summary.capacity().saturating_mul(std::mem::size_of::<u64>()))
    }
    fn len(&self) -> usize {
        self.count
    }
    fn insert(&mut self, index: usize) -> bool {
        assert!(index < self.universe, "active interval index out of domain");
        let word = index / 64;
        let mask = 1u64 << (index % 64);
        let old = self.words[word];
        if old & mask != 0 {
            return false;
        }
        self.words[word] = old | mask;
        if old == 0 {
            self.summary[word / 64] |= 1u64 << (word % 64);
        }
        self.count += 1;
        true
    }
    fn remove(&mut self, index: &usize) -> bool {
        if *index >= self.universe {
            return false;
        }
        let word = index / 64;
        let mask = 1u64 << (index % 64);
        let old = self.words[word];
        if old & mask == 0 {
            return false;
        }
        let next = old & !mask;
        self.words[word] = next;
        if next == 0 {
            self.summary[word / 64] &= !(1u64 << (word % 64));
        }
        self.count -= 1;
        true
    }
    fn iter(&self) -> impl Iterator<Item = usize> + '_ {
        self.summary.iter().enumerate().flat_map(move |(group, &word)| {
            SetOneBits(word).flat_map(move |bit| {
                let index = group * 64 + bit;
                SetOneBits(self.words[index]).map(move |subbit| index * 64 + subbit)
            })
        })
    }
}

/// Event-driven selection of the exact original interval row indices.
///
/// Original Riemann interval splitter scans every input Part at every unique
/// endpoint. All interval endpoints are edges, hence pa<=a && pb>=b for the
/// next edge b is exactly pa<=a && pb>a. No new physical closure is introduced.
/// A BTreeSet retains ascending *input indices*, preserving the old selected
/// row order and therefore combine's IEEE fsum tie sequence.
///
/// Point rows are removed from the active interval list altogether. Signed
/// +/- zero endpoints are grouped using the SAME numeric equality as the
/// original edge Vec::dedup, not by f64::to_bits.
/// Count the *actual* source-row event kinds before allocating sweep arrays.
fn count_sweep_row_kinds(parts: &[Part]) -> CoreResult<(usize, usize)> {
    let (mut nonpoint, mut point) = (0usize, 0usize);
    for p in parts {
        let (a, b) = (p.a.unwrap(), p.b.unwrap());
        if a == b {
            point += 1;
        } else if b > a {
            nonpoint += 1;
        } else {
            return Err(val("invalid finite native interval during sweep"));
        }
    }
    Ok((nonpoint, point))
}

/// Actual fixed-size arrays of a valid two-type source partition.
/// Nonpoint rows own start/end entries; point rows own one point entry and
/// can appear in the current_points array. Both groups need active bitsets.
fn exact_sweep_event_index_bytes(n: usize, nonpoint: usize, point: usize) -> usize {
    debug_assert_eq!(nonpoint.checked_add(point), Some(n));
    let ordinal_bytes = if n <= u32::MAX as usize { 4 } else { std::mem::size_of::<usize>() };
    nonpoint.saturating_mul(2 * ordinal_bytes)
        .saturating_add(point.saturating_mul(ordinal_bytes + std::mem::size_of::<usize>()))
        .saturating_add(
            n.div_ceil(64).saturating_add(n.div_ceil(4096))
                .saturating_mul(std::mem::size_of::<u64>()),
        )
        .saturating_add(256)
}

// The immutable input already owns the exact time endpoints. Keep only
// injective source ordinals in each sorted stream, with a wide fallback.
enum SweepOrdinals { Compact(Vec<u32>), Wide(Vec<usize>) }
impl SweepOrdinals {
    fn new(n:usize, capacity:usize) -> CoreResult<Self> {
        if n <= u32::MAX as usize { Ok(Self::Compact(checkpoint_vec(capacity)?)) }
        else { Ok(Self::Wide(checkpoint_vec(capacity)?)) }
    }
    fn push(&mut self,i:usize) {
        match self {Self::Compact(v)=>v.push(u32::try_from(i).expect("bounded ordinal")),
                    Self::Wide(v)=>v.push(i)}
    }
    fn len(&self)->usize {match self {Self::Compact(v)=>v.len(),Self::Wide(v)=>v.len()}}
    #[cfg(test)]
    fn capacity(&self)->usize {match self {Self::Compact(v)=>v.capacity(),Self::Wide(v)=>v.capacity()}}
    fn get(&self,i:usize)->Option<usize> {
        match self {Self::Compact(v)=>v.get(i).map(|&i|i as usize),Self::Wide(v)=>v.get(i).copied()}
    }
    fn sort(&mut self,time:impl Fn(usize)->f64) {
        let cmp=|a:usize,b:usize|time(a).total_cmp(&time(b)).then(a.cmp(&b));
        match self {Self::Compact(v)=>v.sort_unstable_by(|&a,&b|cmp(a as usize,b as usize)),
                    Self::Wide(v)=>v.sort_unstable_by(|&a,&b|cmp(a,b))}
    }
}

struct IntervalActiveSweep<'a> {
    parts: &'a [Part],
    starts: SweepOrdinals,
    ends: SweepOrdinals,
    points: SweepOrdinals,
    active: ActiveIndexBits,
    current_points: Vec<usize>,
    next_start: usize,
    next_end: usize,
    next_point: usize,
}

impl<'a> IntervalActiveSweep<'a> {
    #[cfg(test)]
    fn new(parts: &'a [Part]) -> CoreResult<Self> {
        let (nonpoint, point) = count_sweep_row_kinds(parts)?;
        Self::new_counted(parts, nonpoint, point)
    }

    fn new_counted(parts: &'a [Part], nonpoint: usize, point: usize) -> CoreResult<Self> {
        debug_assert_eq!(nonpoint.checked_add(point), Some(parts.len()));
        let mut starts = SweepOrdinals::new(parts.len(),nonpoint)?;
        let mut ends = SweepOrdinals::new(parts.len(),nonpoint)?;
        let mut points = SweepOrdinals::new(parts.len(),point)?;
        for (i, p) in parts.iter().enumerate() {
            let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
            if pa == pb { points.push(i); }
            else if pb > pa { starts.push(i); ends.push(i); }
            else { return Err(val("invalid finite native interval during sweep")); }
        }
        starts.sort(|i|parts[i].a.unwrap());
        ends.sort(|i|parts[i].b.unwrap());
        points.sort(|i|parts[i].a.unwrap());
        Ok(Self {
            parts,starts, ends, points,
            active: ActiveIndexBits::new(parts.len())?,
            current_points: checkpoint_vec(point)?,
            next_start: 0, next_end: 0, next_point: 0,
        })
    }

    fn advance(&mut self, a: f64) {
        while let Some(i)=self.ends.get(self.next_end) {
            if self.parts[i].b.unwrap()>a {break}
            self.active.remove(&i);self.next_end+=1;
        }
        while let Some(i)=self.starts.get(self.next_start) {
            if self.parts[i].a.unwrap()>a {break}
            self.active.insert(i);self.next_start+=1;
        }
        self.current_points.clear();
        while let Some(i)=self.points.get(self.next_point) {
            let time=self.parts[i].a.unwrap();
            if time>a {break}
            if time==a {self.current_points.push(i);}
            self.next_point+=1;
        }
        self.current_points.sort_unstable();
    }
}

/// Iterate unique numeric endpoint classes of three already sorted event
/// streams. Exactly the original sort_unstable(total_cmp)+dedup(PartialEq)
/// order: the zero representative must use -0 when any original endpoint
/// has the negative-zero sign bit, including a point with a=+0,b=-0.
fn visit_unique_sweep_edges(
    sweep: &IntervalActiveSweep,
    has_negative_zero: bool,
    mut emit: impl FnMut(f64) -> CoreResult<()>,
) -> CoreResult<usize> {
    let streams = [
        &sweep.starts, &sweep.ends, &sweep.points,
    ];
    let endpoint=|j:usize,i:usize| {
        if j==1 {sweep.parts[i].b.unwrap()} else {sweep.parts[i].a.unwrap()}
    };
    let mut offsets = [0usize; 3];
    let mut count=0usize;
    loop {
        let mut next: Option<f64> = None;
        for j in 0..3 {
            if let Some(i)=streams[j].get(offsets[j]) {
                let value=endpoint(j,i);
                if next.map_or(true, |prior| value.total_cmp(&prior).is_lt()) {
                    next=Some(value);
                }
            }
        }
        let Some(time) = next else {break};
        let canonical = if time == 0.0 && has_negative_zero { -0.0 } else {time};
        emit(canonical)?;
        count += 1;
        for j in 0..3 {
            while streams[j].get(offsets[j])
                .is_some_and(|i| endpoint(j,i) == time) {
                offsets[j] += 1;
            }
        }
    }
    Ok(count)
}

fn unique_sweep_edges(
    parts: &[Part],
    sweep: &IntervalActiveSweep,
    before_allocate: impl FnOnce(usize) -> CoreResult<()>,
) -> CoreResult<Vec<f64>> {
    let neg_zero_bits=(-0.0f64).to_bits();
    let has_negative_zero=parts.iter().any(|p|p.a.0==neg_zero_bits || p.b.0==neg_zero_bits);
    let unique_count=visit_unique_sweep_edges(sweep,has_negative_zero, |_|Ok(()))?;
    before_allocate(unique_count.saturating_mul(std::mem::size_of::<f64>()))?;
    let mut edges=checkpoint_vec(unique_count)?;
    let built=visit_unique_sweep_edges(sweep,has_negative_zero,|value|{
        edges.push(value);
        Ok(())
    })?;
    debug_assert_eq!(built,unique_count);
    Ok(edges)
}

/// Diagnostic census of adjacent non-point interval packets [a,b],[b,c] in one
/// cell's entry output: rows whose (tag, offset) recur in the next packet, and
/// those whose time density mass/(b-a) is bit-equal (a necessary condition for
/// any exact time-merge). Counting only; never changes packets.
fn interval_merge_census(out: &[Packet]) {
    let span = |p: &Packet| {
        p.parts
            .iter()
            .next()
            .and_then(|x| Some((x.a.unwrap(), x.b.unwrap())))
    };
    let mut prev: Option<(f64, f64, BTreeMap<(usize, usize), u64>)> = None;
    for packet in out {
        let Some((a, b)) = span(packet) else { continue };
        if !(b > a) {
            continue;
        }
        let mut here = BTreeMap::new();
        for x in packet.parts.iter() {
            here.insert((x.tag, x.offset), (x.mass / (b - a)).to_bits());
        }
        if let Some((pa, pb, ref before)) = prev {
            if pb == a && pb > pa {
                let mut same_key = 0u64;
                let mut same_density = 0u64;
                for (k, d) in &here {
                    if let Some(d0) = before.get(k) {
                        same_key += 1;
                        same_density += u64::from(d0 == d);
                    }
                }
                crate::v1_trace::add("merge.adjacent_rows", here.len() as u64);
                crate::v1_trace::add("merge.same_key_rows", same_key);
                crate::v1_trace::add("merge.equal_density_rows", same_density);
            }
        }
        prev = Some((a, b, here));
    }
}
fn interval_merge_census_ordered(out:&[Packet])->CoreResult<()> {
    let mut prev:Option<(&Packet,f64,f64)>=None;
    for packet in out {
        let Some(first)=packet.parts.iter().next() else{continue};
        let (a,b)=(first.a.unwrap(),first.b.unwrap());
        if !(b>a) {continue}
        // Verify rather than assume the precondition of the linear intersection.
        let mut last=None;
        for p in &packet.parts {
            let k=(p.tag,p.offset);
            if last.is_some_and(|old|old>=k) {
                return Err(arithmetic("interval diagnostic ordered unique keys differ"));
            }
            last=Some(k);
        }
        if let Some((old,pa,pb))=prev {
            if pb==a && pb>pa {
                let mut before=old.parts.iter().peekable();
                let mut same_key=0u64;
                let mut same_density=0u64;
                for p in &packet.parts {
                    let key=(p.tag,p.offset);
                    while before.peek().is_some_and(|q|(q.tag,q.offset)<key) {before.next();}
                    if let Some(q)=before.peek() {
                        if (q.tag,q.offset)==key {
                            same_key+=1;
                            same_density+=u64::from((q.mass/(pb-pa)).to_bits()==(p.mass/(b-a)).to_bits());
                        }
                    }
                }
                crate::v1_trace::add("merge.adjacent_rows",packet.parts.len() as u64);
                crate::v1_trace::add("merge.same_key_rows",same_key);
                crate::v1_trace::add("merge.equal_density_rows",same_density);
            }
        }
        prev=Some((packet,a,b));
    }
    Ok(())
}
/// Diagnostic: group one cell's incoming rows by non-point interval (a,b) and
/// count maximal runs of time-contiguous intervals whose contributing source
/// set {(cell, head position, rate bits)} is identical. Such runs have
/// proportional route mixtures and equal ready time, so they are exactly
/// mergeable in real arithmetic. Counting only.
fn exact_merge_census(parts: impl Iterator<Item=Part>, src: &[(usize, usize, u64)]) {
    use std::collections::BTreeSet;
    let mut by: BTreeMap<(u64, u64), BTreeSet<(usize, usize, u64)>> = BTreeMap::new();
    let mut points = 0u64;
    for (p, s) in parts.zip(src) {
        let (a, b) = (p.a.unwrap_or(f64::NAN), p.b.unwrap_or(f64::NAN));
        if !(b > a) {
            points += 1;
            continue;
        }
        by.entry((a.to_bits(), b.to_bits())).or_default().insert(*s);
    }
    let mut runs = 0u64;
    let mut prev: Option<(f64, &BTreeSet<(usize, usize, u64)>)> = None;
    let mut ordered: Vec<(f64, f64, &BTreeSet<(usize, usize, u64)>)> = by
        .iter()
        .map(|((a, b), set)| (f64::from_bits(*a), f64::from_bits(*b), set))
        .collect();
    ordered.sort_by(|x, y| x.0.total_cmp(&y.0).then(x.1.total_cmp(&y.1)));
    for (a, b, set) in &ordered {
        let continues = matches!(prev, Some((pb, ps)) if pb == *a && ps == *set);
        if !continues {
            runs += 1;
        }
        prev = Some((*b, set));
    }
    crate::v1_trace::add("exact.intervals", ordered.len() as u64);
    crate::v1_trace::add("exact.runs", runs);
    crate::v1_trace::add("exact.point_rows", points);
}
/// Each source-part row is otherwise 48B because two unbounded usize
/// indexes are retained. In an original capped V03 run the route registry
/// and every path extent are checked to fit u32, so transient incoming rows
/// can use 40B without losing any Part or IEEE-754 endpoint bits.
#[derive(Clone,Copy)]
struct CompactIncomingPart {
    tag:u32,
    offset:u32,
    mass:f64,
    birth:f64,
    a:PackedTime,
    b:PackedTime,
}
impl CompactIncomingPart {
    fn try_new(p:Part)->Option<Self> {
        Some(Self {
            tag:u32::try_from(p.tag).ok()?,
            offset:u32::try_from(p.offset).ok()?,
            mass:p.mass,birth:p.birth,a:p.a,b:p.b,
        })
    }
    fn unpack(self)->Part {
        Part {
            tag:self.tag as usize,offset:self.offset as usize,
            mass:self.mass,birth:self.birth,a:self.a,b:self.b,
        }
    }
}

/// True original append order is preserved in either mode. Full Part storage
/// remains the fallback if the original registry does not support u32 indexes.
const INCOMING_PART_CHUNK:usize=128;
#[derive(Default)]
struct ChunkedParts {
    chunks:Vec<Vec<Part>>,
    compact_chunks:Vec<Vec<CompactIncomingPart>>,
    compressed:bool,
    len:usize,
}
impl ChunkedParts {
    fn new(compressed:bool)->Self {Self{compressed,..Self::default()}}
    fn len(&self)->usize {self.len}
    fn is_empty(&self)->bool {self.len==0}
    fn capacity(&self)->usize {
        if self.compressed {
            self.compact_chunks.iter().map(Vec::capacity).sum()
        } else {
            self.chunks.iter().map(Vec::capacity).sum()
        }
    }
    fn descriptor_capacity(&self)->usize {
        if self.compressed {self.compact_chunks.capacity()}else{self.chunks.capacity()}
    }
    fn physical_capacity_bytes(&self)->usize {
        self.capacity().saturating_mul(if self.compressed {
            std::mem::size_of::<CompactIncomingPart>()
        } else {
            std::mem::size_of::<Part>()
        })
    }
    fn iter(&self)->impl Iterator<Item=Part>+'_ {
        self.chunks.iter().flat_map(|c|c.iter().copied())
            .chain(self.compact_chunks.iter().flat_map(|c|c.iter().copied().map(CompactIncomingPart::unpack)))
    }
    fn get(&self,i:usize)->Part {
        if self.compressed {
            self.compact_chunks[i/INCOMING_PART_CHUNK][i%INCOMING_PART_CHUNK].unpack()
        } else {
            self.chunks[i/INCOMING_PART_CHUNK][i%INCOMING_PART_CHUNK]
        }
    }
    fn push_checked(&mut self,p:Part)->CoreResult<()> {
        if self.compressed {
            let encoded=CompactIncomingPart::try_new(p).ok_or_else(||
                arithmetic("compact incoming source index contract differs"))?;
            if self.compact_chunks.last().is_none_or(|c|c.len()==INCOMING_PART_CHUNK) {
                let page=checkpoint_vec(INCOMING_PART_CHUNK)?;
                if page.capacity()!=INCOMING_PART_CHUNK {
                    return Err(budget("compact incoming fixed page capacity differs"));
                }
                push_checked(&mut self.compact_chunks,page)?;
            }
            self.compact_chunks.last_mut().expect("compact incoming page allocated").push(encoded);
        } else {
            if self.chunks.last().is_none_or(|c|c.len()==INCOMING_PART_CHUNK) {
                let page=checkpoint_vec(INCOMING_PART_CHUNK)?;
                if page.capacity()!=INCOMING_PART_CHUNK {
                    return Err(budget("incoming fixed page capacity not supported"));
                }
                push_checked(&mut self.chunks,page)?;
            }
            self.chunks.last_mut().expect("original incoming page allocated").push(p);
        }
        self.len+=1;
        Ok(())
    }
    fn extend_parts(&mut self,parts:impl IntoIterator<Item=Part>)->CoreResult<()> {
        for p in parts {self.push_checked(p)?;}
        Ok(())
    }
}

/// Same append-only bounded pages for the independent pair of Mark f64
/// fields. Each Mark stays aligned by logical index with one incoming Part.
#[derive(Default)]
struct ChunkedMarks {
    chunks: Vec<Vec<Mark>>,
    len: usize,
}
impl ChunkedMarks {
    fn len(&self) -> usize { self.len }
    fn capacity(&self) -> usize { self.chunks.iter().map(Vec::capacity).sum() }
    fn iter(&self) -> impl Iterator<Item=&Mark> {
        self.chunks.iter().flat_map(|c| c.iter())
    }
    fn push_checked(&mut self, mark: Mark) -> CoreResult<()> {
        if self.chunks.last().is_none_or(|c| c.len()==INCOMING_PART_CHUNK) {
            let chunk=checkpoint_vec(INCOMING_PART_CHUNK)?;
            if chunk.capacity()!=INCOMING_PART_CHUNK {
                return Err(budget("mark fixed page capacity not supported"));
            }
            push_checked(&mut self.chunks,chunk)?;
        }
        self.chunks.last_mut().expect("mark chunk just allocated").push(mark);
        self.len+=1;
        Ok(())
    }
}

/// Conservative upper bound from the allocations actually used by ChunkedParts.
/// Both Part and Mark values occupy stable B-row pages: at most (B-1)
/// unused slots per cell in each. Count two outer Vec descriptor families,
/// each with the original conservative doubling allowance. This is a scoped structural source bound, not RSS.
fn segmented_incoming_charge_for(rows:usize,cells:usize,compressed:bool)->usize {
    if rows==0 {return 0;}
    let part_bytes=if compressed {
        std::mem::size_of::<CompactIncomingPart>()
    } else {
        std::mem::size_of::<Part>()
    };
    let mark_bytes=std::mem::size_of::<Mark>();
    let part_header_bytes=std::mem::size_of::<Vec<Part>>();
    let mark_header_bytes=std::mem::size_of::<Vec<Mark>>();
    let page_slots=rows.saturating_add(
        cells.saturating_mul(INCOMING_PART_CHUNK-1),
    );
    let max_chunks=rows.div_ceil(INCOMING_PART_CHUNK).saturating_add(cells);
    page_slots.saturating_mul(part_bytes.saturating_add(mark_bytes))
        .saturating_add(max_chunks.saturating_mul(
            2*(part_header_bytes+mark_header_bytes),
        ))
}
fn segmented_incoming_charge(rows:usize,cells:usize)->usize {
    segmented_incoming_charge_for(rows,cells,false)
}

/// The source's append-only raw Part and Mark containers each allocate exact
/// B=128 row pages only when that particular destination crosses a boundary.
/// Predict the exact number of live physical pages using source-cell rows;
/// preserve the original conservatively doubled Vec-of-page header envelope.
/// Include the newly allocated source-cell counter Vec and control padding.
fn segmented_incoming_exact_cell_pages_charge(
    rows:usize,cells:usize,live_pages:usize,compressed:bool,
    actual_frozen_descriptor_bytes:Option<usize>,
)->usize {
    let part_bytes=if compressed {
        std::mem::size_of::<CompactIncomingPart>()
    } else {
        std::mem::size_of::<Part>()
    };
    let marks=std::mem::size_of::<Mark>();
    let tracked_cell_vec= cells.saturating_mul(std::mem::size_of::<usize>())
        .saturating_add(128);
    let payload=live_pages.saturating_mul(INCOMING_PART_CHUNK)
        .saturating_mul(part_bytes.saturating_add(marks));
    // Retain original old+grown header allowance DURING appends. After
    // the last physical source Part+Mark append, actual fixed descriptor
    // Vec capacity replaces that fictitious future growth, with no cap change.
    let original_descriptor_envelope=if let Some(actual)=actual_frozen_descriptor_bytes {
        actual
    } else if rows==0 {0}else{
        rows.div_ceil(INCOMING_PART_CHUNK).saturating_add(cells)
            .saturating_mul(2*(std::mem::size_of::<Vec<Part>>()
                              +std::mem::size_of::<Vec<Mark>>()))
    };
    tracked_cell_vec.saturating_add(payload)
        .saturating_add(original_descriptor_envelope)
}

/// This ONLY receives raw source buffers whose last original read already
/// happened. Combine, original weighted speed and latent Mark reductions
/// must have completed before calling it. Keeping the actual owner arguments
/// makes the lifetime proof executable: the pages are dropped before work
/// accounting may reduce its conservative source-row count.
fn release_consumed_incoming_pair(
    work:&mut RoadWorkBudget,
    cell:usize,
    raw:ChunkedParts,
    marks:ChunkedMarks,
)->CoreResult<usize> {
    let rows=raw.len();
    if marks.len()!=rows {
        return Err(arithmetic("expired incoming Part/Mark page lengths differ"));
    }
    if rows>work.incoming {
        return Err(arithmetic("expired raw rows exceed cumulative charged work"));
    }
    let released_payload=raw.physical_capacity_bytes().saturating_add(
        marks.capacity().saturating_mul(std::mem::size_of::<Mark>()),
    );
    let released_descriptors=raw.descriptor_capacity()
        .saturating_mul(std::mem::size_of::<Vec<Part>>())
        .saturating_add(marks.chunks.capacity()
            .saturating_mul(std::mem::size_of::<Vec<Mark>>()));
    drop(raw);
    drop(marks);
    work.release_incoming(cell,rows)?;
    if let Some(actual)=work.incoming_descriptor_live_bytes.as_mut() {
        *actual=actual.checked_sub(released_descriptors).ok_or_else(||
            arithmetic("released Part Mark descriptor capacity exceeded current physical owners"))?;
    }
    crate::v1_trace::add("road_work.expired_source_rows",rows as u64);
    crate::v1_trace::add("road_work.expired_source_payload_bytes",released_payload as u64);
    Ok(rows)
}


/// Full per-step control storage including fixed-page allocation allowances,
/// its carrier and the additional per-cell timed row shells. The module's
/// append projection includes old+new descriptor capacity during growth.
fn timed_control_storage_bound(
    controls:&TimedIncomingControls,additional:usize,cells:usize,
)->CoreResult<usize> {
    let rows=controls.len().checked_add(additional)
        .ok_or_else(||budget("timed incoming control count overflow"))?;
    Ok(controls.projected_append_bytes(additional)?
        .saturating_add(rows.div_ceil(INCOMING_PART_CHUNK).saturating_mul(32))
        .saturating_add(std::mem::size_of::<TimedIncomingControls>())
        .saturating_add(cells.saturating_mul(std::mem::size_of::<TimedIncomingRows>()))
        .saturating_add(128))
}
fn timed_incoming_page_charge(cells:usize,pages:usize,descriptors:Option<usize>)->usize {
    pages.saturating_mul(INCOMING_PART_CHUNK).saturating_mul(32)
        .saturating_add(pages.saturating_mul(32))
        .saturating_add(descriptors.unwrap_or_else(||
            pages.saturating_mul(3).saturating_add(cells)
                .saturating_mul(std::mem::size_of::<Vec<Part>>())))
        .saturating_add(cells.saturating_mul(std::mem::size_of::<usize>()))
        .saturating_add(128)
}
// Splitting one destination into ordered reference and owned tails adds at
// most one page: ceil(r/B)+ceil(o/B)<=ceil((r+o)/B)+1. Charge that full 32 B x
// B page even when empty, allocator metadata, and four extra descriptor slots
// per destination (existing 3*pages+cells bound applied to both vectors).
// Each stored reference uses 12 B; retained savings only for its LIVE row,
// never any assumed page slack. Frozen descriptor capacities remain charged.
fn referenced_incoming_page_charge(base:usize,cells:usize,refs:usize)->usize {
    let extra=INCOMING_PART_CHUNK*32+32+4*std::mem::size_of::<Vec<Part>>();
    // Fail closed if any term overflows the physical address domain.
    cells.checked_mul(extra).and_then(|overhead|base.checked_add(overhead))
        .and_then(|bytes|refs.checked_mul(20).and_then(|saved|bytes.checked_sub(saved)))
        .unwrap_or(usize::MAX)
}
// The original ref envelope includes full raw reference pages and owned
// tail slack. Add a separate reusable raw staging page per destination;
// credit only completed encoded blocks, whose exact capacity never exceeds
// a raw page. All block descriptors remain in the original envelope.
fn packed_reference_charge(base:usize,cells:usize,saved:usize)->usize{
    cells.checked_mul(INCOMING_PART_CHUNK*12+32).and_then(|v|base.checked_add(v)).and_then(|v|v.checked_sub(saved)).unwrap_or(usize::MAX)
}
fn lock_completed_timed_incoming(
    work:&mut RoadWorkBudget,rows:&[TimedIncomingRows],controls:&TimedIncomingControls,
)->CoreResult<()> {
    let tracked=work.incoming_cell_rows.as_ref()
        .ok_or_else(||arithmetic("timed incoming requires a bounded source census"))?;
    if rows.len()!=tracked.len() || work.incoming_descriptor_live_bytes.is_some() {
        return Err(arithmetic("timed incoming destination registry differs"));
    }
    let mut count=0usize;let mut pages=0usize;let mut descriptors=0usize;
    let mut reference_count=0usize;
    for (cell,&expected) in rows.iter().zip(tracked) {
        let refs=cell.referenced_len();
        let owned=cell.len()-refs;
        reference_count=reference_count.saturating_add(refs);
        let physical_pages=refs.div_ceil(INCOMING_PART_CHUNK)+owned.div_ceil(INCOMING_PART_CHUNK);
        if cell.len()!=expected || cell.capacity()!=physical_pages*INCOMING_PART_CHUNK {
            return Err(arithmetic("timed incoming fixed-page census differs"));
        }
        count=count.saturating_add(cell.len());
        pages=pages.saturating_add(expected.div_ceil(INCOMING_PART_CHUNK));
        descriptors=descriptors.saturating_add(cell.descriptor_capacity()
            .saturating_mul(std::mem::size_of::<Vec<Part>>()));
    }
    if count!=work.incoming || pages!=work.incoming_live_pages
        || reference_count!=work.timed_referenced_rows.unwrap_or(0) {
        return Err(arithmetic("timed incoming source preflight differs from actual pages"));
    }
    if let Some(saved)=work.packed_ref_saved{let actual=rows.iter().map(TimedIncomingRows::packed_saved_bytes).sum::<usize>();if saved!=actual{return Err(arithmetic("packed reference credit census differs"))}crate::v1_trace::add("incoming_timed.sealed_block_credit_bytes",saved as u64);}
    work.timed_incoming_control_bytes=Some(timed_control_storage_bound(controls,0,rows.len())?);
    work.incoming_descriptor_live_bytes=Some(descriptors);
    let physical=rows.iter().map(TimedIncomingRows::physical_capacity_bytes).sum::<usize>()
        .saturating_add(controls.physical_capacity_bytes());
    let legacy=pages.saturating_mul(INCOMING_PART_CHUNK)
        .saturating_mul(std::mem::size_of::<CompactIncomingPart>()+std::mem::size_of::<Mark>());
    crate::v1_trace::add("incoming_timed.logical_rows",count as u64);
    crate::v1_trace::add("incoming_timed.event_referenced_rows",reference_count as u64);
    crate::v1_trace::add("incoming_timed.control_rows",controls.len() as u64);
    crate::v1_trace::add("incoming_timed.physical_payload_bytes",physical as u64);
    crate::v1_trace::add("incoming_timed.legacy_part_mark_payload_bytes",legacy as u64);
    crate::v1_trace::add("incoming_timed.saved_payload_bytes",legacy.saturating_sub(physical) as u64);
    Ok(())
}
fn release_consumed_timed_incoming(
    work:&mut RoadWorkBudget,cell:usize,timed:TimedIncomingRows,
)->CoreResult<usize> {
    let rows=timed.len();
    if work.timed_incoming_control_bytes.is_none() {
        return Err(arithmetic("timed incoming source requires its control table charge"));
    }
    let descriptor_bytes=timed.descriptor_capacity().saturating_mul(std::mem::size_of::<Vec<Part>>());
    let payload=timed.physical_capacity_bytes();
    let ref_rows=timed.referenced_len();
    let saved=timed.packed_saved_bytes();
    // This owner is consumed only AFTER all ordered physical moments and
    // source-indexed combine reads have completed.
    drop(timed);
    if let Some(refs)=&mut work.timed_referenced_rows {
        *refs=refs.checked_sub(ref_rows).ok_or_else(||arithmetic("released reference count exceeds census"))?;
    }
    if let Some(total)=&mut work.packed_ref_saved{*total=total.checked_sub(saved).ok_or_else(||arithmetic("expired packed reference credit differs"))?;}
    work.release_incoming(cell,rows)?;
    let descriptors=work.incoming_descriptor_live_bytes.as_mut()
        .ok_or_else(||arithmetic("timed incoming descriptors must be frozen before consume"))?;
    *descriptors=descriptors.checked_sub(descriptor_bytes)
        .ok_or_else(||arithmetic("timed incoming released descriptor count differs"))?;
    crate::v1_trace::add("road_work.expired_source_rows",rows as u64);
    crate::v1_trace::add("incoming_timed.expired_source_payload_bytes",payload as u64);
    Ok(rows)
}

// The index sort and at most one combined Part per source row coexist.
fn receiving_local_combine_scratch(rows: usize, classes: usize) -> usize {
    // Conservative finite-binary64 expansion/map allowance. An expansion
    // has nonoverlapping nonzero terms in the finite binary exponent range;
    // 4096 f64 slots per accumulator exceed the number of binary positions.
    // Include growth overlap and simultaneous class and mass/birth sums.
    let expansion = (classes.saturating_add(2)).saturating_mul(128 * 1024);
    rows.saturating_mul(std::mem::size_of::<usize>() + std::mem::size_of::<Part>())
        .saturating_add(expansion)
}

/// The original combine key, source-index tie order and sum() operations
/// evaluated against stable page indices without flattening the source.
fn combine_chunked_parts(parts: &ChunkedParts) -> CoreResult<Vec<Part>> {
    combine_indexed_parts(parts.len(),|i|parts.get(i))
}

fn combine_indexed_parts(
    len:usize,get:impl Fn(usize)->Part,
)->CoreResult<Vec<Part>> {
    combine_indexed_impl(len,get,|i|i,|i|i,|_,_|Ok(()))
}

// In the indexed lane, retain 32-bit source ordinals only if the complete
// source fits. The comparator and reduction order are unchanged.
fn combine_compact_indexed_parts(
    len:usize,get:impl Fn(usize)->Part,
    mut preflight:impl FnMut(usize,usize)->CoreResult<()>,
)->CoreResult<Vec<Part>> {
    if len <= u32::MAX as usize {
        combine_indexed_impl(len,get,|i|i as u32,|i|i as usize,
            |index_bytes,groups|preflight(index_bytes,groups))
    } else {
        combine_indexed_impl(len,get,|i|i,|i|i,
            |index_bytes,groups|preflight(index_bytes,groups))
    }
}

fn combine_indexed_impl<I:Copy+Ord>(
    len:usize,get:impl Fn(usize)->Part,
    encode:impl Fn(usize)->I,decode:impl Fn(I)->usize,
    mut preflight:impl FnMut(usize,usize)->CoreResult<()>,
)->CoreResult<Vec<Part>> {
    let key = |p: &Part| {
        (p.tag, p.offset, p.a.map_or(u64::MAX, f64::to_bits),
         p.b.map_or(u64::MAX, f64::to_bits))
    };
    preflight(len.saturating_mul(std::mem::size_of::<I>()),0)?;
    let mut indices=checkpoint_vec(len)?;
    indices.extend((0..len).filter(|&i|get(i).mass > 0.0).map(&encode));
    indices.sort_unstable_by(|&a,&b| {
        key(&get(decode(a))).cmp(&key(&get(decode(b)))).then(a.cmp(&b))
    });
    let groups = usize::from(!indices.is_empty())
        + indices.windows(2)
            .filter(|p|key(&get(decode(p[0]))) != key(&get(decode(p[1]))))
            .count();
    preflight(indices.capacity().saturating_mul(std::mem::size_of::<I>()),groups)?;
    let mut out=checkpoint_vec(groups)?;
    let mut start=0;
    while start < indices.len() {
        let mut end=start+1;
        while end < indices.len()
            && key(&get(decode(indices[start])))==key(&get(decode(indices[end]))) {
            end+=1;
        }
        let mut item=get(decode(indices[start]));
        item.mass=sum(indices[start..end].iter().map(|&i|get(decode(i)).mass));
        item.birth=sum(indices[start..end].iter().map(|&i|get(decode(i)).birth));
        out.push(item);
        start=end;
    }
    out.sort_unstable_by(|a,b| {
        a.tag.cmp(&b.tag).then(a.offset.cmp(&b.offset))
            .then(a.a.unwrap_or(-1.0).total_cmp(&b.a.unwrap_or(-1.0)))
            .then(a.b.unwrap_or(-1.0).total_cmp(&b.b.unwrap_or(-1.0)))
    });
    Ok(out)
}

fn combine(parts: Vec<Part>) -> CoreResult<Vec<Part>> {
    let key = |p: &Part| {
        (
            p.tag,
            p.offset,
            p.a.map_or(u64::MAX, f64::to_bits),
            p.b.map_or(u64::MAX, f64::to_bits),
        )
    };
    let mut indices = checkpoint_vec(parts.len())?;
    indices.extend((0..parts.len()).filter(|&i| parts[i].mass > 0.0));
    // Group order is the old BTreeMap key order; original index is the tie
    // breaker, preserving the exact sequence fed to fsum within every group.
    // An index sort needs no per-key Vec<Part> or BTreeMap node allocations.
    indices.sort_unstable_by(|&a, &b| key(&parts[a]).cmp(&key(&parts[b])).then(a.cmp(&b)));
    // Reserve only the resulting groups. Reserving the input count would keep
    // a huge sparse allocation when many source rows share one exact key.
    let groups = usize::from(!indices.is_empty())
        + indices
            .windows(2)
            .filter(|pair| key(&parts[pair[0]]) != key(&parts[pair[1]]))
            .count();
    let mut out = checkpoint_vec(groups)?;
    let mut start = 0;
    while start < indices.len() {
        let mut end = start + 1;
        while end < indices.len() && key(&parts[indices[start]]) == key(&parts[indices[end]]) {
            end += 1;
        }
        let mut part = parts[indices[start]].clone();
        part.mass = sum(indices[start..end].iter().map(|&i| parts[i].mass));
        part.birth = sum(indices[start..end].iter().map(|&i| parts[i].birth));
        out.push(part);
        start = end;
    }
    // Every valid output key is unique, so an allocation-free unstable sort
    // has the same canonical order as the previous stable sort.
    out.sort_unstable_by(|a, b| {
        a.tag
            .cmp(&b.tag)
            .then(a.offset.cmp(&b.offset))
            .then(a.a.unwrap_or(-1.0).total_cmp(&b.a.unwrap_or(-1.0)))
            .then(a.b.unwrap_or(-1.0).total_cmp(&b.b.unwrap_or(-1.0)))
    });
    Ok(out)
}
/// Shared exact source-order reduction for all non-point output intervals.
/// One output row is constructed per combined key, so the production mapper
/// can allocate CorePart directly without also allocating final Vec<Part>.
fn combine_interval_mapped<T>(
    parts: &[Part],
    selected: impl Iterator<Item = usize>,
    selected_count: usize,
    a: f64,
    b: f64,
    mut encode: impl FnMut(Part) -> T,
) -> CoreResult<Vec<T>> {
    let width = b - a;
    let mut indices = checkpoint_vec(selected_count)?;
    for i in selected {
        let p = parts[i];
        let duration = p.b.unwrap() - p.a.unwrap();
        if p.mass * width / duration > 0.0 {
            indices.push(i);
        }
    }
    // All selected rows get precisely the same (a,b) binary patterns.
    // With the original source-index tie key, sorting tag/offset/index is
    // exactly the previous combine's tag/offset/a_bits/b_bits/index key.
    indices.sort_unstable_by(|&i, &j| {
        (parts[i].tag, parts[i].offset, i).cmp(&(parts[j].tag, parts[j].offset, j))
    });
    let key = |i: usize| (parts[i].tag, parts[i].offset);
    let groups = usize::from(!indices.is_empty())
        + indices.windows(2).filter(|w| key(w[0]) != key(w[1])).count();
    let mut out = checkpoint_vec(groups)?;
    let (aa, bb) = (PackedTime::new(Some(a))?, PackedTime::new(Some(b))?);
    let mut start = 0;
    while start < indices.len() {
        let mut end = start + 1;
        while end < indices.len() && key(indices[start]) == key(indices[end]) {
            end += 1;
        }
        let mut p = parts[indices[start]];
        p.mass = sum(indices[start..end].iter().map(|&i| {
            let x = parts[i];
            x.mass * width / (x.b.unwrap() - x.a.unwrap())
        }));
        p.birth = sum(indices[start..end].iter().map(|&i| {
            let x = parts[i];
            x.birth * width / (x.b.unwrap() - x.a.unwrap())
        }));
        p.a = aa;
        p.b = bb;
        out.push(encode(p));
        start = end;
    }
    // The source sort already produces original canonical tag/offset order,
    // with identical endpoint bits for every row. No extra output sorting.
    Ok(out)
}

fn combine_interval_view(
    parts: &[Part],
    selected: impl Iterator<Item = usize>,
    selected_count: usize,
    a: f64,
    b: f64,
) -> CoreResult<Vec<Part>> {
    combine_interval_mapped(parts, selected, selected_count, a, b, |p|p)
}

/// Production direct-core construction: no simultaneous Vec<Part> combined
/// rows and Vec<CorePart> packed rows. Same per-row IEEE sums and output order.
fn combine_interval_core(
    parts: &[Part],
    selected: impl Iterator<Item = usize>,
    selected_count: usize,
    a: f64,
    b: f64,
) -> CoreResult<Vec<CorePart>> {
    combine_interval_mapped(parts, selected, selected_count, a, b, compact_core_part)
}

// Canonical combined input is sorted by tag/offset before any interval
// selection. Its ascending active indices therefore already give the same
// grouping and tie order as the legacy per-edge sort. A two-pass census
// allocates only the exact output cardinality. In the compact lane large
// adjacent packets may share their full immutable key array, without first
// constructing a CorePart Vec or copying a previous packet.
fn ordered_interval_packet<I: Iterator<Item=usize>>(
    parts:&[Part], selected:impl Fn()->I, a:f64,b:f64,
    previous:Option<&Arc<Vec<(u32,u32)>>>,
    before_allocate:impl FnOnce(usize)->CoreResult<()>,
)->CoreResult<(Option<PacketParts>,usize)> {
    ordered_interval_packet_impl(parts,selected,a,b,previous,false,before_allocate)
}
fn ordered_interval_packet_impl<I: Iterator<Item=usize>>(
    parts:&[Part], selected:impl Fn()->I, a:f64,b:f64,
    previous:Option<&Arc<Vec<(u32,u32)>>>,clip:bool,
    before_allocate:impl FnOnce(usize)->CoreResult<()>,
)->CoreResult<(Option<PacketParts>,usize)> {
    let width=b-a;
    let overlap=|p:Part|if clip{(b.min(p.b.unwrap())-a.max(p.a.unwrap())).max(0.)}else{width};
    let scaled=|i:usize| {
        let p=parts[i]; let duration=p.b.unwrap()-p.a.unwrap();
        (p,if clip{p.mass*(overlap(p)/duration)}else{p.mass*width/duration})
    };
    let mut last=None;
    let mut groups=0usize;
    let mut share=previous.is_some();
    for i in selected() {
        let (p,m)=scaled(i);
        if !(m>0.) {continue}
        let k=compact_indices(p.tag,p.offset).expect("checked compact source");
        if last==Some(k) {continue}
        if last.is_some_and(|old|old>k) {return Err(arithmetic("ordered interval source key regressed"))}
        if previous.and_then(|keys|keys.get(groups)).copied()!=Some(k) {share=false;}
        groups+=1;last=Some(k);
    }
    if groups==0 {before_allocate(0)?;return Ok((None,0))}
    share=share && previous.is_some_and(|keys|keys.len()==groups);
    let separate=groups>=32;
    // A new independent moment owner has a conservative 96 B control
    // allowance, and a newly allocated key owner another 96 B. Reused
    // keys remain charged by the first packet's retained allocation.
    let owned_bytes=if separate {
        groups.saturating_mul(16).saturating_add(96)
            .saturating_add(if share {0}else{groups.saturating_mul(8).saturating_add(96)})
    } else {groups.saturating_mul(std::mem::size_of::<CorePart>()).saturating_add(96)};
    // Two expansion accumulators; no selected-index Vec. Keep the finite
    // binary64 expansion envelope from the receiving group reduction.
    before_allocate(owned_bytes.saturating_add(128*1024))?;
    let mut core=checkpoint_vec(if separate {0}else{groups})?;
    let mut moments=checkpoint_vec(if separate {groups}else{0})?;
    let mut keys=checkpoint_vec(if separate&&!share {groups}else{0})?;
    if core.capacity()!=if separate {0}else{groups}
        || moments.capacity()!=if separate {groups}else{0}
        || keys.capacity()!=if separate&&!share {groups}else{0} {
        return Err(budget("ordered interval exact allocation capacity differs"));
    }
    let (aa,bb)=(PackedTime::new(Some(a))?,PackedTime::new(Some(b))?);
    let mut pending:Option<((u32,u32),RoadExpansion,RoadExpansion)>=None;
    let mut emit=|k:(u32,u32),mass:RoadExpansion,birth:RoadExpansion| {
        let (mass,birth)=(mass.finish(),birth.finish());
        if separate {moments.push((mass,birth));if !share {keys.push(k);}}
        else {core.push(CorePart{tag:k.0,offset:k.1,mass,birth});}
    };
    for i in selected() {
        let (p,m)=scaled(i);
        if !(m>0.) {continue}
        let k=compact_indices(p.tag,p.offset).expect("checked compact source");
        if pending.as_ref().is_some_and(|(old,_,_)|*old!=k) {
            let (key,mass,birth)=pending.take().unwrap();emit(key,mass,birth);
        }
        let (_,mass,birth)=pending.get_or_insert_with(||(k,RoadExpansion::default(),RoadExpansion::default()));
        if clip{mass.add_finite(m)?;birth.add_finite(p.birth*(overlap(p)/(p.b.unwrap()-p.a.unwrap())))?;}
        else{mass.add(m);birth.add(p.birth*width/(p.b.unwrap()-p.a.unwrap()));}
    }
    if let Some((k,mass,birth))=pending {emit(k,mass,birth);}
    let result=if separate {
        debug_assert_eq!(moments.len(),groups);
        let keys=if share {previous.unwrap().clone()}else{Arc::new(keys)};
        if share {crate::v1_trace::add("split.shared_adjacent_key_rows",groups as u64);}
        PacketParts::SharedKeys{a:aa,b:bb,keys,moments:Arc::new(moments)}
    } else {
        debug_assert_eq!(core.len(),groups);
        PacketParts::Uniform{a:aa,b:bb,rows:Arc::new(core)}
    };
    if clip && result.iter().any(|p|!finite_nonnegative(p.mass)||!finite_nonnegative(p.birth)){return Err(arithmetic("nonfinite projected moment"))}
    Ok((Some(result),owned_bytes))
}


// Separate research approximation: integrate overlap into bounded time bins.
// No change of route key, target, mass/birth ledger or original exact fallback.
// Input has already been canonical-combined. Points at max clock are exact.
fn project_time_bins(parts:&[Part],target:f64,bins:usize,dt:f64,record_budget:usize,work:&mut RoadWorkBudget)->CoreResult<Option<Vec<Packet>>>{
    if parts.is_empty()||!(1..=64).contains(&bins)||parts.windows(2).any(|w|(w[0].tag,w[0].offset)>(w[1].tag,w[1].offset)){return Ok(None)}
    let mut lo=f64::INFINITY;let mut hi=f64::NEG_INFINITY;let mut points=0usize;let mut intervals=0usize;
    for p in parts{
        if compact_indices(p.tag,p.offset).is_none(){return Ok(None)}
        let (Some(a),Some(b))=(p.a.map_or(None,Some),p.b.map_or(None,Some))else{return Ok(None)};
        if !a.is_finite()||!b.is_finite()||b<a||!finite_nonnegative(p.mass)||!finite_nonnegative(p.birth){return Err(val("invalid projection source"))}
        lo=lo.min(a);hi=hi.max(b);
        if a==b{points+=1}else{intervals+=1}
    }
    if intervals==0||hi-lo>dt+1e-8||hi<=lo{return Ok(None)}
    if parts.iter().any(|p|p.a.map_or(None,Some)==p.b.map_or(None,Some)&&(p.a.0!=hi.to_bits()||p.b.0!=hi.to_bits())){return Ok(None)}
    let shell=(bins+1)*std::mem::size_of::<Packet>();
    work.interval(shell.saturating_add(256))?;
    let mut out:Vec<Packet>=checkpoint_vec(bins+1)?;
    let mut max_width=0.0f64;let mut a=lo;let mut last_shared:Option<usize>=None;let mut records=0usize;
    for k in 1..=bins{
        let b=if k==bins{hi}else{lo+(hi-lo)*(k as f64/bins as f64)};
        if b<=a{continue}
        max_width=max_width.max(b-a);
        let selected=|| (0..parts.len()).filter(|&i|{let p=parts[i];p.a.unwrap()<p.b.unwrap()&&p.b.unwrap()>a&&p.a.unwrap()<b});
        let prev=last_shared.and_then(|i|match &out[i].parts{PacketParts::SharedKeys{keys,..}=>Some(keys),_=>None});
        let (packet,bytes)=ordered_interval_packet_impl(parts,selected,a,b,prev,true,|n|work.interval(shell.saturating_add(n)))?;
        if let Some(parts)=packet{
            records=records.checked_add(parts.len()).ok_or_else(||budget("projection record overflow"))?;
            if records>record_budget{return Err(budget("projected interval record budget"))}
            if matches!(parts,PacketParts::SharedKeys{..}){last_shared=Some(out.len())}
            work.retain_interval(bytes.saturating_add(std::mem::size_of::<Packet>()));
            out.push(Packet{target,parts});
        }
        a=b;
    }
    if points>0{
        work.interval(shell.saturating_add(points.saturating_mul(32)).saturating_add(128*1024+96))?;
        let mut core=checkpoint_vec(points)?;
        core.extend(parts.iter().copied().filter(|p|p.a.0==hi.to_bits()&&p.b.0==hi.to_bits()&&p.mass>0.).map(compact_core_part));
        records=records.checked_add(core.len()).ok_or_else(||budget("projection point record overflow"))?;
        if records>record_budget{return Err(budget("projected point record budget"))}
        if !core.is_empty(){
            let p=PacketParts::Uniform{a:PackedTime::new(Some(hi))?,b:PackedTime::new(Some(hi))?,rows:Arc::new(core)};
            work.retain_interval(p.allocated_bytes().saturating_add(96+std::mem::size_of::<Packet>()));out.push(Packet{target,parts:p});
        }
    }
    let m0=sum(parts.iter().map(|p|p.mass));let b0=sum(parts.iter().map(|p|p.birth));
    let m1=sum(out.iter().flat_map(|p|p.parts.iter().map(|r|r.mass)));let b1=sum(out.iter().flat_map(|p|p.parts.iter().map(|r|r.birth)));
    if ![m0,b0,m1,b1].iter().all(|x|x.is_finite())||(m0-m1).abs()>1e-10*m0.max(1.)||(b0-b1).abs()>1e-10*b0.max(1.){
        return Err(arithmetic("projected interval mass/birth discrepancy"))
    }
    work.end_interval();
    crate::v1_trace::add("projection.cells",1);
    crate::v1_trace::add("projection.in_rows",parts.len()as u64);
    crate::v1_trace::add("projection.out_rows",records as u64);
    crate::v1_trace::add("projection.out_packets",out.len()as u64);
    crate::v1_trace::add("projection.local_mass_time_bound_veh_s_ceil",(m0*max_width).ceil()as u64);
    Ok(Some(out))
}

/// Only the identical (a_bits,b_bits) case can be represented with one
/// Uniform packet header. Signed +/- zero comparisons here are bitwise:
/// numeric point equality alone would incorrectly coalesce distinct clocks.
fn all_point_endpoint_bits_identical(parts: &[Part], source_indices: &[usize]) -> bool {
    let Some(&first) = source_indices.first() else { return true };
    let (a, b) = (parts[first].a.0, parts[first].b.0);
    source_indices.iter().all(|&i| parts[i].a.0 == a && parts[i].b.0 == b)
}

/// For byte-identical endpoint pairs, the original `combine` key reduces
/// to (tag,offset). Emit final CorePart directly in its old canonical order,
/// without the full temporary point Vec<Part>, combined Vec<Part> or second
/// uniform conversion buffer. Mass/birth terms enter the original sum in
/// original source-index order, with no arithmetic reassociation.
fn combine_uniform_point_core(parts: &[Part], source_indices: &[usize]) -> CoreResult<Vec<CorePart>> {
    debug_assert!(all_point_endpoint_bits_identical(parts, source_indices));
    let mut indices = checkpoint_vec(source_indices.len())?;
    indices.extend(source_indices.iter().copied().filter(|&i| parts[i].mass > 0.0));
    indices.sort_unstable_by(|&i, &j| {
        (parts[i].tag, parts[i].offset, i).cmp(&(parts[j].tag, parts[j].offset, j))
    });
    let key = |i: usize| (parts[i].tag, parts[i].offset);
    let groups = usize::from(!indices.is_empty())
        + indices.windows(2).filter(|pair|key(pair[0]) != key(pair[1])).count();
    let mut out = checkpoint_vec(groups)?;
    let mut start=0;
    while start < indices.len() {
        let mut end = start+1;
        while end < indices.len() && key(indices[start]) == key(indices[end]) {
            end += 1;
        }
        let first=parts[indices[start]];
        let mass=sum(indices[start..end].iter().map(|&i|parts[i].mass));
        let birth=sum(indices[start..end].iter().map(|&i|parts[i].birth));
        out.push(compact_core_part(Part {mass, birth, ..first}));
        start=end;
    }
    Ok(out)
}

fn characteristic(v0: f64, target: f64, dt: f64, tau: f64, acc: f64, brake: f64) -> (f64, f64) {
    let difference = target - v0;
    let limit = if difference >= 0.0 { acc } else { brake };
    let acceleration = if difference >= 0.0 { limit } else { -limit };
    let saturated = ((difference.abs() - limit * tau) / limit).max(0.0);
    let first = dt.min(saturated);
    let mut distance = v0 * first + 0.5 * acceleration * first * first;
    let mut speed = v0 + acceleration * first;
    let remain = dt - first;
    if remain > 0.0 {
        let change = -(-remain / tau).exp_m1();
        distance += target * remain + (speed - target) * tau * change;
        speed += (target - speed) * change;
    }
    (distance, speed.max(0.0))
}
impl Motion {
    fn sample(&self, t: f64) -> (f64, f64) {
        characteristic(self.v0, self.target, t, self.tau, self.accel, self.brake)
    }
    fn passage(&self, d: f64) -> CoreResult<f64> {
        if d == 0.0 {
            return Ok(0.0);
        }
        if self.target == 0.0 {
            let saturated = ((self.v0 - self.brake * self.tau) / self.brake).max(0.0);
            let (dx, v) = self.sample(saturated);
            if d >= dx + v * self.tau {
                return Ok(f64::INFINITY);
            }
        }
        let mut hi = (d / self.v0.max(self.target).max(1e-12)).max(1.0);
        let mut found = false;
        for _ in 0..256 {
            if self.sample(hi).0 >= d {
                found = true;
                break;
            }
            hi *= 2.0;
            if !hi.is_finite() {
                return Err(arithmetic("passage bracket overflow"));
            }
        }
        if !found {
            return Err(arithmetic("passage bracket exhausted"));
        }
        let mut lo = 0.0;
        for _ in 0..100 {
            let mid = (lo + hi) / 2.0;
            if self.sample(mid).0 >= d {
                hi = mid
            } else {
                lo = mid
            }
        }
        Ok(hi)
    }
}
impl V1Road {
    /// Retained immutable registry storage owned by this road, excluding its
    /// physical RoadState. Counts actual String/Vec capacities, including nested
    /// buffers and unused reserved slots; this is structural accounting, not
    /// process RSS or a bound on allocator/Python-wrapper overhead. Constructor
    /// lookup maps, per-tick scratch and the engine's private pool are not owned
    /// by these registry fields and must be charged in their respective scopes.
    pub(crate) fn static_storage_bytes(&self) -> usize {
        fn vector_bytes<T>(values: &Vec<T>) -> usize {
            values.capacity().saturating_mul(std::mem::size_of::<T>())
        }
        fn nested_bytes<T>(rows: &Vec<Vec<T>>) -> usize {
            rows.iter().fold(vector_bytes(rows), |total, row| {
                total.saturating_add(vector_bytes(row))
            })
        }
        std::mem::size_of::<Self>()
            .saturating_sub(std::mem::size_of::<RoadState>())
            .saturating_add(self.identity.capacity())
            .saturating_add(nested_bytes(&self.groups))
            .saturating_add(vector_bytes(&self.signals))
            .saturating_add(nested_bytes(&self.paths))
            .saturating_add(vector_bytes(&self.routes))
            .saturating_add(nested_bytes(&self.classes))
            .saturating_add(nested_bytes(&self.incoming))
            .saturating_add(vector_bytes(&self.windows))
    }
    pub(crate) fn restart_metadata_scratch_bytes(&self)->usize{self.state.restart_metadata_scratch_bytes()}
    pub(crate) fn owned_storage_bytes(&self) -> usize {
        self.state.retained_storage_bytes()
    }
    /// Constructor-only identity finalization after retained accounting. The
    /// engine remeasures this String's capacity after binding its final policy.
    pub(crate) fn bind_storage_identity(&mut self, identity: String) -> CoreResult<()> {
        if identity.is_empty()
            || self.state.t != 0.
            || self.owned_record_count() != 0
            || self.state.totals.iter().any(|&v| v != 0.)
        {
            return Err(val(
                "road storage identity can only bind an empty initial owner",
            ));
        }
        self.identity = identity;
        Ok(())
    }
    pub(crate) fn summary(&self) -> (&[f64; 7], &[[f64; 5]]) {
        (&self.state.totals, &self.state.ledger)
    }
    pub(crate) fn write_state<W: Write>(&self, w: &mut W) -> CoreResult<()> {
        self.write_snapshot(w,&self.state)
    }
    pub(crate) fn write_snapshot<W: Write>(&self,w:&mut W,s:&RoadState)->CoreResult<()> {
        self.write_snapshot_codec(w,s,false)
    }
    pub(crate) fn write_snapshot_codec<W:Write>(&self,w:&mut W,s:&RoadState,compact:bool)->CoreResult<()> {
        write_len(w, self.identity.len())?;
        w.write_all(self.identity.as_bytes())
            .map_err(|e| CoreError::io(e.to_string()))?;
        write_f64(w, s.t)?;
        write_len(w, s.cells.len())?;
        for c in &s.cells {
            for &v in &c.v {
                write_f64(w, v)?;
            }
            if compact{self.write_packets_compact(w,&c.packets)?;}else{self.write_packets(w,&c.packets)?;}
            write_len(w, c.latent.len())?;
            for (&k, &v) in &c.latent {
                write_len(w, k)?;
                write_f64(w, v)?;
            }
        }
        write_len(w, s.pending.len())?;
        for q in &s.pending {
            if compact{self.write_packets_compact(w,q)?;}else{self.write_packets(w,q)?;}
        }
        for &v in &s.totals {
            write_f64(w, v)?;
        }
        write_len(w, s.ledger.len())?;
        for row in &s.ledger {
            for &v in row {
                write_f64(w, v)?;
            }
        }
        Ok(())
    }
    fn write_packets<W: Write>(&self, w: &mut W, q: &[Packet]) -> CoreResult<()> {
        write_len(w, q.len())?;
        let scalar_wire=std::env::var_os("METROFLOW_NATIVE_SCALAR_WIRE").is_some();
        for p in q {
            write_f64(w, p.target)?;
            write_len(w, p.parts.len())?;
            for p in &p.parts {
                // Exact little-endian record in one bounded stack buffer.
                // Do not change option flags, order or floating-point bits.
                if scalar_wire{
                write_len(w, p.tag)?;
                write_len(w, p.offset)?;
                write_f64(w, p.mass)?;
                write_f64(w, p.birth)?;
                for v in [p.a.option(), p.b.option()] {
                    write_u64(w, u64::from(v.is_some()))?;
                    if let Some(v) = v {
                        write_f64(w, v)?;
                    }
                }
                }else{
                    let mut bytes=[0u8;64];let mut len=0;
                    let mut append=|x:u64|{bytes[len..len+8].copy_from_slice(&x.to_le_bytes());len+=8;};
                    for x in [p.tag as u64,p.offset as u64,p.mass.to_bits(),p.birth.to_bits()]{append(x);}
                    for v in [p.a.option(),p.b.option()]{append(u64::from(v.is_some()));if let Some(x)=v{append(x.to_bits());}}
                    w.write_all(&bytes[..len]).map_err(|e|CoreError::io(e.to_string()))?;
                }
            }
        }
        Ok(())
    }
    fn read_packets<R: Read>(
        &self,
        r: &mut R,
        remaining: &mut usize,
        work: &mut RoadDecodeBudget,
    ) -> CoreResult<Vec<Packet>> {
        let n = read_len(r, *remaining)?;
        work.reserve(
            n.saturating_mul(std::mem::size_of::<Packet>() + 32),
            n.saturating_mul(32),
        )?;
        let mut q = checkpoint_vec(n)?;
        for _ in 0..n {
            let target = read_f64(r)?;
            let m = read_len(r, *remaining)?;
            if m == 0 {
                return Err(val("empty native checkpoint packet"));
            }
            *remaining -= m;
            // Preserve wire and exact IEEE rows; allocate the final compact
            // representation directly. Only a truly mixed packet needs the
            // legacy wide representation. The late fallback is charged before
            // the two buffers coexist; no guard allowance is relaxed here.
            work.reserve(0,m.saturating_mul(16))?;
            let mut read_part=||->CoreResult<Part>{
                let tag = read_len(r, self.routes.len())?;
                let Some(&(path, _)) = self.routes.get(tag) else {
                    return Err(val("native checkpoint route index differs"));
                };
                let offset = read_len(r, self.paths[path].len())?;
                let mass = read_f64(r)?;
                let birth = read_f64(r)?;
                let mut interval = [None, None];
                for v in &mut interval {
                    *v = match read_u64(r)? {
                        0 => None,
                        1 => Some(read_f64(r)?),
                        _ => return Err(val("native checkpoint option tag differs")),
                    };
                }

                Ok(Part {
                    tag,
                    offset,
                    mass,
                    birth,
                    a: PackedTime::new(interval[0])?,
                    b: PackedTime::new(interval[1])?,
                })
            };
            let first=read_part()?;
            let a=first.a;let b=first.b;
            let parts=if compact_indices(first.tag,first.offset).is_none(){
                work.reserve(m.saturating_mul(std::mem::size_of::<Part>()),0)?;
                let mut wide=checkpoint_vec(m)?;wide.push(first);
                for _ in 1..m{wide.push(read_part()?);}
                PacketParts::Mixed(Arc::new(wide))
            }else{
                let bytes=m.saturating_mul(std::mem::size_of::<CorePart>());
                work.reserve(bytes,0)?;
                let mut compact=checkpoint_vec(m)?;compact.push(compact_core_part(first));
                let mut mixed=None;
                for _ in 1..m{
                    let p=read_part()?;
                    if let Some(wide)=mixed.as_mut(){Vec::<Part>::push(wide,p);continue;}
                    if p.a.0==a.0&&p.b.0==b.0&&compact_indices(p.tag,p.offset).is_some(){
                        compact.push(compact_core_part(p));
                    }else{
                        work.reserve(m.saturating_mul(std::mem::size_of::<Part>()),0)?;
                        let mut wide=checkpoint_vec(m)?;
                        wide.extend(compact.iter().map(|p|Part{tag:p.tag as usize,offset:p.offset as usize,mass:p.mass,birth:p.birth,a,b}));
                        wide.push(p);
                        drop(std::mem::take(&mut compact));
                        work.decoded=work.decoded.checked_sub(bytes).ok_or_else(||arithmetic("compact decode accounting"))?;
                        mixed=Some(wide);
                    }
                }
                if let Some(wide)=mixed{PacketParts::Mixed(Arc::new(wide))}else{PacketParts::Uniform{a,b,rows:Arc::new(compact)}}
            };
            q.push(Packet{target,parts});
        }
        Ok(q)
    }
    pub(crate) fn read_state<R: Read>(&self,r:&mut R)->CoreResult<RoadState>{self.read_state_codec(r,false)}
    pub(crate) fn read_state_codec<R:Read>(&self,r:&mut R,compact:bool)->CoreResult<RoadState>{
        read_exact_len(r, self.identity.len())?;
        let mut identity = vec![0; self.identity.len()];
        r.read_exact(&mut identity)
            .map_err(|e| CoreError::io(e.to_string()))?;
        if identity != self.identity.as_bytes() {
            return Err(val("native road checkpoint binding differs"));
        }
        let t = read_f64(r)?;
        read_exact_len(r, self.groups.len())?;
        let mut remaining = self.record_budget;
        let mut work = RoadDecodeBudget {
            limit: self.storage_budget,
            retained_input: if self.storage_budget.is_some() {
                self.retained_input_bytes
                    .max(self.state.retained_storage_bytes())
            } else {
                0
            },
            decoded: std::mem::size_of::<RoadState>().saturating_add(3 * 32),
            validation: if compact{2*1024*1024}else{0},
        };
        // Include empty tree roots and both packet-queue buffer allowances for
        // every cell, before constructing the first outer vector.
        work.reserve(
            self.groups
                .len()
                .saturating_mul(std::mem::size_of::<Cell>() + 256 + 2 * 32),
            self.groups.len().saturating_mul(32),
        )?;
        let mut cells = if compact{compact_checkpoint_vec(self.groups.len())?}else{checkpoint_vec(self.groups.len())?};
        for _ in &self.groups {
            let mut v = [0.; 8];
            for x in &mut v {
                *x = read_f64(r)?;
            }
            let packets=if compact{self.read_packets_compact(r,&mut remaining,&mut work)?}else{self.read_packets(r,&mut remaining,&mut work)?};
            let n = read_len(r, self.classes.len())?;
            work.reserve(n.saturating_mul(256), 0)?;
            let mut latent = BTreeMap::new();
            for _ in 0..n {
                let k = read_len(r, self.classes.len())?;
                let v = read_f64(r)?;
                if latent.insert(k, v).is_some() {
                    return Err(val("duplicate native checkpoint latent class"));
                }
            }
            cells.push(Cell { v, packets, latent });
        }
        read_exact_len(r, self.groups.len())?;
        work.reserve(
            self.groups
                .len()
                .saturating_mul(std::mem::size_of::<Vec<Packet>>()),
            0,
        )?;
        let mut pending = if compact{compact_checkpoint_vec(self.groups.len())?}else{checkpoint_vec(self.groups.len())?};
        for _ in &self.groups {
            pending.push(if compact{self.read_packets_compact(r,&mut remaining,&mut work)?}else{self.read_packets(r,&mut remaining,&mut work)?});
        }
        let mut totals = [0.; 7];
        for v in &mut totals {
            *v = read_f64(r)?;
        }
        read_exact_len(r, self.classes.len())?;
        work.reserve(
            self.classes
                .len()
                .saturating_mul(std::mem::size_of::<[f64; 5]>()),
            0,
        )?;
        let mut ledger = if compact{compact_checkpoint_vec(self.classes.len())?}else{checkpoint_vec(self.classes.len())?};
        for _ in &self.classes {
            let mut row = [0.; 5];
            for v in &mut row {
                *v = read_f64(r)?;
            }
            ledger.push(row);
        }
        let mut state = RoadState {
            t,
            cells,
            pending,
            totals,
            ledger,
        };
        self.check_state_codec(&state,compact)?;
        // State restoration is a strict source-bound, post-decode lifetime.
        // Exact ordered-keyset interning replaces independent full CorePart
        // payloads with actually shared immutable key arrays only in capped
        // native runs. Reconstructed Part values and wire stay identical.
        if self.storage_budget.is_some()&&!compact {
            state.intern_exact_keysets()?;
            self.check_state(&state)?;
        }
        Ok(state)
    }
    pub(crate) fn install_state(&mut self, state: RoadState) {
        self.rollback(state);
        self.retained_input_bytes = 0;
        self.service_event_accounting = None;
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn class_for_route(&self,tag:usize)->Option<usize>{self.routes.get(tag).map(|x|x.1)}
    #[cfg(feature="native-cli")]
    pub(crate) fn set_research_interval_bins(&mut self,bins:usize)->CoreResult<()>{
        if !self.intervals||!(1..=64).contains(&bins){return Err(val("research interval bins outside supported domain"))}
        self.research_interval_bins=Some(bins);Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn set_research_rank_bins(&mut self,bins:usize)->CoreResult<()>{
        if !self.intervals||!(1..=16).contains(&bins)||self.research_interval_bins.is_some()||!self.can_compact_incoming_parts(){return Err(val("research rank bins outside supported domain"))}
        self.research_rank_bins=Some(bins);Ok(())
    }
    #[cfg(feature="native-cli")]
    pub(crate) fn set_research_ready_mass(&mut self,milli:u64)->CoreResult<()>{
        if self.research_rank_bins.is_none()||!(1..=10000).contains(&milli){return Err(val("ready rank mass outside domain or missing rank closure"))}
        self.research_ready_mass_milli=Some(milli);Ok(())
    }
    pub(crate) fn owned_time(&self) -> f64 {
        self.state.t
    }
    /// Future self.capture() clones the current immutable PacketParts Arc
    /// backings rather than physically re-allocating those row payloads.
    /// Use ACTUAL live immutable allocation identities only. This is the
    /// deduplicated unique data payload, not a bound on shell clones or RSS.
    pub(crate) fn owned_paired_payload_credit(&self,input:&RoadState)->usize{self.state.paired_shared_payload_lower_bound(input)}
    pub(crate) fn owned_unique_immutable_arc_payload_bytes(&self)->usize {
        self.state.arc_backing_census().unique_payload_bytes
    }
    pub(crate) fn checkpoint(&self) -> RoadState {
        self.state.clone()
    }
    /// Diagnostic only: ownership overlap of committed and supplied snapshot.
    pub(crate) fn arc_committed_snapshot_union(&self, supplied: &RoadState) -> ArcBackingCensus {
        RoadState::arc_backing_union(&[&self.state, supplied])
    }
    pub(crate) fn rollback(&mut self, state: RoadState) {
        self.state = state;
    }
    /// Internal phase allowance from the engine's combined byte policy. This
    /// changes accounting metadata only; the phase's existing preflight checks
    /// validate before allocation, without another whole-state scan here.
    pub(crate) fn set_phase_storage_budget(&mut self, bytes: usize) -> CoreResult<()> {
        let minimum = std::mem::size_of::<Part>().max(std::mem::size_of::<EventRow>());
        if bytes < minimum {
            return Err(budget(&format!(
                "native road storage budget exceeded: phase=allowance assignment, required_bytes={minimum}, budget_bytes={bytes}")));
        }
        self.storage_budget = Some(bytes);
        self.record_budget = bytes / std::mem::size_of::<Part>();
        Ok(())
    }
    /// Known call-input metadata must not leak into later load/branch checks.
    /// The engine separately accounts for the input bundle during final capture.
    pub(crate) fn clear_call_storage_accounting(&mut self) {
        self.retained_input_bytes = 0;
        self.service_event_accounting = None;
    }
    pub(crate) fn begin_call_storage_accounting(&mut self) {
        self.service_event_accounting = None;
        self.retained_input_bytes = if self.storage_budget.is_some() {
            self.state.retained_storage_bytes()
        } else {
            0
        };
    }
    pub(crate) fn configure_service_event_accounting(
        &mut self,
        input_bytes: usize,
        max_tag_bytes: usize,
        shared_input_current: bool,
    ) {
        self.service_event_accounting = self.storage_budget.map(|_| ServiceEventAccounting {
            input_bytes,
            current_bytes: input_bytes,
            shared_input_current,
            max_tag_bytes,
        });
    }
    pub(crate) fn service_sink_tag_bytes(&self) -> Option<usize> {
        self.service_event_accounting.map(|a| a.max_tag_bytes)
    }
    pub(crate) fn set_service_event_current_bytes(
        &mut self, current_bytes: usize, shared_input_current: bool,
    ) {
        if let Some(accounting) = &mut self.service_event_accounting {
            accounting.current_bytes = current_bytes;
            accounting.shared_input_current = shared_input_current;
        }
    }
    pub(crate) fn owned_record_count(&self) -> usize {
        self.state
            .cells
            .iter()
            .flat_map(|c| c.packets.iter())
            .map(|p| p.parts.len())
            .sum::<usize>()
            + self
                .state
                .pending
                .iter()
                .flatten()
                .map(|p| p.parts.len())
                .sum::<usize>()
    }
    pub(crate) fn checkpoint_event_limit(&self) -> usize {
        self.storage_budget.map_or(self.record_budget, |bytes| {
            bytes / std::mem::size_of::<EventRow>()
        })
    }
    pub(crate) fn event_resolution_stats(&self) -> (u64, f64, f64, f64) {
        let stats = self
            .event_resolution
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        (
            stats.count,
            stats.processed_time_bound,
            stats.clock_roundoff_bound,
            stats.rate_weighted_mass_bound,
        )
    }
    fn can_compact_incoming_parts(&self)->bool {
        self.storage_budget.is_some()
            && self.routes.len() < u32::MAX as usize
            && self.paths.iter().all(|p|p.len()<u32::MAX as usize)
    }
    pub(crate) fn can_compact_candidate_events(&self)->bool {
        // All route tags and source/destination cell indices derive from
        // these configured registries. Reserve u32::MAX for dest=None.
        self.storage_budget.is_some()
            && self.routes.len() < u32::MAX as usize
            && self.groups.len() < u32::MAX as usize
    }
    /// Source-phase scratch for the checked streaming native path. Old
    /// 32B/row reserve covered materialized per-row observations that no
    /// longer exist here. Keep a separate worst-case key expansion (8B
    /// per SharedKeys row), packet descriptor/ready storage, pending raw
    /// remainder, per-destination finite expansion and per-worker sums.
    fn source_observation_reserve(&self,s:&RoadState,stats:&RoadDebugStats)->usize{
        let rows=stats.cell_parts.saturating_add(stats.pending_parts);
        let old=rows.saturating_mul(32);
        if !cfg!(all(feature="native-cli",not(feature="python-extension")))
            || std::env::var("METROFLOW_NATIVE_STREAM_SOURCE").as_deref()!=Ok("1")
            || !receiving_lifetime_enabled() || !self.intervals || !self.can_compact_incoming_parts()
            || !self.can_compact_candidate_events() || self.checkpoint_event_limit()>u32::MAX as usize
            || std::env::var("METROFLOW_EXPERIMENTAL_EVENT_INDEX_INCOMING").as_deref()!=Ok("1"){return old}
        let packets=stats.cell_packets.saturating_add(stats.pending_packets);
        let cells=self.groups.len();let max_inc=self.incoming.iter().map(Vec::len).max().unwrap_or(0);
        // The optional new bound is valid for the finite physical domain,
        // and no raw attribution vectors. Extremely large coefficients use
        // the established legacy reserve instead of this specialization.
        if s.t>1e12||self.dt>1e6||s.totals.iter().any(|x|*x>1e12)||self.groups.iter().flatten().chain(self.classes.iter().flatten()).any(|x|*x>1e12)||self.windows.iter().any(|w|w.3>1e6){return old}
        let shared_rows=s.cells.iter().flat_map(|c|&c.packets).chain(s.pending.iter().flatten()).fold(0usize,|n,p|n.saturating_add(if matches!(&p.parts,PacketParts::SharedKeys{..}){p.parts.len()}else{0}));
        let workers=rayon::current_num_threads().max(1).min(cells);
        // Two per-destination moment maps for ONE currently inspected head;
        // all prior heads retain only scalar beta maps. 128KiB per finite
        // expansion covers 4096 f64 components and growth overlap.
        let reductions=128usize.saturating_mul(1024).saturating_mul(2usize.saturating_mul(self.registered_successor_width).saturating_add(3*workers).saturating_add(16));
        let maps=1024usize.saturating_mul(cells.saturating_add(1)).saturating_mul(max_inc.saturating_mul(4).saturating_add(8));
        let workspace=packets.saturating_mul(64).saturating_add(shared_rows.saturating_mul(8))
            .saturating_add(stats.pending_parts.saturating_mul(4*std::mem::size_of::<Part>()+std::mem::size_of::<Offer>()))
            .saturating_add(reductions).saturating_add(maps).saturating_add(2*1024*1024);
        // Do not change the legacy conservative small-state contract if
        // this independent envelope would be larger than the old one.
        workspace.min(old)
    }
    fn work_budget(
        &self,
        state: &RoadState,
        offers: &[Offer],
        call_input: Option<&RoadState>,
    ) -> CoreResult<RoadWorkBudget> {
        if self.storage_budget.is_none() {
            return Ok(RoadWorkBudget {
                limit: None,
                base: 0,
                transfer_exclusive_cell_scratch:0,
                events: 0, event_candidate_live_bound: None,
                incoming: 0,
                incoming_page_cells: self.groups.len(),
                incoming_cell_rows:None,incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
                compact_events: self.can_compact_candidate_events(),
                compact_incoming: self.can_compact_incoming_parts(), timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
                interval_retained: 0,
                interval_transient: 0,
                service_events: None,
            });
        }
        let stats = state.debug_stats();
        let rows = stats.cell_parts.saturating_add(stats.pending_parts);
        let groups = self.groups.len();
        let supplied_retained = state.retained_storage_bytes();
        let maximum_retained = supplied_retained.max(self.retained_input_bytes);
        // The Python caller retains the same immutable input until the whole
        // advance ends. Later ticks may replace every originally shared Arc.
        let exact_shared = call_input.map_or(0, |input| {
            state.paired_shared_payload_lower_bound(input)
                .min(supplied_retained.min(self.retained_input_bytes))
        });
        let optin = std::env::var("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET")
            .ok().as_deref() == Some("source_pair_only");
        let experimental_credit = if optin { exact_shared } else { 0 };
        let paired_credit = exact_shared;
        crate::v1_trace::add("arc.default_pointer_verified_credit",exact_shared as u64);
        crate::v1_trace::add("arc.experimental_paired_credit",experimental_credit as u64);
        let combine_scratch=stats.max_cell_parts
            .saturating_mul(2*std::mem::size_of::<Part>());
        let source_observation_bytes=self.source_observation_reserve(state,&stats);
        let base=maximum_retained.saturating_mul(3).saturating_sub(paired_credit).saturating_add(source_observation_bytes)
            .saturating_add(
                offers
                    .len()
                    .saturating_mul(4 * std::mem::size_of::<Part>() + std::mem::size_of::<Offer>()),
            )
            .saturating_add(combine_scratch)
            .saturating_add(groups.saturating_mul(1024 + self.classes.len() * 1024));
        if let Some(limit) = self.storage_budget {
            crate::v1_trace::guard(
                "road_base",
                "components",
                base,
                limit,
                &[
                    ("state_retained", state.retained_storage_bytes()),
                    ("input_retained", self.retained_input_bytes),
                    ("rows",rows),
                    ("source_observation_bytes",source_observation_bytes),
                    ("legacy_source_observation_bytes",rows.saturating_mul(32)),
                    ("registered_successor_width",self.registered_successor_width),
                    ("offers",offers.len()),
                    ("max_cell_parts", stats.max_cell_parts),
                    ("groups", groups),
                    ("classes", self.classes.len()),
                    ("paired_arc_credit", paired_credit),
                    ("default_pointer_verified_credit",exact_shared),
                    ("experimental_pointer_verified_credit",experimental_credit),
                ],
            );
        }
        let mut work = RoadWorkBudget {
            limit: self.storage_budget,
            base,
            transfer_exclusive_cell_scratch:combine_scratch,
            events: 0, event_candidate_live_bound: None,
            incoming: 0,
            incoming_page_cells: self.groups.len(),
            incoming_cell_rows:Some(vec![0;self.groups.len()]),incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events: self.can_compact_candidate_events(),
            compact_incoming: self.can_compact_incoming_parts(), timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained: 0,
            interval_transient: 0,
            service_events: self.service_event_accounting,
        };
        if self.intervals && self.can_compact_incoming_parts() {
            work.timed_incoming_control_bytes=Some(timed_control_storage_bound(
                &TimedIncomingControls::new(),0,groups)?);
            if self.can_compact_candidate_events() && self.checkpoint_event_limit()<=u32::MAX as usize
                && std::env::var_os("METROFLOW_EXPERIMENTAL_EVENT_INDEX_INCOMING").as_deref()==Some(std::ffi::OsStr::new("1")) {
                work.timed_referenced_rows=Some(0);
                if cfg!(all(feature="native-cli",not(feature="python-extension"))) && std::env::var("METROFLOW_NATIVE_PACKED_REF").as_deref()==Ok("1"){work.packed_ref_saved=Some(0);}
            }
        }
        // Only the timed indexed consumer with explicitly disjoint source /
        // receiving lifetimes has its own later per-cell allocation guard.
        let phase=if work.timed_referenced_rows.is_some()&&receiving_lifetime_enabled(){
            "source tick preflight"
        }else{"tick preflight"};
        work.require(0,phase)?;
        Ok(work)
    }
    /// Called only after the entire road step_state frame returns. At this
    /// point old incoming/Mark, queue and interval sweep workspaces are dead.
    /// Do not reuse their obsolete RoadWorkBudget lifetime in the flat phase.
    fn materialize_event_after_road(
        &self, candidate:&mut RoadState, pages:ChunkedEvents,
    )->CoreResult<Vec<EventRow>> {
        if let Some(limit)=self.storage_budget {
            let max_state=self.state.retained_storage_bytes()
                .max(self.retained_input_bytes)
                .max(candidate.retained_storage_bytes());
            let road_owners=max_state.saturating_mul(3);
            let old_events=self.service_event_accounting.map_or(0,|v|
                v.input_bytes.saturating_add(
                    if v.shared_input_current {0} else {v.current_bytes}
                ));
            let required=postroad_event_materialization_bytes(
                road_owners,old_events,pages.physical_capacity_bytes(),pages.descriptor_capacity(),pages.len(),
            );
            crate::v1_trace::guard(
                "road_post","event candidate materialize after road",required,limit,
                &[
                    ("retained_road_owners",road_owners),
                    ("committed_input_event_bytes",old_events),
                    ("paged_event_slots",pages.capacity()),
                    ("paged_event_payload_bytes",pages.physical_capacity_bytes()),
                    ("page_descriptor_slots",pages.descriptor_capacity()),
                    ("flat_event_rows",pages.len()),
                ],
            );
            check_storage_limit(
                Some(limit),required,"event candidate materialize after road",
            )?;
        }
        // The explicit standalone API requests a flat Vec. Its pages die
        // before keyset interning; the native proposal below skips this export.
        let flat = pages.into_flat_checked()?;
        self.intern_candidate_keysets(candidate,
            flat.capacity().saturating_mul(std::mem::size_of::<EventRow>()),None)?;
        Ok(flat)
    }

    fn intern_candidate_keysets(
        &self, candidate: &mut RoadState, candidate_event_bytes: usize,
        call_input:Option<&RoadState>,
    ) -> CoreResult<()> {
        if let Some(limit) = self.storage_budget {
            let stats = candidate.debug_stats();
            let committed_retained = self.state.retained_storage_bytes();
            let supplied_retained = self.retained_input_bytes;
            let candidate_retained = candidate.retained_storage_bytes();
            let gross_owner_sum = postroad_continuous_owner_sum(
                committed_retained, supplied_retained, candidate_retained,
            );
            let input_credit=postroad_input_payload_credit(&self.state,call_input,supplied_retained,committed_retained);
            let owner_sum=gross_owner_sum.saturating_sub(input_credit);
            let old_events = self.service_event_accounting.map_or(0, |v|
                v.input_bytes.saturating_add(
                    if v.shared_input_current { 0 } else { v.current_bytes }
                ));
            let packets = stats.cell_packets.saturating_add(stats.pending_packets);
            let allocation_rows=candidate.keyset_allocation_row_count();
            let (cell_rows,cell_packets)=candidate.peak_cell_keyset_workspace()?;
            let required = postroad_continuous_keyset_peak_event_bytes(
                owner_sum, old_events, candidate_event_bytes,
                cell_rows, cell_packets,
            );
            crate::v1_trace::guard(
                "road_post", "continuous keyset allocation", required, limit,
                &[("committed_road_retained", committed_retained),
                  ("supplied_input_road_retained", supplied_retained),
                  ("candidate_road_retained", candidate_retained),
                  ("road_owner_sum", owner_sum), ("gross_road_owner_sum",gross_owner_sum),
                  ("input_committed_pointer_credit",input_credit), ("old_event_bytes", old_events),
                  ("candidate_event_storage_bytes", candidate_event_bytes),
                  ("candidate_uniform_rows", stats.uniform_parts),
                  ("candidate_keyset_allocation_rows", allocation_rows),
                  ("peak_cell_keyset_allocation_rows", cell_rows),
                  ("peak_cell_packets", cell_packets),
                  ("candidate_existing_shared_rows",stats.uniform_parts.saturating_sub(allocation_rows)),
                  ("candidate_packets", packets)],
            );
            check_storage_limit(Some(limit), required, "continuous keyset allocation")?;
            let before = candidate.retained_storage_bytes();
            let changed = candidate.intern_exact_keysets()?;
            let after = candidate.retained_storage_bytes();
            crate::v1_trace::add("keyset.continuous_converted", changed as u64);
            crate::v1_trace::add("keyset.continuous_saved_bytes", before.saturating_sub(after) as u64);
        }
        Ok(())
    }

    pub(crate) fn owned_step(&mut self, dt: f64, offers: Vec<Offer>) -> CoreResult<Vec<EventRow>> {
        self.begin_call_storage_accounting();
        let (mut s, pages) = self.step_state(&self.state, dt, offers, None)?;
        let e=self.materialize_event_after_road(&mut s,pages)?;
        self.state = s;
        Ok(e)
    }
    /// Build a candidate against the current immutable owner. The coupled
    /// service/journey transaction installs it only after its other owners
    /// validate, avoiding a second full road clone solely for rollback.
    pub(crate) fn propose_owned_step(
        &self,
        dt: f64,
        offers: Vec<Offer>,
        call_input: Option<&RoadState>,
    ) -> CoreResult<(RoadState, ChunkedEvents)> {
        let (mut state, pages) = self.step_state(&self.state, dt, offers, call_input)?;
        self.intern_candidate_keysets(&mut state, pages.retained_storage_bytes(),call_input)?;
        crate::v1_trace::add("event_history.retained_rows", pages.len() as u64);
        crate::v1_trace::add("event_history.retained_storage_bytes", pages.retained_storage_bytes() as u64);
        Ok((state, pages))
    }
    fn class(&self, p: &Part) -> usize {
        self.routes[p.tag].1
    }
    fn path(&self, tag: usize) -> &[usize] {
        &self.paths[self.routes[tag].0]
    }
    fn dest(&self, p: &Part) -> Option<usize> {
        self.path(p.tag).get(p.offset + 1).copied()
    }
    fn footprint(&self, tag: usize) -> f64 {
        self.classes[self.routes[tag].1][12]
    }
    fn occupancy(&self, c: &Cell) -> f64 {
        sum(c.packets.iter().map(mass))
    }
    fn occupied(&self, c: &Cell) -> f64 {
        sum(c
            .packets
            .iter()
            .flat_map(|p| p.parts.iter().map(|x| x.mass * self.footprint(x.tag))))
    }
    fn factor(&self, i: usize, t: f64) -> f64 {
        self.windows
            .iter()
            .filter(|w| w.0 == i && w.1 <= t && t < w.2)
            .fold(1.0, |a, w| a * w.3)
    }
    fn green(&self, i: usize, t: f64) -> bool {
        self.signals[i].map_or(true, |(c, g, o)| (t - o).rem_euclid(c) < g)
    }
    fn blank(&self, t: f64) -> RoadState {
        RoadState {
            t,
            cells: (0..self.groups.len())
                .map(|_| Cell {
                    v: [0., 1., 0., 0., 0., 0., 0., 0.],
                    packets: vec![],
                    latent: BTreeMap::new(),
                })
                .collect(),
            pending: vec![vec![]; self.groups.len()],
            totals: [0.; 7],
            ledger: vec![[0.; 5]; self.classes.len()],
        }
    }
    fn motion(&self, i: usize, c: &Cell, dt: f64, factor: f64) -> CoreResult<Motion> {
        let mut counts: BTreeMap<usize, RoadExpansion> = BTreeMap::new();
        for packet in &c.packets {
            for p in &packet.parts {
                counts.entry(self.class(&p)).or_default().add_finite(p.mass)?;
            }
        }
        let counts: BTreeMap<usize, f64> = counts.into_iter().map(|(k, v)| (k, v.finish())).collect();
        if counts.is_empty() {
            return Ok(Motion {
                dx: 0.,
                speed: 0.,
                v0: 0.,
                target: 0.,
                tau: 1.,
                accel: 1.,
                brake: 1.,
                latent: BTreeMap::new(),
                initial: BTreeMap::new(),
                hazards: BTreeMap::new(),
            });
        }
        let total = sum(counts.values().copied());
        let occupied = sum(counts.iter().map(|(k, m)| m * self.classes[*k][6]));
        if occupied > self.groups[i][4] {
            return Err(val("PHYSICAL_INFEASIBLE: class lengths exceed lane space"));
        }
        let gap = (self.groups[i][4] - occupied) / total;
        let cap = if factor == 0.0 {
            0.0
        } else {
            self.groups[i][1]
        };
        let mut inverse = Vec::new();
        let mut initial = BTreeMap::new();
        let mut mid = BTreeMap::new();
        let mut latent = BTreeMap::new();
        let mut hazards = BTreeMap::new();
        let mut admissible = f64::INFINITY;
        let mut accel = f64::INFINITY;
        let mut brake = f64::INFINITY;
        for (&k, &n) in &counts {
            let c0 = &self.classes[k];
            let p = *c.latent.get(&k).unwrap_or(&c0[7]);
            let nu = c0[9] * (c0[10] / (gap + c0[6])).powi(2);
            let rate = c0[8] + nu;
            if !rate.is_finite() {
                return Err(arithmetic("latent relaxation overflow"));
            }
            let relax = |p: f64, h: f64| {
                if rate == 0.0 {
                    p
                } else {
                    p + (c0[8] / rate - p) * (-(-rate * h).exp_m1())
                }
            };
            let ph = relax(p, dt / 2.0);
            initial.insert(k, p);
            mid.insert(k, ph);
            latent.insert(k, relax(ph, dt / 2.0));
            hazards.insert(k, nu);
            inverse.push((n / total) / c0[1]);
            admissible = admissible.min(c0[0].min(cap).min(((gap - c0[4]) / c0[5]).max(0.0)));
            accel = accel.min(c0[2]);
            brake = brake.min(c0[3]);
        }
        let inverse = sum(inverse);
        let target = admissible
            * sum(counts
                .iter()
                .map(|(&k, &n)| (n / total) * mid[&k] / self.classes[k][1]))
            / inverse;
        if !target.is_finite() || !inverse.is_finite() {
            return Err(arithmetic("nonfinite closure coefficients"));
        }
        let (dx, speed) = characteristic(c.v[7], target, dt, 1.0 / inverse, accel, brake);
        Ok(Motion {
            dx,
            speed,
            v0: c.v[7],
            target,
            tau: 1.0 / inverse,
            accel,
            brake,
            latent,
            initial,
            hazards,
        })
    }
    fn interval_packets(
        &self,
        parts: Vec<Part>,
        target: f64,
        work: &mut RoadWorkBudget,
    ) -> CoreResult<Vec<Packet>> {
        // Live for the whole call; each interval adds its own rows (the
        // selected-row Vec, combine's index and output) and the packet list
        // with room for its doubling reallocation. Only packed rows that are
        // pushed to the output outlive their interval.
        // The previous implementation first allocated 2*n f64 endpoints
        // and sorted/deduped them. The sorted event streams now yield exactly
        // k unique numeric edges, so no 2*n endpoint buffer ever exists.
        let (nonpoint_rows, point_rows) = count_sweep_row_kinds(&parts)?;
        if let Some(bins)=self.research_interval_bins{
            if let Some(projected)=project_time_bins(&parts,target,bins,self.dt,self.record_budget,work)?{return Ok(projected)}
            crate::v1_trace::add("projection.exact_fallback_cells",1);
        }
        // One source-wide check, outside the edge loop. If *any* legacy
        // row requires wide tag/offset, retain exact old Part backed storage.
        let compactable_source = parts.iter()
            .all(|p| compact_indices(p.tag, p.offset).is_some());
        let event_index_bytes = exact_sweep_event_index_bytes(
            parts.len(), nonpoint_rows, point_rows,
        );
        const POINT_ROW_BYTES: usize =
            2 * std::mem::size_of::<Part>() + std::mem::size_of::<usize>();
        const INTERVAL_ROW_BYTES: usize =
            std::mem::size_of::<CorePart>() + std::mem::size_of::<usize>();
        const WIDE_INTERVAL_ROW_BYTES: usize =
            std::mem::size_of::<Part>() + std::mem::size_of::<usize>();

        // Preflight the actual index arrays before allocating them.
        work.require(event_index_bytes,"indexed sweep preflight")?;
        let mut sweep =
            IntervalActiveSweep::new_counted(&parts, nonpoint_rows, point_rows)?;
        // The second guard now reflects the actual k-element endpoint vector,
        // as well as all the still-live sweep index/point/active buffers.
        let edges = unique_sweep_edges(&parts, &sweep, |unique_bytes| {
            work.require(
                unique_bytes.saturating_add(event_index_bytes),
                "interval edges and indexed sweep",
            )
        })?;
        let edge_bytes=edges.len().saturating_mul(std::mem::size_of::<f64>());
        let transient = |count: usize, packets: usize, is_point: bool| {
            edge_bytes
                .saturating_add(event_index_bytes)
                .saturating_add(count.saturating_mul(if is_point {
                    POINT_ROW_BYTES
                } else if compactable_source {
                    INTERVAL_ROW_BYTES
                } else {
                    WIDE_INTERVAL_ROW_BYTES
                }))
                .saturating_add(
                    packets
                        .saturating_add(1)
                        .max(4)
                        .saturating_mul(3 * std::mem::size_of::<Packet>()),
                )
        };
        let lifetime=work.timed_referenced_rows.is_some() && receiving_lifetime_enabled();
        let mut out:Vec<Packet> = vec![];
        let mut records = 0;
        let ordered_stream=compactable_source && work.timed_referenced_rows.is_some()
            && parts.windows(2).all(|w|(w[0].tag,w[0].offset)<=(w[1].tag,w[1].offset));
        let mut last_shared:Option<usize>=None;
        for (k, &a) in edges.iter().enumerate() {
            sweep.advance(a);
            let count = sweep.current_points.len();
            let uniform_point = compactable_source
                && all_point_endpoint_bits_identical(&parts, &sweep.current_points);
            // Homogeneous byte-identical point endpoints need only the final
            // CorePart buffer and source index array (40B/selected row);
            // mixed signed-zero or other bit-distinct endpoints retain the
            // exact original materialized path and its 104B/row guard.
            work.interval(transient(count, out.len(), !uniform_point)
                .saturating_add(if lifetime && count>0 {128*1024+96}else{0}))?;
            let packed_point = if uniform_point {
                let core = combine_uniform_point_core(&parts, &sweep.current_points)?;
                if core.is_empty() {
                    None
                } else {
                    let first = parts[sweep.current_points[0]];
                    records += core.len();
                    Some(PacketParts::Uniform {
                        a: first.a,
                        b: first.b,
                        rows: Arc::new(core),
                    })
                }
            } else {
                let mut point = checkpoint_vec(count)?;
                point.extend(sweep.current_points.iter().map(|&i| parts[i]));
                let point = combine(point)?;
                if point.is_empty() {
                    None
                } else {
                    records += point.len();
                    Some(work.pack_parts(point)?)
                }
            };
            if let Some(parts) = packed_point {
                work.retain_interval(
                    parts.allocated_bytes().saturating_add(std::mem::size_of::<Packet>())
                        .saturating_add(if lifetime {96}else{0}),
                );
                push_checked(&mut out, Packet { target, parts })?;
            }
            if k + 1 < edges.len() {
                let b = edges[k + 1];
                let count = sweep.active.len();
                if ordered_stream {
                    let prev=last_shared.and_then(|index|match &out[index].parts {
                        PacketParts::SharedKeys{keys,..}=>Some(keys),_=>None,
                    });
                    let base=transient(0,out.len(),false);
                    let (packed,charge)=ordered_interval_packet(&parts,||sweep.active.iter(),a,b,prev,
                        |bytes|work.interval(base.saturating_add(bytes)))?;
                    if let Some(parts)=packed {
                        records+=parts.len();
                        if matches!(parts,PacketParts::SharedKeys{..}) {last_shared=Some(out.len());}
                        work.retain_interval(charge.saturating_add(std::mem::size_of::<Packet>()));
                        push_checked(&mut out,Packet{target,parts})?;
                    }
                    if records>self.record_budget {return Err(budget("entry interval record budget"));}
                    continue;
                }
                work.interval(transient(count, out.len(), false)
                    .saturating_add(if lifetime && count>0 {128*1024+96}else{0}))?;
                // Original fallback for wide or noncanonical input.
                let packed = if compactable_source {
                    let core =
                        combine_interval_core(&parts, sweep.active.iter(), count, a, b)?;
                    if core.is_empty() {
                        None
                    } else {
                        records += core.len();
                        Some(PacketParts::Uniform {
                            a: PackedTime::new(Some(a))?,
                            b: PackedTime::new(Some(b))?,
                            rows: Arc::new(core),
                        })
                    }
                } else {
                    // Full 64-bit original Part route labels; never truncate.
                    let wide =
                        combine_interval_view(&parts, sweep.active.iter(), count, a, b)?;
                    if wide.is_empty() {
                        None
                    } else {
                        records += wide.len();
                        Some(work.pack_parts(wide)?)
                    }
                };
                if let Some(parts) = packed {
                    work.retain_interval(
                        parts
                            .allocated_bytes()
                            .saturating_add(std::mem::size_of::<Packet>())
                            .saturating_add(if lifetime {96}else{0}),
                    );
                    push_checked(&mut out, Packet { target, parts })?;
                }
            }
            if records > self.record_budget {
                return Err(budget("entry interval record budget"));
            }
        }
        work.end_interval();
        if crate::v1_trace::enabled() {
            crate::v1_trace::add("split.in_rows", parts.len() as u64);
            crate::v1_trace::add("split.edges", edges.len() as u64);
            crate::v1_trace::add("split.out_rows", records as u64);
            crate::v1_trace::add("split.out_packets", out.len() as u64);
            if lifetime {interval_merge_census_ordered(&out)?;} else {interval_merge_census(&out);}
        }
        Ok(out)
    }
    fn rates(
        &self,
        heads: &BTreeMap<usize, BTreeMap<usize, f64>>,
        send: &BTreeMap<usize, f64>,
        receive: &BTreeMap<usize, f64>,
    ) -> CoreResult<BTreeMap<usize, f64>> {
        let mut q: BTreeMap<usize, f64> = heads.keys().map(|&i| (i, 0.)).collect();
        let mut active: smallvec::SmallVec<[usize; 8]> = heads.keys().copied().filter(|i| send[i] > 0.).collect();
        while !active.is_empty() {
            let mut bound = active.iter().map(|i| (send[i] - q[i]) / self.groups[*i][5]).fold(f64::INFINITY, f64::min);
            for (&j, &supply) in receive {
                let slope = sum(active
                    .iter()
                    .map(|i| heads[i].get(&j).copied().unwrap_or(0.) * self.groups[*i][5]));
                if slope > 0. {
                    let used = sum(heads
                        .iter()
                        .map(|(&i, b)| b.get(&j).copied().unwrap_or(0.) * q[&i]));
                    bound = bound.min((supply - used).max(0.) / slope);
                }
            }
            let step = bound.max(0.);
            for &i in &active {
                *q.get_mut(&i).unwrap() += step * self.groups[i][5];
            }
            let saturated: smallvec::SmallVec<[usize; 8]> = receive
                .iter()
                .filter_map(|(&j, &supply)| {
                    if supply
                        - sum(heads
                            .iter()
                            .map(|(&i, b)| b.get(&j).copied().unwrap_or(0.) * q[&i]))
                        <= 1e-12 * supply.max(1.)
                    {
                        Some(j)
                    } else {
                        None
                    }
                })
                .collect();
            let n = active.len();
            active.retain(|i| {
                send[i] - q[i] > 1e-12 * send[i].max(1.)
                    && !saturated
                        .iter()
                        .any(|j| heads[i].get(j).copied().unwrap_or(0.) > 0.)
            });
            if active.len() == n {
                return Err(arithmetic("progressive supply allocation stalled"));
            }
        }
        Ok(q)
    }
    fn check_state(&self,s:&RoadState)->CoreResult<()>{self.check_state_codec(s,compact_checkpoint_enabled())}
    fn check_state_codec(&self,s:&RoadState,compact:bool)->CoreResult<()> {
        if s.cells.len()!=self.groups.len()||s.pending.len()!=self.groups.len()||s.ledger.len()!=self.classes.len()||!finite_nonnegative(s.t)||s.totals.iter().any(|v|!finite_nonnegative(*v)){return Err(val("invalid native road state schema/ledger"))}
        let packets=s.cells.iter().map(|c|c.packets.len()).chain(s.pending.iter().map(Vec::len)).fold(0usize,usize::saturating_add);
        let scratch=if compact{road_stream_validation_bound(packets,s.cells.len())}else{
            // Keep the established small-budget/legacy admission contract
            // until the compact codec is selected explicitly.
            let rows=s.cells.iter().flat_map(|c|&c.packets).chain(s.pending.iter().flatten()).map(|p|p.parts.len()).fold(0usize,usize::saturating_add);
            rows.saturating_mul(16).saturating_add(packets.saturating_add(s.cells.len()).saturating_mul(32))
        };
        if self.storage_budget.is_some(){
            // debug_stats/retained_storage_bytes has a key-pointer census,
            // not an array of physical rows. Admit that transient first.
            check_storage_limit(self.storage_budget,scratch,"streaming validation census")?;
            let bytes=s.retained_storage_bytes().max(self.retained_input_bytes).saturating_mul(3).saturating_add(scratch);
            check_storage_limit(self.storage_budget,bytes,"state validation workspace")?;
        }
        let mut stored:Vec<_>=(0..self.classes.len()).map(|_|RoadExpansion::default()).collect();
        let mut all=RoadExpansion::default();let mut residence=RoadExpansion::default();let mut records=0usize;
        // Each reduction sees exactly its old input order: packet mass
        // nested for occupancy, flat row order for length occupancy, class
        // streams across road then pending, no change to arithmetic barriers.
        for (i,c) in s.cells.iter().enumerate(){
            if !c.v[0].is_finite()||!c.v[1].is_finite()||!(0.0..=1.0).contains(&c.v[1])||c.v[2..].iter().any(|x|!finite_nonnegative(*x))||c.latent.iter().any(|(k,x)|*k>=self.classes.len()||!x.is_finite()||!(0.0..=1.0).contains(x)){return Err(val("invalid native cell state"))}
            if c.packets.windows(2).any(|w|w[0].target>w[1].target+1e-10)||s.pending[i].windows(2).any(|w|w[0].target>w[1].target){return Err(arithmetic("packet/source order"))}
            let mut occupancy=RoadExpansion::default();let mut occupied=RoadExpansion::default();
            for (pending,qs) in [(false,&c.packets),(true,&s.pending[i])]{
                if pending{
                    let occ=std::mem::take(&mut occupancy).finish_finite()?;
                    if (c.v[2]-c.v[3]-occ).abs()>1e-9*c.v[2].max(1.){return Err(arithmetic("cell mass ledger"))}
                    if std::mem::take(&mut occupied).finish_finite()?>self.groups[i][4]+1e-9*self.groups[i][4].max(1.){return Err(arithmetic("cell storage"))}
                    residence.add_finite((c.v[2]-c.v[3])*s.t-c.v[4]+c.v[5])?;all.add_finite(occ)?;
                }
                for packet in qs{
                    if packet.parts.is_empty()||!packet.target.is_finite()||pending&&!(0.0..=s.t).contains(&packet.target){return Err(val("empty/invalid native packet"))}
                    let mut packet_mass=RoadExpansion::default();
                    for p in &packet.parts{
                        records=records.checked_add(1).ok_or_else(||budget("packet row count overflow"))?;
                        if records>self.record_budget{return Err(budget("packet state budget"))}
                        if p.tag>=self.routes.len()||!p.mass.is_finite()||p.mass<=0.||!finite_nonnegative(p.birth)||p.birth>p.mass*s.t+1e-8{return Err(val("invalid homogeneous native part"))}
                        if self.path(p.tag).get(p.offset)!=Some(&i){return Err(val("native route suffix mismatch"))}
                        if p.a.is_some()!=p.b.is_some()||p.a.is_some_and(|a|!a.is_finite()||a<0.||!p.b.unwrap().is_finite()||a>p.b.unwrap()||p.b.unwrap()>s.t+1e-9){return Err(val("invalid native entry interval"))}
                        packet_mass.add_finite(p.mass)?;stored[self.class(&p)].add_finite(p.mass)?;
                        if !pending{occupied.add_finite(p.mass*self.footprint(p.tag))?;}
                    }
                    let m=packet_mass.finish_finite()?;
                    if pending{all.add_finite(m)?;}else{occupancy.add_finite(m)?;}
                }
            }
        }
        let tol=1e-9*s.totals[0].max(1.);
        if (s.totals[0]-s.totals[1]-all.finish_finite()?).abs()>tol{return Err(arithmetic("network mass ledger"))}
        let total_residence=residence.finish_finite()?+s.totals[4]+s.totals[5]+s.totals[6];
        let system=(s.totals[0]-s.totals[1])*s.t-s.totals[2]+s.totals[3];
        if !total_residence.is_finite()||!system.is_finite()||(total_residence-system).abs()>1e-8*total_residence.max(1.){return Err(arithmetic("residence ledger"))}
        for (l,acc) in s.ledger.iter().zip(stored){if l.iter().any(|x|!finite_nonnegative(*x))||(l[0]-l[1]-acc.finish_finite()?).abs()>1e-9*l[0].max(1.){return Err(arithmetic("class mass/ledger mismatch"))}}
        for (a,b) in [(0,0),(1,1),(2,4),(4,5)]{let mut acc=RoadExpansion::default();for l in &s.ledger{acc.add_finite(l[a])?;}let observed=acc.finish_finite()?;if (observed-s.totals[b]).abs()>1e-8*observed.max(s.totals[b]).max(1.){return Err(arithmetic("class/global ledger mismatch"))}}
        Ok(())
    }
    fn step_state(
        &self,
        s: &RoadState,
        dt: f64,
        offers: Vec<Offer>,
        call_input: Option<&RoadState>,
    ) -> CoreResult<(RoadState, ChunkedEvents)> {
        self.check_state(s)?;
        if !dt.is_finite() || dt <= 0. {
            return Err(val("positive finite interval required"));
        }
        let t = s.t;
        let end = t + dt;
        if !end.is_finite() {
            return Err(arithmetic("road clock overflow"));
        }
        // Reserve the working allowance before copying large state/source
        // vectors. Large Vec allocations below use fallible reservations.
        let mut work = self.work_budget(s, &offers, call_input)?;
        if crate::v1_trace::enabled() {
            let stats = s.debug_stats();
            crate::v1_trace::add("tick.offers", offers.len() as u64);
            crate::v1_trace::add("tick.cell_parts", stats.cell_parts as u64);
            crate::v1_trace::add("tick.pending_parts", stats.pending_parts as u64);
            crate::v1_trace::add("tick.cell_packets", stats.cell_packets as u64);
            crate::v1_trace::add("tick.pending_packets", stats.pending_packets as u64);
        }
        for &(_, a, b, _) in &self.windows {
            if (t + 1e-10 < a && a < end - 1e-10) || (t + 1e-10 < b && b < end - 1e-10) {
                return Err(val("interval crosses a closure boundary"));
            }
        }
        for &(cycle, green, offset) in self.signals.iter().flatten() {
            for phase in [0., green] {
                let edge = offset + phase + (((t - offset - phase) / cycle).floor() + 1.) * cycle;
                if t + 1e-10 < edge && edge < end - 1e-10 {
                    return Err(val("interval crosses a signal boundary"));
                }
            }
        }
        // Cell queues are copied exactly once into the independent motion
        // workspaces below. Cloning them here as well only retained a second,
        // unused copy until each cell's survivors replaced it near commit.
        let mut out = RoadState {
            t: end,
            cells: s
                .cells
                .iter()
                .map(|cell| Cell {
                    v: cell.v,
                    packets: Vec::new(),
                    latent: BTreeMap::new(),
                })
                .collect(),
            pending: s
                .pending
                .iter()
                .map(|queue| clone_packets(queue))
                .collect::<CoreResult<_>>()?,
            totals: s.totals,
            ledger: s.ledger.clone(),
        };
        let mut new: BTreeMap<usize, Vec<Part>> = BTreeMap::new();
        let (mut born, mut birth1, mut inherited) = (0., 0., 0.);
        for (tag, m, b, a, z) in offers {
            if tag >= self.routes.len()
                || !finite_nonnegative(m)
                || !finite_nonnegative(b)
                || b > m * t
                || (m == 0. && b != 0.)
                || a.is_some() != z.is_some()
                || a.is_some_and(|a| {
                    !finite_nonnegative(a)
                        || !finite_nonnegative(z.unwrap())
                        || a > z.unwrap()
                        || z.unwrap() > t + 1e-9
                })
            {
                return Err(val("invalid source mass/birth/interval"));
            }
            if m > 0. {
                push_checked(
                    new.entry(self.path(tag)[0]).or_default(),
                    Part {
                        tag,
                        offset: 0,
                        mass: m,
                        birth: b,
                        a: PackedTime::new(a)?,
                        b: PackedTime::new(z)?,
                    },
                )?;
                born += m;
                birth1 += b;
                inherited += m * t - b;
                out.ledger[self.routes[tag].1][0] += m;
            }
        }
        for (i, p) in new {
            push_checked(
                &mut out.pending[i],
                Packet {
                    target: t,
                    parts: if work.timed_referenced_rows.is_some()&&receiving_lifetime_enabled(){
                        // Raw offered vectors and the source-only combine
                        // index/output are already in the offer reserve.
                        // Charge the new packed allocation independently.
                        PacketParts::pack(combine(p)?,|bytes|work.require(bytes,"source offer packing"))?
                    }else{work.pack_parts(combine(p)?)?},
                },
            )?;
        }
        let source_wait = dt * sum(out.pending.iter().flat_map(|q| q.iter().map(mass)));
        for q in &out.pending {
            for packet in q {
                for p in &packet.parts {
                    out.ledger[self.class(&p)][2] += dt * p.mass;
                }
            }
        }
        let n = self.groups.len();
        let factor: Vec<f64> = (0..n).map(|i| self.factor(i, t + dt / 2.)).collect();
        let receive: Vec<f64> = (0..n).map(|i| self.groups[i][2] * factor[i]).collect();
        let mut free: Vec<f64> = receive.iter().map(|r| r * dt).collect();
        let mut space: Vec<f64> = (0..n)
            .map(|i| (self.groups[i][4] - self.occupied(&s.cells[i])).max(0.))
            .collect();
        // Every prediction reads the same immutable old state. Keep each
        // cell's arithmetic and packet order unchanged; collect by index and
        // inspect results serially so even multiple failures choose the same
        // error as the serial oracle. Node allocation below is not parallel.
        let predictions = ordered_map(n, 32, |i| -> CoreResult<_> {
            let c = &s.cells[i];
            let m = self.motion(i, c, dt, factor[i])?;
            let distance = sum(c
                .packets
                .iter()
                .map(|p| mass(p) * m.dx.min((p.target - c.v[0]).max(0.))));
            let mut q = checkpoint_vec(c.packets.len())?;
            for p in &c.packets {
                let d = p.target - c.v[0];
                let ready = if d <= m.dx + 1e-10 {
                    m.passage(d.max(0.))?
                } else {
                    f64::INFINITY
                };
                q.push((clone_packet(p)?, ready));
            }
            Ok((m, q, distance))
        });
        let mut motions = Vec::with_capacity(n);
        let mut queues = Vec::with_capacity(n);
        for (i, prediction) in predictions.into_iter().enumerate() {
            let (m, q, distance) = prediction?;
            out.cells[i].v[0] += m.dx;
            out.cells[i].v[7] = m.speed;
            out.cells[i].latent = m.latent.clone();
            out.cells[i].v[6] += distance;
            queues.push(q);
            motions.push(m);
        }
        let mut position = vec![0; n];
        // Diagnostic only: previous serve per cell (head position, rate bits, end time).
        let mut last_serve: Vec<Option<(usize, u64, f64)>> = if crate::v1_trace::enabled() {
            vec![None; n]
        } else {
            Vec::new()
        };
        let mut events = ChunkedEvents::new(self.can_compact_candidate_events());
        let compact_incoming=self.can_compact_incoming_parts();
        let use_timed_incoming=work.timed_incoming_control_bytes.is_some();
        let mut timed_controls=TimedIncomingControls::new();
        let mut timed_rows=checkpoint_vec(if use_timed_incoming {n}else{0})?;
        if use_timed_incoming {
            timed_rows.extend((0..n).map(|_|if work.packed_ref_saved.is_some(){TimedIncomingRows::new_packed()}else{TimedIncomingRows::new()}));
        }
        let mut incoming: Vec<ChunkedParts> = (0..n)
            .map(|_| ChunkedParts::new(compact_incoming)).collect();
        // Diagnostic only: source (cell, head position, rate bits) per incoming row.
        let mut incoming_src: Vec<Vec<(usize, usize, u64)>> = if crate::v1_trace::source_attribution_enabled() {
            vec![vec![]; n]
        } else {
            Vec::new()
        };
        let mut marks: Vec<ChunkedMarks> = (0..n)
            .map(|_| ChunkedMarks::default()).collect();
        let (mut sink, mut exit1, mut hold) = (0., 0., 0.);
        let mut resolution = EventResolutionStats::default();
        for inc in &self.incoming {
            let mut clock = EventClock::default();
            let mut iterations = 0;
            while clock.remaining(dt) > 0. {
                let cursor = clock.hi;
                iterations += 1;
                if iterations
                    > self
                        .event_budget
                        .unwrap_or(self.record_budget + 2 * inc.len())
                {
                    return Err(budget("packet junction budget"));
                }
                // Heads identify owned queue rows. Cloning a potentially huge
                // mixed packet just to inspect its mass/routes retained a full
                // extra Part vector for every junction event.
                // The active heads are immutable until the serve loop.
                // Cache their exact old fsum result for this event only.
                let mut heads: BTreeMap<usize, f64> = BTreeMap::new();
                let mut future = vec![];
                let mut beta: BTreeMap<usize, BTreeMap<usize, f64>> = BTreeMap::new();
                let mut beta_space: BTreeMap<usize, BTreeMap<usize, f64>> = BTreeMap::new();
                for &i in inc {
                    if position[i] >= queues[i].len() {
                        continue;
                    }
                    let (packet, ready) = &queues[i][position[i]];
                    if clock.after_ready(*ready) {
                        if *ready < dt {
                            future.push(*ready);
                        }
                        continue;
                    }
                    let mut dest: BTreeMap<usize, RoadExpansion> = BTreeMap::new();
                    let mut ds: BTreeMap<usize, RoadExpansion> = BTreeMap::new();
                    for p in &packet.parts {
                        let j = self.dest(&p).unwrap_or(n);
                        dest.entry(j).or_default().add_finite(p.mass)?;
                        ds.entry(j).or_default().add_finite(p.mass*self.footprint(p.tag))?;
                    }
                    let pm=mass(packet);heads.insert(i,pm);
                    beta.insert(i, dest.into_iter().map(|(j, v)| (j, v.finish() / pm)).collect());
                    beta_space.insert(i, ds.into_iter().map(|(j, v)| (j, v.finish() / pm)).collect());
                }
                let send: BTreeMap<usize, f64> = heads
                    .keys()
                    .map(|&i| {
                        (
                            i,
                            self.groups[i][3]
                                * factor[i]
                                * if self.green(i, t + dt / 2.) { 1. } else { 0. },
                        )
                    })
                    .collect();
                let rec: BTreeMap<usize, f64> = beta
                    .values()
                    .flat_map(|b| {
                        b.keys().filter(|&&j| j < n).map(|&j| {
                            (
                                j,
                                if free[j] > 1e-13 && space[j] > 1e-13 {
                                    receive[j]
                                } else {
                                    0.
                                },
                            )
                        })
                    })
                    .collect();
                let rates: BTreeMap<usize, f64> = self
                    .rates(&beta, &send, &rec)?
                    .into_iter()
                    .filter(|(_, r)| *r > 0.)
                    .collect();
                if rates.is_empty() {
                    if future.is_empty() {
                        break;
                    }
                    clock.jump(future.into_iter().fold(f64::INFINITY, f64::min));
                    continue;
                }
                let dr: BTreeMap<usize, f64> = rec
                    .keys()
                    .map(|&j| {
                        (
                            j,
                            sum(rates
                                .iter()
                                .map(|(&i, &r)| beta[&i].get(&j).copied().unwrap_or(0.) * r)),
                        )
                    })
                    .collect();
                let sr: BTreeMap<usize, f64> = rec
                    .keys()
                    .map(|&j| {
                        (
                            j,
                            sum(rates
                                .iter()
                                .map(|(&i, &r)| beta_space[&i].get(&j).copied().unwrap_or(0.) * r)),
                        )
                    })
                    .collect();
                let mut h = clock.remaining(dt);
                let mut time_boundary = Some(dt);
                for &x in &future {
                    let remaining = clock.remaining(x);
                    if remaining > 0. && remaining < h {
                        h = remaining;
                        time_boundary = Some(x);
                    }
                }
                for (&i, &r) in &rates {
                    let limit=heads[&i]/r;
                    if limit < h {
                        h = limit;
                        time_boundary = None;
                    }
                }
                for (&j, &r) in &dr {
                    if r > 0. {
                        let limit = free[j] / r;
                        if limit < h {
                            h = limit;
                            time_boundary = None;
                        }
                    }
                }
                for (&j, &r) in &sr {
                    if r > 0. {
                        let limit = space[j] / r;
                        if limit < h {
                            h = limit;
                            time_boundary = None;
                        }
                    }
                }
                let subulp = h > 0. && cursor + h == cursor;
                let retires_head = subulp
                    && rates.iter().any(|(&i, &rate)| {
                        let fraction=(rate*h/heads[&i]).min(1.);
                        fraction == 1. || 1. - fraction < 1e-14
                    });
                if h <= 0. || (subulp && !clock.active && !retires_head) {
                    // Construct diagnostics only on failure. Keep the event
                    // candidates, reduction order and rejection rule unchanged.
                    let head_context: Vec<_> = rates
                        .iter()
                        .map(|(&i, &rate)| {
                            let (packet, ready) = &queues[i][position[i]];
                            let head_mass=heads[&i];
                            (
                                i,
                                position[i],
                                *ready,
                                packet.parts.len(),
                                head_mass,
                                rate,
                                head_mass / rate,
                            )
                        })
                        .collect();
                    let destination_context: Vec<_> = rec
                        .keys()
                        .map(|&j| {
                            let demand = dr[&j];
                            let occupied_rate = sr[&j];
                            (
                                j,
                                free[j],
                                space[j],
                                receive[j],
                                demand,
                                occupied_rate,
                                if demand > 0. {
                                    free[j] / demand
                                } else {
                                    f64::INFINITY
                                },
                                if occupied_rate > 0. {
                                    space[j] / occupied_rate
                                } else {
                                    f64::INFINITY
                                },
                            )
                        })
                        .collect();
                    let reason = if h <= 0. {
                        "nonpositive_duration"
                    } else {
                        "unrepresentable_cursor_increment_without_head_progress"
                    };
                    return Err(arithmetic(&format!(
                        "packet event resolution exhausted: reason={reason}, t={t:?}, cursor={cursor:?}, h={h:?}, dt={dt:?}, cursor_bits={:#018x}, h_bits={:#018x}, cursor_plus_h={:?}, absolute_start={:?}, absolute_end={:?}, incoming={inc:?}, iteration={iterations}, events={}, future={future:?}, supply_floor=1e-13, head_fields=(index,position,ready,parts,mass,rate,mass_over_rate), heads={head_context:?}, destination_fields=(index,free,space,receive,dr,sr,free_over_dr,space_over_sr), destinations={destination_context:?}",
                        cursor.to_bits(), h.to_bits(), cursor + h, t + cursor, t + cursor + h, events.len()
                    )));
                }
                if subulp {
                    clock.active = true;
                    clock.stats.count = clock.stats.count.saturating_add(1);
                    clock.stats.processed_time_bound =
                        upper_add(clock.stats.processed_time_bound, h);
                    for &rate in rates.values() {
                        // Diagnostic bound for ordinary rounded mass splitting;
                        // these positive masses are still served and retained.
                        let product = rate * h;
                        let product_bound = if product.is_finite() {
                            f64::from_bits(product.to_bits() + 1)
                        } else {
                            product
                        };
                        clock.stats.rate_weighted_mass_bound =
                            upper_add(clock.stats.rate_weighted_mass_bound, product_bound);
                    }
                    clock.check_bound()?;
                }
                let local_mid = clock.offset(h / 2.);
                let start_time = if clock.active {
                    t + clock.offset(0.)
                } else {
                    t + cursor
                };
                let end_time = if clock.active {
                    t + clock.offset(h)
                } else {
                    t + cursor + h
                };
                let mid = if clock.active {
                    t + local_mid
                } else {
                    t + cursor + h / 2.
                };
                let mut retired_heads = 0usize;
                for (&i, &rate) in &rates {
                    let packet = &queues[i][position[i]].0;
                    let ready = queues[i][position[i]].1;
                    let mut fraction=(rate*h/heads[&i]).min(1.);
                    if 1. - fraction < 1e-14 {
                        fraction = 1.;
                    }
                    let incoming_count=served_parts(&packet.parts,fraction)
                        .filter(|part|self.dest(part).is_some()).count();
                    work.event_candidate_live_bound=Some(events.projected_candidate_bytes(
                        packet.parts.len(),i,start_time,end_time,
                    )?);
                    if use_timed_incoming {
                        // At most one immutable time/mark control per class in
                        // this serve; all original per-row arithmetic remains.
                        work.timed_incoming_control_bytes=Some(timed_control_storage_bound(
                            &timed_controls,self.classes.len(),n)?);
                    }
                    if let Some(refs)=&mut work.timed_referenced_rows {
                        *refs=refs.checked_add(incoming_count).ok_or_else(||budget("receiving reference count overflow"))?;
                    }
                    work.transfer_indexed(
                        packet.parts.len(),
                        served_parts(&packet.parts,fraction)
                            .filter_map(|part|self.dest(&part)),
                    )?;
                    if self.storage_budget.is_some()
                        && events.len().saturating_add(packet.parts.len())
                            > self.checkpoint_event_limit()
                    {
                        return Err(budget("packet transfer budget"));
                    }
                    // The trace still counts the same logical rows. The
                    // transient served Vec is replaced by a read-only view.
                    let served_rows = if crate::v1_trace::enabled() {
                        served_parts(&packet.parts, fraction).count()
                    } else {
                        0
                    };
                    if crate::v1_trace::enabled() {
                        let key = (position[i], rate.to_bits());
                        let class = match last_serve[i] {
                            Some((pos, bits, prev_end))
                                if (pos, bits) == key && prev_end == start_time =>
                            {
                                "xfer.same_rate_contiguous_rows"
                            }
                            Some((pos, _, prev_end))
                                if pos == position[i] && prev_end == start_time =>
                            {
                                "xfer.rate_change_contiguous_rows"
                            }
                            Some((pos, _, _)) if pos == position[i] => "xfer.same_head_gap_rows",
                            _ => "xfer.new_head_rows",
                        };
                        crate::v1_trace::add(class, served_rows as u64);
                        last_serve[i] = Some((position[i], rate.to_bits(), end_time));
                        crate::v1_trace::add("xfer.serve_rows", served_rows as u64);
                        crate::v1_trace::add("xfer.partial_serve", u64::from(fraction < 1.));
                        crate::v1_trace::add("xfer.serve_incoming_rows", incoming_count as u64);
                        crate::v1_trace::add(
                            "xfer.sink_rows",
                            served_rows.saturating_sub(incoming_count) as u64,
                        );
                        if fraction < 1. {
                            crate::v1_trace::add("xfer.partial_rows", served_rows as u64);
                        }
                        crate::v1_trace::add("xfer.head_rows", packet.parts.len() as u64);
                    }
                    // The original immutable head packet remains alive
                    // through the served Part, event and Mark source-order
                    // computations. Delay the independent remainder
                    // allocation until those raw incoming pages are actually
                    // appended, so the source's physically allocated page
                    // descriptors can be measured for that exact conversion.
                    // No mass/birth arithmetic, fraction or source f64 sum
                    // argument order is changed by this source-lifetime move.
                    let sm = sum(served_parts(&packet.parts, fraction).map(|p| p.mass));
                    out.cells[i].v[3] += sm;
                    out.cells[i].v[5] += sm * mid;
                    let mut serve_controls=[None;3];
                    let mut class_marks:[Option<Mark>;3]=[None;3];
                    // Exactly original IEEE mass/birth transform + source order.
                    for mut p in served_parts(&packet.parts, fraction) {
                        let k = self.class(&p);
                        out.ledger[k][3] += p.mass * (local_mid - ready).max(0.);
                        let j = self.dest(&p);
                        events.push_checked(
                            (p.tag, i, j, p.mass, start_time, end_time, p.birth),
                        )?;
                        if let Some(j) = j {
                            free[j] = (free[j] - p.mass).max(0.);
                            space[j] = (space[j] - p.mass * self.footprint(p.tag)).max(0.);
                            out.ledger[k][4] += p.mass * (end - mid);
                            hold += p.mass * (end - mid);
                            // All served rows of one source/class at the
                            // same local midpoint have the identical mark.
                            // Cache the original arithmetic, not an
                            // approximation or reassociated expression.
                            let mark=*class_marks[k].get_or_insert_with(||{
                                let m=&motions[i];let rate=self.classes[k][8]+m.hazards[&k];let p0=m.initial[&k];
                                let latent=if rate==0.{p0}else{p0+(self.classes[k][8]/rate-p0)*(-(-rate*local_mid).exp_m1())};
                                compact_mark(m.sample(local_mid).1,latent)
                            });
                            p.offset += 1;
                            if self.intervals {
                                p.a = PackedTime::new(Some(start_time))?;
                                p.b = PackedTime::new(Some(end_time))?;
                            }
                            if use_timed_incoming {
                                let control=match serve_controls[k] {
                                    Some(id)=>id,
                                    None=>{
                                        let id=timed_controls.push_checked(p.a,p.b,mark)?;
                                        serve_controls[k]=Some(id);
                                        id
                                    }
                                };
                                debug_assert_eq!(timed_controls.get(control).2.0.to_bits(),mark.0.to_bits());
                                debug_assert_eq!(timed_controls.get(control).2.1.to_bits(),mark.1.to_bits());
                                if work.timed_referenced_rows.is_some() {
                                    let saved=timed_rows[j].push_event(p,control,&timed_controls,&events,events.len()-1)?;
                                    if let Some(total)=&mut work.packed_ref_saved{*total=total.checked_add(saved).ok_or_else(||budget("packed reference credit overflow"))?;}
                                } else {
                                    timed_rows[j].push_checked(p,control,&timed_controls)?;
                                }
                            } else {
                                marks[j].push_checked(mark)?;
                                incoming[j].push_checked(p)?;
                            }
                            if !incoming_src.is_empty() {
                                incoming_src[j].push((i, position[i], rate.to_bits()));
                            }
                        } else {
                            sink += p.mass;
                            out.ledger[k][1] += p.mass;
                            exit1 += p.mass * mid;
                        }
                    }
                    // The served immutable source is no longer needed after
                    // the loop; physical incoming Part/Mark and event pages
                    // have their final capacity for this packet. The source
                    // remainder now receives the identical original f64
                    // transform, and the slot is replaced at exactly the
                    // original logical packet lifecycle boundary.
                    if fraction < 1. {
                        let remainder=if use_timed_incoming {
                            // No intermediate raw Part remainder: preflight and
                            // allocate the sole final packed owner directly.
                            PacketParts::pack_scaled_from(&packet.parts,1.-fraction,
                                |bytes|work.require(bytes,"source remainder packing"))?
                        } else {
                            work.pack_parts_with_live_descriptors(
                                portion(&packet.parts,1.-fraction)?,&incoming,&marks)?
                        };
                        queues[i][position[i]].0.parts=remainder;
                    } else {
                        position[i] += 1;
                        retired_heads += 1;
                    }
                }
                if crate::v1_trace::enabled() {
                    crate::v1_trace::add("xfer.substep_heads", rates.len() as u64);
                }
                if !clock.advance(h, time_boundary)? && retired_heads == 0 {
                    return Err(arithmetic(
                        "packet compensated clock made no finite progress",
                    ));
                }
                if events.len() > self.checkpoint_event_limit() {
                    return Err(budget("packet transfer budget"));
                }
            }
            // A rounded boundary subtraction can put the represented pair a
            // fraction of an ULP beyond dt. Keep that explicit and bounded.
            let overshoot = (-clock.remaining(dt)).max(0.);
            if clock.active && overshoot > 0. {
                clock.stats.clock_roundoff_bound =
                    upper_add(clock.stats.clock_roundoff_bound, overshoot);
                clock.check_bound()?;
            }
            resolution.merge(clock.stats);
        }
        if use_timed_incoming && crate::v1_trace::enabled() {
            crate::v1_trace::add("event_time.source_rows",events.len() as u64);
            crate::v1_trace::add("event_time.exact_time_runs",events.time_len as u64);
            crate::v1_trace::add("event_time.source_time_runs",events.control_len as u64);
            crate::v1_trace::add("event_time.physical_payload_bytes",events.physical_capacity_bytes() as u64);
            crate::v1_trace::add("event_time.saved_payload_bytes",
                events.capacity().saturating_mul(std::mem::size_of::<CompactEventRow>())
                    .saturating_sub(events.physical_capacity_bytes()) as u64);
        }
        if work.limit.is_some() && crate::v1_trace::enabled() && !use_timed_incoming {
            crate::v1_trace::add("event_time.source_rows",events.len() as u64);
            crate::v1_trace::add("event_time.exact_time_runs",events.time_len as u64);
            crate::v1_trace::add("event_time.source_time_runs",events.control_len as u64);
            crate::v1_trace::add("event_time.physical_payload_bytes",events.physical_capacity_bytes() as u64);
            crate::v1_trace::add("event_time.saved_payload_bytes",
                events.capacity().saturating_mul(std::mem::size_of::<CompactEventRow>())
                    .saturating_sub(events.physical_capacity_bytes()) as u64);
            let incoming_cap: usize = incoming.iter().map(ChunkedParts::capacity).sum();
            let incoming_real_payload:usize=incoming.iter().map(ChunkedParts::physical_capacity_bytes).sum();
            let marks_cap: usize = marks.iter().map(ChunkedMarks::capacity).sum();
            let incoming_len: usize = incoming.iter().map(ChunkedParts::len).sum();
            crate::v1_trace::guard(
                "road_actual",
                "transfer buffers",
                events
                    .capacity()
                    .saturating_mul(std::mem::size_of::<EventRow>())
                    .saturating_add(incoming_cap.saturating_mul(std::mem::size_of::<Part>()))
                    .saturating_add(marks_cap.saturating_mul(std::mem::size_of::<Mark>())),
                work.limit.unwrap_or(usize::MAX),
                &[
                    ("events_len", events.len()),
                    ("events_cap", events.capacity()),
                    ("incoming_len", incoming_len),
                    ("incoming_cap", incoming_cap),
                    ("incoming_real_payload_bytes", incoming_real_payload),
                    ("marks_cap", marks_cap),
                    ("charged_events", work.events),
                    ("charged_incoming", work.incoming),
                ],
            );
        }
        for i in 0..n {
            for (p, ready) in &queues[i][position[i]..] {
                for part in &p.parts {
                    out.ledger[self.class(&part)][3] += part.mass * (dt - ready).max(0.);
                }
            }
            // The transition owns these queue packets; moving survivors avoids
            // copying all remaining Part rows a second time at commit.
            let queue = std::mem::take(&mut queues[i]);
            let mut survivors = checkpoint_vec(queue.len() - position[i])?;
            survivors.extend(
                queue
                    .into_iter()
                    .skip(position[i])
                    .map(|(packet, _)| packet),
            );
            out.cells[i].packets = survivors;
            let mut active: smallvec::SmallVec<[bool; 8]> = std::iter::repeat_n(false,self.classes.len()).collect();
            for p in &out.cells[i].packets {
                for x in &p.parts {
                    active[self.class(&x)] = true;
                }
            }
            out.cells[i].latent.retain(|k, _| active[*k]);
            if !active.iter().any(|b| *b) {
                out.cells[i].v[7] = 0.;
            }
        }
        for i in 0..n {
            let mut remain = vec![];
            for p in &out.pending[i] {
                let ps = sum(p.parts.iter().map(|p| p.mass * self.footprint(p.tag)));
                let mut f = if free[i] > 0. && space[i] > 0. {
                    1.0_f64.min(free[i] / mass(p)).min(space[i] / ps)
                } else {
                    0.
                };
                if 1. - f < 1e-14 {
                    f = 1.;
                }
                let expected_pending=if f>0.0 {
                    p.parts.iter().filter(|part|part.mass*f>0.0).count()
                }else{0};
                if f > 0.0 {
                    if use_timed_incoming {
                        work.timed_incoming_control_bytes=Some(timed_control_storage_bound(
                            &timed_controls,self.classes.len(),n)?);
                    }
                    work.transfer_indexed(
                        0,std::iter::repeat(i).take(expected_pending),
                    )?;
                }
                if crate::v1_trace::enabled() {
                    crate::v1_trace::add("pending.rows", p.parts.len() as u64);
                    if f > 0. && f < 1. {
                        crate::v1_trace::add("pending.partial_rows", p.parts.len() as u64);
                    }
                }
                let mut parts = portion(&p.parts, f)?;
                debug_assert_eq!(parts.len(),expected_pending);
                let m = sum(parts.iter().map(|p| p.mass));
                free[i] = (free[i] - m).max(0.);
                space[i] =
                    (space[i] - sum(parts.iter().map(|p| p.mass * self.footprint(p.tag)))).max(0.);
                let mut pending_controls=[None;3];
                for part in &mut parts {
                    let k = self.class(&part);
                    if self.intervals {
                        part.a = PackedTime::new(Some(end))?;
                        part.b = PackedTime::new(Some(end))?;
                    }
                    let mark=compact_mark(self.classes[k][11], self.classes[k][7]);
                    if use_timed_incoming {
                        let control=match pending_controls[k] {
                            Some(id)=>id,
                            None=>{
                                let id=timed_controls.push_checked(part.a,part.b,mark)?;
                                pending_controls[k]=Some(id);
                                id
                            }
                        };
                        timed_rows[i].push_checked(*part,control,&timed_controls)?;
                    } else {
                        marks[i].push_checked(mark)?;
                    }
                }
                // Paged appends do not reallocate previous incoming Part rows.
                if !incoming_src.is_empty() {
                    let k = incoming_src[i].len();
                    incoming_src[i].extend((0..parts.len()).map(|_| (usize::MAX, k, 0)));
                }
                if use_timed_incoming {drop(parts);} else {incoming[i].extend_parts(parts)?;}
                if f < 1. {
                    push_checked(
                        &mut remain,
                        Packet {
                            target: p.target,
                            parts: work.pack_parts_with_live_descriptors(
                                portion(&p.parts, 1. - f)?,&incoming,&marks,
                            )?,
                        },
                    )?;
                }
            }
            out.pending[i] = remain;
        }
        // All raw Part and Mark appends have ended. Verify actual fixed page
        // header Vec capacities before replacing growth-time envelope in
        // subsequent interval sorting/packet packing source workspaces.
        if use_timed_incoming {
            lock_completed_timed_incoming(&mut work,&timed_rows,&timed_controls)?;
        } else {
            work.lock_completed_incoming_descriptors(&incoming,&marks)?;
        }
        // Retain the old reserve for default and wide representations. In
        // the opt-in exact indexed lane, only one consumer is live at a time.
        let full_consumer_base = work.base;
        let local_consumer = use_timed_incoming && work.timed_referenced_rows.is_some();
        let use_lifetimes=local_consumer && receiving_lifetime_enabled();
        let consumer_floor = if use_lifetimes {
            // All junction and pending loops have ended. Their row observers
            // and raw temporary arrays are dead. Queue survivors now belong
            // to out, which is measured before crediting any scratch.
            drop(motions);drop(queues);drop(position);drop(last_serve);
            drop(free);drop(space);
            let stats=s.debug_stats();
            let rows=stats.cell_parts.saturating_add(stats.pending_parts);
            let old=s.retained_storage_bytes().max(self.retained_input_bytes);
            let candidate=out.retained_storage_bytes();
            let source_observation_bytes=self.source_observation_reserve(s,&stats);
            let floor=receiving_lifetime_floor_bytes(full_consumer_base,work.transfer_exclusive_cell_scratch,source_observation_bytes,old,candidate)?;
            crate::v1_trace::add("receiving.expired_source_observation_bytes",source_observation_bytes as u64);
            crate::v1_trace::add("receiving.initial_candidate_owner_bytes",candidate as u64);
            work.base=floor;
            work.require(0,"receiving phase actual candidate owner")?;
            floor
        } else {full_consumer_base.saturating_sub(work.transfer_exclusive_cell_scratch)};
        // One exact-size rank ordinal scratch for the largest receiving cell.
        // All smaller cells reuse it; its whole lifetime stays in base charge.
        let mut rank_workspace:Vec<(u64,u32)>=Vec::new();
        let rank_bytes=if self.research_rank_bins.is_some(){
            let max=if use_timed_incoming{timed_rows.iter().map(TimedIncomingRows::len).max().unwrap_or(0)}else{incoming.iter().map(ChunkedParts::len).max().unwrap_or(0)};
            let bytes=max.checked_mul(std::mem::size_of::<(u64,u32)>()).ok_or_else(||budget("rank workspace bytes overflow"))?;
            work.require(bytes,"rank reusable ordinal workspace")?;
            rank_workspace=checkpoint_vec(max)?;
            if rank_workspace.capacity()!=max{return Err(budget("rank reusable capacity differs"))}
            crate::v1_trace::add("rank.workspace_reserved_bytes",bytes as u64);
            bytes
        }else{0};
        let consumer_floor=consumer_floor.saturating_add(rank_bytes);
        if !local_consumer{work.base=work.base.saturating_add(rank_bytes);}
        for i in 0..n {
            if local_consumer { work.base = consumer_floor; }
            let raw_rows=if use_timed_incoming {timed_rows[i].len()}else{incoming[i].len()};
            if !incoming_src.is_empty() && raw_rows>0 {
                if use_timed_incoming {
                    exact_merge_census(timed_rows[i].iter_with_events(&timed_controls,&events).map(|(p,_)|p),&incoming_src[i]);
                } else {
                    exact_merge_census(incoming[i].iter(), &incoming_src[i]);
                }
            }
            // Diagnostic-only input sequence is consumed and is not retained
            // for any original physical source calculation in a later cell.
            if !incoming_src.is_empty() {
                drop(std::mem::take(&mut incoming_src[i]));
            }
            // One compact mark accompanies exactly one source-order incoming
            // Part (both road service and pending-offer insertion paths).
            // Never call combine before consuming the aligned raw rows.
            if !use_timed_incoming && raw_rows != marks[i].len() {
                return Err(arithmetic("incoming Part/Mark source-order alignment differs"));
            }
            if local_consumer && raw_rows == 0 {
                // No transfer or pending arrival; the legacy added==0 arm
                // leaves the cell unchanged. Empty pages own no payload.
                continue;
            }
            let local_peak = if local_consumer {
                receiving_local_combine_scratch(0, self.classes.len())
            } else { 0 };
            if local_consumer {
                work.require(local_peak, "timed incoming local consumer preflight")?;
                crate::v1_trace::add("incoming_timed.local_consumer_scratch_bytes",local_peak as u64);
            }
            let old = self.occupancy(&out.cells[i]);
            let weighted_speed = if use_timed_incoming {
                sum(timed_rows[i].iter_with_events(&timed_controls,&events).map(|(part,mark)|part.mass*mark.0))
            } else {
                sum(incoming[i].iter().zip(marks[i].iter())
                    .map(|(part,mark)|part.mass*mark.0))
            };
            let mut byclass: BTreeMap<usize, ClassMoments> = BTreeMap::new();
            // Original fsum class input order: all unchanged survivor rows,
            // followed by each received mark in original append order.
            for packet in &out.cells[i].packets {
                for p in &packet.parts {
                    let k = self.class(&p);
                    byclass.entry(k).or_default().add(p.mass, out.cells[i].latent[&k]);
                }
            }
            if use_timed_incoming {
                for (part,mark) in timed_rows[i].iter_with_events(&timed_controls,&events) {
                    let k=self.class(&part);
                    byclass.entry(k).or_default().add(part.mass,mark.1);
                }
            } else {
                for (part, mark) in incoming[i].iter().zip(marks[i].iter()) {
                    let k = self.class(&part);
                    byclass.entry(k).or_default().add(part.mass,mark.1);
                }
            }
            // Same source-index key/tie order and separate mass/birth sum()
            // barriers. The timed carrier is read directly: no full raw
            // Part+Mark materialization exists at any point in this lane.
            let target = out.cells[i].v[0] + self.groups[i][0];
            let mut projected=None;
            let (parts,expired)=if use_timed_incoming {
                work.require(local_peak,"timed incoming direct combine")?;
                let source=std::mem::take(&mut timed_rows[i]);
                let get=|index|source.get_with_events(index,&timed_controls,&events).0;
                let parts=if let Some(bins)=self.research_rank_bins {
                    projected=Some(v1_rank_projection::project_with(source.len(),get,target,bins,dt,self.record_budget,local_peak,&mut work,&mut rank_workspace)?);
                    Vec::new()
                }else if local_consumer {
                    combine_compact_indexed_parts(source.len(),get,|index_bytes,groups|{
                        let scratch=local_peak.saturating_add(index_bytes)
                            .saturating_add(groups.saturating_mul(std::mem::size_of::<Part>()));
                        work.require(scratch,"timed incoming exact group allocation")
                    })?
                } else {combine_indexed_parts(source.len(),get)?};
                let expired=release_consumed_timed_incoming(&mut work,i,source)?;
                (parts,expired)
            } else {
                let source=std::mem::take(&mut incoming[i]);
                let parts=if let Some(bins)=self.research_rank_bins{
                    projected=Some(v1_rank_projection::project_with(source.len(),|index|source.get(index),target,bins,dt,self.record_budget,local_peak,&mut work,&mut rank_workspace)?);
                    Vec::new()
                }else{combine_chunked_parts(&source)?};
                let expired_marks=std::mem::take(&mut marks[i]);
                let expired=release_consumed_incoming_pair(&mut work,i,source,expired_marks)?;
                (parts,expired)
            };
            debug_assert_eq!(expired,raw_rows);
            if crate::v1_trace::enabled() && raw_rows > 0 {
                crate::v1_trace::add("entry.raw_rows", raw_rows as u64);
                crate::v1_trace::add("entry.combined_rows", projected.as_ref().map_or(parts.len(),|(p,_)|p.iter().map(|p|p.parts.len()).sum::<usize>()) as u64);
            }
            let added = projected.as_ref().map_or_else(||sum(parts.iter().map(|p|p.mass)),|(_,m)|*m);
            if added == 0. {
                continue;
            }
            let speed =
                (old * out.cells[i].v[7] + weighted_speed) / (old + added);
            out.cells[i].v[7] = speed;
            out.cells[i].latent = byclass
                .into_iter()
                .map(|(k, v)| {
                    (
                        k,
                        v.mean(),
                    )
                })
                .collect();
            if local_consumer && projected.is_none() {
                // Index vector is gone; the combined input is still owned
                // by interval_packets. Its separate sweep and packet
                // allocation envelopes remain intact.
                work.base = consumer_floor.saturating_add(
                    parts.capacity().saturating_mul(std::mem::size_of::<Part>()));
            }
            let packets = if let Some((p,_))=projected{p}else if self.intervals {
                self.interval_packets(parts, target, &mut work)?
            } else {
                vec![Packet {
                    target,
                    parts: work.pack_parts(parts)?,
                }]
            };
            if local_consumer { work.base = consumer_floor; }
            // The returned list, the cell's old slot buffer and its grown
            // replacement coexist during the reservation. Slots of interval
            // packets are already retained; charge any extra slack retained.
            let slot = std::mem::size_of::<Packet>();
            let old_capacity = out.cells[i].packets.capacity();
            let needed = out.cells[i].packets.len().saturating_add(packets.len());
            let grown = if needed > old_capacity {
                needed.max(old_capacity.saturating_mul(2)).max(4)
            } else {
                0
            };
            work.require(
                packets
                    .capacity()
                    .saturating_add(old_capacity)
                    .saturating_add(grown)
                    .saturating_mul(slot),
                "cell packet reservation",
            )?;
            out.cells[i]
                .packets
                .try_reserve(packets.len())
                .map_err(|_| budget("native road packet allocation unavailable"))?;
            let charged = if self.intervals { packets.len() } else { 0 };
            work.retain_interval(
                out.cells[i]
                    .packets
                    .capacity()
                    .saturating_sub(old_capacity)
                    .saturating_sub(charged)
                    .saturating_mul(slot),
            );
            out.cells[i].packets.extend(packets);
            out.cells[i].v[2] += added;
            out.cells[i].v[4] += added * end;
        }
        if let Some(milli)=self.research_ready_mass_milli{
            if local_consumer{work.base=consumer_floor;}
            for cell in &mut out.cells{v1_ready_rank::coalesce(&mut cell.packets,cell.v[0],milli as f64/1000.,60.,&mut work)?;}
        }
        drop(rank_workspace);
        work.base = full_consumer_base;
        // No timed source/control owner survives into validation or the
        // persistent candidate. Legacy state/checkpoint representation stays.
        drop(timed_rows);
        drop(timed_controls);
        for (j, v) in [born, sink, birth1, exit1, source_wait, hold, inherited]
            .into_iter()
            .enumerate()
        {
            out.totals[j] += v;
        }
        self.check_state(&out)?;
        if self.storage_budget.is_some() {
            let retained = s
                .retained_storage_bytes()
                .max(out.retained_storage_bytes())
                .max(self.retained_input_bytes);
            let observed = self.storage_budget.is_some_and(|limit| {
                crate::v1_trace::guard(
                    "road_candidate",
                    "candidate and immutable snapshot",
                    retained.saturating_mul(3),
                    limit,
                    &[("retained", retained)],
                )
            });
            if !observed {
                check_storage_limit(
                    self.storage_budget,
                    retained.saturating_mul(3),
                    "candidate and immutable snapshot",
                )?;
            }
        }
        for i in 0..n {
            let tol = 1e-9 * out.totals[0].max(1.);
            if out.cells[i].v[2] - s.cells[i].v[2] > receive[i] * dt + tol
                || out.cells[i].v[3] - s.cells[i].v[3] > self.groups[i][3] * factor[i] * dt + tol
            {
                return Err(arithmetic("link rate budget"));
            }
        }
        if resolution.count > 0 {
            self.event_resolution
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .merge(resolution);
        }
        // Return still-paged source-ordered rows; the caller materializes
        // them only AFTER this function drops all work-local allocations.
        Ok((out, events))
    }
    fn row(&self) -> StateRow {
        let s = &self.state;
        let part = |p: Part| (p.tag, p.offset, p.mass, p.birth, p.a.option(), p.b.option());
        let packet = |p: &Packet| (p.target, p.parts.iter().map(part).collect());
        (
            self.identity.clone(),
            s.t,
            s.cells
                .iter()
                .map(|c| {
                    (
                        c.v.to_vec(),
                        c.packets.iter().map(packet).collect(),
                        c.latent.iter().map(|(&k, &v)| (k, v)).collect(),
                    )
                })
                .collect(),
            s.pending
                .iter()
                .map(|q| q.iter().map(packet).collect())
                .collect(),
            s.totals.to_vec(),
            s.ledger.iter().map(|v| v.to_vec()).collect(),
        )
    }
    fn row_packets(
        &self,
        rows: Vec<PacketRow>,
        work: &mut RoadDecodeBudget,
    ) -> CoreResult<Vec<Packet>> {
        work.reserve(
            rows.len()
                .saturating_mul(std::mem::size_of::<Packet>() + 32),
            rows.len().saturating_mul(32),
        )?;
        let mut result = checkpoint_vec(rows.len())?;
        for (target, rows) in rows {
            work.reserve(
                rows.len().saturating_mul(std::mem::size_of::<Part>()),
                rows.len().saturating_mul(16),
            )?;
            let mut parts = checkpoint_vec(rows.len())?;
            for (tag, offset, mass, birth, a, b) in rows {
                parts.push(Part {
                    tag,
                    offset,
                    mass,
                    birth,
                    a: PackedTime::new(a)?,
                    b: PackedTime::new(b)?,
                });
            }
            result.push(Packet {
                target,
                parts: work.pack_parts(parts)?,
            });
        }
        Ok(result)
    }
    fn from_row(&self, row: StateRow) -> CoreResult<RoadState> {
        let (identity, t, cells, pending, totals, ledger) = row;
        if identity != self.identity {
            return Err(val("native road checkpoint binding differs"));
        }
        // The typed frontend rows already exist on entry. Charge their large
        // buffers as well as the new owner before allocating either expanded
        // Part rows or their common-interval CorePart representation.
        let input_bytes = if self.storage_budget.is_some() {
            let queues = cells.iter().map(|c| &c.1).chain(pending.iter());
            let packet_bytes = queues
                .map(|q| {
                    q.capacity()
                        .saturating_mul(std::mem::size_of::<PacketRow>())
                        .saturating_add(
                            q.iter()
                                .map(|p| {
                                    p.1.capacity()
                                        .saturating_mul(std::mem::size_of::<PartRow>())
                                })
                                .sum::<usize>(),
                        )
                })
                .sum::<usize>();
            packet_bytes
                .saturating_add(
                    cells
                        .capacity()
                        .saturating_mul(std::mem::size_of::<CellRow>()),
                )
                .saturating_add(
                    pending
                        .capacity()
                        .saturating_mul(std::mem::size_of::<Vec<PacketRow>>()),
                )
                .saturating_add(
                    cells
                        .iter()
                        .map(|c| {
                            c.0.capacity()
                                .saturating_mul(8)
                                .saturating_add(c.2.capacity().saturating_mul(16))
                        })
                        .sum::<usize>(),
                )
                .saturating_add(totals.capacity().saturating_mul(8))
                .saturating_add(
                    ledger
                        .capacity()
                        .saturating_mul(std::mem::size_of::<Vec<f64>>()),
                )
                .saturating_add(
                    ledger
                        .iter()
                        .map(|l| l.capacity().saturating_mul(8))
                        .sum::<usize>(),
                )
        } else {
            0
        };
        let mut work = RoadDecodeBudget {
            limit: self.storage_budget,
            retained_input: if self.storage_budget.is_some() {
                self.retained_input_bytes
                    .max(self.state.retained_storage_bytes())
            } else {
                0
            },
            decoded: std::mem::size_of::<RoadState>()
                .saturating_add(3 * 32)
                .saturating_add(input_bytes),
            validation: 0,
        };
        work.reserve(
            cells
                .len()
                .saturating_mul(std::mem::size_of::<Cell>() + 256 + 2 * 32),
            cells.len().saturating_mul(32),
        )?;
        let mut cs = checkpoint_vec(cells.len())?;
        for (v, p, l) in cells {
            let v: [f64; 8] = v.try_into().map_err(|_| val("cell row length"))?;
            work.reserve(l.len().saturating_mul(256), 0)?;
            let latent: BTreeMap<usize, f64> = l.iter().copied().collect();
            if latent.len() != l.len() {
                return Err(val("duplicate latent class"));
            }
            cs.push(Cell {
                v,
                packets: self.row_packets(p, &mut work)?,
                latent,
            });
        }
        let totals: [f64; 7] = totals.try_into().map_err(|_| val("totals row length"))?;
        work.reserve(
            ledger.len().saturating_mul(std::mem::size_of::<[f64; 5]>()),
            0,
        )?;
        let mut ls = checkpoint_vec(ledger.len())?;
        for l in ledger {
            ls.push(l.try_into().map_err(|_| val("ledger row length"))?);
        }
        work.reserve(
            pending
                .len()
                .saturating_mul(std::mem::size_of::<Vec<Packet>>()),
            0,
        )?;
        let mut sources = checkpoint_vec(pending.len())?;
        for q in pending {
            sources.push(self.row_packets(q, &mut work)?);
        }
        let s = RoadState {
            t,
            cells: cs,
            pending: sources,
            totals,
            ledger: ls,
        };
        self.check_state(&s)?;
        Ok(s)
    }
}
crate::optional_binding::optional_pymethods!(V1Road,
    [

    ] {
    /// Explicit byte-budget mode; legacy constructor record guards remain the
    /// default. Configuration is atomic and never mutates physical state.
    pub(crate) fn configure_storage_budget(&mut self, bytes: usize) -> CoreResult<()> {
        if bytes < std::mem::size_of::<Part>().max(std::mem::size_of::<EventRow>()) {
            return Err(val("positive native road storage budget required"));
        }
        let before = (self.storage_budget, self.record_budget);
        self.storage_budget = Some(bytes);
        self.record_budget = bytes / std::mem::size_of::<Part>();
        if let Err(error) = self.check_state(&self.state) {
            self.storage_budget = before.0;
            self.record_budget = before.1;
            return Err(error);
        }
        Ok(())
    }
    }
    [

    ] {

    fn storage_limits(&self) -> (Option<usize>, usize, usize, Option<usize>) {
        (
            self.storage_budget,
            self.record_budget,
            self.checkpoint_event_limit(),
            self.event_budget,
        )
    }
    }
    [

    ] {

    fn event_resolution_diagnostics(&self) -> (u64, f64, f64, f64) {
        self.event_resolution_stats()
    }
    }
    [

    ] {

    fn storage_layout_bytes(&self) -> (usize, usize, usize, usize) {
        (
            std::mem::size_of::<CorePart>(),
            std::mem::size_of::<Part>(),
            std::mem::size_of::<Packet>(),
            std::mem::size_of::<EventRow>(),
        )
    }
    }
    [

    ] {

    fn packet_storage_counts(&self) -> (usize, usize, usize, usize) {
        let stats = self.state.debug_stats();
        (
            stats.uniform_packets,
            stats.mixed_packets,
            stats.uniform_parts,
            stats.mixed_parts,
        )
    }
    }
    [
    #[new]
    #[pyo3(signature = (identity, dt, groups, signals, routes, classes, incoming, windows, record_budget, event_budget, intervals))]
    ] {

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        identity: String,
        dt: f64,
        groups: Vec<Vec<f64>>,
        signals: Vec<Option<(f64, f64, f64)>>,
        routes: Vec<(Vec<usize>, usize)>,
        classes: Vec<Vec<f64>>,
        incoming: Vec<Vec<usize>>,
        windows: Vec<(usize, f64, f64, f64)>,
        record_budget: usize,
        event_budget: Option<usize>,
        intervals: bool,
    ) -> CoreResult<Self> {
        let mut paths = Vec::new();
        let mut lookup: HashMap<Vec<usize>, usize> = HashMap::new();
        let mut tags = Vec::with_capacity(routes.len());
        for (path, k) in routes {
            let id = if let Some(&id) = lookup.get(&path) {
                id
            } else {
                let id = paths.len();
                lookup.insert(path.clone(), id);
                paths.push(path);
                id
            };
            tags.push((id, k));
        }
        Self::new_shared_routes(
            identity,
            dt,
            groups,
            signals,
            paths,
            tags,
            classes,
            incoming,
            windows,
            record_budget,
            event_budget,
            intervals,
        )
    }
    }
    [

    ] {

    fn snapshot(&self) -> StateRow {
        self.row()
    }
    }
    [

    ] {

    fn restore(&mut self, row: StateRow) -> CoreResult<()> {
        let s = self.from_row(row)?;
        self.state = s;
        self.retained_input_bytes = 0;
        self.service_event_accounting = None;
        Ok(())
    }
    }
    [

    ] {

    fn reset(&mut self, t: f64) -> CoreResult<()> {
        if !finite_nonnegative(t) || (t / self.dt - (t / self.dt).round()).abs() > 1e-9 {
            return Err(val("nonnegative grid-aligned time origin"));
        }
        self.state = self.blank(t);
        self.retained_input_bytes = 0;
        self.service_event_accounting = None;
        Ok(())
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn step(&mut self, py: Python<'_>, dt: f64, offers: Vec<Offer>) -> CoreResult<Vec<EventRow>> {
        self.begin_call_storage_accounting();
        let (mut s, pages) = py.allow_threads(|| self.step_state(&self.state, dt, offers, None))?;
        let e=self.materialize_event_after_road(&mut s,pages)?;
        self.state = s;
        Ok(e)
    }
    }
    [

    ] {

    #[cfg(feature="python-extension")]
    fn advance_batch(
        &mut self,
        py: Python<'_>,
        steps: Vec<(f64, Vec<Offer>)>,
    ) -> CoreResult<Vec<Vec<EventRow>>> {
        // Each successful interval commits; failures retain the last valid interval.
        self.begin_call_storage_accounting();
        let mut events = vec![];
        for (dt, offers) in steps {
            let (mut s, pages) = py.allow_threads(|| self.step_state(&self.state, dt, offers, None))?;
            let e=self.materialize_event_after_road(&mut s,pages)?;
            self.state = s;
            events.push(e);
        }
        Ok(events)
    }
    }
    [

    ] {

    fn registry_sizes(&self) -> (usize, usize, usize) {
        (self.routes.len(), self.paths.len(), self.groups.len())
    }
    }
);

impl V1Road {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new_shared_routes(
        identity: String,
        dt: f64,
        groups: Vec<Vec<f64>>,
        signals: Vec<Option<(f64, f64, f64)>>,
        paths: Vec<Vec<usize>>,
        routes: Vec<(usize, usize)>,
        classes: Vec<Vec<f64>>,
        incoming: Vec<Vec<usize>>,
        windows: Vec<(usize, f64, f64, f64)>,
        record_budget: usize,
        event_budget: Option<usize>,
        intervals: bool,
    ) -> CoreResult<Self> {
        let n = groups.len();
        if identity.is_empty()
            || n == 0
            || routes.is_empty()
            || !dt.is_finite()
            || dt <= 0.
            || record_budget == 0
            || event_budget == Some(0)
            || signals.len() != n
            || classes.is_empty()
            || classes.len() > 3
        {
            return Err(val("invalid native road configuration"));
        }
        if groups
            .iter()
            .any(|g| g.len() != 6 || g.iter().any(|x| !x.is_finite() || *x <= 0.))
            || classes.iter().any(|c| {
                c.len() != 13
                    || c.iter().any(|x| !finite_nonnegative(*x))
                    || [0, 1, 2, 3, 5, 6, 12].iter().any(|&i| c[i] <= 0.)
                    || c[7] > 1.
            })
        {
            return Err(val("invalid native physical coefficients"));
        }
        for &(cycle, green, offset) in signals.iter().flatten() {
            if !cycle.is_finite()
                || cycle <= 0.
                || !green.is_finite()
                || green < 0.
                || green > cycle
                || !offset.is_finite()
            {
                return Err(val("invalid native signal"));
            }
        }
        if windows.iter().any(|&(i, a, b, f)| {
            i >= n || !finite_nonnegative(a) || !b.is_finite() || b <= a || !finite_nonnegative(f)
        }) {
            return Err(val("invalid native closure"));
        }
        let mut seen = vec![0usize; n];
        for inc in &incoming {
            for &i in inc {
                if i >= n {
                    return Err(val("incoming index"));
                }
                seen[i] += 1;
            }
        }
        if seen.iter().any(|&n| n != 1) {
            return Err(val("incoming partition"));
        }
        if paths
            .iter()
            .any(|p| p.is_empty() || p.iter().any(|&i| i >= n))
            || routes
                .iter()
                .any(|&(p, k)| p >= paths.len() || k >= classes.len())
        {
            return Err(val("invalid native route"));
        }
        let registered_successor_width=registered_successor_width(&paths,n);
        let mut r = Self {
            identity,
            dt,
            groups,
            signals,
            paths,
            registered_successor_width,
            routes,
            classes,
            incoming,
            windows,
            record_budget,
            storage_budget: None,
            retained_input_bytes: 0,
            service_event_accounting: None,
            event_resolution: Mutex::new(EventResolutionStats::default()),
            event_budget,
            intervals,
            research_interval_bins:None,
            research_rank_bins:None,
            research_ready_mass_milli:None,
            state: RoadState {
                t: 0.,
                cells: vec![],
                pending: vec![],
                totals: [0.; 7],
                ledger: vec![],
            },
        };
        r.state = r.blank(0.);
        Ok(r)
    }
}

#[cfg(test)]
mod workspace_accounting_tests {
    use super::*;

    fn budget(limit: usize) -> RoadWorkBudget {
        RoadWorkBudget {
            limit: Some(limit),
            base: 0,
            transfer_exclusive_cell_scratch:0,
            events: 0, event_candidate_live_bound: None,
            incoming: 0,
            incoming_page_cells: 0,
            incoming_cell_rows:None,incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events: false,
            compact_incoming: false, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained: 0,
            interval_transient: 0,
            service_events: None,
        }
    }

    #[test]
    fn bounded_projection_retains_marked_mass_birth_and_endpoint_atom(){
        let mut w=budget(10_000_000);
        let mut parts=Vec::new();
        for tag in 0..64{for j in 0..21{
            let a=j as f64/4.;let b=a+1.25;
            parts.push(Part{tag,offset:1,mass:0.5,birth:2.5,a:PackedTime::new(Some(a)).unwrap(),b:PackedTime::new(Some(b)).unwrap()});
        }parts.push(Part{tag,offset:1,mass:0.25,birth:1.25,a:PackedTime::new(Some(6.25)).unwrap(),b:PackedTime::new(Some(6.25)).unwrap()});}
        let out=project_time_bins(&parts,123.,4,10.,10000,&mut w).unwrap().unwrap();
        assert!(out.len()<=5);
        for tag in 0..64{
            let m=sum(out.iter().flat_map(|p|p.parts.iter()).filter(|p|p.tag==tag).map(|p|p.mass));
            let b=sum(out.iter().flat_map(|p|p.parts.iter()).filter(|p|p.tag==tag).map(|p|p.birth));
            assert!((m-10.75).abs()<1e-12);assert!((b-53.75).abs()<1e-12);
        }
        assert_eq!(out.last().unwrap().parts.iter().next().unwrap().a.0,6.25f64.to_bits());
        assert!(out.iter().map(|p|p.parts.len()).sum::<usize>()<=5*64);
        let mut invalid=parts.clone();invalid[0].b=invalid[0].a;
        assert!(project_time_bins(&invalid,123.,4,10.,10000,&mut w).unwrap().is_none());
    }
    #[test]
    fn interval_transient_is_released_and_only_packed_rows_are_retained() {
        let mut w = budget(10_000);
        w.interval(9_000).unwrap();
        w.retain_interval(400);
        w.end_interval();
        // A second large interval fits once the first one's workspace died.
        w.interval(9_000).unwrap();
        w.retain_interval(400);
        w.end_interval();
        assert_eq!(w.interval_retained, 800);
        assert_eq!(w.interval_transient, 0);
        // Retained packed rows stay charged in later phases.
        assert!(w.require(10_000 - 800, "later").is_ok());
        assert!(w.require(10_000 - 799, "later").is_err());
    }

    #[test]
    fn road_step_event_charge_has_no_sink_terms() {
        let a = ServiceEventAccounting {
            input_bytes: 1_000,
            current_bytes: 2_000,
            shared_input_current: false,
            max_tag_bytes: 64,
        };
        let rows = 10_000;
        assert_eq!(
            a.road_step_bytes(rows),
            3_000 + paged_event_candidate_bytes(rows)
        );
        assert_eq!(a.road_step_bytes(0), 3_000+std::mem::size_of::<ChunkedEvents>());
    }

    #[test]
    fn sink_envelope_counts_only_exiting_rows() {
        assert_eq!(sink_envelope_bytes(0, 64), 0);
        let one = sink_envelope_bytes(1, 64);
        let many = sink_envelope_bytes(1_000, 64);
        assert!(one > 0 && many > 900 * (256 + 2 * 96));
        // Monotone in the exiting-row count.
        assert!(sink_envelope_bytes(1_001, 64) > many);
    }
}


#[cfg(test)]
mod exact_interval_sweep_tests {
    use super::*;

    fn row(tag: usize, mass: f64, birth: f64, a: f64, b: f64) -> Part {
        Part {
            tag,
            offset: tag % 3,
            mass,
            birth,
            a: PackedTime::new(Some(a)).unwrap(),
            b: PackedTime::new(Some(b)).unwrap(),
        }
    }

    fn check_old_selection_matches_events(rows: &[Part]) {
        let mut edges: Vec<f64> = rows.iter().flat_map(|r| [r.a.unwrap(), r.b.unwrap()]).collect();
        edges.sort_unstable_by(f64::total_cmp);
        edges.dedup();
        let mut indexed = IntervalActiveSweep::new(rows).unwrap();
        for (k, &a) in edges.iter().enumerate() {
            indexed.advance(a);
            let actual_points: Vec<_> = indexed.current_points.iter().copied().collect();
            let expected_points: Vec<_> = rows.iter().enumerate()
                .filter(|(_, x)| x.a == Some(a) && x.b == Some(a))
                .map(|(i, _)| i).collect();
            assert_eq!(actual_points, expected_points, "point index at {a:?}");
            if let Some(&b) = edges.get(k+1) {
                let original: Vec<_> = rows.iter().enumerate()
                    .filter(|(_, p)| p.a.unwrap() <= a &&
                        p.b.unwrap() >= b && p.b > p.a)
                    .map(|(i, _)| i).collect();
                let active: Vec<_> = indexed.active.iter().collect();
                assert_eq!(active, original, "interval [{a:?},{b:?}]");
            }
        }
    }

    #[test]
    fn original_finite_interval_and_point_selection_is_bitorder_preserving() {
        let rows = vec![
            row(1, 0.11, 2., -0., 2.),
            row(2, 0.25, 3., 0., 1.),
            row(3, 0.03, 4., -0., -0.),
            row(4, 0.04, 5., 0., 0.),
            row(5, 0.06, 6., 1., 1.),
            row(6, 0.07, 7., 2., 2.),
            row(7, 0.09, 8., 1., 3.),
            row(8, 0.10, 9., 3., 4.),
            row(9, 0.15, 10., 4., 4.),
        ];
        check_old_selection_matches_events(&rows);
    }

    #[test]
    fn randomized_original_scan_vs_event_sweep_selected_indices() {
        let mut seed = 0x59C9_2026_u64;
        for count in [1, 2, 5, 17, 64, 256, 700] {
            let mut rows = Vec::new();
            for i in 0..count {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let a = ((seed >> 24) % 40) as f64 - 10.;
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let width = ((seed >> 24) % 13) as f64;
                rows.push(row(i % 7, (i as f64 + 1.) / 100.,
                              (i as f64) * 0.07, a, a + width));
            }
            check_old_selection_matches_events(&rows);
            rows.reverse();
            check_old_selection_matches_events(&rows);
        }
    }

    fn fingerprint_part(p: Part) -> (usize, usize, u64, u64, Option<u64>, Option<u64>) {
        (
            p.tag,
            p.offset,
            p.mass.to_bits(),
            p.birth.to_bits(),
            p.a.option().map(f64::to_bits),
            p.b.option().map(f64::to_bits),
        )
    }

    #[test]
    fn original_split_and_combine_ieee_payloads_match_event_selected_rows() {
        let mut seed = 0x1E57_2026_u64;
        let mut rows = vec![
            row(1, 0.00125, 0.19, -0., -0.),
            row(1, 0.00250, 0.57, 0., 0.),
            row(2, 0.05432, 0.91, 0., 2.),
            row(2, 0.03410, 0.07, 0., 3.),
        ];
        for i in 0..451 {
            seed = seed.wrapping_mul(2862933555777941757).wrapping_add(3037000493);
            let a = ((seed >> 24) % 90) as f64 / 3.;
            seed = seed.wrapping_mul(2862933555777941757).wrapping_add(3037000493);
            let b = a + ((seed >> 24) % 30) as f64 / 3.;
            rows.push(row(i % 9, 0.000001 + (i as f64) * 0.000127,
                          0.00713 + (i as f64) * 0.0000119, a, b));
        }
        let mut edges: Vec<_> = rows.iter()
            .flat_map(|x| [x.a.unwrap(),x.b.unwrap()]).collect();
        edges.sort_unstable_by(f64::total_cmp);
        edges.dedup();
        let mut sweep = IntervalActiveSweep::new(&rows).unwrap();
        for (k,&a) in edges.iter().enumerate() {
            sweep.advance(a);
            let old_point = combine(rows.iter()
                .filter(|x| x.a == Some(a) && x.b == Some(a))
                .copied().collect()).unwrap();
            let new_point = combine(sweep.current_points.iter()
                .map(|&i| rows[i]).collect()).unwrap();
            assert_eq!(old_point.into_iter().map(fingerprint_part).collect::<Vec<_>>(),
                       new_point.into_iter().map(fingerprint_part).collect::<Vec<_>>());
            if let Some(&b) = edges.get(k+1) {
                let transform = |p: Part| {
                    let (pa,pb) = (p.a.unwrap(),p.b.unwrap());
                    let mut q=p;
                    q.mass = q.mass * (b-a) / (pb-pa);
                    q.birth = q.birth * (b-a) / (pb-pa);
                    q.a=PackedTime::new(Some(a)).unwrap();
                    q.b=PackedTime::new(Some(b)).unwrap();
                    q
                };
                let reference = combine(rows.iter().copied()
                    .filter(|x| x.a.unwrap() <=a && x.b.unwrap()>=b && x.b>x.a)
                    .map(transform).collect()).unwrap();
                let candidate = combine(sweep.active.iter().map(|i| transform(rows[i]))
                    .collect()).unwrap();
                assert_eq!(
                    reference.into_iter().map(fingerprint_part).collect::<Vec<_>>(),
                    candidate.into_iter().map(fingerprint_part).collect::<Vec<_>>(),
                    "split+combine bytes mismatch on interval [{a:?},{b:?}]",
                );
            }
        }
    }

    #[test]
    #[ignore]
    fn benchmark_original_naive_scan_vs_event_sweep_selection_only() {
        use std::hint::black_box;
        use std::time::Instant;
        let mut rows = Vec::new();
        for i in 0..5000 {
            let a = (i % 90) as f64;
            let b = a + (i % 31 + 1) as f64;
            rows.push(row(i % 13, (i as f64 + 1.) / 35000.,
                          i as f64 * 0.00017, a, b));
        }
        let mut edges: Vec<_> = rows.iter()
            .flat_map(|x| [x.a.unwrap(),x.b.unwrap()]).collect();
        edges.sort_unstable_by(f64::total_cmp);
        edges.dedup();
        let mut reference_time = 0u128;
        let mut optimized_time = 0u128;
        let mut original_selections=0usize;
        let mut indexed_selections=0usize;
        for _ in 0..4 {
            let start=Instant::now();
            let mut output=0usize;
            for (i,&a) in edges.iter().enumerate() {
                output+=rows.iter()
                    .filter(|p| p.a == Some(a) && p.b == Some(a)).count();
                if let Some(&b) = edges.get(i+1) {
                    output+=rows.iter().filter(|p| p.a.unwrap()<=a &&
                        p.b.unwrap()>=b && p.b>p.a).count();
                }
            }
            reference_time+=start.elapsed().as_nanos();
            original_selections=black_box(output);
            let start=Instant::now();
            let mut sweep=IntervalActiveSweep::new(&rows).unwrap();
            let mut selected=0;
            for &a in &edges {
                sweep.advance(a);
                selected+=sweep.current_points.len()+sweep.active.len();
            }
            optimized_time+=start.elapsed().as_nanos();
            indexed_selections=black_box(selected);
        }
        assert_eq!(original_selections,indexed_selections);
        println!("V03_SWEEP_BENCH rows={} edges={} original_ns={} sweep_ns={} ratio={:.5}",
                 rows.len(),edges.len(),reference_time,optimized_time,
                 reference_time as f64/optimized_time as f64);
    }

}


#[cfg(test)]
mod unique_arc_backing_account_tests {
    use super::*;

    fn part(tag: usize, mass: f64, a: f64, b: f64) -> Part {
        Part {
            tag, offset: 0, mass, birth: mass * 7.0,
            a: PackedTime::new(Some(a)).unwrap(),
            b: PackedTime::new(Some(b)).unwrap(),
        }
    }
    fn example_state(parts: Vec<PacketParts>) -> RoadState {
        let n=parts.len();
        RoadState {
            t: 0.0,
            cells: vec![Cell {
                v: [0.0;8],
                packets: parts.into_iter().map(|parts| Packet { target: 0.0, parts }).collect(),
                latent: BTreeMap::new(),
            }],
            pending: vec![Vec::new()],
            totals: [0.0;7],
            ledger: Vec::new(),
        }
    }

    #[test]
    fn duplicated_uniform_arc_backing_is_counted_once_but_owner_count_kept() {
        let packed=PacketParts::pack(
            vec![part(0,0.25,0.0,2.0),part(1,0.75,0.0,2.0)],
            |_|Ok(())).unwrap();
        let v=example_state(vec![packed.clone_checked().unwrap(),
                                 packed.clone_checked().unwrap(),packed]);
        let c=v.arc_backing_census();
        assert_eq!(c.owner_count,3);
        assert_eq!(c.unique_backing_count,1);
        assert_eq!(c.owner_payload_bytes,3*2*std::mem::size_of::<CorePart>());
        assert_eq!(c.unique_payload_bytes,2*std::mem::size_of::<CorePart>());
        assert_eq!(c.duplicate_payload_bytes,2*2*std::mem::size_of::<CorePart>());
    }

    #[test]
    fn equal_payload_but_independent_mixed_allocations_are_not_aliases() {
        let rows=vec![part(1,0.1,-0.0,3.0),part(2,0.9,0.0,2.0)];
        let independent=PacketParts::pack(rows.clone(), |_|Ok(())).unwrap();
        let shared=PacketParts::pack(rows, |_|Ok(())).unwrap();
        let v=example_state(vec![independent,shared.clone_checked().unwrap(),shared]);
        let c=v.arc_backing_census();
        assert_eq!(c.owner_count,3);
        assert_eq!(c.unique_backing_count,2);
        assert_eq!(c.owner_payload_bytes,3*2*std::mem::size_of::<Part>());
        assert_eq!(c.unique_payload_bytes,2*2*std::mem::size_of::<Part>());
        assert_eq!(c.duplicate_payload_bytes,2*std::mem::size_of::<Part>());
    }

    #[test]
    fn zero_capacity_backing_still_has_unique_arc_metadata() {
        let a=PacketParts::pack(vec![], |_|Ok(())).unwrap();
        let b=PacketParts::pack(vec![], |_|Ok(())).unwrap();
        let v=example_state(vec![a,b]);
        let c=v.arc_backing_census();
        assert_eq!(c.owner_count,2);
        assert_eq!(c.unique_backing_count,2);
        assert_eq!(c.owner_payload_bytes,0);
        assert_eq!(c.unique_payload_bytes,0);
        assert_eq!(c.duplicate_payload_bytes,0);
        // Census never treats zero-capacity distinct Arcs as one alias.
        assert_eq!(c.unique_arc_control_allowance_bytes,2*96);
    }
}


#[cfg(test)]
mod unique_arc_live_state_union_tests {
    use super::*;

    fn sample_state() -> RoadState {
        let parts=PacketParts::pack(
            vec![Part{tag:1,offset:0,mass:0.5,birth:1.,
                      a:PackedTime::new(Some(0.)).unwrap(),
                      b:PackedTime::new(Some(3.)).unwrap()}],
            |_| Ok(())
        ).unwrap();
        RoadState {
            t: 0.,
            cells: vec![Cell{v:[0.;8],packets:vec![Packet{target:0.,parts}],latent:BTreeMap::new()}],
            pending:vec![vec![]],
            totals:[0.;7],ledger:vec![],
        }
    }

    #[test]
    fn three_live_cloned_roadstates_are_one_shared_backing_but_three_owners() {
        let input=sample_state();
        let committed=input.clone();
        let candidate=input.clone();
        let x=RoadState::arc_backing_union(&[&input,&committed,&candidate]);
        let bytes=std::mem::size_of::<CorePart>();
        assert_eq!(x.owner_count,3);
        assert_eq!(x.unique_backing_count,1);
        assert_eq!(x.owner_payload_bytes,3*bytes);
        assert_eq!(x.unique_payload_bytes,bytes);
        assert_eq!(x.duplicate_payload_bytes,2*bytes);
        assert_eq!(x.unique_arc_control_allowance_bytes,96);
        assert_eq!(input.arc_backing_census().duplicate_payload_bytes,0);
    }

    #[test]
    fn identical_independent_roadstate_is_not_shared_even_at_same_part_bits() {
        let a=sample_state();
        let b=sample_state();
        let x=RoadState::arc_backing_union(&[&a,&b]);
        assert_eq!(x.owner_count,2);
        assert_eq!(x.unique_backing_count,2);
        assert_eq!(x.duplicate_payload_bytes,0);
    }

    #[test]
    fn empty_union_is_exact_zero_and_single_state_agrees_with_existing_census() {
        let empty=RoadState::arc_backing_union(&[]);
        assert_eq!(empty.owner_payload_bytes,0);
        assert_eq!(empty.unique_payload_bytes,0);
        assert_eq!(empty.owner_count,0);
        let state=sample_state();
        let a=state.arc_backing_census();
        let b=RoadState::arc_backing_union(&[&state]);
        assert_eq!(a.owner_payload_bytes,b.owner_payload_bytes);
        assert_eq!(a.unique_payload_bytes,b.unique_payload_bytes);
        assert_eq!(a.unique_backing_count,b.unique_backing_count);
    }
}


#[cfg(test)]
mod conservative_arc_pair_credit_tests {
    use super::*;

    fn one() -> RoadState {
        let p=PacketParts::pack(vec![
            Part{tag:1,offset:0,mass:0.2,birth:0.3,
                 a:PackedTime::new(Some(0.)).unwrap(),
                 b:PackedTime::new(Some(3.)).unwrap()},
            Part{tag:2,offset:0,mass:0.7,birth:0.8,
                 a:PackedTime::new(Some(0.)).unwrap(),
                 b:PackedTime::new(Some(3.)).unwrap()}
        ], |_|Ok(())).unwrap();
        RoadState{
            t:0.,cells:vec![Cell{v:[0.;8],packets:vec![Packet{target:0.,parts:p}],latent:BTreeMap::new()}],
            pending:vec![Vec::new()],totals:[0.;7],ledger:Vec::new(),
        }
    }

    #[test]
    fn paired_clone_credit_counts_only_guaranteed_arc_aliases() {
        let source=one();
        let committed=source.clone();
        let saved=source.paired_shared_payload_lower_bound(&committed);
        assert_eq!(saved,2*std::mem::size_of::<CorePart>());
        assert_eq!(source.arc_backing_census().duplicate_payload_bytes,0);
        let unrelated=one();
        assert_eq!(source.paired_shared_payload_lower_bound(&unrelated),0);
    }

    #[test]
    fn postroad_credit_requires_live_distinct_and_fully_charged_input(){
        let input=one();let committed=input.clone();let candidate=one();
        let a=input.retained_storage_bytes();let b=committed.retained_storage_bytes();let c=candidate.retained_storage_bytes();
        let credit=postroad_input_payload_credit(&committed,Some(&input),a,b);
        assert_eq!(credit,2*std::mem::size_of::<CorePart>());
        assert_eq!(postroad_input_payload_credit(&committed,Some(&input),a-1,b),0);
        assert_eq!(postroad_input_payload_credit(&committed,Some(&committed),b,b),0);
        assert_eq!(postroad_input_payload_credit(&committed,Some(&candidate),c,b),0);
        assert_eq!(postroad_input_payload_credit(&committed,None,a,b),0);
        let gross=postroad_continuous_owner_sum(b,a,c);
        let required=postroad_continuous_keyset_peak_event_bytes(gross-credit,17,31,2,1);
        assert!(check_storage_limit(Some(required),postroad_continuous_keyset_peak_event_bytes(gross,17,31,2,1),"old double charge").is_err());
        assert!(check_storage_limit(Some(required),required,"live distinct owners").is_ok());
        let u=RoadState::arc_backing_union(&[&input,&committed,&candidate]);
        assert!(credit<=u.duplicate_payload_bytes);
    }
    #[test]
    fn unshared_original_input_earns_zero_after_the_committed_state_changes() {
        let original = one();
        let first_tick = original.clone();
        assert!(first_tick.paired_shared_payload_lower_bound(&original) > 0);
        let later_tick = one();
        assert_eq!(later_tick.paired_shared_payload_lower_bound(&original), 0);
        assert_eq!(later_tick.paired_shared_payload_lower_bound(&later_tick), 0);
    }

    #[test]
    fn paired_credit_is_sound_for_three_states_and_distinct_candidate() {
        let source=one();
        let committed=source.clone();
        let candidate=one();
        let max_cost=source.retained_storage_bytes()
            .max(committed.retained_storage_bytes())
            .max(candidate.retained_storage_bytes());
        let discount=source.paired_shared_payload_lower_bound(&committed);
        let bound=max_cost.saturating_mul(3).saturating_sub(discount);
        let all=RoadState::arc_backing_union(&[&source,&committed,&candidate]);
        let total_shells=source.retained_storage_bytes()
            +committed.retained_storage_bytes()
            +candidate.retained_storage_bytes();
        // Exactly one duplicated backing is a lower bound on owner-counted
        // storage redundancy, keeping all candidate+outer metadata intact.
        assert_eq!(all.owner_count,3);
        assert_eq!(all.unique_backing_count,2);
        assert!(bound>=total_shells-discount);
        assert!(discount<=max_cost);
    }

    #[test]
    fn credit_never_exceeds_owner_payload_or_cross_snapshot_union_duplicates() {
        let a=one();
        let b=a.clone();
        let c=RoadState::arc_backing_union(&[&a,&b]);
        let credit=a.paired_shared_payload_lower_bound(&b);
        assert!(credit<=c.duplicate_payload_bytes);
        assert!(credit<=a.arc_backing_census().owner_payload_bytes);
    }
}

#[cfg(test)]
mod compact_mark_exactness_tests {
    use super::*;

    fn part(tag: usize, mass: f64, birth: f64, offset: usize) -> Part {
        Part { tag, mass, birth, offset,
            a: PackedTime::new(Some(-0.0)).unwrap(),
            b: PackedTime::new(Some(3.0)).unwrap() }
    }

    fn original_mark(p:&Part,speed:f64,latent:f64)->(usize,f64,f64,f64) {
        (p.tag%7,p.mass,speed,latent)
    }

    fn original_bits(m:(usize,f64,f64,f64))->(usize,u64,u64,u64){
        (m.0,m.1.to_bits(),m.2.to_bits(),m.3.to_bits())
    }

    #[test]
    fn speed_latent_only_mark_is_exactly_reconstructible_from_the_existing_part() {
        let inputs=[
            part(9,0.1,0.3,2),part(3,0.7,0.0,0),
            part(8,f64::from_bits(1),f64::from_bits(2),3),
            part(0,0.91,0.1,1),
        ];
        let speeds=[0.01,-0.0,0.9,0.11];
        let latents=[1.0,0.5,0.0,0.23];
        for ((p,u),q) in inputs.iter().zip(speeds).zip(latents) {
            let expected=original_mark(p,u,q);
            let m=compact_mark(u,q);
            let reconstructed=reconstruct_mark(p,&m,|p| p.tag%7);
            assert_eq!(original_bits(reconstructed),original_bits(expected));
        }
        assert_eq!(std::mem::size_of::<Mark>(),16);
    }

    #[test]
    fn original_ordered_fsum_speed_and_latent_are_bit_exact_over_mixed_classes() {
        let mut parts=Vec::new();
        let mut full=Vec::new();
        let mut reduced=Vec::new();
        let mut seed=0x2026_1120_BEEF_u64;
        for i in 0..1024 {
            seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let mass=f64::from_bits(0x3fa0000000000000+(seed&0xffff));
            seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let speed=f64::from_bits(0x3fa0000000000000+(seed&0xffff));
            seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let latent=f64::from_bits(0x3fa0000000000000+(seed&0xffff));
            let p=part(i%17,mass,mass*13.0,i%5);
            full.push(original_mark(&p,speed,latent));
            reduced.push(compact_mark(speed,latent));
            parts.push(p);
        }
        let full_speed=sum(full.iter().map(|m|m.1*m.2));
        let reduced_speed=sum(parts.iter().zip(&reduced).map(|(p,m)|p.mass*m.0));
        assert_eq!(full_speed.to_bits(),reduced_speed.to_bits());
        let mut a=BTreeMap::<usize,Vec<(f64,f64)>>::new();
        let mut b=BTreeMap::<usize,Vec<(f64,f64)>>::new();
        for &m in &full {a.entry(m.0).or_default().push((m.1,m.3));}
        for (p,m) in parts.iter().zip(&reduced){
            b.entry(p.tag%7).or_default().push((p.mass,m.1));
        }
        for (key,vals) in &a {
            assert_eq!(
                sum(vals.iter().map(|(mass,latent)|mass*latent)).to_bits(),
                sum(b[key].iter().map(|(mass,latent)|mass*latent)).to_bits()
            );
            assert_eq!(
                sum(vals.iter().map(|(mass,_)|*mass)).to_bits(),
                sum(b[key].iter().map(|(mass,_)|*mass)).to_bits()
            );
        }
    }

    #[test]
    fn empty_and_multidest_mark_stream_has_one_to_one_alignment() {
        let mut incoming=Vec::new();
        let mut compact=Vec::new();
        for i in 0..65 {
            let p=part(i%10,0.2+(i as f64)*0.00001,(i as f64)*0.3,i%5);
            incoming.push(p);
            compact.push(compact_mark((i as f64)/77.0,(i as f64)/103.0));
        }
        assert_eq!(incoming.len(),compact.len());
        for (p,m) in incoming.iter().zip(&compact){
            let q=reconstruct_mark(p,m,|p|p.tag%7);
            assert_eq!(q.0,p.tag%7);
            assert_eq!(q.1.to_bits(),p.mass.to_bits());
        }
        let blank:Vec<Part>=Vec::new();
        let marks:Vec<Mark>=Vec::new();
        assert_eq!(blank.len(),marks.len());
    }
}


#[cfg(test)]
mod hierarchical_active_index_bitset_tests {
    use super::*;

    #[test]
    fn bitset_operations_are_exactly_ordered_like_btree_over_boundary_cardinalities() {
        for len in [0usize,1,2,63,64,65,127,128,129,4095,4096,4097,8195] {
            let mut compact=ActiveIndexBits::new(len).unwrap();
            let mut reference=BTreeSet::<usize>::new();
            let mut state=0x2026_1120_5678u64;
            assert_eq!(compact.len(),0);
            assert_eq!(compact.iter().collect::<Vec<_>>(), Vec::<usize>::new());
            for step in 0..3000usize {
                if len==0 { continue; }
                state=state.wrapping_mul(6364136223846793005).wrapping_add(1);
                let idx=(state as usize)%len;
                if step%7==0 || state&1==0 {
                    let a=compact.insert(idx);
                    let b=reference.insert(idx);
                    assert_eq!(a,b);
                } else {
                    let a=compact.remove(&idx);
                    let b=reference.remove(&idx);
                    assert_eq!(a,b);
                }
                assert_eq!(compact.len(),reference.len());
                if step%113==0 {
                    assert_eq!(compact.iter().collect::<Vec<_>>(),
                               reference.iter().copied().collect::<Vec<_>>());
                }
            }
            assert_eq!(compact.iter().collect::<Vec<_>>(),
                       reference.iter().copied().collect::<Vec<_>>());
            assert!(compact.capacity_bytes() <=
                    ((len+63)/64)*8 + ((len+4095)/4096)*8 + 128);
        }
    }

    #[test]
    fn original_rust_ieee_interval_sweep_selected_row_order_unchanged() {
        let mut rows=Vec::new();
        for i in 0..1397usize {
            let pa=if i%101==0 {-0.0} else {(i%17) as f64};
            let pb=if i%11==0 {pa} else {pa+(i%7+1) as f64};
            rows.push(Part {
                tag:i%19,offset:i%5,
                mass:(i as f64+1.)/3000.,
                birth:(i as f64+7.)/9000.,
                a:PackedTime::new(Some(pa)).unwrap(),
                b:PackedTime::new(Some(pb)).unwrap(),
            });
        }
        let mut original=BTreeSet::new();
        let mut sweep=IntervalActiveSweep::new(&rows).unwrap();
        let mut endpoints=Vec::new();
        endpoints.extend(rows.iter().flat_map(|p|[p.a.unwrap(),p.b.unwrap()]));
        endpoints.sort_unstable_by(f64::total_cmp);
        endpoints.dedup();
        for (edge_id,&a) in endpoints.iter().enumerate() {
            sweep.advance(a);
            if edge_id+1>=endpoints.len() {continue;}
            let b=endpoints[edge_id+1];
            original.clear();
            for (i,p) in rows.iter().enumerate() {
                if p.a.unwrap()!=p.b.unwrap() &&
                   p.a.unwrap()<=a && p.b.unwrap()>=b {
                    original.insert(i);
                }
            }
            let actual=sweep.active.iter().collect::<Vec<_>>();
            let expected=original.iter().copied().collect::<Vec<_>>();
            assert_eq!(actual,expected);
            let old_fsum=sum(expected.iter().map(|&i| {
                let p=rows[i];
                p.mass*(b-a)/(p.b.unwrap()-p.a.unwrap())
            }));
            let new_fsum=sum(actual.iter().map(|&i| {
                let p=rows[i];
                p.mass*(b-a)/(p.b.unwrap()-p.a.unwrap())
            }));
            assert_eq!(old_fsum.to_bits(),new_fsum.to_bits());
        }
    }
}

#[cfg(test)]
mod composed_interval_view_tests {
    use super::*;

    fn bits(p: Part) -> (usize, usize, u64, u64, u64, u64) {
        (p.tag, p.offset, p.mass.to_bits(), p.birth.to_bits(),
         p.a.unwrap().to_bits(), p.b.unwrap().to_bits())
    }

    #[test]
    fn source_index_view_matches_materialized_ieee_split_and_combine() {
        let mut source = Vec::new();
        for i in 0..1173usize {
            let a = if i % 109 == 0 { -0.0 } else { (i * 19 % 17) as f64 * 0.25 };
            let b = a + (i * 37 % 19) as f64 * 0.25;
            let mass = match i % 23 {
                0 => f64::from_bits(1),
                1 => 0.,
                2 => 1e-200,
                3 => 1e200,
                _ => (i % 31 + 1) as f64 / 4096.,
            };
            source.push(Part {
                tag: i % 9, offset: i % 5, mass,
                birth: if i % 13 == 0 { 1e-200 } else { (i + 3) as f64 / 997. },
                a: PackedTime::new(Some(a)).unwrap(),
                b: PackedTime::new(Some(b)).unwrap(),
            });
        }
        let mut endpoints: Vec<_> = source.iter().flat_map(|p| [p.a.unwrap(), p.b.unwrap()]).collect();
        endpoints.sort_unstable_by(f64::total_cmp);
        endpoints.dedup();
        let mut sweep = IntervalActiveSweep::new(&source).unwrap();
        for (i, &a) in endpoints.iter().enumerate() {
            sweep.advance(a);
            let Some(&b) = endpoints.get(i + 1) else { continue };
            let mut materialized = Vec::new();
            for j in sweep.active.iter() {
                let mut p = source[j];
                let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
                p.mass = p.mass * (b - a) / (pb - pa);
                p.birth = p.birth * (b - a) / (pb - pa);
                p.a = PackedTime::new(Some(a)).unwrap();
                p.b = PackedTime::new(Some(b)).unwrap();
                materialized.push(p);
            }
            let original = combine(materialized).unwrap();
            let view = combine_interval_view(&source, sweep.active.iter(), sweep.active.len(), a, b).unwrap();
            assert_eq!(
                original.into_iter().map(bits).collect::<Vec<_>>(),
                view.into_iter().map(bits).collect::<Vec<_>>(),
                "view changed IEEE result on edge {i} [{a:?},{b:?}]"
            );
        }
    }

    #[test]
    fn source_index_view_empty_and_nonassociative_duplicate_keys() {
        let a = PackedTime::new(Some(0.)).unwrap();
        let b = PackedTime::new(Some(1.)).unwrap();
        let rows: Vec<Part> = (0..101).map(|i| Part {
            tag: 0, offset: 0,
            mass: if i % 2 == 0 { 1e-12 } else { 1e-6 },
            birth: if i % 3 == 0 { 1e12 } else { 1e-12 },
            a, b,
        }).collect();
        let baseline = combine(rows.clone()).unwrap();
        let view = combine_interval_view(&rows, 0..rows.len(), rows.len(), 0., 1.).unwrap();
        assert_eq!(baseline.into_iter().map(bits).collect::<Vec<_>>(),
                   view.into_iter().map(bits).collect::<Vec<_>>());
        assert!(combine_interval_view(&rows, std::iter::empty(), 0, 0., 1.).unwrap().is_empty());
    }
}

#[cfg(test)]
mod exact_shared_event_source_budget_tests {
    use super::*;

    #[test]
    fn only_pointer_identical_old_event_backing_can_be_counted_once() {
        let one = ServiceEventAccounting {
            input_bytes: 8192, current_bytes: 8192,
            max_tag_bytes: 0, shared_input_current: true,
        };
        let separate = ServiceEventAccounting {
            shared_input_current: false, ..one
        };
        let candidate = 10usize;
        // Candidate is now physically held in fixed-size event pages.
        // Sharing of old committed input/current events remains pointer based.
        let candidate_bytes = paged_event_candidate_bytes(candidate);
        assert_eq!(one.road_step_bytes(candidate), 8192 + candidate_bytes);
        assert_eq!(separate.road_step_bytes(candidate), 2 * 8192 + candidate_bytes);
        assert_eq!(one.road_step_bytes(0), 8192 + std::mem::size_of::<ChunkedEvents>());
        // Distinct current backing: never subtract a value-equal buffer.
    }
}

#[cfg(test)]
mod direct_core_interval_pack_tests {
    use super::*;

    fn signature(p: Part) -> (usize, usize, u64, u64, u64, u64) {
        (p.tag, p.offset, p.mass.to_bits(), p.birth.to_bits(),
         p.a.unwrap().to_bits(), p.b.unwrap().to_bits())
    }

    #[test]
    fn direct_core_rows_match_old_combined_uniform_packet_bits() {
        let mut rows = Vec::new();
        for i in 0..371usize {
            let a = if i % 17 == 0 {-0.0} else {0.};
            let b = if i % 11 == 0 {1.} else {2.};
            let mass = match i % 13 {
                0 => f64::from_bits(1),
                1 => 0.,
                2 => 1e-100,
                3 => 1e100,
                _ => (i % 19 + 1) as f64 / 71000.,
            };
            rows.push(Part {
                tag:i%7,offset:i%3,mass,
                birth: if i%3==0 {mass} else {mass * 1.25},
                a:PackedTime::new(Some(a)).unwrap(),
                b:PackedTime::new(Some(b)).unwrap(),
            });
        }
        for (a,b) in [(-0., 1.), (0., 1.), (0.25,0.75), (1.,2.)] {
            let selected:Vec<usize> = (0..rows.len()).filter(|&i| {
                rows[i].a.unwrap()<=a && rows[i].b.unwrap()>=b
            }).collect();
            let old = combine_interval_view(&rows,selected.iter().copied(),selected.len(),a,b).unwrap();
            let old_pack = PacketParts::pack(old, |_|Ok(())).unwrap();
            let direct = combine_interval_core(&rows,selected.iter().copied(),selected.len(),a,b).unwrap();
            let new_pack = PacketParts::Uniform {
                a:PackedTime::new(Some(a)).unwrap(),
                b:PackedTime::new(Some(b)).unwrap(),
                rows:Arc::new(direct),
            };
            assert_eq!(
                old_pack.iter().map(signature).collect::<Vec<_>>(),
                new_pack.iter().map(signature).collect::<Vec<_>>(),
                "direct packed result changed on [{a:?},{b:?}]"
            );
        }
    }

    #[test]
    fn direct_core_empty_and_duplicate_key_order() {
        let rows = vec![
            Part{tag:1,offset:2,mass:1e-10,birth:3e-10,
                 a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(1.)).unwrap()},
            Part{tag:1,offset:2,mass:1e20,birth:7e20,
                 a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(1.)).unwrap()},
            Part{tag:1,offset:2,mass:1e-10,birth:11e-10,
                 a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(1.)).unwrap()},
        ];
        assert!(combine_interval_core(&rows, std::iter::empty(), 0, 0., 1.).unwrap().is_empty());
        let reference=combine_interval_view(&rows,0..3,3,0.,1.).unwrap();
        let core=combine_interval_core(&rows,0..3,3,0.,1.).unwrap();
        let wrapped=PacketParts::Uniform{
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap(),
            rows:Arc::new(core),
        };
        assert_eq!(reference.into_iter().map(signature).collect::<Vec<_>>(),
                   wrapped.iter().map(signature).collect::<Vec<_>>());
    }
}

#[cfg(test)]
mod direct_uniform_point_pack_tests {
    use super::*;

    fn signature(p: Part) -> (usize, usize, u64, u64, u64, u64) {
        (p.tag, p.offset, p.mass.to_bits(), p.birth.to_bits(),
         p.a.unwrap().to_bits(), p.b.unwrap().to_bits())
    }

    #[test]
    fn uniform_point_direct_core_matches_legacy_group_sum_and_packet_bits() {
        for t in [-0., 0., 10.25, 25650.] {
            let a = PackedTime::new(Some(t)).unwrap();
            let rows:Vec<Part> = (0..309usize).map(|i| {
                let mass = match i%11 {
                    0 => 0., 1 => f64::from_bits(1), 2 => 1e-200,
                    3 => 1e100, _ => (i%7+1) as f64 / 7717.,
                };
                Part {
                    tag:i%13,offset:i%5,mass,
                    birth: if i%3==0 {mass} else {mass*1.125},
                    a,b:a,
                }
            }).collect();
            let indices:Vec<usize> = (0..rows.len()).rev().collect();
            let indices:Vec<usize> = indices.into_iter().rev().collect();
            assert!(all_point_endpoint_bits_identical(&rows,&indices));
            let ref_pack = PacketParts::pack(
                combine(indices.iter().map(|&i|rows[i]).collect()).unwrap(),
                |_|Ok(())).unwrap();
            let core = combine_uniform_point_core(&rows,&indices).unwrap();
            let fast = PacketParts::Uniform {a,b:a, rows:Arc::new(core)};
            assert_eq!(ref_pack.iter().map(signature).collect::<Vec<_>>(),
                       fast.iter().map(signature).collect::<Vec<_>>());
        }
    }

    #[test]
    fn signed_zero_mixed_point_endpoints_refuse_fast_path() {
        let negative = PackedTime::new(Some(-0.)).unwrap();
        let positive = PackedTime::new(Some(0.)).unwrap();
        let p = |a,b| Part {tag:0,offset:0,mass:0.25,birth:0.375,a,b};
        let rows = vec![p(negative,positive),p(positive,positive)];
        assert!(!all_point_endpoint_bits_identical(&rows,&[0,1]));
        let original = PacketParts::pack(combine(rows).unwrap(), |_|Ok(())).unwrap();
        assert!(!original.is_uniform());
        assert!(all_point_endpoint_bits_identical(&[],&[]));
    }
}

#[cfg(test)]
mod sweep_partition_live_bound_tests {
    use super::*;

    fn make_row(i: usize, a: f64, b: f64) -> Part {
        Part {
            tag: i % 17, offset: i % 3, mass: (i as f64 + 1.) / 107.,
            birth: (i as f64 + 3.) / 103.,
            a: PackedTime::new(Some(a)).unwrap(),
            b: PackedTime::new(Some(b)).unwrap(),
        }
    }

    #[test]
    fn only_classified_source_rows_allocate_their_real_event_arrays() {
        for n in [0usize, 1, 2, 63, 64, 65, 127, 128, 129, 4095, 4097] {
            let mut rows = Vec::new();
            for i in 0..n {
                let a = if i % 109 == 0 { -0.0 } else { (i % 37) as f64 };
                let b = if i % 3 == 0 { a } else { a + (i % 4 + 1) as f64 };
                rows.push(make_row(i,a,b));
            }
            let (u,q) = count_sweep_row_kinds(&rows).unwrap();
            assert_eq!(u+q,n);
            assert_eq!(q, (0..n).filter(|i| i % 3 == 0).count());
            let sweep=IntervalActiveSweep::new(&rows).unwrap();
            assert_eq!((sweep.starts.len(), sweep.ends.len(), sweep.points.len()),(u,u,q));
            assert!(sweep.starts.capacity() <= u + 16);
            assert!(sweep.ends.capacity() <= u + 16);
            assert!(sweep.points.capacity() <= q + 16);
            assert!(sweep.current_points.capacity() <= q + 16);
            let old = n*56 + (n.div_ceil(64)+n.div_ceil(4096))*8 + 256;
            let reduced = exact_sweep_event_index_bytes(n,u,q);
            assert_eq!(old - reduced, 48*u+44*q);
            assert!(reduced <= old);
        }
    }

    #[test]
    fn ordinal_width_fallback_and_order_are_injective() {
        let mut wide=SweepOrdinals::new(u32::MAX as usize+2,3).unwrap();
        let values=[u32::MAX as usize+1,0,1];
        for i in values {wide.push(i);}
        wide.sort(|_|-0.0);
        assert_eq!((0..3).map(|i|wide.get(i).unwrap()).collect::<Vec<_>>(),vec![0,1,u32::MAX as usize+1]);
        let mut narrow=SweepOrdinals::new(9,3).unwrap();
        for i in [5,1,3] {narrow.push(i);}
        narrow.sort(|i|if i==5 {-0.0}else{0.0});
        assert_eq!((0..3).map(|i|narrow.get(i).unwrap()).collect::<Vec<_>>(),vec![5,1,3]);
    }

    #[test]
    fn opposite_sign_zeros_are_numeric_points_but_bit_distinct() {
        let rows=[
            make_row(0,-0.,0.),
            make_row(1,0.,-0.),
            make_row(2,-0.,1.),
            make_row(3,0.,2.),
        ];
        assert_eq!(count_sweep_row_kinds(&rows).unwrap(),(2,2));
        let mut sweep=IntervalActiveSweep::new(&rows).unwrap();
        sweep.advance(-0.);
        assert_eq!(sweep.current_points, vec![0,1]);
        assert_eq!(sweep.active.iter().collect::<Vec<_>>(),vec![2,3]);
    }

    #[test]
    fn reversed_interval_is_rejected_without_reclassifying_as_point() {
        let rows=[make_row(0,2.,1.)];
        assert!(count_sweep_row_kinds(&rows).is_err());
        assert!(IntervalActiveSweep::new(&rows).is_err());
    }
}

#[cfg(test)]
mod exact_merged_unique_edges_tests {
    use super::*;

    fn p(i:usize, a:f64, b:f64) -> Part {
        Part {
            tag:i%7,offset:i%4,mass:(i+1) as f64/37.,
            birth:(i+3) as f64/31.,
            a:PackedTime::new(Some(a)).unwrap(),
            b:PackedTime::new(Some(b)).unwrap(),
        }
    }

    fn assert_equal_to_legacy_edges(rows: Vec<Part>) {
        let mut old=Vec::new();
        old.extend(rows.iter().flat_map(|p|[p.a.unwrap(),p.b.unwrap()]));
        old.sort_unstable_by(f64::total_cmp);
        old.dedup();
        let sweep=IntervalActiveSweep::new(&rows).unwrap();
        let mut bytes_guard=None;
        let actual=unique_sweep_edges(&rows,&sweep,|bytes|{
            bytes_guard=Some(bytes);
            Ok(())
        }).unwrap();
        assert_eq!(
            old.iter().map(|v|v.to_bits()).collect::<Vec<_>>(),
            actual.iter().map(|v|v.to_bits()).collect::<Vec<_>>(),
            "unique-edge sorted/dedup bit patterns differ"
        );
        assert_eq!(bytes_guard,Some(old.len()*std::mem::size_of::<f64>()));
        assert!(actual.capacity() <= old.len()+16);
        assert!(actual.len() <= rows.len()*2);
    }

    #[test]
    fn unique_edges_match_original_across_zero_sign_permutations_and_empty() {
        assert_equal_to_legacy_edges(vec![]);
        assert_equal_to_legacy_edges(vec![p(0,0.,-0.)]);
        assert_equal_to_legacy_edges(vec![p(0,-0.,0.)]);
        assert_equal_to_legacy_edges(vec![p(0,0.,0.)]);
        assert_equal_to_legacy_edges(vec![
            p(0,0.,-0.),p(1,0.,0.),p(2,-0.,0.),
            p(3,-3.,-1.),p(4,-1.,0.),p(5,0.,4.),
            p(6,4.,4.),p(7,4.,7.),
        ]);
        assert_equal_to_legacy_edges(vec![
            p(0,0.,0.),p(1,0.,1.),p(2,1.,1.),p(3,1.,2.)
        ]);
    }

    #[test]
    fn unique_edges_match_original_seeded_intervals_and_many_duplicate_endpoints() {
        let mut seed=0xC03E_2026_u64;
        for n in [1usize,2,63,64,65,4097,10000] {
            let mut rows=Vec::new();
            for i in 0..n {
                seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let a=if i%127==0 {-0.0} else {((seed>>28)%41) as f64 / 4. - 4.};
                seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let b=if i%19==0 {a} else {a+((seed>>28)%9+1) as f64 / 8.};
                rows.push(p(i,a,b));
            }
            assert_equal_to_legacy_edges(rows);
        }
        assert_equal_to_legacy_edges((0..20000).map(|i|p(i,0.,1.)).collect());
    }
}

#[cfg(test)]
mod exact_narrow_lineage_indices_tests {
    use super::*;

    fn p(tag: usize, offset: usize, mass: f64, a: f64, b: f64) -> Part {
        Part {
            tag, offset, mass, birth: mass * 1.25,
            a: PackedTime::new(Some(a)).unwrap(),
            b: PackedTime::new(Some(b)).unwrap(),
        }
    }
    fn bits(p: Part) -> (usize, usize, u64, u64, u64, u64) {
        (p.tag, p.offset, p.mass.to_bits(), p.birth.to_bits(),
         p.a.0, p.b.0)
    }

    #[test]
    fn compact_core_layout_is_24_bytes_and_integer_bounds_are_lossless() {
        assert_eq!(std::mem::size_of::<CorePart>(), 24);
        assert_eq!(std::mem::size_of::<Part>(), 48);
        assert_eq!(compact_indices(0,0), Some((0,0)));
        assert_eq!(compact_indices(u32::MAX as usize,u32::MAX as usize),
                   Some((u32::MAX,u32::MAX)));
        assert!(compact_indices(u32::MAX as usize,1).is_some());
    }

    #[test]
    fn all_original_mass_birth_and_signed_zero_endpoint_bits_roundtrip() {
        for (i, mass) in [f64::from_bits(1), 0.0, 1e-200, 1e200, 0.125, 1.0].into_iter().enumerate() {
            for (a,b) in [(-0.0,-0.0),(0.0,0.0),(-0.0,0.0),(0.0,1.0)] {
                let source=p(i, i+3, mass, a, b);
                let packet=PacketParts::pack(vec![source], |_| Ok(())).unwrap();
                assert_eq!(packet.iter().map(bits).collect::<Vec<_>>(),
                           vec![bits(source)]);
            }
        }
    }

    #[cfg(target_pointer_width = "64")]
    #[test]
    fn overflow_indices_are_never_truncated_and_preserve_legacy_part_fields() {
        let too_big=(u32::MAX as usize)+1;
        assert!(compact_indices(too_big,0).is_none());
        assert!(compact_indices(0,too_big).is_none());
        for (tag,offset) in [(too_big,0),(0,too_big),(too_big,too_big)] {
            let source=p(tag,offset,0.125,-0.0,4.0);
            let packet=PacketParts::pack(vec![source], |_|Ok(())).unwrap();
            assert!(matches!(packet, PacketParts::Mixed(_)),
                "out of range indexes cannot be narrowed without loss");
            assert_eq!(packet.iter().map(bits).collect::<Vec<_>>(),
                       vec![bits(source)]);
        }
    }

    #[test]
    fn distinguish_mixed_signed_zeros_even_if_indices_are_compactable() {
        let a=p(0,0,0.25,-0.0,0.0);
        let b=p(1,1,0.5,0.0,0.0);
        let packet=PacketParts::pack(vec![a,b], |_|Ok(())).unwrap();
        assert!(matches!(packet,PacketParts::Mixed(_)));
        assert_eq!(packet.iter().map(bits).collect::<Vec<_>>(),
                   vec![bits(a),bits(b)]);
    }
}

#[cfg(test)]
mod exact_segmented_incoming_buffer_tests {
    use super::*;

    fn row(i:usize,a:f64,b:f64) -> Part {
        Part {
            tag:i%11,offset:i%5,
            mass: match i%17 {
                0 => 0.,1 => f64::from_bits(1),2 => 1e-190,
                3 => 1e190, _=>(i%19+1) as f64/4096.,
            },
            birth:if i%13==0 {1e-100} else {(i+1) as f64/11.},
            a:PackedTime::new(Some(a)).unwrap(),
            b:PackedTime::new(Some(b)).unwrap(),
        }
    }
    fn bits(p:Part)->(usize,usize,u64,u64,u64,u64){
        (p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)
    }
    #[test]
    fn segmented_source_order_matches_original_vec_at_chunk_boundaries() {
        for n in [0,1,2,63,64,65,127,128,129,319,1001] {
            let rows:Vec<_>=(0..n).map(|i|{
                let a=if i%23==0 {-0.0} else {(i%7) as f64/4.};
                let b=if i%9==0 {a} else {a+(i%3+1) as f64};
                row(i,a,b)
            }).collect();
            let mut chunks=ChunkedParts::default();
            for &r in &rows {chunks.push_checked(r).unwrap();}
            assert_eq!(chunks.len(),n);
            assert_eq!(chunks.is_empty(),n==0);
            assert_eq!(chunks.iter().map(bits).collect::<Vec<_>>(),
                       rows.iter().copied().map(bits).collect::<Vec<_>>());
            for (i,r) in rows.iter().enumerate(){assert_eq!(bits(chunks.get(i)),bits(*r));}
            assert_eq!(chunks.chunks.len(),n.div_ceil(INCOMING_PART_CHUNK));
            assert!(chunks.chunks.iter().all(|x|x.capacity()==INCOMING_PART_CHUNK));
            assert_eq!(chunks.capacity(),n.div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK);
        }
    }
    #[test]
    fn no_existing_page_is_reallocated_while_appending_many_later_rows() {
        let mut c=ChunkedParts::default();
        for i in 0..INCOMING_PART_CHUNK {c.push_checked(row(i,0.,1.)).unwrap();}
        let old=c.chunks[0].as_ptr();
        for i in INCOMING_PART_CHUNK..1007 {c.push_checked(row(i,0.,1.)).unwrap();}
        assert_eq!(old,c.chunks[0].as_ptr());
        assert_eq!(c.chunks.len(),1007usize.div_ceil(INCOMING_PART_CHUNK));
    }
    #[test]
    fn original_source_sorted_group_sum_remains_bit_equal_for_duplicate_and_signed_zero_keys() {
        let mut rows=Vec::new();
        for i in 0..1107 {
            let a=if i%41==0 {-0.0} else {0.0};
            let b=if i%41==0 {-0.0} else {0.0};
            rows.push(row(i,a,b));
        }
        let original=combine(rows.clone()).unwrap();
        let mut chunks=ChunkedParts::default();
        chunks.extend_parts(rows.into_iter()).unwrap();
        let packed=combine_chunked_parts(&chunks).unwrap();
        assert_eq!(original.into_iter().map(bits).collect::<Vec<_>>(),
                   packed.into_iter().map(bits).collect::<Vec<_>>());
    }
    #[test]
    fn changed_guard_has_real_pages_and_conservative_capacity_slack() {
        let r=7_968_194usize;
        let g=1586usize;
        let original=r*2*(std::mem::size_of::<Part>()+std::mem::size_of::<Mark>());
        let proposed=segmented_incoming_charge(r,g);
        assert_eq!(original,1_019_928_832);
        assert_eq!(proposed,528_983_872);
        assert_eq!(original-proposed,490_944_960);
        assert!(segmented_incoming_charge(0,g)==0);
    }
}

#[cfg(test)]
mod exact_segmented_mark_alignment_tests {
    use super::*;

    #[test]
    fn ordered_mark_pages_preserve_each_original_f64_bit_and_pairing() {
        for n in [0usize,1,63,64,65,127,128,129,1025] {
            let mut parts=ChunkedParts::default();
            let mut marks=ChunkedMarks::default();
            let mut expected=Vec::new();
            for i in 0..n {
                let a=if i%17==0 {-0.0} else {(i%23) as f64/41.};
                let mark=compact_mark(a, if i%29==0 {f64::from_bits(1)} else {-a});
                let part=Part {
                    tag:i%3,offset:i%7,mass:(i%19+1) as f64/331.,
                    birth: (i%13) as f64/29.,
                    a:PackedTime::new(Some(0.)).unwrap(),
                    b:PackedTime::new(Some(1.)).unwrap(),
                };
                expected.push((part,mark));
                parts.push_checked(part).unwrap();
                marks.push_checked(mark).unwrap();
            }
            assert_eq!(parts.len(), marks.len());
            assert_eq!(marks.len(),n);
            assert_eq!(marks.capacity(),n.div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK);
            assert!(marks.chunks.iter().all(|v|v.capacity()==INCOMING_PART_CHUNK));
            assert_eq!(marks.iter().zip(parts.iter()).map(|(m,p)|(
                m.0.to_bits(),m.1.to_bits(),p.mass.to_bits())).collect::<Vec<_>>(),
                expected.iter().map(|(p,m)|(
                m.0.to_bits(),m.1.to_bits(),p.mass.to_bits())).collect::<Vec<_>>());
            let old=sum(expected.iter().map(|(p,m)|p.mass*m.0));
            let now=sum(parts.iter().zip(marks.iter()).map(|(p,m)|p.mass*m.0));
            assert_eq!(old.to_bits(),now.to_bits());
        }
    }
    #[test]
    fn appending_new_marks_does_not_move_old_paged_mark_backing() {
        let mut marks=ChunkedMarks::default();
        for i in 0..INCOMING_PART_CHUNK {
            marks.push_checked(compact_mark(i as f64, -0.)).unwrap();
        }
        let p=marks.chunks[0].as_ptr();
        for i in INCOMING_PART_CHUNK..1001 {
            marks.push_checked(compact_mark(i as f64, 0.)).unwrap();
        }
        assert_eq!(p,marks.chunks[0].as_ptr());
    }
    #[test]
    fn actual_two_page_source_bound_uses_one_copy_of_each_row() {
        assert_eq!(segmented_incoming_charge(8_992_612,1586),595_314_912);
        assert_eq!(segmented_incoming_charge(0,1586),0);
    }
}

#[cfg(test)]
mod exact_paged_event_candidate_tests {
    use super::*;

    fn e(i: usize) -> EventRow {
        (
            i % 17,
            i % 31,
            if i % 9 == 0 { None } else { Some(i % 53) },
            if i % 11 == 0 { f64::from_bits(1) } else { (i % 37 + 1) as f64/117. },
            if i % 13 == 0 {-0.0} else { (i % 43) as f64/11. },
            if i % 19 == 0 {-0.0} else { (i % 43 + 1) as f64/11. },
            if i % 23 == 0 { f64::from_bits(1) } else { (i % 29) as f64/19. },
        )
    }
    fn bits(x: EventRow) -> (usize,usize,Option<usize>,u64,u64,u64,u64) {
        (x.0,x.1,x.2,x.3.to_bits(),x.4.to_bits(),x.5.to_bits(),x.6.to_bits())
    }

    #[test]
    fn paged_events_reconstruct_original_exact_tuple_bits_and_order() {
        for n in [0usize,1,2,4095,4096,4097,8193,20011] {
            let original:Vec<_>=(0..n).map(e).collect();
            let mut pages=ChunkedEvents::default();
            for &event in &original { pages.push_checked(event).unwrap(); }
            assert_eq!(pages.len(), n);
            assert_eq!(pages.capacity(),n.div_ceil(EVENT_PAGE_ROWS)*EVENT_PAGE_ROWS);
            assert_eq!(pages.chunks.len(),n.div_ceil(EVENT_PAGE_ROWS));
            assert!(pages.chunks.iter().all(|page|page.capacity()==EVENT_PAGE_ROWS));
            assert_eq!(pages.iter().map(bits).collect::<Vec<_>>(),
                       original.iter().copied().map(bits).collect::<Vec<_>>());
            assert_eq!(pages.into_flat_checked().unwrap().into_iter().map(bits).collect::<Vec<_>>(),
                       original.into_iter().map(bits).collect::<Vec<_>>());
        }
    }

    #[test]
    fn old_event_page_never_moves_when_later_events_are_appended() {
        let mut pages=ChunkedEvents::default();
        for i in 0..EVENT_PAGE_ROWS { pages.push_checked(e(i)).unwrap(); }
        let ptr=pages.chunks[0].as_ptr();
        for i in EVENT_PAGE_ROWS..(EVENT_PAGE_ROWS*3+17) { pages.push_checked(e(i)).unwrap(); }
        assert_eq!(pages.chunks[0].as_ptr(), ptr);
        assert_eq!(pages.len(),EVENT_PAGE_ROWS*3+17);
    }

    #[test]
    fn actual_candidate_page_structural_bound_is_not_only_a_numeric_discount() {
        assert_eq!(std::mem::size_of::<EventRow>(),64);
        assert_eq!(std::mem::size_of::<Vec<EventRow>>(),24);
        let n=9_100_145usize;
        let old=3*n*64+96;
        let page=paged_event_candidate_bytes(n);
        assert_eq!(old,1_747_227_936);
        let carrier_growth=std::mem::size_of::<ChunkedEvents>()-96;
        assert_eq!(page,582_644_120+carrier_growth);
        assert_eq!(old-page,1_164_583_816-carrier_growth);
        assert_eq!(paged_event_candidate_bytes(0),std::mem::size_of::<ChunkedEvents>());
    }
}

#[cfg(test)]
mod postroad_event_lifetime_tests {
    use super::*;

    #[test]
    fn finishing_after_workspaces_drop_charges_distinct_real_backings_only() {
        let original_road_snapshots=1_900_000_000usize;
        let old_events=500_000_000usize;
        let page_rows=10_665_984usize;
        let page_headers=4_096usize;
        let exact_rows=10_663_078usize;
        let actual=postroad_event_materialization_bytes(
            original_road_snapshots,old_events,page_rows*std::mem::size_of::<EventRow>(),page_headers,exact_rows,
        );
        let expected=original_road_snapshots+old_events
            +page_rows*std::mem::size_of::<EventRow>()
            +page_headers*std::mem::size_of::<Vec<EventRow>>()
            +exact_rows*std::mem::size_of::<EventRow>()
            +std::mem::size_of::<ChunkedEvents>()+std::mem::size_of::<Vec<EventRow>>();
        assert_eq!(actual,expected);
        assert!(actual<5_188_657_743usize);
        assert!(actual>original_road_snapshots+old_events);
    }

    #[test]
    fn no_event_history_uses_no_candidate_rows_or_flattening()
    {
        assert_eq!(postroad_event_materialization_bytes(11,23,0,0,0),
            11+23+std::mem::size_of::<ChunkedEvents>()+std::mem::size_of::<Vec<EventRow>>());
    }
}

#[cfg(test)]
mod exact_route_keyset_census_tests {
    use super::*;

    fn packet(keys:&[(u32,u32)], masses:&[f64], a:f64,b:f64)->PacketParts {
        assert_eq!(keys.len(),masses.len());
        PacketParts::Uniform {
            a:PackedTime::new(Some(a)).unwrap(),
            b:PackedTime::new(Some(b)).unwrap(),
            rows:Arc::new(keys.iter().zip(masses.iter()).map(|(&(tag,offset),&mass)|CorePart{
                tag,offset,mass,birth:mass*1.75,
            }).collect()),
        }
    }
    fn state(ps:Vec<PacketParts>)->RoadState {
        RoadState{
            t:0.,cells:vec![Cell{v:[0.;8], packets:ps.into_iter()
                .map(|parts|Packet{target:0.,parts}).collect(),latent:BTreeMap::new()}],
            pending:vec![vec![]],totals:[0.;7],ledger:vec![],
        }
    }

    #[test]
    fn census_recognizes_identical_key_sequences_with_distinct_physical_moments() {
        let k=[(2,0),(17,5),(2,3)];
        let first=packet(&k,&[0.1,0.2,0.3],-0.,1.);
        let other_moments=packet(&k,&[0.4,0.5,0.6],2.,3.);
        let reordered=packet(&[(17,5),(2,0),(2,3)],&[0.2,0.1,0.3],0.,1.);
        let shadow=first.clone_checked().unwrap();
        let s=state(vec![first,other_moments,reordered,shadow]);
        let c=s.ordered_keyset_census();
        assert_eq!(c.uniform_packet_owners,4);
        assert_eq!(c.distinct_uniform_backings,3);
        assert_eq!(c.distinct_keysets,2);
        assert_eq!(c.repeated_key_packets,1);
        assert_eq!(c.repeated_key_rows,3);
        assert_eq!(c.potential_saved_key_payload_bytes,24);
        assert_eq!(c.max_tag,17);
        assert_eq!(c.max_offset,5);
    }

    #[test]
    fn same_length_but_different_order_cannot_share_keys_even_if_mass_equal() {
        let one=packet(&[(1,0),(2,1)], &[0.25,0.75],0.,1.);
        let two=packet(&[(2,1),(1,0)], &[0.25,0.75],0.,1.);
        let a=match &one {PacketParts::Uniform{rows,..}=>rows.as_slice(),_=>unreachable!()};
        let b=match &two {PacketParts::Uniform{rows,..}=>rows.as_slice(),_=>unreachable!()};
        assert!(!same_ordered_core_keys(a,b));
        let c=state(vec![one,two]).ordered_keyset_census();
        assert_eq!(c.repeated_key_rows,0);
    }

    #[test]
    fn unequal_endpoint_bit_patterns_do_not_change_key_identity_or_physical_bits() {
        let a=packet(&[(7,1)], &[f64::from_bits(1)],-0.,0.);
        let b=packet(&[(7,1)], &[0.5],0.,0.);
        let s=state(vec![a,b]);
        let c=s.ordered_keyset_census();
        assert_eq!(c.repeated_key_rows,1);
        let actual:Vec<_>=s.cells[0].packets.iter().map(|p|{
            p.parts.iter().map(|r|(r.tag,r.offset,r.mass.to_bits(),r.birth.to_bits(),
                r.a.0,r.b.0)).collect::<Vec<_>>()
        }).collect();
        assert_ne!(actual[0][0].4,actual[1][0].4);
    }
}

#[cfg(test)]
mod exact_persistent_keyset_storage_tests {
    use super::*;

    fn dense(keys:&[(u32,u32)], bias:f64, a:f64, b:f64)->PacketParts {
        PacketParts::Uniform {
            a:PackedTime::new(Some(a)).unwrap(),
            b:PackedTime::new(Some(b)).unwrap(),
            rows:Arc::new(keys.iter().enumerate().map(|(i,&(tag,offset))|
                CorePart{tag,offset,mass:(i+1) as f64/151.+bias,
                         birth: if i%11==0 {f64::from_bits(1)}
                         else {(i+3) as f64/31.+bias}}).collect()),
        }
    }
    fn state(parts:Vec<PacketParts>)->RoadState {
        RoadState{t:0.,cells:vec![Cell{
            v:[0.;8],packets:parts.into_iter().map(|p|Packet{target:0.,parts:p}).collect(),
            latent:BTreeMap::new()}],
            pending:vec![vec![]],totals:[0.;7],ledger:vec![]}
    }
    fn signature(p: Part)->(usize,usize,u64,u64,u64,u64){
        (p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)
    }

    #[test]
    fn independent_same_keys_share_only_metadata_not_ieee_moments() {
        let keys:Vec<_>=(0..64).map(|i|((i%13) as u32, (i/13) as u32)).collect();
        let mut s=state(vec![dense(&keys,0.0,-0.,1.),dense(&keys,0.3,0.,2.0)]);
        let before=s.cells[0].packets.iter().map(|p|
            p.parts.iter().map(signature).collect::<Vec<_>>()).collect::<Vec<_>>();
        let bytes_before=s.retained_storage_bytes();
        let changed=s.intern_exact_keysets().unwrap();
        let after=s.cells[0].packets.iter().map(|p|
            p.parts.iter().map(signature).collect::<Vec<_>>()).collect::<Vec<_>>();
        assert_eq!(before,after);
        assert!(changed>=2);
        let (x,y)=(&s.cells[0].packets[0].parts,&s.cells[0].packets[1].parts);
        match (x,y) {
            (PacketParts::SharedKeys{keys:k1,moments:v1,..},
             PacketParts::SharedKeys{keys:k2,moments:v2,..}) => {
                assert!(Arc::ptr_eq(k1,k2));
                assert!(!Arc::ptr_eq(v1,v2));
                assert_eq!(k1.len(),64);
                assert_ne!(v1[0].0.to_bits(),v2[0].0.to_bits());
            },
            _=>panic!("both independent packets should share only exact ordered keys"),
        }
        assert!(s.retained_storage_bytes()<bytes_before);
    }

    #[test]
    fn different_key_order_and_original_wide_mixed_values_never_intern() {
        let mut x:Vec<_>=(0..64).map(|i|(i as u32, 0u32)).collect();
        let mut y=x.clone();
        y.swap(0,1);
        let wide=Part{tag:(u32::MAX as usize)+1,offset:0,mass:0.25,birth:0.5,
            a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(1.)).unwrap()};
        let fallback=PacketParts::pack(vec![wide], |_|Ok(())).unwrap();
        let mut s=state(vec![dense(&x,0.,0.,1.),dense(&y,0.,0.,1.),fallback]);
        let before=s.cells[0].packets.iter().map(|p|
            p.parts.iter().map(signature).collect::<Vec<_>>()).collect::<Vec<_>>();
        assert_eq!(s.intern_exact_keysets().unwrap(),0);
        assert!(matches!(s.cells[0].packets[2].parts,PacketParts::Mixed(_)));
        let after=s.cells[0].packets.iter().map(|p|
            p.parts.iter().map(signature).collect::<Vec<_>>()).collect::<Vec<_>>();
        assert_eq!(before,after);
        x.clear();
    }

    #[test]
    fn cell_and_pending_share_exact_keys_with_one_live_cell_workspace() {
        let mut s=state(vec![]);
        s.cells.clear();
        s.pending.clear();
        let sizes=[16usize,64,513,33];
        for (i,&n) in sizes.iter().enumerate() {
            let keys:Vec<_>=(0..n).map(|j|(j as u32,i as u32)).collect();
            let first=dense(&keys,0.,-0.,1.);
            let second=dense(&keys,0.125,0.,2.);
            s.cells.push(Cell{v:[0.;8],packets:vec![Packet{target:0.,parts:first}],latent:BTreeMap::new()});
            s.pending.push(vec![Packet{target:0.,parts:second}]);
        }
        let bit_rows=|s:&RoadState|s.cells.iter().map(|c|&c.packets).chain(&s.pending)
            .flat_map(|q|q.iter()).map(|p|p.parts.iter().map(signature).collect::<Vec<_>>())
            .collect::<Vec<_>>();
        let bytes=s.retained_storage_bytes();
        let before=bit_rows(&s);
        let (rows,packets)=s.peak_cell_keyset_workspace().unwrap();
        assert_eq!((rows,packets),(2*513,2));
        let local=postroad_continuous_keyset_peak_event_bytes(bytes,13,17,rows,packets);
        let global=postroad_continuous_keyset_peak_event_bytes(bytes,13,17,2*sizes.iter().sum::<usize>(),8);
        assert!(check_storage_limit(Some(local),global,"old global keyset peak").is_err());
        assert!(check_storage_limit(Some(local-1),local,"cell keyset peak").is_err());
        assert!(check_storage_limit(Some(local),local,"cell keyset peak").is_ok());
        assert_eq!(s.intern_exact_keysets().unwrap(),8);
        assert_eq!(bit_rows(&s),before);
        assert!(s.retained_storage_bytes()<=bytes);
        for (c,q) in s.cells.iter().zip(&s.pending) {
            match (&c.packets[0].parts,&q[0].parts) {
                (PacketParts::SharedKeys{keys:k0,moments:m0,..},PacketParts::SharedKeys{keys:k1,moments:m1,..})=>{
                    assert!(Arc::ptr_eq(k0,k1)); assert!(!Arc::ptr_eq(m0,m1));
                },
                _=>panic!("expected independent moment arrays and shared keys"),
            }
        }
    }

    #[test]
    fn local_workspace_selects_combined_row_and_packet_peak() {
        let mut s=state(vec![dense(&[(0,0);200],0.,0.,1.)]);
        let many=state((0..100).map(|_|dense(&[],0.,0.,1.)).collect());
        s.cells.extend(many.cells);
        s.pending.extend(many.pending);
        assert_eq!(s.peak_cell_keyset_workspace().unwrap(),(0,100));
    }

    #[test]
    fn already_shared_full_arc_is_not_converted_into_two_new_allocations() {
        let keys:Vec<_>=(0..64).map(|i|(i as u32, 0u32)).collect();
        let p=dense(&keys,0.,0.,1.);
        let mut s=state(vec![p.clone_checked().unwrap(),p]);
        let before=s.arc_backing_census();
        assert_eq!(before.unique_backing_count,1);
        assert_eq!(s.intern_exact_keysets().unwrap(),0);
        assert_eq!(s.arc_backing_census().unique_backing_count,1);
    }
}

#[cfg(test)]
mod continuous_keyset_and_page_geometry_tests {
    use super::*;

    #[test]
    fn actual_source_100k_part_mark_work_pages_have_optimal_power_two_size() {
        assert_eq!(INCOMING_PART_CHUNK,128);
        assert_eq!(segmented_incoming_charge(11_764_502,1_586),774_794_848);
        assert_eq!(segmented_incoming_charge(0,1_586),0);
        assert_eq!(segmented_incoming_charge(11_764_502,1_586)
                   +2_327_104,777_121_952);
    }

    #[test]
    fn postroad_continuous_interning_counts_both_old_state_and_new_scratch() {
        let estimated=postroad_continuous_keyset_peak_bytes(
            postroad_continuous_owner_sum(100_000,100_000,100_000),
            20_000, 200, 500, 7,
        );
        let expected=3*100_000+20_000
            +200*std::mem::size_of::<EventRow>()
            +500*std::mem::size_of::<CorePart>()
            +7*512+96;
        assert_eq!(estimated,expected);
        assert!(estimated>=3*100_000+20_000+200*64);
    }

    #[test]
    fn new_page_geometry_retains_indexwise_order_and_original_mark_bits() {
        let mut parts=ChunkedParts::default();
        let mut marks=ChunkedMarks::default();
        for i in 0..(INCOMING_PART_CHUNK*3+11) {
            let v=Part {
                tag:i%13,offset:i%7,
                mass:if i%11==0 {f64::from_bits(1)} else {(i+1) as f64/257.},
                birth:if i%5==0 {-0.0} else {(i+7) as f64},
                a:PackedTime::new(Some(if i%19==0 {-0.0} else {0.0})).unwrap(),
                b:PackedTime::new(Some(1.0)).unwrap(),
            };
            parts.push_checked(v).unwrap();
            marks.push_checked(compact_mark(v.mass, v.birth)).unwrap();
        }
        assert_eq!(parts.len(),marks.len());
        assert!(parts.chunks.iter().all(|c|c.capacity()==INCOMING_PART_CHUNK));
        assert!(marks.chunks.iter().all(|c|c.capacity()==INCOMING_PART_CHUNK));
        for (i,(p,m)) in parts.iter().zip(marks.iter()).enumerate() {
            assert_eq!(p.tag,i%13);
            assert_eq!(m.0.to_bits(),p.mass.to_bits());
            assert_eq!(m.1.to_bits(),p.birth.to_bits());
            assert_eq!(parts.get(i).a.0,p.a.0);
        }
    }
}

#[cfg(test)]
mod exact_compact_candidate_event_tests {
    use super::*;

    fn event(i:usize) -> EventRow {
        (i%501,i%1586,if i%13==0{None}else{Some(i%1586)},
            if i%7==0 {f64::from_bits(1)} else {i as f64/117.},
            if i%19==0 {-0.0} else {i as f64/200.},
            if i%23==0 {-0.0} else {i as f64/199.},
            if i%31==0 {f64::from_bits(1)} else {i as f64/41.})
    }
    fn bits(x:EventRow)->(usize,usize,Option<usize>,u64,u64,u64,u64){
        (x.0,x.1,x.2,x.3.to_bits(),x.4.to_bits(),x.5.to_bits(),x.6.to_bits())
    }

    #[test]
    fn packed_event_row_has_genuine_48byte_payload_and_ieee_exact_inverse() {
        assert_eq!(std::mem::size_of::<EventRow>(),64);
        assert_eq!(std::mem::size_of::<CompactEventRow>(),48);
        for i in 0..1000 {
            let original=event(i);
            let compact=CompactEventRow::try_new(original).unwrap();
            assert_eq!(bits(compact.unpack()),bits(original));
        }
        assert!(CompactEventRow::try_new((u32::MAX as usize+1,0,None,1.,2.,3.,4.)).is_none());
        assert!(CompactEventRow::try_new((0,0,Some(u32::MAX as usize),1.,2.,3.,4.)).is_none());
    }

    #[test]
    fn packed_event_pages_reproduce_original_sixteen_million_ieee_order_boundaries() {
        for n in [0usize,1,4095,4096,4097,8193,16011] {
            let mut p=ChunkedEvents::new(true);
            let expected=(0..n).map(event).map(bits).collect::<Vec<_>>();
            for i in 0..n {p.push_checked(event(i)).unwrap();}
            assert_eq!(p.len(),n);
            assert_eq!(p.capacity(),n.div_ceil(EVENT_PAGE_ROWS)*EVENT_PAGE_ROWS);
            assert!(p.physical_capacity_bytes()<=p.capacity()*48+p.capacity().div_ceil(64)*8);
            let got=p.into_flat_checked().unwrap().into_iter().map(bits).collect::<Vec<_>>();
            assert_eq!(expected,got);
        }
    }

    #[test]
    fn wide_default_legacy_event_rows_remain_valid_without_truncation() {
        let x=(u32::MAX as usize+1,usize::MAX,Some(usize::MAX),
            0.125,-0.0,0.0,f64::from_bits(1));
        let mut p=ChunkedEvents::default();
        p.push_checked(x).unwrap();
        assert_eq!(bits(p.into_flat_checked().unwrap()[0]),bits(x));
    }

    #[test]
    fn source_derived_candidate_event_charge_matches_real_packed_allocation() {
        let n=9_100_145usize;
        let old=paged_event_candidate_bytes(n);
        let compact=paged_compact_event_candidate_bytes(n);
        assert_eq!(old-compact,16*(n.div_ceil(EVENT_PAGE_ROWS)*EVENT_PAGE_ROWS));
        assert!(old-compact>140_000_000);
        assert_eq!(paged_compact_event_candidate_bytes(0),std::mem::size_of::<ChunkedEvents>());
    }
}

#[cfg(test)]
mod exact_compact_incoming_source_tests {
    use super::*;
    fn row(i:usize)->Part {
        Part {tag:i%1503,offset:i%20,
            mass:if i%9==0 {f64::from_bits(1)} else {i as f64/191.},
            birth:if i%7==0 {-0.0} else {i as f64/37.},
            a:PackedTime::new(Some(if i%13==0 {-0.0} else {0.0})).unwrap(),
            b:PackedTime::new(Some(1.0)).unwrap()}
    }
    fn bits(p:Part)->(usize,usize,u64,u64,u64,u64){
        (p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)
    }
    #[test]
    fn packed_incoming_part_is_exact_40byte_injective_source_row() {
        assert_eq!(std::mem::size_of::<Part>(),48);
        assert_eq!(std::mem::size_of::<CompactIncomingPart>(),40);
        for i in 0..2000 {
            let orig=row(i);
            let packed=CompactIncomingPart::try_new(orig).unwrap();
            assert_eq!(bits(packed.unpack()),bits(orig));
        }
        let mut bad=row(5);bad.tag=(u32::MAX as usize)+1;
        assert!(CompactIncomingPart::try_new(bad).is_none());
    }
    #[test]
    fn source_order_across_part_mark_page_boundaries_is_bit_identical() {
        for n in [0usize,1,127,128,129,255,256,257,1013] {
            let mut pages=ChunkedParts::new(true);
            let reference=(0..n).map(row).map(bits).collect::<Vec<_>>();
            for i in 0..n {pages.push_checked(row(i)).unwrap();}
            assert_eq!(pages.len(),n);
            assert_eq!(pages.capacity(),n.div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK);
            assert_eq!(pages.iter().map(bits).collect::<Vec<_>>(),reference);
            for i in 0..n {assert_eq!(bits(pages.get(i)),bits(row(i)));}
        }
    }
    #[test]
    fn compact_physical_pages_reduce_source_charge_without_a_budget_override() {
        let r=13_460_957usize;
        let g=1586usize;
        let wide=segmented_incoming_charge(r,g);
        let compact=segmented_incoming_charge_for(r,g,true);
        assert_eq!(wide-compact,8*(r+127*g));
        assert!(compact<wide-100_000_000);
        assert_eq!(segmented_incoming_charge_for(0,g,true),0);
    }
    #[test]
    fn uncapped_wide_part_mode_keeps_original_usize_range() {
        let mut p=ChunkedParts::default();
        let mut a=row(1);a.offset=u32::MAX as usize+1;
        p.push_checked(a).unwrap();
        assert_eq!(bits(p.get(0)),bits(a));
    }
}

#[cfg(test)]
mod exact_consumed_packet_source_lifetime_tests {
    use super::*;

    fn source(i:usize)->Part {
        Part{tag:i%7,offset:i%3,
             mass:if i%11==0 {f64::from_bits(1)} else {(i+1) as f64/67.},
             birth:if i%19==0 {-0.0} else {i as f64/29.},
             a:PackedTime::new(Some(if i%3==0 {-0.0} else {0.0})).unwrap(),
             b:PackedTime::new(Some(1.0)).unwrap()}
    }
    fn work(n:usize)->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(10_000_000),
            base:0,transfer_exclusive_cell_scratch:0,
            events: 0, event_candidate_live_bound: None,incoming:n,incoming_page_cells:1586,
            incoming_cell_rows:None,incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,compact_incoming:true, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained:0,interval_transient:0,
            service_events:None,
        }
    }

    #[test]
    fn release_only_after_both_physically_allocated_part_and_mark_pages_expire() {
        for n in [0usize,1,127,128,129,257,1025] {
            let mut p=ChunkedParts::new(true);
            let mut m=ChunkedMarks::default();
            for i in 0..n {
                let r=source(i);
                p.push_checked(r).unwrap();
                m.push_checked(compact_mark(r.mass,r.birth)).unwrap();
            }
            let mut b=work(n+2048);
            let old=b.incoming;
            let mut checksum=0u64;
            for (x,y) in p.iter().zip(m.iter()) {
                checksum ^= x.mass.to_bits() ^ y.0.to_bits();
            }
            assert_eq!(checksum,0); // all original paired mass f64 bit patterns equal
            let charged_before=segmented_incoming_charge_for(b.incoming,1586,true);
            let released=release_consumed_incoming_pair(&mut b,0,p,m).unwrap();
            assert_eq!(released,n);
            assert_eq!(b.incoming,old-n);
            let charged_after=segmented_incoming_charge_for(b.incoming,1586,true);
            assert!(charged_after<=charged_before);
            assert_eq!(charged_before-charged_after,
                if n==0 {0}else {
                    56*n + 96*(old.div_ceil(INCOMING_PART_CHUNK)
                       - (old-n).div_ceil(INCOMING_PART_CHUNK))
                });
        }
    }

    #[test]
    fn source_release_rejects_unequal_mark_counts_or_overclaim_without_discarding() {
        let mut x=ChunkedParts::new(true);
        x.push_checked(source(1)).unwrap();
        let m=ChunkedMarks::default();
        let mut b=work(1);
        assert!(release_consumed_incoming_pair(&mut b,0,x,m).is_err());
        assert_eq!(b.incoming,1);
        let mut y=ChunkedParts::new(true);
        let mut mm=ChunkedMarks::default();
        for i in 0..2 {
            let r=source(i);
            y.push_checked(r).unwrap();
            mm.push_checked(compact_mark(r.mass,r.birth)).unwrap();
        }
        assert!(release_consumed_incoming_pair(&mut b,0,y,mm).is_err());
        assert_eq!(b.incoming,1);
    }
}

#[cfg(test)]
mod exact_postroad_live_owner_bound_tests {
    use super::*;

    #[test]
    fn exact_three_live_road_owners_are_added_individually_without_alias_credit() {
        let committed=545_136_024usize;
        let call_input=545_136_024usize;
        let candidate=745_155_216usize;
        let individually_charged=postroad_continuous_owner_sum(
            committed,call_input,candidate,
        );
        assert_eq!(individually_charged,1_835_427_264);
        assert_eq!(3*candidate-individually_charged,400_038_384);
        let required=postroad_continuous_keyset_peak_bytes(
            individually_charged,
            795_376_448,14_432_257,34_610_422,631_350,
        );
        assert_eq!(required,4_708_369_584);
        assert!(required<5_087_563_191);
        assert_eq!(5_087_563_191-required,379_193_607);
    }

    #[test]
    fn zero_and_nonidentical_owner_terms_are_never_assumed_pointer_sharing() {
        assert_eq!(postroad_continuous_owner_sum(0,0,0),0);
        assert_eq!(postroad_continuous_owner_sum(7,13,19),39);
        assert_eq!(postroad_continuous_owner_sum(5,5,5),15);
    }
}

#[cfg(test)]
mod exact_event_page_live_capacity_contract_tests {
    use super::*;

    fn expected(n:usize, sz:usize)->usize {
        let original_metadata=std::mem::size_of::<ChunkedEvents>();
        if n==0{return original_metadata;}
        let pages=n.div_ceil(EVENT_PAGE_ROWS);
        pages*EVENT_PAGE_ROWS*sz
            +(pages+1)*3*std::mem::size_of::<Vec<EventRow>>()
            +original_metadata
    }
    #[test]
    fn candidate_allocation_charges_actual_preallocated_page_capacity_not_fictitious_slack() {
        for n in [0usize,1,4095,4096,4097,8191,8192,8193,16011,
                    8_739_669,14_054_346] {
            assert_eq!(paged_compact_event_candidate_bytes(n),
                       expected(n,std::mem::size_of::<CompactEventRow>()),
                       "compact event source count {n}");
            assert_eq!(paged_event_candidate_bytes(n),
                       expected(n,std::mem::size_of::<EventRow>()),
                       "wide event source count {n}");
        }
    }
    #[test]
    fn source_100k_measured_transfer_guards_are_predicted_to_clear_without_cap_changes() {
        let short=8_739_669usize;
        let long=14_054_346usize;
        let old=|n:usize|(n+EVENT_PAGE_ROWS-1)*48
            +(n.div_ceil(EVENT_PAGE_ROWS)+1)*3*std::mem::size_of::<Vec<EventRow>>()+96;
        let carrier_growth=std::mem::size_of::<ChunkedEvents>()-96;
        assert_eq!(old(short)-paged_compact_event_candidate_bytes(short),139_200-carrier_growth);
        assert_eq!(old(long)-paged_compact_event_candidate_bytes(long),46_512-carrier_growth);
        assert!(139_200-carrier_growth>6_609);
        assert!(46_512-carrier_growth>11_513);
    }
    #[test]
    fn physical_page_chunk_capacity_and_event_bits_remain_unchanged() {
        for n in [0usize,1,4096,4097,8193] {
            let mut pages=ChunkedEvents::new(true);
            for i in 0..n {
                pages.push_checked((
                    i%1300,i%1586,if i%7==0{None}else{Some(i%1586)},
                    if i%11==0{f64::from_bits(1)}else{i as f64/73.},
                    if i%13==0{-0.0}else{i as f64/131.},
                    if i%17==0{-0.0}else{i as f64/223.},
                    i as f64/89.,
                )).unwrap();
            }
            assert_eq!(pages.physical_capacity_bytes(),
                n.div_ceil(EVENT_PAGE_ROWS)*(EVENT_PAGE_ROWS*40+FLAG_WORDS_PER_PAGE*8)
                  +n.div_ceil(CONTROL_PAGE_ROWS)*CONTROL_PAGE_ROWS*8);
        }
    }
}

#[cfg(test)]
mod exact_incoming_cell_page_liveness_tests {
    use super::*;

    fn work(g:usize)->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(100_000_000),base:0,transfer_exclusive_cell_scratch:0,
            events: 0, event_candidate_live_bound: None,incoming:0,
            incoming_page_cells:g,compact_events:true,compact_incoming:true, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            incoming_cell_rows:Some(vec![0;g]),incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    fn part(i:usize)->Part {
        Part {
            tag:i%31,offset:i%7,
            mass:if i%11==0 {f64::from_bits(1)}else{(i+1) as f64/79.},
            birth:if i%13==0 {-0.0}else{i as f64/17.},
            a:PackedTime::new(Some(0.0)).unwrap(),
            b:PackedTime::new(Some(1.0)).unwrap(),
        }
    }
    #[test]
    fn projected_source_cell_pages_equal_physically_live_part_and_mark_pages() {
        let mut w=work(3);
        let dests=(0..129).map(|_|0usize)
            .chain(std::iter::once(1))
            .chain((0..256).map(|_|2));
        w.transfer_indexed(386,dests).unwrap();
        assert_eq!(w.incoming,386);
        assert_eq!(w.incoming_cell_rows.as_ref().unwrap(),&vec![129,1,256]);
        assert_eq!(w.incoming_live_pages,2+1+2);
        let bound=segmented_incoming_exact_cell_pages_charge(
            w.incoming,w.incoming_page_cells,w.incoming_live_pages,true,None,
        );
        let expected=5*INCOMING_PART_CHUNK*(40+16)
            +2*(386usize.div_ceil(INCOMING_PART_CHUNK)+3)*(24+24)
            +(3*std::mem::size_of::<usize>()+128);
        assert_eq!(bound,expected);
        assert!(bound<segmented_incoming_charge_for(386,3,true)+
            3*std::mem::size_of::<usize>()+128);
        let mut p=ChunkedParts::new(true);
        let mut m=ChunkedMarks::default();
        for i in 0..129{
            let r=part(i);
            p.push_checked(r).unwrap();
            m.push_checked(compact_mark(r.mass,r.birth)).unwrap();
        }
        assert_eq!(p.physical_capacity_bytes(),2*128*40);
        assert_eq!(m.capacity()*std::mem::size_of::<Mark>(),2*128*16);
        release_consumed_incoming_pair(&mut w,0,p,m).unwrap();
        assert_eq!(w.incoming,257);
        assert_eq!(w.incoming_live_pages,3);
        assert_eq!(w.incoming_cell_rows.as_ref().unwrap(),&vec![0,1,256]);
        assert_eq!(segmented_incoming_exact_cell_pages_charge(
            w.incoming,w.incoming_page_cells,w.incoming_live_pages,true,None,
        ),3*INCOMING_PART_CHUNK*56+
          2*(257usize.div_ceil(INCOMING_PART_CHUNK)+3)*(24+24)
          +(3*8+128));
    }
    #[test]
    fn page_growth_is_only_at_true_cell_local_128_row_boundary() {
        let mut w=work(2);
        w.transfer_indexed(0,(0..127).map(|_|0usize)).unwrap();
        assert_eq!(w.incoming_live_pages,1);
        w.transfer_indexed(0,[0,1]).unwrap();
        assert_eq!(w.incoming_live_pages,2);
        w.transfer_indexed(0,[0]).unwrap();
        assert_eq!(w.incoming_live_pages,3);
        assert_eq!(w.incoming_cell_rows.as_ref().unwrap(),&vec![129,1]);
        assert!(w.transfer_indexed(0,[2usize]).is_err());
    }
}

#[cfg(test)]
mod exact_locked_incoming_descriptor_lifetime_tests {
    use super::*;

    fn work()->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(100_000_000),base:0,transfer_exclusive_cell_scratch:0,
            events: 0, event_candidate_live_bound: None,incoming:0,
            incoming_page_cells:3,
            incoming_cell_rows:Some(vec![0;3]),incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,compact_incoming:true, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    #[test]
    fn original_stable_source_vec_descriptors_can_be_counted_from_actual_capacity() {
        let mut w=work();
        let mut parts:Vec<ChunkedParts>=(0..3).map(|_|ChunkedParts::new(true)).collect();
        let mut marks:Vec<ChunkedMarks>=(0..3).map(|_|ChunkedMarks::default()).collect();
        for (j,n) in [(0usize,129usize),(1,1),(2,256)] {
            w.transfer_indexed(0,std::iter::repeat(j).take(n)).unwrap();
            for i in 0..n {
                let p=Part{tag:i%7,offset:0,mass:(i+1) as f64/59.,
                    birth:if i%13==0{-0.0}else{i as f64/19.},
                    a:PackedTime::new(Some(0.0)).unwrap(),
                    b:PackedTime::new(Some(1.0)).unwrap()};
                parts[j].push_checked(p).unwrap();
                marks[j].push_checked(compact_mark(p.mass,p.birth)).unwrap();
            }
        }
        assert_eq!(w.incoming,386);
        assert_eq!(w.incoming_live_pages,5);
        let before=segmented_incoming_exact_cell_pages_charge(
            386,3,5,true,None,
        );
        w.lock_completed_incoming_descriptors(&parts,&marks).unwrap();
        let actual:usize=(0..3).map(|i|
            (parts[i].descriptor_capacity()+marks[i].chunks.capacity())*
            std::mem::size_of::<Vec<Part>>()).sum();
        assert_eq!(w.incoming_descriptor_live_bytes,Some(actual));
        let after=segmented_incoming_exact_cell_pages_charge(
            386,3,5,true,Some(actual),
        );
        assert!(after<before);
        assert_eq!(before-after,2*(386usize.div_ceil(128)+3)*48-actual);
        assert!(w.transfer_indexed(0,[1]).is_err()); // the stable lifetime cannot append
        let expired_parts=std::mem::take(&mut parts[0]);
        let expired_marks=std::mem::take(&mut marks[0]);
        release_consumed_incoming_pair(&mut w,0,expired_parts,expired_marks).unwrap();
        assert_eq!(w.incoming,257);
        assert_eq!(w.incoming_live_pages,3);
        let remaining_actual:usize=(1..3).map(|i|
            (parts[i].descriptor_capacity()+marks[i].chunks.capacity())*
            std::mem::size_of::<Vec<Part>>()).sum();
        assert_eq!(w.incoming_descriptor_live_bytes,Some(remaining_actual));
    }
    #[test]
    fn locked_descriptor_state_checks_physical_mark_alignment_before_admission() {
        let mut w=work();
        w.transfer_indexed(0,[0usize]).unwrap();
        let mut parts:Vec<ChunkedParts>=(0..3).map(|_|ChunkedParts::new(true)).collect();
        let marks:Vec<ChunkedMarks>=(0..3).map(|_|ChunkedMarks::default()).collect();
        let x=Part{tag:1,offset:0,mass:1.,birth:0.,
            a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(1.)).unwrap()};
        parts[0].push_checked(x).unwrap();
        assert!(w.lock_completed_incoming_descriptors(&parts,&marks).is_err());
        assert_eq!(w.incoming_descriptor_live_bytes,None);
    }
}

#[cfg(test)]
mod exact_pending_pack_live_descriptor_tests {
    use super::*;

    fn example(i:usize)->Part {
        Part {
            tag:i%7,offset:i%3,
            mass:(i+1) as f64/61.,
            birth:if i%13==0{-0.0}else{i as f64/39.},
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap(),
        }
    }
    #[test]
    fn pending_packet_pack_uses_current_vec_capacity_without_freezing_future_appends() {
        let mut w=RoadWorkBudget {
            limit:Some(100000000),base:0,transfer_exclusive_cell_scratch:0,
            events: 0, event_candidate_live_bound: None,incoming:0,
            incoming_page_cells:3,
            incoming_cell_rows:Some(vec![0;3]),incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,compact_incoming:true, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained:0,interval_transient:0,service_events:None,
        };
        let mut incoming:Vec<ChunkedParts>=(0..3).map(|_|ChunkedParts::new(true)).collect();
        let mut marks:Vec<ChunkedMarks>=(0..3).map(|_|ChunkedMarks::default()).collect();
        for (j,n) in [(0usize,129usize),(1,1),(2,256)]{
            w.transfer_indexed(0,std::iter::repeat(j).take(n)).unwrap();
            for i in 0..n {
                let part=example(i);
                incoming[j].push_checked(part).unwrap();
                marks[j].push_checked(compact_mark(part.mass,part.birth)).unwrap();
            }
        }
        let actual=(0..3).map(|i|(
            incoming[i].descriptor_capacity()*std::mem::size_of::<Vec<Part>>()
            +marks[i].chunks.capacity()*std::mem::size_of::<Vec<Mark>>()
        )).sum();
        let old=segmented_incoming_exact_cell_pages_charge(
            386,3,5,true,None,
        );
        let new=segmented_incoming_exact_cell_pages_charge(
            386,3,5,true,Some(actual),
        );
        assert!(old-new>24);
        w.limit=Some(old+24-1);
        let original_packet=example(1);
        assert!(w.require(24,"packet interval packing").is_err());
        let packed=w.pack_parts_with_live_descriptors(
            vec![original_packet],&incoming,&marks,
        ).unwrap();
        let row=packed.iter().next().unwrap();
        assert_eq!(row.tag,original_packet.tag);
        assert_eq!(row.mass.to_bits(),original_packet.mass.to_bits());
        assert_eq!(row.birth.to_bits(),original_packet.birth.to_bits());
        assert_eq!(w.incoming_descriptor_live_bytes,None);
        // A future pending source append may still allocate new page headers.
        w.transfer_indexed(0,std::iter::once(1usize)).unwrap();
        assert_eq!(w.incoming_cell_rows.as_ref().unwrap(),&vec![129,2,256]);
        assert_eq!(w.incoming_descriptor_live_bytes,None);
    }
}

#[cfg(test)]
mod fifo_moment_nonclosure_physical_source_tests {
    use super::*;

    /// Original physical source-level packet representation: a cohort's
    /// birth value is its mass-weighted original entry/source time. Serve
    /// chronological queue heads exactly via the production served_parts()
    /// iterator and its unchanged (m, birth) scaling rule.
    fn source_fifo_departure(cohort_masses:[usize;3],quota:f64)->(f64,f64){
        let mut remaining=quota;
        let mut served_mass=0.0;
        let mut served_birth=0.0;
        for (i,integer_mass) in cohort_masses.into_iter().enumerate(){
            if remaining<=0. {break;}
            let m=integer_mass as f64;
            let part=Part {
                tag:0,offset:0,mass:m,birth:m*(i as f64),
                a:PackedTime::new(Some(i as f64)).unwrap(),
                b:PackedTime::new(Some(i as f64)).unwrap(),
            };
            let packet=PacketParts::pack(vec![part], |_|Ok(())).unwrap();
            let fraction=remaining.min(m)/m;
            for served in served_parts(&packet,fraction) {
                served_mass+=served.mass;
                served_birth+=served.birth;
                remaining-=served.mass;
            }
        }
        assert!(remaining.abs()<1e-12);
        (served_mass,served_birth)
    }
    #[test]
    fn exact_fifo_source_counterexample_same_mass_and_birth_different_departure_age(){
        let x=[3usize,2,3];
        let y=[1usize,6,1];
        let moments=|cohorts:[usize;3]|->(usize,usize){
            (cohorts.iter().sum(),
             cohorts.iter().enumerate().map(|(i,m)|i*m).sum())
        };
        assert_eq!(moments(x),(8,8));
        assert_eq!(moments(y),(8,8));
        let a=source_fifo_departure(x,2.);
        let b=source_fifo_departure(y,2.);
        assert!((a.0-2.).abs()<1e-12 && (b.0-2.).abs()<1e-12);
        assert_eq!(a.1.to_bits(),0.0f64.to_bits());
        assert!((b.1-1.).abs()<1e-12);
        assert_ne!(a.1.to_bits(),b.1.to_bits());
    }
    #[test]
    fn retaining_individual_packet_birth_and_source_interval_bits_is_not_global_closure(){
        let part=Part {
            tag:0,offset:0,mass:f64::from_bits(1),birth:-0.0,
            a:PackedTime::new(Some(-0.0)).unwrap(),
            b:PackedTime::new(Some(0.0)).unwrap(),
        };
        let packed=PacketParts::pack(vec![part], |_|Ok(())).unwrap();
        let row=packed.iter().next().unwrap();
        assert_eq!(row.mass.to_bits(),part.mass.to_bits());
        assert_eq!(row.birth.to_bits(),part.birth.to_bits());
        assert_eq!(row.a.0,part.a.0);
        assert_eq!(row.b.0,part.b.0);
        let served=served_parts(&packed,1.).next().unwrap();
        assert_eq!(served.mass.to_bits(),part.mass.to_bits());
        assert_eq!(served.birth.to_bits(),part.birth.to_bits());
    }
}

#[cfg(test)]
mod exact_shared_fifo_source_arc_credit_tests {
    use super::*;

    fn state(packets:Vec<PacketParts>)->RoadState {
        RoadState{
            t:0.,cells:vec![Cell{v:[0.;8],packets:packets.into_iter()
                .map(|parts|Packet{target:0.,parts}).collect(),latent:BTreeMap::new()}],
            pending:vec![vec![]],totals:[0.;7],ledger:vec![],
        }
    }
    #[test]
    fn distinct_shared_key_backings_are_counted_once_not_per_cohort(){
        let keys=Arc::new(vec![(3u32,0u32),(4,1),(5,2)]);
        let moments0=Arc::new(vec![(0.25,1.0),(0.5,2.0),(0.75,3.0)]);
        let moments1=Arc::new(vec![(0.875,0.0),(0.625,2.0),(0.125,3.0)]);
        let parts=|moments|PacketParts::SharedKeys{
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap(),
            keys:keys.clone(),moments,
        };
        let a=state(vec![parts(moments0),parts(moments1)]);
        let b=a.clone();
        let actual_unique=a.paired_shared_payload_lower_bound(&b);
        assert_eq!(actual_unique,3*(std::mem::size_of::<(u32,u32)>()
                                  +2*std::mem::size_of::<(f64,f64)>()));
        assert_eq!(actual_unique,120);
        assert_eq!(a.paired_shared_payload_lower_bound(&state(vec![
            PacketParts::SharedKeys{
                a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(1.)).unwrap(),
                keys:Arc::new(vec![(3u32,0u32),(4,1),(5,2)]),
                moments:Arc::new(vec![(0.25,1.0),(0.5,2.0),(0.75,3.0)])
            }
        ])),0);
    }
    #[test]
    fn cloned_source_uniform_arc_with_two_packet_owners_must_not_doublecount(){
        let p=PacketParts::pack(vec![Part{
            tag:1,offset:0,mass:0.25,birth:-0.0,
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap(),
        }], |_|Ok(())).unwrap();
        let a=state(vec![p.clone_checked().unwrap(),p]);
        let b=a.clone();
        assert_eq!(a.paired_shared_payload_lower_bound(&b),std::mem::size_of::<CorePart>());
        assert_eq!(a.arc_backing_census().unique_backing_count,1);
    }
}

#[cfg(test)]
mod original_transfer_exclusive_cell_scratch_tests {
    use super::*;
    fn phase_source_budget()->RoadWorkBudget {
        RoadWorkBudget{
            limit:Some(900),base:1000,
            transfer_exclusive_cell_scratch:150,
            events: 0, event_candidate_live_bound: None,incoming:0,incoming_page_cells:0,
            incoming_cell_rows:None,incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events:false,compact_incoming:false, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    #[test]
    fn only_source_transfer_preflight_excludes_future_interval_cell_combine_scratch(){
        let mut work=phase_source_budget();
        assert!(work.require(0,"tick preflight").is_err());
        assert!(work.transfer_indexed(0,std::iter::empty::<usize>()).is_ok());
        assert!(work.require(0,"packet interval packing").is_err());
        assert!(work.require(0,"entry interval split").is_err());
        assert_eq!(work.base,1000);
    }
    #[test]
    fn local_receiver_source_only_checks_exclude_future_cell_workspace(){
        let work=phase_source_budget();
        assert!(work.require(0,"source tick preflight").is_ok());
        assert!(work.require(49,"source offer packing").is_ok());
        assert!(work.require(51,"source offer packing").is_err());
        assert!(work.require(0,"tick preflight").is_err());
        assert!(work.require(0,"packet interval packing").is_err());
    }
    #[test]
    fn no_unearned_transfer_credit_for_zero_extra_or_nontransfer_call(){
        let mut w=phase_source_budget();
        w.transfer_exclusive_cell_scratch=0;
        assert!(w.transfer_indexed(0,std::iter::empty::<usize>()).is_err());
        w.transfer_exclusive_cell_scratch=150;
        assert!(w.require(100,"transfer candidates").is_err());
        assert!(w.require(0,"checkpoint decode preflight").is_err());
    }
}

#[cfg(test)]
mod original_weighted_fifo_physical_rates_theorem_tests {
    use super::*;
    fn original_source_node()->V1Road {
        let mut groups=vec![vec![1.0;6];3];
        groups[0][5]=1.;
        groups[1][5]=2.;
        groups[2][5]=1.;
        V1Road::new(
            "weighted-priority-physical-node".to_string(),10.,
            groups,vec![None;3],
            vec![(vec![0,1],0)],
            vec![vec![1.;13]],
            vec![vec![0,1,2]],vec![],
            100_000,Some(100_000),true,
        ).unwrap()
    }
    fn heads()->BTreeMap<usize,BTreeMap<usize,f64>> {
        BTreeMap::from([
            (0,BTreeMap::from([(0,1.),(1,0.)])),
            (1,BTreeMap::from([(0,0.5),(1,0.5)])),
            (2,BTreeMap::from([(0,0.),(1,1.)])),
        ])
    }
    #[test]
    fn original_progressive_junction_exact_physical_bottleneck_prediction(){
        let road=original_source_node();
        let demand=BTreeMap::from([(0,10.),(1,10.),(2,4.)]);
        let capacities=BTreeMap::from([(0,3.),(1,5.)]);
        let q=road.rates(&heads(),&demand,&capacities).unwrap();
        assert_eq!([q[&0],q[&1],q[&2]],[1.5,3.,3.5]);
        assert_eq!([q[&0]+q[&1]*0.5,q[&1]*0.5+q[&2]],[3.,5.]);
        let relief=BTreeMap::from([(0,4.),(1,5.)]);
        let q2=road.rates(&heads(),&demand,&relief).unwrap();
        assert_eq!([q2[&0],q2[&1],q2[&2]],[2.,4.,3.]);
        assert_eq!([q2[&0]+q2[&1]*0.5,q2[&1]*0.5+q2[&2]],[4.,5.]);
        assert_eq!(q2.values().sum::<f64>()-q.values().sum::<f64>(),1.0);
    }
    #[test]
    fn zero_downstream_capacity_blocks_only_upstream_sources_that_use_it() {
        let road=original_source_node();
        let demand=BTreeMap::from([(0,10.),(1,10.),(2,4.)]);
        let receiving=BTreeMap::from([(0,0.),(1,5.)]);
        let q=road.rates(&heads(),&demand,&receiving).unwrap();
        assert_eq!([q[&0],q[&1],q[&2]],[0.,0.,4.]);
    }
}


#[cfg(test)]
mod source_remainder_lifetime_tests {
    use super::*;

    fn fixture(limit: usize) -> (RoadWorkBudget, Vec<ChunkedParts>, Vec<ChunkedMarks>) {
        (RoadWorkBudget {
            limit: Some(limit), base: 1_000_000,
            transfer_exclusive_cell_scratch: 200_000,
            events: 0, event_candidate_live_bound: None, incoming: 0, incoming_page_cells: 1,
            incoming_cell_rows: Some(vec![0]), incoming_live_pages: 0,
            incoming_descriptor_live_bytes: None,
            compact_events: true, compact_incoming: true, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained: 0, interval_transient: 0, service_events: None,
        }, vec![ChunkedParts::new(true)], vec![ChunkedMarks::default()])
    }

    fn source_part() -> Part {
        Part { tag: 3, offset: 2, mass: 7., birth: 14.,
            a: PackedTime::new(Some(3.)).unwrap(),
            b: PackedTime::new(Some(4.)).unwrap() }
    }

    #[test]
    fn source_remainder_admits_only_its_live_raw_and_packed_buffers() {
        let (mut work, incoming, marks) = fixture(900_000);
        assert!(work.require(24, "packet interval packing").is_err());
        assert!(work.require(0, "entry interval split").is_err());
        let original = source_part();
        let result = work.pack_parts_with_live_descriptors(vec![original], &incoming, &marks);
        assert!(result.is_ok(), "source remainder wrongly includes future cell combine scratch");
        let packed = result.unwrap();
        let actual = packed.iter().next().unwrap();
        assert_eq!((actual.tag, actual.offset), (original.tag, original.offset));
        assert_eq!(actual.mass.to_bits(), original.mass.to_bits());
        assert_eq!(actual.birth.to_bits(), original.birth.to_bits());
        assert_eq!((actual.a.0, actual.b.0), (original.a.0, original.b.0));
        assert_eq!(work.incoming_descriptor_live_bytes, None);
        assert_eq!(work.base, 1_000_000);
        work.transfer_indexed(0, std::iter::once(0)).unwrap();
        assert_eq!(work.incoming_cell_rows.as_ref().unwrap(), &vec![1]);
    }

    #[test]
    fn source_remainder_budget_boundary_charges_both_buffers_and_restores_on_error() {
        let tracked_bytes = segmented_incoming_exact_cell_pages_charge(0, 1, 0, true, Some(0));
        let actual_bytes = std::mem::size_of::<Part>() + std::mem::size_of::<CorePart>();
        let required = 800_000 + tracked_bytes + actual_bytes;
        let (mut work, incoming, marks) = fixture(required - 1);
        assert!(work.pack_parts_with_live_descriptors(vec![source_part()], &incoming, &marks).is_err());
        assert_eq!(work.incoming_descriptor_live_bytes, None);
        work.limit = Some(required);
        let result = work.pack_parts_with_live_descriptors(vec![source_part()], &incoming, &marks);
        assert!(result.is_ok(), "exact live-buffer boundary must be admissible");
        assert_eq!(work.incoming_descriptor_live_bytes, None);
        work.transfer_exclusive_cell_scratch = 0;
        assert!(work.pack_parts_with_live_descriptors(vec![source_part()], &incoming, &marks).is_err());
        assert_eq!(work.incoming_descriptor_live_bytes, None);
    }

    #[test]
    fn mixed_remainder_still_charges_raw_buffer_before_reusing_it() {
        let tracked_bytes = segmented_incoming_exact_cell_pages_charge(0, 1, 0, true, Some(0));
        let (mut work, incoming, marks) = fixture(800_000 + tracked_bytes);
        let mut wide = source_part();
        wide.tag = u32::MAX as usize + 1;
        assert!(work.pack_parts_with_live_descriptors(vec![wide], &incoming, &marks).is_err(),
            "mixed fallback must charge its actual raw allocation");
        assert_eq!(work.incoming_descriptor_live_bytes, None);
    }
}


#[cfg(test)]
mod exact_event_time_run_tests {
    use super::*;
    fn bits(e:EventRow)->(usize,usize,Option<usize>,u64,u64,u64,u64) {
        (e.0,e.1,e.2,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits())
    }
    fn row(i:usize)->EventRow {
        let k=i/64;
        (i%133, i%17, if i%11==0 {None}else{Some(i%19)},
         (i+1) as f64/131.,
         if k%13==0 {-0.0}else{k as f64/91.},
         if k%17==0 {0.0}else{k as f64/31.+1.},
         if i%7==0 {f64::from_bits(1)}else{i as f64/71.})
    }
    #[test]
    fn repeated_time_pairs_allocate_once_per_run_not_once_per_physical_row() {
        let n=3*EVENT_PAGE_ROWS+17;
        let mut pages=ChunkedEvents::new(true);
        for i in 0..n {pages.push_checked(row(i)).unwrap();}
        assert_eq!(pages.control_len,n);
        let expected_payload=pages.capacity()*24 + pages.capacity().div_ceil(64)*8
            + n.div_ceil(CONTROL_PAGE_ROWS)*CONTROL_PAGE_ROWS*8 + EVENT_PAGE_ROWS*16;
        assert_eq!(pages.physical_capacity_bytes(), expected_payload,
            "repeated source time pairs still stored in every physical event row");
        let expected=(0..n).map(row).map(bits).collect::<Vec<_>>();
        assert_eq!(pages.iter().map(bits).collect::<Vec<_>>(),expected);
        assert_eq!(pages.into_flat_checked().unwrap().into_iter().map(bits).collect::<Vec<_>>(),expected);
    }
    #[test]
    fn source_runs_share_control_bits_across_payload_and_flag_pages() {
        let mut events = ChunkedEvents::new(true);
        let n = EVENT_PAGE_ROWS * 3 + 77;
        let expected = (0..n).map(|i| {
            let mut e = row(i);
            e.1 = if (4093..8195).contains(&i) { 7 } else { 9 };
            e.4 = if i < 8196 { -0.0 } else { 0.0 };
            e.5 = 2.0;
            e
        }).collect::<Vec<_>>();
        for &e in &expected {
            let bound = events.projected_append_storage_bytes(e).unwrap();
            events.push_checked(e).unwrap();
            assert!(events.retained_storage_bytes() <= bound);
        }
        assert_eq!(events.control_len, 4);
        assert_eq!(events.time_len, 2);
        let old_payload = events.capacity() * 32 + EVENT_PAGE_ROWS * 16;
        assert!(old_payload - events.physical_capacity_bytes() >= 7 * n);
        assert_eq!(events.iter().map(bits).collect::<Vec<_>>(),
                   expected.into_iter().map(bits).collect::<Vec<_>>());
    }
    #[test]
    fn projected_source_append_bounds_both_page_and_descriptor_allocations() {
        assert_eq!(std::mem::size_of::<EventPayload>(),24);
        assert_eq!(std::mem::size_of::<(u64,u64)>(),16);
        let mut pages=ChunkedEvents::new(true);
        let mut ordinal=0usize;
        for (batch,requested) in [1usize,17,4095,4096,4097,0,73].into_iter().enumerate() {
            let start=if batch%2==0 {-0.0}else{0.0};
            let end=(batch+1) as f64;
            let projected=pages.projected_candidate_bytes(requested,batch,start,end).unwrap();
            // The source preflight uses head length, which can overcount a
            // filtered zero-mass row. Prove the predicted buffer still covers
            // every actual prefix, including both header Vec allocations.
            let actual=requested.saturating_sub(usize::from(batch%3==0));
            for _ in 0..actual {
                let mut e=row(ordinal); e.1=batch; e.4=start;e.5=end;
                pages.push_checked(e).unwrap();ordinal+=1;
                let observed=pages.physical_capacity_bytes()
                    +pages.descriptor_capacity()*std::mem::size_of::<Vec<EventRow>>()
                    +std::mem::size_of::<ChunkedEvents>();
                assert!(observed<=projected,"actual allocation exceeds source projection");
            }
        }
        // Deliberately return to an older pair: only consecutive bit-identical
        // pairs share a run. Equal numerical signed zeros must stay distinct.
        let before=pages.time_len;
        for pair in [(-0.0,3.0),(0.0,3.0),(-0.0,3.0)] {
            pages.push_checked((0,0,None,1.0,pair.0,pair.1,0.0)).unwrap();
        }
        assert_eq!(pages.time_len,before+3);
    }

    #[test]
    fn event_carrier_bound_preserves_all_original_input_and_current_history_bytes() {
        let carrier=paged_run_event_candidate_bytes(12_305,250,193);
        let tracked=segmented_incoming_exact_cell_pages_charge(0,0,0,true,None);
        let mut work=RoadWorkBudget {
            limit:Some(111+222+carrier+tracked),base:0,
            transfer_exclusive_cell_scratch:0,
            events:12_305,event_candidate_live_bound:Some(carrier),incoming:0,
            incoming_page_cells:0,incoming_cell_rows:Some(vec![]),incoming_live_pages:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,compact_incoming:true, timed_incoming_control_bytes: None, timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained:0,interval_transient:0,
            service_events:Some(ServiceEventAccounting {
                input_bytes:111,current_bytes:222,shared_input_current:false,max_tag_bytes:0,
            }),
        };
        assert!(work.require(0,"transfer candidates").is_ok());
        work.limit=Some(111+222+carrier+tracked-1);
        assert!(work.require(0,"transfer candidates").is_err());
        work.service_events.as_mut().unwrap().shared_input_current=true;
        work.limit=Some(111+carrier+tracked);
        assert!(work.require(0,"transfer candidates").is_ok());
        work.limit=Some(111+carrier+tracked-1);
        assert!(work.require(0,"transfer candidates").is_err());
    }

    #[test]
    fn distinct_time_bits_and_page_boundaries_preserve_every_event_field() {
        let n=EVENT_PAGE_ROWS+3;
        let original=(0..n).map(|i| {
            let mut e=row(i);
            e.4=if i%2==0 {-0.0}else{0.0};
            e.5=f64::from_bits((i+1) as u64);
            e
        }).collect::<Vec<_>>();
        let mut pages=ChunkedEvents::new(true);
        for &e in &original {pages.push_checked(e).unwrap();}
        assert!(pages.physical_capacity_bytes()<=pages.capacity()*48+pages.capacity().div_ceil(64)*8);
        assert_eq!(pages.into_flat_checked().unwrap().into_iter().map(bits).collect::<Vec<_>>(),
            original.into_iter().map(bits).collect::<Vec<_>>());
    }
}


#[cfg(test)]
mod event_carrier_metadata_tests {
    use super::*;
    #[test]
    fn zero_row_page_allowance_covers_the_actual_living_carrier() {
        let carrier=std::mem::size_of::<ChunkedEvents>();
        assert!(paged_event_candidate_bytes(0)>=carrier,
            "empty wide event allowance is smaller than its actual carrier");
        assert!(paged_compact_event_candidate_bytes(0)>=carrier,
            "empty compact fallback allowance is smaller than its actual carrier");
        assert!(paged_run_event_candidate_bytes(0,0,0)>=carrier);
    }
    #[test]
    fn flatten_allowance_covers_coexisting_carrier_and_flat_vec_header_at_zero_rows() {
        let metadata=std::mem::size_of::<ChunkedEvents>()
            +std::mem::size_of::<Vec<EventRow>>();
        let required=postroad_event_materialization_bytes(11,23,0,0,0);
        assert!(required>=11+23+metadata,
            "flatten allowance misses actual coexisting metadata at zero rows");
        assert!(check_storage_limit(Some(11+23+metadata-1),required,"metadata boundary").is_err());
        assert!(check_storage_limit(Some(required),required,"metadata boundary").is_ok());
    }
}

#[cfg(test)]
mod retained_event_append_bound_tests {
    use super::*;

    #[test]
    fn streaming_decode_projection_bounds_actual_retention_for_both_domains() {
        for compressed in [false, true] {
            for repeat_time in [false, true] {
                let mut events = ChunkedEvents::new(compressed);
                for i in 0..(EVENT_PAGE_ROWS * 2 + 7) {
                    let time = if repeat_time { -0.0 } else { i as f64 };
                    let tag = if compressed { i % 257 } else { u32::MAX as usize + 1 };
                    let row = (tag, 0, None, 0.1, time, time + 1.0, -0.0);
                    let before = events.projected_append_storage_bytes(row).unwrap();
                    events.push_checked(row).unwrap();
                    assert!(events.retained_storage_bytes() <= before,
                        "pre-allocation bound missed physical carrier capacity");
                }
                assert_eq!(events.iter().count(), EVENT_PAGE_ROWS * 2 + 7);
            }
        }
    }
}

#[cfg(test)]
mod timed_incoming_workspace_contract_tests {
    use super::*;

    fn work(cells: usize, controls: &TimedIncomingControls) -> RoadWorkBudget {
        RoadWorkBudget {
            limit: Some(usize::MAX), base: 0, transfer_exclusive_cell_scratch: 0,
            events: 0, event_candidate_live_bound: None,
            incoming: 0, incoming_page_cells: cells,
            incoming_cell_rows: Some(vec![0; cells]), incoming_live_pages: 0,
            incoming_descriptor_live_bytes: None,
            compact_events: true, compact_incoming: true,
            timed_incoming_control_bytes: Some(timed_control_storage_bound(controls,0,cells).unwrap()), timed_referenced_rows: None, packed_ref_saved:None,
            interval_retained: 0, interval_transient: 0, service_events: None,
        }
    }

    #[test]
    fn global_projection_covers_minimum_headers_and_all_cell_page_boundaries() {
        let mut controls=TimedIncomingControls::new();
        let p=Part {tag:1,offset:2,mass:0.125,birth:0.03125,
            a:PackedTime::new(Some(-0.0)).unwrap(),b:PackedTime::new(Some(1.0)).unwrap()};
        let id=controls.push_checked(p.a,p.b,(0.5,0.25)).unwrap();
        let mut cells:Vec<_>=(0..3).map(|_|TimedIncomingRows::new()).collect();
        let mut budget=work(3,&controls);
        for index in 0..4097 {
            let destination=index%3;
            budget.transfer_indexed(0,[destination]).unwrap();
            let real_append_peak=cells.iter().enumerate().map(|(i,c)|
                c.projected_append_bytes(usize::from(i==destination)).unwrap()).sum::<usize>();
            assert!(timed_incoming_page_charge(3,budget.incoming_live_pages,None)>=real_append_peak);
            cells[destination].push_checked(p,id,&controls).unwrap();
        }
        lock_completed_timed_incoming(&mut budget,&cells,&controls).unwrap();
        assert_eq!(budget.incoming,4097);
        for cell in 0..3 {
            let count=cells[cell].len();
            let mut raw=ChunkedParts::new(true);
            let mut marks=ChunkedMarks::default();
            for (part,mark) in cells[cell].iter(&controls) {
                raw.push_checked(part).unwrap(); marks.push_checked(mark).unwrap();
            }
            let combined=combine_chunked_parts(&raw).unwrap();
            let direct=combine_indexed_parts(cells[cell].len(),|i|cells[cell].get(i,&controls).0).unwrap();
            assert_eq!(direct.len(),combined.len());
            assert!(direct.iter().zip(&combined).all(|(a,b)|
                (a.tag,a.offset,a.mass.to_bits(),a.birth.to_bits(),a.a.0,a.b.0)==
                (b.tag,b.offset,b.mass.to_bits(),b.birth.to_bits(),b.a.0,b.b.0)));
            assert_eq!(combined.len(),1);
            assert_eq!(combined[0].mass.to_bits(),(count as f64*0.125).to_bits());
            let before=budget.incoming;
            drop(raw);drop(marks); // only the materialized test oracle
            let released=release_consumed_timed_incoming(&mut budget,cell,
                std::mem::take(&mut cells[cell])).unwrap();
            assert_eq!(released,count);
            assert_eq!(budget.incoming,before-count);
        }
        assert_eq!(budget.incoming_live_pages,0);
        assert_eq!(budget.incoming_descriptor_live_bytes,Some(0));
        assert_eq!(controls.len(),1);
    }

    #[test]
    fn source_charge_remains_until_all_direct_combine_reads_finish() {
        let mut controls=TimedIncomingControls::new();
        let p=Part {tag:1,offset:2,mass:1.0,birth:0.0,
            a:PackedTime::new(Some(0.0)).unwrap(),b:PackedTime::new(Some(1.0)).unwrap()};
        let id=controls.push_checked(p.a,p.b,(0.5,0.25)).unwrap();
        let mut cells=vec![TimedIncomingRows::new()];
        let mut budget=work(1,&controls);
        budget.transfer_indexed(0,[0]).unwrap();
        cells[0].push_checked(p,id,&controls).unwrap();
        lock_completed_timed_incoming(&mut budget,&cells,&controls).unwrap();
        let encoded=timed_incoming_page_charge(1,budget.incoming_live_pages,
            budget.incoming_descriptor_live_bytes)+budget.timed_incoming_control_bytes.unwrap();
        budget.limit=Some(encoded-1);
        assert!(budget.require(0,"timed incoming direct combine").is_err());
        budget.limit=Some(encoded);
        assert!(budget.require(0,"timed incoming direct combine").is_ok());
        let combined=combine_indexed_parts(cells[0].len(),|i|cells[0].get(i,&controls).0).unwrap();
        assert_eq!(combined[0].mass.to_bits(),p.mass.to_bits());
        assert_eq!(budget.incoming,1);
        assert_eq!(cells[0].len(),1);
        release_consumed_timed_incoming(&mut budget,0,std::mem::take(&mut cells[0])).unwrap();
        assert_eq!(budget.incoming,0);
        assert_eq!(budget.incoming_live_pages,0);
        assert_eq!(controls.len(),1);
    }
}

#[cfg(test)]
mod source_specific_keyset_workspace_tests {
    use super::*;

    fn fixture(n:usize, include_uniform:bool)->RoadState {
        let keys=Arc::new((0..n).map(|i|(i as u32,1u32)).collect::<Vec<_>>());
        let moments=Arc::new((0..n).map(|i|
            (f64::from_bits(0x3fd0000000000000+i as u64),0.125)).collect::<Vec<_>>());
        let a=PackedTime::new(Some(1.0)).unwrap();let b=PackedTime::new(Some(2.0)).unwrap();
        let shared=Packet {target:2.0,parts:PacketParts::SharedKeys{a,b,keys:keys.clone(),moments}};
        let mut packets=vec![];
        if include_uniform {
            packets.push(Packet {target:2.0,parts:PacketParts::Uniform{a,b,
                rows:Arc::new(keys.iter().map(|&(tag,offset)|
                    CorePart{tag,offset,mass:0.5,birth:0.25}).collect())}});
        }
        packets.push(shared);
        RoadState {t:2.0,cells:vec![Cell{v:[0.;8],packets,latent:BTreeMap::new()}],
            pending:vec![vec![]],totals:[0.;7],ledger:vec![]}
    }
    fn bits(s:&RoadState)->Vec<(usize,usize,u64,u64,u64,u64)> {
        s.cells.iter().flat_map(|c|&c.packets).flat_map(|p|p.parts.iter())
            .map(|p|(p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)).collect()
    }

    #[test]
    fn interning_bound_allocates_only_uniform_rows_and_preserves_shared_moment_owner() {
        let n=4097;let mut s=fixture(n,true);
        let before=bits(&s);
        let (old_keys,old_moments)=match &s.cells[0].packets[1].parts {
            PacketParts::SharedKeys{keys,moments,..}=>(keys.clone(),moments.clone()),_=>unreachable!(),
        };
        assert_eq!(s.debug_stats().uniform_parts,2*n);
        assert_eq!(s.keyset_allocation_row_count(),n);
        let owners=s.retained_storage_bytes();
        let old=postroad_continuous_keyset_peak_event_bytes(owners,123,456,2*n,2);
        let corrected=postroad_continuous_keyset_peak_event_bytes(owners,123,456,n,2);
        assert_eq!(old-corrected,n*std::mem::size_of::<CorePart>());
        assert!(check_storage_limit(Some(corrected),old,"old shared-row projection").is_err());
        assert!(check_storage_limit(Some(corrected),corrected,"source-specific projection").is_ok());
        s.intern_exact_keysets().unwrap();
        assert_eq!(bits(&s),before);
        assert_eq!(s.keyset_allocation_row_count(),0);
        match &s.cells[0].packets[1].parts {
            PacketParts::SharedKeys{keys,moments,..}=>{
                assert!(Arc::ptr_eq(moments,&old_moments));
                assert!(Arc::ptr_eq(keys,&old_keys));
            },
            _=>panic!("existing shared source changed representation"),
        }
    }

    #[test]
    fn existing_shared_rows_need_metadata_but_no_new_key_or_moment_payload() {
        let mut s=fixture(4097,false);let before=bits(&s);
        let retained=s.retained_storage_bytes();
        assert_eq!(s.keyset_allocation_row_count(),0);
        let required=postroad_continuous_keyset_peak_event_bytes(retained,0,0,0,1);
        assert_eq!(required,retained+512+3*32);
        s.intern_exact_keysets().unwrap();
        assert_eq!(bits(&s),before);
        assert_eq!(s.keyset_allocation_row_count(),0);
    }
}


#[cfg(test)]
mod exact_streaming_remainder_tests {
    use super::*;
    fn make_part(tag:usize,off:usize,mass:f64,birth:f64,a:f64,b:f64)->Part {
        Part{tag,offset:off,mass,birth,
            a:PackedTime::new(Some(a)).unwrap(),
            b:PackedTime::new(Some(b)).unwrap()}
    }
    fn payload(parts:&PacketParts)->Vec<(usize,usize,u64,u64,u64,u64)>{
        parts.iter().map(|p|(p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)).collect()
    }
    #[test]
    fn scaled_source_direct_matches_eager_for_uniform_shared_and_mixed() {
        let originals=vec![
            make_part(1,0,0.75,0.125,-0.0,2.),
            make_part(2,1,0.5,0.25,-0.0,2.),
            make_part(3,2,1e-300,0.625,-0.0,2.),
        ];
        let uniform=PacketParts::pack(originals.clone(), |_|Ok(())).unwrap();
        let keys=Arc::new(vec![(1u32,0u32),(2,1),(3,2)]);
        let moments=Arc::new(vec![(0.75,0.125),(0.5,0.25),(1e-300,0.625)]);
        let shared=PacketParts::SharedKeys {
            a:PackedTime::new(Some(-0.0)).unwrap(),
            b:PackedTime::new(Some(2.)).unwrap(),keys,moments
        };
        let mut nonuniform=originals.clone();
        nonuniform[1].b=PackedTime::new(Some(3.)).unwrap();
        let mixed=PacketParts::Mixed(Arc::new(nonuniform));
        let wide=PacketParts::Mixed(Arc::new(vec![
            make_part(u32::MAX as usize +1,0,1.,-0.,0.,1.),
            make_part(1,0,0.5,1.,0.,1.),
        ]));
        let signed=PacketParts::Mixed(Arc::new(vec![
            make_part(1,0,0.5,0.5,0.,1.),
            make_part(1,0,0.5,0.5,-0.,1.),
        ]));
        assert_eq!(std::mem::size_of::<Part>(),48);
        assert_eq!(std::mem::size_of::<CorePart>(),24);
        for source in [&uniform,&shared,&mixed,&wide,&signed] {
            for f in [0.,0.25,0.7,1.,1e-100] {
                let eager=PacketParts::pack(portion(source,f).unwrap(), |_|Ok(())).unwrap();
                let direct=PacketParts::pack_scaled_from(source,f, |_|Ok(())).unwrap();
                assert_eq!(std::mem::discriminant(&eager),std::mem::discriminant(&direct));
                assert_eq!(payload(&eager),payload(&direct));
            }
        }
    }
    #[test]
    fn direct_source_allocation_excludes_full_temporary_part_buffer() {
        let n=257usize;
        let source=PacketParts::pack(
            (0..n).map(|i|make_part(1,i,0.125,0.25,2.,3.)).collect(),
            |_|Ok(())
        ).unwrap();
        let eager=portion(&source,0.5).unwrap();
        assert_eq!(eager.capacity(),n);
        let original_raw=eager.capacity()*std::mem::size_of::<Part>();
        let mut charged=0usize;
        let compact=PacketParts::pack_scaled_from(&source,0.5,|bytes|{
            charged=bytes;
            if bytes>n*std::mem::size_of::<CorePart>() {
                Err(budget("direct packet writes must not charge old raw buffer"))
            } else {Ok(())}
        }).unwrap();
        assert_eq!(charged,n*std::mem::size_of::<CorePart>());
        assert_eq!(compact.len(),n);
        assert!(original_raw>charged);
        let old=PacketParts::pack(eager, |_|Ok(())).unwrap();
        assert_eq!(payload(&old),payload(&compact));
    }
}

#[cfg(test)]
mod class_moment_stream_tests {
    use super::*;
// Expansion summation, including the round-to-even correction used by math.fsum.
fn legacy_sum<I: IntoIterator<Item = f64>>(values: I) -> f64 {
    let mut p: Vec<f64> = Vec::new();
    for mut x in values {
        let mut i = 0;
        for j in 0..p.len() {
            let mut y = p[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                p[i] = lo;
                i += 1;
            }
            x = hi;
        }
        p.truncate(i);
        if x != 0.0 {
            p.push(x);
        }
    }
    let mut hi = 0.0;
    let mut lo = 0.0;
    if let Some(x) = p.pop() {
        hi = x;
        while let Some(x) = p.pop() {
            let y = hi;
            hi = y + x;
            lo = x - (hi - y);
            if lo != 0.0 {
                break;
            }
        }
        if !p.is_empty()
            && ((lo < 0.0 && p[p.len() - 1] < 0.0) || (lo > 0.0 && p[p.len() - 1] > 0.0))
        {
            let y = lo * 2.0;
            let x = hi + y;
            if y == x - hi {
                hi = x;
            }
        }
    }
    hi
}

    #[test]
    fn streaming_expansions_match_legacy_order_and_rounding() {
        let mut seed=42u64;
        for n in [0,1,2,17,257,2048] {
            for _ in 0..32 {
                let mut values=Vec::new();
                for _ in 0..n {
                    seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                    let x=f64::from_bits(((seed>>52)%1800+1)<<52 | (seed & ((1u64<<52)-1)));
                    values.push(x * if seed&1==0 {1.0} else {-1.0});
                }
                assert_eq!(sum(values.iter().copied()).to_bits(),legacy_sum(values).to_bits());
            }
        }
        let mut pairs=vec![(1.0,0.5),(f64::from_bits(1),1.0),(1e-17,0.75),(1e-20,0.0)];
        pairs.extend((1..1000).map(|j|(1.0/(j as f64),0.001*j as f64)));
        let mut moments=ClassMoments::default();
        for &(m,l) in &pairs { moments.add(m,l); }
        let expected=legacy_sum(pairs.iter().map(|(m,l)|m*l))/legacy_sum(pairs.iter().map(|(m,_)|*m));
        assert_eq!(moments.mean().to_bits(),expected.to_bits());
    }
}


#[cfg(test)]
mod receiving_local_lifetime_tests {
    use super::*;
    #[test]
    fn measured_old_maximum_is_not_the_active_consumer() {
        // Same measured base and limit as the archived 6 GiB Valley refusal.
        let historical = 4_977_552_461usize;
        let limit = 4_881_896_463usize;
        let old = 187_014_048usize;
        let local = receiving_local_combine_scratch(100_000, 3);
        assert!(historical > limit);
        assert_eq!(local, 6_255_360);
        assert!(historical - old + local < limit);
        // A large active cell must still pay for its actual scratch.
        assert!(historical-old+receiving_local_combine_scratch(3_000_000,3)>limit);
    }

    #[test]
    fn local_scratch_covers_index_and_combined_capacity() {
        for n in [0usize,1,128,129,65536] {
            let bytes = n*(std::mem::size_of::<Part>()+std::mem::size_of::<usize>());
            assert!(receiving_local_combine_scratch(n,3)>=bytes);
        }
    }
}

#[cfg(test)]
mod compact_receiving_group_tests {
    use super::*;
    #[test]
    fn compact_source_ordinals_and_group_census_preserve_order_and_bits() {
        let rows:Vec<Part>=(0..4096).map(|i|Part{
            tag:i%13,offset:i%5,
            mass:if i%31==0 {0.} else {2f64.powi(-((i%61) as i32))},
            birth:2f64.powi(-((i%53) as i32)),
            a:PackedTime::new(Some((i%3) as f64)).unwrap(),b:PackedTime::new(Some((i%3+1) as f64)).unwrap(),
        }).collect();
        let old=combine_indexed_parts(rows.len(),|i|rows[i]).unwrap();
        let mut charges=vec![];
        let new=combine_compact_indexed_parts(rows.len(),|i|rows[i],|b,g|{charges.push((b,g));Ok(())}).unwrap();
        assert_eq!(old.len(),new.len());
        assert_eq!(charges,vec![(rows.len()*4,0),(rows.len()*4,new.len())]);
        assert!(new.len()<rows.len());
        for (a,b) in old.iter().zip(new.iter()) {
            assert_eq!((a.tag,a.offset,a.a.0,a.b.0,a.mass.to_bits(),a.birth.to_bits()),
                       (b.tag,b.offset,b.a.0,b.b.0,b.mass.to_bits(),b.birth.to_bits()));
        }
    }
}

#[cfg(test)]
mod ordered_stream_interval_tests {
    use super::*;
    #[test]
    fn repeated_ordered_keys_reuse_only_keys_and_match_legacy_bits() {
        let mut parts=Vec::new();
        for tag in 0..64 {
            for j in 0..3 {
                parts.push(Part{tag,offset:0,mass:(tag+1) as f64*2f64.powi(-j-2),
                    birth:(tag+2) as f64*2f64.powi(-j-3),
                    a:PackedTime::new(Some(-0.)).unwrap(),
                    b:PackedTime::new(Some(2.+j as f64)).unwrap()});
            }
        }
        let selected=||0..parts.len();
        let (p,c)=ordered_interval_packet(&parts,selected,0.,1.,None,|_|Ok(())).unwrap();
        let p=p.unwrap();
        let keys=match &p {PacketParts::SharedKeys{keys,..}=>keys,_=>panic!("expected shared-key representation")};
        let (q,d)=ordered_interval_packet(&parts,selected,1.,2.,Some(keys),|_|Ok(())).unwrap();
        let q=q.unwrap();
        assert_eq!(c-d,64*8+96);
        match &q {PacketParts::SharedKeys{keys:k,..}=>assert!(Arc::ptr_eq(keys,k)),_=>panic!("expected shared key reuse")}
        for (packet,a,b) in [(p,0.,1.),(q,1.,2.)] {
            let old=combine_interval_core(&parts,selected(),parts.len(),a,b).unwrap();
            for (x,y) in packet.iter().zip(old.iter()) {
                assert_eq!((x.tag,x.offset,x.mass.to_bits(),x.birth.to_bits(),x.a.0,x.b.0),
                    (y.tag as usize,y.offset as usize,y.mass.to_bits(),y.birth.to_bits(),a.to_bits(),b.to_bits()));
            }
            assert_eq!(packet.len(),old.len());
        }
    }
    #[test]
    fn selected_subset_underflow_and_changed_keys_match_legacy() {
        let parts:Vec<_>=(0..80).map(|i|Part{tag:i/2,offset:i%2,mass:if i%7==0{f64::from_bits(1)}else{0.75},
            birth:1.,a:PackedTime::new(Some(0.)).unwrap(),b:PackedTime::new(Some(4.)).unwrap()}).collect();
        let selected=|| (0..parts.len()).filter(|i|i%5!=0);
        let (out,_)=ordered_interval_packet(&parts,selected,0.,0.125,None,|_|Ok(())).unwrap();
        let old=combine_interval_core(&parts,selected(),parts.len(),0.,0.125).unwrap();
        let out=out.unwrap();assert_eq!(old.len(),out.len());
        for (x,y) in out.iter().zip(old.iter()) {
            assert_eq!((x.tag,x.offset,x.mass.to_bits(),x.birth.to_bits()),(y.tag as usize,y.offset as usize,y.mass.to_bits(),y.birth.to_bits()));
        }
    }
}

#[cfg(test)]
mod receiving_lifetime_floor_tests {
    use super::*;
    #[test]
    fn expired_source_rows_only_credit_once_and_candidate_growth_is_charged() {
        assert_eq!(receiving_lifetime_floor(100000,8000,1000,20000,23000).unwrap(),63000);
        assert_eq!(receiving_lifetime_floor(100000,8000,1000,20000,17000).unwrap(),60000);
        assert!(receiving_lifetime_floor(1000,8000,1000,20000,23000).is_err());
    }
}

#[cfg(test)]
mod direct_wire_decode_tests {
    use super::*;
    fn model()->V1Road {
        V1Road::new("direct-wire".into(),10.,vec![vec![1.;6];2],vec![None;2],
            vec![(vec![0,1],0)],vec![vec![1.;13]],vec![vec![0,1]],vec![],100000,Some(100000),true).unwrap()
    }
    fn input(n:usize,mixed:bool)->Vec<u8>{
        let p=Packet{target:1.,parts:PacketParts::Mixed(Arc::new((0..n).map(|i|Part{
            tag:0,offset:0,mass:(i+1) as f64/10000.,birth:f64::from_bits(i as u64),
            a:PackedTime::new(Some(-0.)).unwrap(),
            b:PackedTime::new(Some(if mixed&&i==n-1{1.}else{0.})).unwrap(),
        }).collect()))};
        let mut wire=vec![];
        model().write_packets(&mut wire,&[p]).unwrap();
        wire
    }
    #[test]
    fn uniform_decode_does_not_require_raw_part_buffer(){
        let n=4096;
        let old_wire=input(n,false);
        let cap=3*(std::mem::size_of::<Packet>()+32+n*std::mem::size_of::<CorePart>())+32+n*16;
        let mut w=RoadDecodeBudget{limit:Some(cap),retained_input:0,decoded:0,validation:0};
        let road=model();let q=road.read_packets(&mut &old_wire[..],&mut n.clone(),&mut w).unwrap();
        assert!(q[0].parts.is_uniform());
        let mut actual=vec![];road.write_packets(&mut actual,&q).unwrap();
        assert_eq!(old_wire,actual);
    }
    #[test]
    fn mixed_late_fallback_preserves_exact_rows(){
        let n=4096;let wire=input(n,true);let road=model();
        let mut w=RoadDecodeBudget{limit:None,retained_input:0,decoded:0,validation:0};
        let q=road.read_packets(&mut &wire[..],&mut n.clone(),&mut w).unwrap();
        assert!(!q[0].parts.is_uniform());
        let mut actual=vec![];road.write_packets(&mut actual,&q).unwrap();
        assert_eq!(wire,actual);
        assert_eq!(w.decoded,std::mem::size_of::<Packet>()+32+n*std::mem::size_of::<Part>());
    }
}

#[cfg(test)]
mod inline_expansion_storage_tests {
    use super::*;
    #[test]
    fn inline_and_spill_preserve_original_expansion_bits() {
        fn reference(xs:&[f64])->f64 {
            let mut p:Vec<f64>=vec![];
            for &v in xs {let mut x=v;let mut i=0;for j in 0..p.len(){
                let mut y=p[j];if x.abs()<y.abs(){std::mem::swap(&mut x,&mut y)}
                let hi=x+y;let lo=y-(hi-x);if lo!=0.{p[i]=lo;i+=1;}x=hi;
            }p.truncate(i);if x!=0.{p.push(x)}}
            let mut hi=0.;let mut lo=0.;
            if let Some(x)=p.pop(){hi=x;while let Some(x)=p.pop(){let y=hi;hi=y+x;lo=x-(hi-y);if lo!=0.{break}}
                if !p.is_empty()&&((lo<0.&&p[p.len()-1]<0.)||(lo>0.&&p[p.len()-1]>0.)){let y=lo*2.;let x=hi+y;if y==x-hi{hi=x}}
            }hi
        }
        let mut seed=7u64;let mut spill=0usize;
        for len in [0,1,2,3,16,64,257] {
            for _ in 0..128 {
                let xs:Vec<_>=(0..len).map(|_|{seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                    let x=f64::from_bits((seed&0x800f_ffff_ffff_ffff)|(((seed>>53)%2046+1)<<52));x
                }).collect();
                let mut a=RoadExpansion::default();for &x in &xs {a.add(x);}
                spill+=usize::from(a.p.spilled());
                let x=a.finish();let y=reference(&xs);
                assert!(x.to_bits()==y.to_bits()||x.is_nan()&&y.is_nan());
            }
        }
        let mut a=RoadExpansion::default();for x in [1.,0.5,0.25,-0.]{a.add(x);}
        assert!(!a.p.spilled());assert_eq!(a.finish().to_bits(),1.75f64.to_bits());assert!(spill>0);
    }
}

fn compact_checkpoint_vec<T>(n:usize)->CoreResult<Vec<T>>{let v=checkpoint_vec(n)?;if v.capacity()!=n{return Err(budget("compact checkpoint exact allocation capacity differs"))}Ok(v)}
fn wire_u32<W:Write>(w:&mut W,x:u32)->CoreResult<()>{
    w.write_all(&x.to_le_bytes()).map_err(|e|CoreError::io(e.to_string()))
}
fn read_wire_u32<R:Read>(r:&mut R)->CoreResult<u32>{
    let mut b=[0u8;4];r.read_exact(&mut b).map_err(|e|CoreError::io(e.to_string()))?;
    Ok(u32::from_le_bytes(b))
}
fn packed_from_wire(x:u64)->CoreResult<PackedTime>{
    if x==PackedTime::NONE{Ok(PackedTime(x))}else{PackedTime::new(Some(f64::from_bits(x)))}
}
fn write_moments<W:Write>(w:&mut W,m:f64,b:f64)->CoreResult<()>{
    let mut row=[0u8;16];row[..8].copy_from_slice(&m.to_bits().to_le_bytes());row[8..].copy_from_slice(&b.to_bits().to_le_bytes());
    w.write_all(&row).map_err(|e|CoreError::io(e.to_string()))
}
// Same little-endian bytes as scalar wire, amortize calls into BufWriter.
// A single stack buffer is reused across all packets in a queue.
fn wire_fixed_batch<W:Write,T,const N:usize>(w:&mut W,rows:&[T],scratch:&mut [u8],encode:impl Fn(&T)->[u8;N])->CoreResult<()>{
    let batch=scratch.len()/N;
    if batch==0{return Err(arithmetic("compact wire batch capacity"))}
    for chunk in rows.chunks(batch){
        for (dst,row) in scratch.chunks_exact_mut(N).zip(chunk){dst.copy_from_slice(&encode(row));}
        w.write_all(&scratch[..chunk.len()*N]).map_err(|e|CoreError::io(e.to_string()))?;
    }
    Ok(())
}
fn wire_core_row(row:&CorePart)->[u8;24]{
    let mut b=[0;24];b[..4].copy_from_slice(&row.tag.to_le_bytes());b[4..8].copy_from_slice(&row.offset.to_le_bytes());
    b[8..16].copy_from_slice(&row.mass.to_bits().to_le_bytes());b[16..].copy_from_slice(&row.birth.to_bits().to_le_bytes());b
}
fn wire_key_row(row:&(u32,u32))->[u8;8]{
    let mut b=[0;8];b[..4].copy_from_slice(&row.0.to_le_bytes());b[4..].copy_from_slice(&row.1.to_le_bytes());b
}
fn wire_moment_row(row:&(f64,f64))->[u8;16]{
    let mut b=[0;16];b[..8].copy_from_slice(&row.0.to_bits().to_le_bytes());b[8..].copy_from_slice(&row.1.to_bits().to_le_bytes());b
}
fn wire_mixed_row(p:&Part)->[u8;48]{
    let mut b=[0;48];
    for (dst,x) in b.chunks_exact_mut(8).zip([p.tag as u64,p.offset as u64,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0]){dst.copy_from_slice(&x.to_le_bytes());}b
}
impl V1Road{
    /// MFWHOLE2 road section. Version 1's logical rows are unchanged.
    /// Within a queue, only the most recent explicit shared key owner may be
    /// reused. No pointer values enter the wire. All interval/birth/mass bits
    /// are copied, never normalized or re-associated.
    fn write_packets_compact<W:Write>(&self,w:&mut W,q:&[Packet])->CoreResult<()>{
        if std::env::var_os("METROFLOW_NATIVE_SCALAR_COMPACT_WIRE").as_deref()==Some(std::ffi::OsStr::new("1")){
            return self.write_packets_compact_scalar(w,q)
        }
        write_len(w,q.len())?;
        let mut previous:Option<&Arc<Vec<(u32,u32)>>>=None;
        let mut scratch=[0u8;24*1024];
        for p in q{
            write_f64(w,p.target)?;write_len(w,p.parts.len())?;
            match &p.parts{
                PacketParts::Uniform{a,b,rows}=>{
                    write_u64(w,0)?;write_u64(w,a.0)?;write_u64(w,b.0)?;
                    wire_fixed_batch(w,rows.as_slice(),&mut scratch,wire_core_row)?;
                }
                PacketParts::SharedKeys{a,b,keys,moments}=>{
                    let reuse=previous.is_some_and(|old|Arc::ptr_eq(old,keys));
                    write_u64(w,if reuse{3}else{2})?;write_u64(w,a.0)?;write_u64(w,b.0)?;
                    if !reuse{wire_fixed_batch(w,keys.as_slice(),&mut scratch,wire_key_row)?;}
                    wire_fixed_batch(w,moments.as_slice(),&mut scratch,wire_moment_row)?;
                    previous=Some(keys);
                }
                PacketParts::Mixed(rows)=>{
                    write_u64(w,1)?;wire_fixed_batch(w,rows.as_slice(),&mut scratch,wire_mixed_row)?;
                }
            }
        }
        Ok(())
    }
    fn write_packets_compact_scalar<W:Write>(&self,w:&mut W,q:&[Packet])->CoreResult<()>{
        write_len(w,q.len())?;
        let mut previous:Option<&Arc<Vec<(u32,u32)>>>=None;
        for p in q{
            write_f64(w,p.target)?;write_len(w,p.parts.len())?;
            match &p.parts{
                PacketParts::Uniform{a,b,rows}=>{
                    write_u64(w,0)?;write_u64(w,a.0)?;write_u64(w,b.0)?;
                    for row in rows.iter(){wire_u32(w,row.tag)?;wire_u32(w,row.offset)?;write_moments(w,row.mass,row.birth)?;}
                }
                PacketParts::SharedKeys{a,b,keys,moments}=>{
                    let reuse=previous.is_some_and(|old|Arc::ptr_eq(old,keys));
                    write_u64(w,if reuse{3}else{2})?;write_u64(w,a.0)?;write_u64(w,b.0)?;
                    if !reuse{for &(tag,offset) in keys.iter(){wire_u32(w,tag)?;wire_u32(w,offset)?;}}
                    for &(m,b) in moments.iter(){write_moments(w,m,b)?;}
                    previous=Some(keys);
                }
                PacketParts::Mixed(rows)=>{
                    write_u64(w,1)?;
                    for p in rows.iter(){
                        write_len(w,p.tag)?;write_len(w,p.offset)?;write_moments(w,p.mass,p.birth)?;
                        write_u64(w,p.a.0)?;write_u64(w,p.b.0)?;
                    }
                }
            }
        }
        Ok(())
    }
    fn read_packets_compact<R:Read>(&self,r:&mut R,remaining:&mut usize,work:&mut RoadDecodeBudget)->CoreResult<Vec<Packet>>{
        let n=read_len(r,*remaining)?;
        work.reserve(n.saturating_mul(std::mem::size_of::<Packet>()+32),n.saturating_mul(64))?;
        let mut out=compact_checkpoint_vec(n)?;
        let mut previous:Option<Arc<Vec<(u32,u32)>>>=None;
        let check_key=|tag:usize,offset:usize|->CoreResult<()>{
            let &(p,_)=self.routes.get(tag).ok_or_else(||val("compact wire route tag"))?;
            if offset>=self.paths[p].len(){return Err(val("compact wire route offset"))}Ok(())
        };
        for _ in 0..n{
            let target=read_f64(r)?;let m=read_len(r,*remaining)?;
            if m==0{return Err(val("empty compact wire packet"))}*remaining-=m;
            let kind=read_u64(r)?;
            let parts=match kind{
                0=>{
                    let a=packed_from_wire(read_u64(r)?)?;let b=packed_from_wire(read_u64(r)?)?;
                    work.reserve(m.saturating_mul(std::mem::size_of::<CorePart>()),0)?;
                    let mut rows=compact_checkpoint_vec(m)?;
                    for _ in 0..m{
                        let tag=read_wire_u32(r)?;let offset=read_wire_u32(r)?;check_key(tag as usize,offset as usize)?;
                        rows.push(CorePart{tag,offset,mass:read_f64(r)?,birth:read_f64(r)?});
                    }
                    PacketParts::Uniform{a,b,rows:Arc::new(rows)}
                }
                1=>{
                    work.reserve(m.saturating_mul(std::mem::size_of::<Part>()),0)?;
                    let mut rows=compact_checkpoint_vec(m)?;
                    for _ in 0..m{
                        let tag=read_len(r,self.routes.len())?;let offset=read_len(r,usize::MAX)?;check_key(tag,offset)?;
                        rows.push(Part{tag,offset,mass:read_f64(r)?,birth:read_f64(r)?,a:packed_from_wire(read_u64(r)?)?,b:packed_from_wire(read_u64(r)?)?});
                    }
                    PacketParts::Mixed(Arc::new(rows))
                }
                2|3=>{
                    let a=packed_from_wire(read_u64(r)?)?;let b=packed_from_wire(read_u64(r)?)?;
                    let keys=if kind==3{
                        previous.as_ref().filter(|k|k.len()==m).ok_or_else(||val("compact wire key reference absent or wrong length"))?.clone()
                    }else{
                        work.reserve(m.saturating_mul(8).saturating_add(96),0)?;
                        let mut keys=compact_checkpoint_vec(m)?;
                        for _ in 0..m{let tag=read_wire_u32(r)?;let offset=read_wire_u32(r)?;check_key(tag as usize,offset as usize)?;keys.push((tag,offset));}
                        Arc::new(keys)
                    };
                    work.reserve(m.saturating_mul(16),0)?;
                    let mut moments=compact_checkpoint_vec(m)?;for _ in 0..m{moments.push((read_f64(r)?,read_f64(r)?));}
                    previous=Some(keys.clone());
                    PacketParts::SharedKeys{a,b,keys,moments:Arc::new(moments)}
                }
                _=>return Err(val("compact wire packet kind")),
            };
            out.push(Packet{target,parts});
        }
        Ok(out)
    }
}
#[cfg(test)]
mod compact_checkpoint_wire_tests{
    use super::*;
    #[test]
    fn explicit_shared_wire_roundtrip_reuses_keys_and_preserves_legacy_bytes(){
        let road=V1Road::new("compact-wire".into(),1.,vec![vec![1.;6];2],vec![None;2],vec![(vec![0,1],0)],vec![vec![1.;13]],vec![vec![0,1]],vec![],100000,None,true).unwrap();
        let keys=Arc::new(vec![(0,0);1024]);
        let a=PackedTime::new(Some(-0.)).unwrap();let b=PackedTime::new(Some(1.)).unwrap();
        let p=|v:f64|Packet{target:1.,parts:PacketParts::SharedKeys{a,b,keys:keys.clone(),moments:Arc::new(vec![(v,0.);1024])}};
        let q=vec![p(0.5),p(0.25),Packet{target:2.,parts:PacketParts::Uniform{a,b,rows:Arc::new(vec![CorePart{tag:0,offset:1,mass:0.125,birth:0.}])}},p(0.75)];
        let mut old=vec![];let mut compact=vec![];road.write_packets(&mut old,&q).unwrap();road.write_packets_compact(&mut compact,&q).unwrap();
        let mut scalar=vec![];road.write_packets_compact_scalar(&mut scalar,&q).unwrap();assert_eq!(compact,scalar);
        let mixed=Packet{target:3.,parts:PacketParts::Mixed(Arc::new(vec![Part{tag:0,offset:0,mass:0.5,birth:-0.,a,b};1001]))};
        let uniform=Packet{target:4.,parts:PacketParts::Uniform{a,b,rows:Arc::new(vec![CorePart{tag:0,offset:0,mass:0.5,birth:-0.};1025])}};
        let mut c=vec![];let mut v=vec![];let more=[mixed,uniform];road.write_packets_compact(&mut c,&more).unwrap();road.write_packets_compact_scalar(&mut v,&more).unwrap();assert_eq!(c,v);

        assert!(compact.len()<old.len()/2);
        let mut work=RoadDecodeBudget{limit:None,retained_input:0,decoded:0,validation:0};
        let got=road.read_packets_compact(&mut &compact[..],&mut 100000,&mut work).unwrap();
        let mut expanded=vec![];road.write_packets(&mut expanded,&got).unwrap();assert_eq!(expanded,old);
        match (&got[0].parts,&got[1].parts,&got[3].parts){
            (PacketParts::SharedKeys{keys:a,..},PacketParts::SharedKeys{keys:b,..},PacketParts::SharedKeys{keys:c,..})=>{assert!(Arc::ptr_eq(a,b));assert!(Arc::ptr_eq(a,c));}
            _=>panic!("lost explicit shared keys"),
        }
        // First shared declaration cannot be a back-reference.
        let mut bad_wire=compact.clone();bad_wire[24..32].copy_from_slice(&3u64.to_le_bytes());
        let mut work=RoadDecodeBudget{limit:None,retained_input:0,decoded:0,validation:0};
        assert!(road.read_packets_compact(&mut &bad_wire[..],&mut 100000,&mut work).is_err());
        assert!(road.read_packets_compact(&mut &compact[..compact.len()-1],&mut 100000,&mut work).is_err());
    }
}

#[cfg(test)]
mod streaming_validation_tests{
    use super::*;
    #[test]
    fn checked_finite_expansion_matches_exact_order_and_rejects_overflow(){
        let xs=[1e-300,1e100,0.5,-1e100,0.25,2e-300];
        let mut checked=RoadExpansion::default();for x in xs{checked.add_finite(x).unwrap();}
        assert_eq!(checked.finish_finite().unwrap().to_bits(),sum(xs).to_bits());
        let mut bad=RoadExpansion::default();bad.add_finite(f64::MAX).unwrap();assert!(bad.add_finite(f64::MAX).is_err());
        assert!(RoadExpansion::default().add_finite(f64::NAN).is_err());
    }
    #[test]
    fn validation_workspace_depends_on_packet_shells_not_rows(){
        assert_eq!(road_stream_validation_bound(100,20),2*1024*1024+6400+640);
    }
}

#[cfg(test)]
mod compact_decode_envelope_tests{
    use super::*;
    #[test]
    fn bound_matches_actual_decode_accounting_for_aliases_and_mixed_rows(){
        let road=V1Road::new("compact-bound".into(),1.,vec![vec![1.;6]],vec![None],vec![(vec![0],0)],vec![vec![1.;13]],vec![vec![0]],vec![],100000,None,true).unwrap();
        let a=PackedTime::new(Some(0.)).unwrap();let b=PackedTime::new(Some(1.)).unwrap();
        let keys=Arc::new(vec![(0,0);32]);
        let p=||Packet{target:1.,parts:PacketParts::SharedKeys{a,b,keys:keys.clone(),moments:Arc::new(vec![(0.125,0.);32])}};
        let mut s=road.blank(1.);
        s.cells[0].packets=vec![p(),p(),Packet{target:1.,parts:PacketParts::Mixed(Arc::new(vec![Part{tag:0,offset:0,mass:0.25,birth:0.,a,b}]))}];
        s.pending[0]=vec![p(),p()]; // queue boundary forces a new key declaration.
        let (bound,scratch)=s.compact_decode_envelope();
        let mut work=RoadDecodeBudget{limit:None,retained_input:0,
            decoded:std::mem::size_of::<RoadState>()+3*32+std::mem::size_of::<Cell>()+256+2*32+std::mem::size_of::<Vec<Packet>>()+std::mem::size_of::<[f64;5]>(),
            validation:2*1024*1024+32};
        for q in [&s.cells[0].packets,&s.pending[0]]{
            let mut wire=vec![];road.write_packets_compact(&mut wire,q).unwrap();
            let got=road.read_packets_compact(&mut &wire[..],&mut 100000,&mut work).unwrap();
            let mut out=vec![];let mut old=vec![];road.write_packets(&mut out,&got).unwrap();road.write_packets(&mut old,q).unwrap();assert_eq!(out,old);
        }
        assert_eq!(bound,work.decoded);assert_eq!(scratch,work.validation);
    }
}

// B10 bounded road-owner primitive. The caller must bind both route variants
// to the same canonical journey owner; this function does not mutate the
// journey registry or apply a routing probability. Only an actual ready
// FIFO head can change its remaining suffix, never a pending source.
#[cfg(any(test,feature="native-cli"))]
impl V1Road {
    #[allow(dead_code)]
    pub(crate) fn registered_path(&self,tag:usize)->Option<&[usize]>{self.routes.get(tag).map(|&(p,_)|self.paths[p].as_slice())}
    pub(crate) fn apply_ready_suffix(&self, s: &RoadState, cell: usize,
        old_tag: usize, new_tag: usize, owners: &[Option<usize>],
        legal_turns: &[(usize,usize)]) -> CoreResult<RoadState> {
        self.check_state(s)?;
        if old_tag == new_tag || old_tag >= self.routes.len() ||
            new_tag >= self.routes.len() || owners.len() != self.routes.len() ||
            owners[old_tag].is_none() || owners[old_tag] != owners[new_tag] ||
            self.routes[old_tag].1 != self.routes[new_tag].1 {
            return Err(val("suffix route owner or class differs"));
        }
        let c = s.cells.get(cell).ok_or_else(||val("suffix cell missing"))?;
        let head = c.packets.first().ok_or_else(||val("suffix head missing"))?;
        if head.target > c.v[0] {
            return Err(val("suffix head not yet at boundary"));
        }
        let old = self.path(old_tag);
        let new = self.path(new_tag);
        if old.last() != new.last() || new.windows(2)
            .any(|w| !legal_turns.contains(&(w[0], w[1]))) {
            return Err(val("suffix destination or legal turn differs"));
        }
        let mut changed = 0usize;
        for p in head.parts.iter() {
            if p.tag != old_tag {continue}
            if p.offset+1 >= new.len() || p.offset+1 >= old.len() ||
                old[..=p.offset] != new[..=p.offset] {
                return Err(val("suffix occupied prefix differs"));
            }
            changed += 1;
        }
        if changed == 0 {return Err(val("suffix head has no matching route"))}
        let base = s.retained_storage_bytes().max(self.retained_input_bytes);
        let extra = head.parts.len().saturating_mul(
            std::mem::size_of::<Part>() + std::mem::size_of::<CorePart>());
        let required = base.saturating_mul(3).saturating_add(extra)
            .saturating_add(road_stream_validation_bound(
                s.cells.iter().map(|c|c.packets.len())
                    .chain(s.pending.iter().map(Vec::len)).fold(0usize,usize::saturating_add),
                s.cells.len()));
        check_storage_limit(self.storage_budget,required,"ready suffix transaction")?;
        let mut rows=checkpoint_vec(head.parts.len())?;
        for mut p in head.parts.iter() {
            if p.tag==old_tag {p.tag=new_tag}
            rows.push(p);
        }
        let packed=PacketParts::pack(rows, |_|Ok(()))?;
        let mut next=s.clone();
        next.cells[cell].packets[0].parts=packed;
        self.check_state(&next)?;
        Ok(next)
    }
}

#[cfg(test)]
mod ready_suffix_owner_tests {
    use super::*;
    #[test]
    fn actual_fifo_head_suffix_changes_destination_preserving_ledgers() {
        let mut road=V1Road::new("suffix-ready".into(),10.,
            vec![vec![10.,10.,2.,2.,200.,1.];6],
            vec![Some((100.,50.,50.)),None,None,None,None,None],
            vec![(vec![0,1,3,5],0),(vec![0,2,4,5],0)],
            vec![vec![10.,2.,2.,4.,2.,1.,5.,1.,0.2,0.3,10.,0.,5.]],
            vec![vec![0],vec![1],vec![2],vec![3,4],vec![5]],vec![],
            100000,None,true).unwrap();
        let legal=[(0,1),(1,3),(3,5),(0,2),(2,4),(4,5)];
        road.owned_step(10.,vec![(0,1.,0.,Some(0.),Some(0.))]).unwrap();
        for _ in 0..4 {road.owned_step(10.,vec![]).unwrap();}
        let prior=road.state.clone();
        assert_eq!(prior.t,50.);
        assert!(!prior.cells[0].packets.is_empty());
        assert!(road.apply_ready_suffix(&prior,0,0,1,&[Some(0),Some(1)],&legal).is_err());
        assert!(road.apply_ready_suffix(&prior,0,0,1,&[Some(0),Some(0)],&legal[..3]).is_err());
        let updated=road.apply_ready_suffix(&prior,0,0,1,&[Some(0),Some(0)],&legal).unwrap();
        assert_eq!(updated.totals,prior.totals);
        assert_eq!(updated.ledger,prior.ledger);
        assert_eq!(updated.cells[0].v,prior.cells[0].v);
        let a=prior.cells[0].packets[0].parts.iter().next().unwrap();
        let b=updated.cells[0].packets[0].parts.iter().next().unwrap();
        assert_eq!(a.tag,0);assert_eq!(b.tag,1);
        assert_eq!((a.mass.to_bits(),a.birth.to_bits(),a.a.0,a.b.0,a.offset),
                   (b.mass.to_bits(),b.birth.to_bits(),b.a.0,b.b.0,b.offset));
        road.state=updated;
        let mut events=road.owned_step(10.,vec![]).unwrap();
        for _ in 0..19 {events.extend(road.owned_step(10.,vec![]).unwrap());}
        assert!(events.iter().any(|e|e.0==1&&e.1==0&&e.2==Some(2)));
        assert!(!events.iter().any(|e|e.1==0&&e.2==Some(1)));
        assert!((road.state.totals[0]-1.).abs()<1e-10);
        assert!((road.state.totals[1]-1.).abs()<1e-10);
        road.check_state(&road.state).unwrap();
    }
}

// MFWHOLE3 event section: consecutive source/time control runs followed by
// exact ordered payloads. No flat EventRow copy, no sorting, no arithmetic.
impl ChunkedEvents {
    pub(crate) fn can_write_runs(&self)->bool {self.compressed}
    pub(crate) fn write_runs<W:Write>(&self,w:&mut W)->CoreResult<()> {
        if !self.compressed{return Err(val("run wire needs compact event domain"))}
        let mut starts=self.flag_chunks.iter().flatten().enumerate().flat_map(|(word,&bits)|{
            let mut bits=bits;
            std::iter::from_fn(move ||{
                if bits==0{return None}
                let b=bits.trailing_zeros() as usize;bits&=bits-1;Some(word*64+b)
            })
        }).peekable();
        let mut controls=self.control_chunks.iter().flatten();
        let mut payload=(0..self.len).map(|i|self.compact_payload(i).expect("event payload index"));
        let mut done=0usize;
        while let Some(start)=starts.next(){
            if start!=done||start>=self.len{return Err(arithmetic("event run boundary differs"))}
            let stop=starts.peek().copied().unwrap_or(self.len);
            if stop<=start||stop>self.len{return Err(arithmetic("event run length differs"))}
            let &(source,time)=controls.next().ok_or_else(||arithmetic("event run control missing"))?;
            let &(a,b)=self.time_chunks.get(time as usize/EVENT_PAGE_ROWS)
                .and_then(|p|p.get(time as usize%EVENT_PAGE_ROWS)).ok_or_else(||arithmetic("event run time missing"))?;
            write_len(w,stop-start)?;wire_u32(w,source)?;write_u64(w,a)?;write_u64(w,b)?;
            for _ in start..stop{
                let p=payload.next().ok_or_else(||arithmetic("event run payload missing"))?;
                let mut row=[0u8;24];row[..4].copy_from_slice(&p.tag.to_le_bytes());
                row[4..8].copy_from_slice(&p.dest.to_le_bytes());
                row[8..16].copy_from_slice(&p.mass.to_bits().to_le_bytes());
                row[16..].copy_from_slice(&p.birth.to_bits().to_le_bytes());
                w.write_all(&row).map_err(|e|CoreError::io(e.to_string()))?;
            }
            done=stop;
        }
        if done!=self.len||controls.next().is_some()||payload.next().is_some(){return Err(arithmetic("event run census differs"))}
        Ok(())
    }
    pub(crate) fn read_runs<R:Read>(r:&mut R,n:usize,limit:Option<usize>)->CoreResult<Self>{
        let mut events=Self::new(true);
        if limit.is_some_and(|x|events.retained_storage_bytes()>x){return Err(budget("event run initial storage budget"))}
        while events.len<n{
            let count=read_len(r,n-events.len)?;
            if count==0{return Err(val("empty event wire run"))}
            let source=read_wire_u32(r)?;let a=read_f64(r)?;let b=read_f64(r)?;
            if !finite_nonnegative(a)||!finite_nonnegative(b)||a>b{return Err(val("invalid event wire run time"))}
            if events.last_source()==Some(source)&&events.last_time==Some((a.to_bits(),b.to_bits())){return Err(val("redundant event wire run"))}
            // Every append in this run has the same source and time. The
            // final fixed-page bound covers all monotonic intermediate
            // page counts and both old/new outer Vec descriptor allocations.
            let required=events.projected_candidate_bytes(count,source as usize,a,b)?;
            if limit.is_some_and(|x|required>x){return Err(budget("native service event run decode storage budget exceeded"))}
            for _ in 0..count{
                let mut bytes=[0u8;24];r.read_exact(&mut bytes).map_err(|e|CoreError::io(e.to_string()))?;
                let tag=u32::from_le_bytes(bytes[..4].try_into().unwrap());
                let dest=u32::from_le_bytes(bytes[4..8].try_into().unwrap());
                let mass=f64::from_bits(u64::from_le_bytes(bytes[8..16].try_into().unwrap()));
                let birth=f64::from_bits(u64::from_le_bytes(bytes[16..24].try_into().unwrap()));
                if !finite_nonnegative(mass)||!finite_nonnegative(birth){return Err(val("invalid event wire moment"))}
                events.push_checked((tag as usize,source as usize,
                    if dest==u32::MAX{None}else{Some(dest as usize)},mass,a,b,birth))?;
            }
        }
        Ok(events)
    }
}
#[cfg(test)]
mod exact_event_run_wire_tests {
    use super::*;
    fn bits(e:EventRow)->(usize,usize,Option<usize>,u64,u64,u64,u64){
        (e.0,e.1,e.2,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits())
    }
    #[test]
    fn run_wire_roundtrip_crosses_payload_flag_control_and_time_pages() {
        let mut e=ChunkedEvents::new(true);
        // Repeated controls, source-only changes, signed-zero clocks,
        // more than one time/control page, and exact tail.
        for i in 0..33001usize{
            let run=i/7;
            let a=if run==0{-0.0}else{run as f64};
            e.push_checked((i%321,run%91,if i%11==0{None}else{Some(i%9)},0.125,a,a+0.5,i as f64/8.)).unwrap();
        }
        let mut buf=vec![];e.write_runs(&mut buf).unwrap();
        let decoded=ChunkedEvents::read_runs(&mut &buf[..],e.len(),None).unwrap();
        assert_eq!(decoded.iter().map(bits).collect::<Vec<_>>(),e.iter().map(bits).collect::<Vec<_>>());
        assert_eq!(decoded.retained_storage_bytes(),e.retained_storage_bytes());
        let mut again=vec![];decoded.write_runs(&mut again).unwrap();assert_eq!(again,buf);
        assert!(buf.len()<e.len()*32);
        assert!(ChunkedEvents::read_runs(&mut &buf[..buf.len()-1],e.len(),None).is_err());
        assert!(ChunkedEvents::read_runs(&mut &buf[..],e.len(),Some(1000)).is_err());
        let mut empty=vec![];ChunkedEvents::new(true).write_runs(&mut empty).unwrap();
        assert!(empty.is_empty());assert_eq!(ChunkedEvents::read_runs(&mut &empty[..],0,None).unwrap().len(),0);
    }
    #[test] fn run_wire_rejects_bad_count_before_payload(){
        let mut b=vec![];write_len(&mut b,0).unwrap();
        assert!(ChunkedEvents::read_runs(&mut &b[..],1,None).is_err());
        let mut b=vec![];write_len(&mut b,999).unwrap();
        assert!(ChunkedEvents::read_runs(&mut &b[..],1,None).is_err());
    }
}

pub(crate) fn stream_sink_envelope_bytes(service_rows:usize,max_tag_bytes:usize)->usize{
    service_rows.saturating_mul(256).saturating_add(64).saturating_add(max_tag_bytes).saturating_add(32)
}

#[cfg(test)]
mod registered_width_tests {
 use super::*;
 #[test] fn exact_union_counts_terminal_and_deduplicates_repeated_routes(){
  assert_eq!(registered_successor_width(&[vec![0,1],vec![0,2],vec![0],vec![0,1],vec![3,0,2]],4),3);
  assert_eq!(registered_successor_width(&[vec![0,1,0,1]],2),2);
 }
 #[test] fn wide_registry_falls_back_to_universal_bound(){assert_eq!(registered_successor_width(&[vec![0]],100000),100001);}
}

#[cfg(test)]
mod packed_event_carrier_tests {
    use super::*;
    fn row(i:usize)->EventRow{
        let run=i/11;
        (i%113,run%31,if i%7==0{None}else{Some(i%23)},if i%3==0{0.125}else{0.25},run as f64,run as f64+0.5,(i%5)as f64)
    }
    fn bits(e:EventRow)->(usize,usize,Option<usize>,u64,u64,u64,u64){(e.0,e.1,e.2,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits())}
    #[test] fn packed_candidate_exact_bits_projection_and_wire(){
        let mut plain=ChunkedEvents{compressed:true,..Default::default()};
        let mut packed=ChunkedEvents{compressed:true,packed_payload:Some(Default::default()),..Default::default()};
        for i in 0..EVENT_PAGE_ROWS*3+17{
            let e=row(i);
            let limit=packed.projected_append_storage_bytes(e).unwrap();
            plain.push_checked(e).unwrap();packed.push_checked(e).unwrap();
            assert!(packed.retained_storage_bytes()<=limit);
            let p=packed.compact_payload(i).unwrap();
            assert_eq!((p.tag as usize,p.mass.to_bits(),p.birth.to_bits()),(e.0,e.3.to_bits(),e.6.to_bits()));
        }
        assert!(plain.iter().map(bits).eq(packed.iter().map(bits)));
        assert!(packed.retained_storage_bytes()<plain.retained_storage_bytes());
        let(mut a,mut b)=(vec![],vec![]);
        plain.write_runs(&mut a).unwrap();packed.write_runs(&mut b).unwrap();assert_eq!(a,b);
    }
}

#[cfg(feature="native-cli")]
pub struct PackedRankProbe{refs:v1_ref_blocks::PackedRefs,events:v1_event_blocks::PackedEvents,len:usize}
#[cfg(feature="native-cli")]
impl PackedRankProbe{
    pub fn new(len:usize)->CoreResult<Self>{
        if len>u32::MAX as usize||len==0{return Err(val("probe length"))}
        let mut refs=v1_ref_blocks::PackedRefs::default();let mut events=v1_event_blocks::PackedEvents::default();
        for i in 0..len{
            refs.push(v1_ref_blocks::ReceivingRef{event:i as u32,offset:(i%13)as u32,control:(i/57)as u32})?;
            events.push(EventPayload{tag:(i%311)as u32,dest:(i%7)as u32,mass:0.125,birth:0.25})?;
        }
        Ok(Self{refs,events,len})
    }
    pub fn saved_bytes(&self)->[usize;2]{[self.refs.saved_bytes(),self.events.saved()]}
    pub fn get(&self,i:usize)->[u64;5]{
        let r=self.refs.get(i%self.len).unwrap();let e=self.events.get(r.event as usize).unwrap();
        [r.event as u64,r.offset as u64,r.control as u64,e.mass.to_bits(),e.birth.to_bits()]
    }
}

#[cfg(feature="native-cli")]
pub fn allocation_probe_rank_moments(values:&[(f64,f64)])->CoreResult<[f64;2]>{v1_rank_projection::moment_probe(values)}

#[cfg(feature="native-cli")]
impl V1Road{
    pub(crate) fn audit_rank_observables(&self,s:&RoadState)->CoreResult<(Vec<[f64;6]>,Vec<[f64;4]>)>{
        use v1_rank_projection::Acc;
        let n=self.routes.len();let c=s.cells.len();
        let bytes=n.saturating_mul(std::mem::size_of::<[Acc;4]>()+std::mem::size_of::<[f64;4]>()).saturating_add(c.saturating_mul(48));
        if bytes>64*1024*1024{return Err(budget("rank audit summary exceeds 64MiB"))}
        let mut tags=checkpoint_vec(n)?;tags.resize(n,[Acc::default();4]);
        let mut cells=checkpoint_vec(c)?;
        for cell in &s.cells{
            cells.push([self.occupancy(cell),self.occupied(cell),cell.v[7],cell.v[2],cell.v[3],cell.v[6]]);
            for p in cell.packets.iter().flat_map(|p|p.parts.iter()){
                let a=tags.get_mut(p.tag).ok_or_else(||val("rank audit tag outside registry"))?;
                a[0].add(p.mass)?;a[1].add(p.birth)?;a[2].add(p.mass*p.offset as f64)?;
                let t=p.a.unwrap_or(0.)+0.5*(p.b.unwrap_or(0.)-p.a.unwrap_or(0.));a[3].add(p.mass*t)?;
            }
        }
        let mut out=checkpoint_vec(n)?;out.extend(tags.into_iter().map(|a|a.map(|x|x.value())));
        Ok((cells,out))
    }
}
