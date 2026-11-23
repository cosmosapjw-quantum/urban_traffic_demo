//! Rust owner of the V1 T02/T04 finite-response FIFO packet state.
//! Registry paths are interned; tags retain independent observable ledgers.
use crate::v1_parallel::ordered_map;
use pyo3::exceptions::{PyArithmeticError, PyIOError, PyMemoryError, PyValueError};
use pyo3::prelude::*;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::io::{Read, Write};
use std::sync::{Arc, Mutex, Weak};
// Shadow-only experiment; the original V03 road kernel and checkpoint layout
// remain unchanged in non-test native builds.
#[cfg(test)]
#[path = "v1_lineage_shadow.rs"]
mod lineage_shadow;

// Versioned by the enclosing engine header. Integers and IEEE-754 bit patterns
// have a fixed little-endian representation independent of Python objects.
pub(crate) fn write_u64<W: Write>(w: &mut W, v: u64) -> PyResult<()> {
    w.write_all(&v.to_le_bytes())
        .map_err(|e| PyIOError::new_err(e.to_string()))
}
pub(crate) fn read_u64<R: Read>(r: &mut R) -> PyResult<u64> {
    let mut b = [0; 8];
    r.read_exact(&mut b)
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(u64::from_le_bytes(b))
}
pub(crate) fn write_f64<W: Write>(w: &mut W, v: f64) -> PyResult<()> {
    write_u64(w, v.to_bits())
}
pub(crate) fn read_f64<R: Read>(r: &mut R) -> PyResult<f64> {
    Ok(f64::from_bits(read_u64(r)?))
}
pub(crate) fn write_len<W: Write>(w: &mut W, v: usize) -> PyResult<()> {
    write_u64(w, v as u64)
}
pub(crate) fn read_len<R: Read>(r: &mut R, max: usize) -> PyResult<usize> {
    let v = usize::try_from(read_u64(r)?).map_err(|_| val("native checkpoint length overflow"))?;
    if v > max {
        return Err(val(&format!(
            "native checkpoint length exceeds configuration/budget: observed_length={v}, allowed_length={max}"
        )));
    }
    Ok(v)
}
pub(crate) fn read_exact_len<R: Read>(r: &mut R, n: usize) -> PyResult<()> {
    if read_len(r, n)? != n {
        return Err(val("native checkpoint shape differs"));
    }
    Ok(())
}
pub(crate) fn checkpoint_vec<T>(n: usize) -> PyResult<Vec<T>> {
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
    fn new(value: Option<f64>) -> PyResult<Self> {
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
        before_allocate: impl FnOnce(usize) -> PyResult<()>,
    ) -> PyResult<Self> {
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
    fn clone_checked(&self) -> PyResult<Self> {
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
    /// Pointer witnesses only; equal row values never establish ownership.
    fn visit_shared_backings(
        &self,other:&Self,mut visit:impl FnMut(u8,usize,usize)
    ) {
        match (self,other) {
            (Self::Uniform{rows:a,..},Self::Uniform{rows:b,..})
                if Arc::ptr_eq(a,b) => visit(0,Arc::as_ptr(a) as usize,
                    a.capacity().saturating_mul(std::mem::size_of::<CorePart>())),
            (Self::Mixed(a),Self::Mixed(b))
                if Arc::ptr_eq(a,b) => visit(1,Arc::as_ptr(a) as usize,
                    a.capacity().saturating_mul(std::mem::size_of::<Part>())),
            (Self::SharedKeys{keys:ak,moments:am,..},
             Self::SharedKeys{keys:bk,moments:bm,..}) => {
                if Arc::ptr_eq(ak,bk) {
                    visit(2,Arc::as_ptr(ak) as usize,
                        ak.capacity().saturating_mul(std::mem::size_of::<(u32,u32)>()));
                }
                if Arc::ptr_eq(am,bm) {
                    visit(3,Arc::as_ptr(am) as usize,
                        am.capacity().saturating_mul(std::mem::size_of::<(f64,f64)>()));
                }
            },
            _=>{},
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
struct RoadWorkBudget {
    limit: Option<usize>,
    base: usize,
    /// Original two hypothetical max-cell Part scratch buffers belong to
    /// future/active interval combination. They are never alive at transfer
    /// preflight, during a source-transfer pending remainder CorePart pack,
    /// or after source completion when direct packet conversion runs.
    /// Those two narrow packet stages charge the actual simultaneously live
    /// source Part Vec plus CorePart allocation; active combine/interval
    /// phases retain the full old envelope. Physical caps are unchanged.
    transfer_exclusive_cell_scratch:usize,
    /// Four-f64/old-Part motion/validation envelope is needed only while
    /// source scans run. The live queue and Motion maps remain charged.
    row_scan_scratch_bytes:usize,
    expired_motion_scan_credit:usize,
    /// Source trace-only (cell,head,rate) owners. Count actual Vec capacities
    /// separately from the expired old per-Part motion scan.
    diagnostic_source_live_bytes:usize,
    /// Exact source/working-candidate Arc payload alias, restricted to
    /// ready=+infinity packets. These cannot enter a finite event-clock
    /// service head and move unchanged into the candidate survivors.
    /// Allocator metadata and all packet/Vec shells remain charged.
    frozen_queue_payload_credit:usize,
    events: usize,
    incoming: usize,
    incoming_page_cells: usize,
    /// Per-destination exact predicted row count. Only for bounded source.
    /// Updated BEFORE each physical append, and reset only after actual
    /// Part+Mark owners have been dropped for that destination.
    incoming_cell_rows: Option<Vec<usize>>,
    incoming_live_pages:usize,
    /// Present only for event-backed incoming. Pending rows own a separate
    /// direct Part spill, in addition to the order-preserving reference row.
    incoming_direct_cell_rows:Option<Vec<usize>>,
    incoming_direct_live_pages:usize,
    incoming_outer_bytes:usize,
    /// Real Part+Mark page-descriptor storage after all raw appends finish.
    incoming_descriptor_live_bytes:Option<usize>,
    compact_events: bool,
    narrow_events:bool,
    compact_incoming: bool,
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
    /// Exact original NativeWholeEngine::restore snapshot–committed RoadState
    /// Arc overlap before advance. Applies ONLY at the old source clock.
    original_input_road_shared: Option<(f64,usize)>,
}
impl ServiceEventAccounting {
    /// Event buffers live during the road step: the call-input and current
    /// committed buffers (charged separately, never assumed shared) and the
    /// append-only fixed-size pages, which never reallocate old EventRows.
    /// Whole-engine pages remain the immutable final store; standalone public
    /// road APIs still materialize flat output in a separately guarded stage.
    fn road_step_bytes(self, generated_rows: usize) -> usize {
        self.road_step_bytes_for(generated_rows,false)
    }
    fn road_step_bytes_for(self,generated_rows:usize,compressed:bool)->usize {
        self.road_step_bytes_for_tier(generated_rows,compressed,false)
    }
    fn road_step_bytes_for_tier(self,generated_rows:usize,compressed:bool,narrow:bool)->usize {
        self.input_bytes
            .saturating_add(if self.shared_input_current {0} else {self.current_bytes})
            .saturating_add(persistent_event_candidate_upper_bytes_for(
                generated_rows,compressed,narrow))
    }
}
// The public EventRow is unchanged (64B on x86_64). Only the transient
// candidate and service store use checked 40B/48B source-code tiers. The
// public EventRow and checkpoint wire retain their original representation.
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

/// Exact smaller-cell tier: no f64 is changed and None has its own
/// reserved destination code. Source 65535 remains representable; a
/// configured <=65535-cell registry guarantees every destination <65535.
#[derive(Clone,Copy)]
#[repr(C)]
struct NarrowEventRow {
    tag:u32,
    source:u16,
    dest:u16,
    mass:f64,
    start:f64,
    end:f64,
    birth:f64,
}
impl NarrowEventRow {
    fn try_new(e:EventRow)->Option<Self> {
        Some(Self{tag:u32::try_from(e.0).ok()?,
            source:u16::try_from(e.1).ok()?,
            dest:match e.2 {
                None=>u16::MAX,
                Some(x) if x<u16::MAX as usize=>u16::try_from(x).ok()?,
                Some(_)=>return None,
            },
            mass:e.3,start:e.4,end:e.5,birth:e.6})
    }
    fn unpack(self)->EventRow {
        (self.tag as usize,self.source as usize,
            if self.dest==u16::MAX {None}else{Some(self.dest as usize)},
            self.mass,self.start,self.end,self.birth)
    }
}
/// Mixed-width pages remain in one source-ordered descriptor Vec. If a
/// later row does not fit u16, only its currently open page is promoted;
/// every older page and every logical event index stays unchanged.
enum CompactEventPage {
    Narrow(Vec<NarrowEventRow>),
    Standard(Vec<CompactEventRow>),
}
impl CompactEventPage {
    fn new(capacity:usize,first:CompactEventRow)->PyResult<Self> {
        if NarrowEventRow::try_new(first.unpack()).is_some() {
            let rows=checkpoint_vec::<NarrowEventRow>(capacity)?;
            if rows.capacity()!=capacity {return Err(budget("narrow event page capacity differs"));}
            Ok(Self::Narrow(rows))
        }else{
            let rows=checkpoint_vec::<CompactEventRow>(capacity)?;
            if rows.capacity()!=capacity {return Err(budget("compact event page capacity differs"));}
            Ok(Self::Standard(rows))
        }
    }
    fn capacity(&self)->usize {
        match self {Self::Narrow(p)=>p.capacity(),Self::Standard(p)=>p.capacity()}
    }
    fn len(&self)->usize {
        match self {Self::Narrow(p)=>p.len(),Self::Standard(p)=>p.len()}
    }
    fn payload_bytes(&self)->usize {
        match self {
            Self::Narrow(p)=>p.capacity().saturating_mul(std::mem::size_of::<NarrowEventRow>()),
            Self::Standard(p)=>p.capacity().saturating_mul(std::mem::size_of::<CompactEventRow>()),
        }
    }
    fn get(&self,index:usize)->Option<EventRow> {
        match self {
            Self::Narrow(p)=>p.get(index).copied().map(NarrowEventRow::unpack),
            Self::Standard(p)=>p.get(index).copied().map(CompactEventRow::unpack),
        }
    }
    fn iter(&self)->CompactEventPageIter<'_> {
        match self {
            Self::Narrow(p)=>CompactEventPageIter::Narrow(p.iter()),
            Self::Standard(p)=>CompactEventPageIter::Standard(p.iter()),
        }
    }
    fn push_checked(&mut self,row:CompactEventRow)->PyResult<()> {
        if let Self::Narrow(old)=self {
            if let Some(narrow)=NarrowEventRow::try_new(row.unpack()) {
                old.push(narrow);
                return Ok(());
            }
            // The unknown-registry admission bound charges both the old
            // 40-B page and this 48-B replacement before either may coexist.
            let capacity=old.capacity();
            let mut replacement=checkpoint_vec::<CompactEventRow>(capacity)?;
            if replacement.capacity()!=capacity {
                return Err(budget("promoted event page capacity differs"));
            }
            replacement.extend(old.iter().copied().map(|v|
                CompactEventRow::try_new(v.unpack()).expect("u16 row is u32 representable")));
            *self=Self::Standard(replacement);
        }
        match self {
            Self::Standard(page)=>page.push(row),
            Self::Narrow(_)=>unreachable!(),
        }
        Ok(())
    }
    #[cfg(test)]
    fn as_ptr(&self)->*const () {
        match self {
            Self::Narrow(p)=>p.as_ptr().cast(),
            Self::Standard(p)=>p.as_ptr().cast(),
        }
    }
}
enum CompactEventPageIter<'a> {
    Narrow(std::slice::Iter<'a,NarrowEventRow>),
    Standard(std::slice::Iter<'a,CompactEventRow>),
}
impl Iterator for CompactEventPageIter<'_> {
    type Item=EventRow;
    fn next(&mut self)->Option<EventRow> {
        match self {
            Self::Narrow(p)=>p.next().copied().map(NarrowEventRow::unpack),
            Self::Standard(p)=>p.next().copied().map(CompactEventRow::unpack),
        }
    }
}

pub(crate) struct ChunkedEvents {
    chunks:Vec<Vec<EventRow>>,
    compact_chunks:Vec<CompactEventPage>,
    compressed:bool,
    len:usize,
    /// Identity only. Incoming views separately borrow the actual event data.
    source_token:Arc<()>,
    fixed_page_indexing:bool,
}
impl Default for ChunkedEvents {
    fn default()->Self {
        Self{chunks:Vec::new(),compact_chunks:Vec::new(),compressed:false,len:0,
            source_token:Arc::new(()),fixed_page_indexing:true}
    }
}
impl ChunkedEvents {
    pub(crate) fn new(compressed:bool)->Self {
        Self {compressed,..Self::default()}
    }
    pub(crate) fn len(&self)->usize {self.len}
    fn capacity(&self)->usize {
        if self.compressed {
            self.compact_chunks.iter().map(CompactEventPage::capacity).sum()
        } else {
            self.chunks.iter().map(Vec::capacity).sum()
        }
    }
    fn descriptor_capacity(&self)->usize {
        if self.compressed {self.compact_chunks.capacity()} else {self.chunks.capacity()}
    }
    fn physical_capacity_bytes(&self)->usize {
        if self.compressed {
            self.compact_chunks.iter().map(CompactEventPage::payload_bytes).sum()
        }else{
            self.capacity().saturating_mul(std::mem::size_of::<EventRow>())
        }
    }
    pub(crate) fn iter(&self)->impl Iterator<Item=EventRow>+'_ {
        self.chunks.iter().flat_map(|c|c.iter().copied())
            .chain(self.compact_chunks.iter().flat_map(CompactEventPage::iter))
    }
    fn get_checked(&self,index:usize)->Option<EventRow> {
        if index>=self.len {return None;}
        if !self.fixed_page_indexing {return self.iter().nth(index);}
        let (page,row)=(index/EVENT_PAGE_ROWS,index%EVENT_PAGE_ROWS);
        if self.compressed {
            self.compact_chunks.get(page)?.get(row)
        }else{
            self.chunks.get(page)?.get(row).copied()
        }
    }
    pub(crate) fn compressed(&self)->bool {self.compressed}
    /// Actual reserved backing capacities plus per-allocation/control padding.
    /// The carrier is shared through one Arc; callers count pointer-identical
    /// service snapshots once, but independent stores never receive a credit.
    pub(crate) fn storage_bytes(&self)->usize {
        let mut bytes=event_store_shell_bytes();
        if self.chunks.capacity()>0 {
            bytes=bytes.saturating_add(
                self.chunks.capacity().saturating_mul(std::mem::size_of::<Vec<EventRow>>())
            ).saturating_add(128);
        }
        if self.compact_chunks.capacity()>0 {
            bytes=bytes.saturating_add(
                self.compact_chunks.capacity().saturating_mul(std::mem::size_of::<CompactEventPage>())
            ).saturating_add(128);
        }
        for page in &self.chunks {
            bytes=bytes.saturating_add(page.capacity().saturating_mul(
                std::mem::size_of::<EventRow>())).saturating_add(128);
        }
        for page in &self.compact_chunks {
            bytes=bytes.saturating_add(page.payload_bytes()).saturating_add(128);
        }
        bytes
    }
    pub(crate) fn decode_storage_upper_bytes(&self)->usize {
        // The real native loader chooses a row ceiling BEFORE observing
        // payload codes. Keep its generic 48/64-B admission bound here even
        // for an all-narrow store; never promise a 40-B future admission that
        // that loader would reject before reading its first event.
        decoded_event_store_upper_bytes(self.len,self.compressed)
    }
    pub(crate) fn push_checked(&mut self,e:EventRow)->PyResult<()> {
        self.push_with_page_capacity(e,EVENT_PAGE_ROWS)
    }
    /// Total wire rows are known before decoding: the final page allocates
    /// only its remaining rows, never a speculative full page.
    pub(crate) fn push_decoded_checked(&mut self,e:EventRow,total:usize)->PyResult<()> {
        if self.len>=total {return Err(arithmetic("decoded event rows exceed wire length"));}
        self.push_with_page_capacity(e,EVENT_PAGE_ROWS.min(total-self.len))
    }
    fn push_with_page_capacity(&mut self,e:EventRow,next_capacity:usize)->PyResult<()> {
        if self.compressed {
            let packed=CompactEventRow::try_new(e).ok_or_else(||
                arithmetic("compressed event source-index contract differs"))?;
            if self.compact_chunks.last().is_none_or(|c|c.len()==c.capacity()) {
                if self.compact_chunks.last().is_some_and(|c|c.len()!=EVENT_PAGE_ROWS) {
                    self.fixed_page_indexing=false;
                }
                let page=CompactEventPage::new(next_capacity,packed)?;
                push_checked(&mut self.compact_chunks,page)?;
            }
            self.compact_chunks.last_mut().expect("compact page allocated").push_checked(packed)?;
        } else {
            if self.chunks.last().is_none_or(|c|c.len()==c.capacity()) {
                if self.chunks.last().is_some_and(|c|c.len()!=EVENT_PAGE_ROWS) {
                    self.fixed_page_indexing=false;
                }
                let page=checkpoint_vec(next_capacity)?;
                if page.capacity()!=next_capacity {
                    return Err(budget("wide event page capacity differs"));
                }
                push_checked(&mut self.chunks,page)?;
            }
            self.chunks.last_mut().expect("wide page allocated").push(e);
        }
        self.len+=1;
        Ok(())
    }
    fn into_flat_checked(self)->PyResult<Vec<EventRow>> {
        let mut flat=checkpoint_vec(self.len)?;
        if flat.capacity()!=self.len {
            return Err(budget("flat event output reserve exceeds exact native contract"));
        }
        for page in self.chunks {
            flat.extend(page);
        }
        for page in self.compact_chunks {
            match page {
                CompactEventPage::Narrow(rows)=>flat.extend(rows.into_iter().map(NarrowEventRow::unpack)),
                CompactEventPage::Standard(rows)=>flat.extend(rows.into_iter().map(CompactEventRow::unpack)),
            }
        }
        debug_assert_eq!(flat.len(),self.len);
        Ok(flat)
    }
}

fn event_store_shell_bytes()->usize {
    std::mem::size_of::<ChunkedEvents>()
        .saturating_add(2*std::mem::size_of::<usize>()).saturating_add(128)
        // Separate identity Arc allocation, including its control block and
        // padding. A Weak identity does not keep event data alive.
        .saturating_add(2*std::mem::size_of::<usize>()).saturating_add(128)
}
/// Conservative live bound including descriptor reallocation overlap and
/// allocator padding. It is monotone in n and uses exact final-page payload
/// during checkpoint decoding. Compact eligibility follows configured
/// registries; a wide registry takes the original usize/Option path.
pub(crate) fn decoded_event_store_upper_bytes(n:usize,compressed:bool)->usize {
    event_store_upper_bytes(n,compressed,false)
}
fn event_store_upper_bytes(n:usize,compressed:bool,narrow_registry:bool)->usize {
    if n==0 {return event_store_shell_bytes();}
    let pages=n.div_ceil(EVENT_PAGE_ROWS);
    let row_bytes=if !compressed {std::mem::size_of::<EventRow>()}
        else if narrow_registry {std::mem::size_of::<NarrowEventRow>()}
        else {std::mem::size_of::<CompactEventRow>()};
    let descriptor=if compressed {std::mem::size_of::<CompactEventPage>()}
        else {std::mem::size_of::<Vec<EventRow>>()};
    // With unknown source codes a partly filled narrow page may need a
    // wider replacement. It coexists with AT MOST this one old narrow page.
    let promotion=if compressed && !narrow_registry {
        n.min(EVENT_PAGE_ROWS).saturating_mul(std::mem::size_of::<NarrowEventRow>())
    }else{0};
    event_store_shell_bytes()
        .saturating_add(n.saturating_mul(row_bytes))
        .saturating_add(pages.saturating_mul(128))
        .saturating_add(pages.saturating_add(1).saturating_mul(3*descriptor))
        .saturating_add(2*128).saturating_add(promotion)
}
fn persistent_event_candidate_upper_bytes(n:usize,compressed:bool)->usize {
    persistent_event_candidate_upper_bytes_for(n,compressed,false)
}
fn persistent_event_candidate_upper_bytes_for(
    n:usize,compressed:bool,narrow_registry:bool,
)->usize {
    let slots=if n==0 {0} else {n.div_ceil(EVENT_PAGE_ROWS).saturating_mul(EVENT_PAGE_ROWS)};
    event_store_upper_bytes(slots,compressed,narrow_registry)
}

/// Exact source-backed row capacity for append-only, fixed-size pages.
/// ChunkedEvents::push_checked allocates exactly B slots for each newly
/// started page and checks real Vec::capacity()==B. Therefore for positive
/// n, *physically live* row slots are exactly B*ceil(n/B), not n+B-1.
/// The ORIGINAL transient 3x page-descriptor growth bound and original 96B
/// metadata reserve remain unchanged; no physical payload or cap is erased.
fn paged_event_candidate_payload_bytes(n:usize,row_bytes:usize)->usize {
    const META:usize=3*32;
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
/// The three distinct immutable road owners coexist after the road step:
/// committed, supplied input and the newly built candidate. Each owner
/// carries its own observable retained byte count. Three times the maximum
/// fictitiously allocates a second or third full copy of the candidate.
fn postroad_materialization_owner_bytes(
    committed:usize,input:usize,candidate:usize,
)->usize {
    postroad_continuous_owner_sum(committed,input,candidate)
}
/// Source-exact triple-owner charge: keep ALL observable road shells and
/// every unique immutable packet backing. Original source input and the
/// currently committed road were cloned by NativeWholeEngine::restore at a
/// source-verified physical clock. No other call path is granted this credit.
/// Only Arc pointer identities actually common to current+candidate are
/// credited on the second pair. Same-valued but independently allocated
/// arrays are never counted as aliases.
pub(crate) fn source_road_service_joint_live_owner_charge(
    committed:&RoadState,candidate:&RoadState,supplied_retained:usize,
    original_source_verified:Option<(f64,usize)>,
)->(usize,usize,usize) {
    postroad_source_verified_arc_owner_charge(
        committed,candidate,supplied_retained,original_source_verified)
}
fn postroad_source_verified_arc_owner_charge(
    committed:&RoadState,candidate:&RoadState,supplied_retained:usize,
    original_source_verified:Option<(f64,usize)>,
)->(usize,usize,usize) {
    let committed_bytes=committed.retained_storage_bytes();
    let candidate_bytes=candidate.retained_storage_bytes();
    let old_sum=postroad_materialization_owner_bytes(
        committed_bytes,supplied_retained,candidate_bytes);
    let source_credit=original_source_verified.map_or(0,|(clock,credit)|
        if clock==committed.t {
            credit.min(committed_bytes).min(supplied_retained)
        } else {0}
    );
    let candidate_credit=committed.paired_shared_payload_lower_bound(candidate)
        .min(committed_bytes).min(candidate_bytes);
    (old_sum.saturating_sub(source_credit)
         .saturating_sub(candidate_credit),
     source_credit,candidate_credit)
}
fn postroad_continuous_keyset_peak_bytes(
    owner_sum:usize, old_events:usize,
    flat_rows:usize, core_rows:usize, packet_owners:usize,
)->usize {
    owner_sum
        .saturating_add(old_events)
        .saturating_add(flat_rows.saturating_mul(std::mem::size_of::<EventRow>()))
        .saturating_add(core_rows.saturating_mul(std::mem::size_of::<CorePart>()))
        .saturating_add(packet_owners.saturating_mul(512))
        .saturating_add(3*32)
}


/// Keyset intern is an OPTIONAL immutable representation optimization, not a
/// precondition for a completed physical road state. If its conservative
/// all-candidate transient allocation estimate does not fit, do not start
/// allocating keys or moments. Existing Uniform and SharedKeys packets are
/// fully usable, exactly checkpointable and will be subject to subsequent
/// unchanged source/step storage guards.
fn maybe_intern_exact_keysets(
    candidate:&mut RoadState, limit:usize, required:usize,
)->PyResult<(usize,bool)> {
    if required>limit {
        return Ok((0,true));
    }
    Ok((candidate.intern_exact_keysets()?,false))
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
        .saturating_add(3*32)
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
    fn check_bound(&self) -> PyResult<()> {
        if self.stats.processed_time_bound + self.stats.clock_roundoff_bound
            > EVENT_CLOCK_TOLERANCE_S
        {
            return Err(arithmetic(&format!(
                "packet compensated clock roundoff budget exceeded: processed_subulp_s={:?}, clock_roundoff_s={:?}, tolerance_s={EVENT_CLOCK_TOLERANCE_S:?}",
                self.stats.processed_time_bound, self.stats.clock_roundoff_bound)));
        }
        Ok(())
    }
    fn advance(&mut self, h: f64, boundary: Option<f64>) -> PyResult<bool> {
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
    fn pack_parts(&mut self, parts: Vec<Part>) -> PyResult<PacketParts> {
        let raw_bytes = parts.capacity().saturating_mul(std::mem::size_of::<Part>());
        let packed = PacketParts::pack(parts, |bytes| self.reserve(bytes, 0))?;
        if packed.is_uniform() {
            self.decoded = self.decoded.saturating_sub(raw_bytes);
        }
        Ok(packed)
    }
    fn reserve(&mut self, bytes: usize, validation: usize) -> PyResult<()> {
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
/// Both kinds of descriptor backing are reserved serially. Earlier old
/// diagnostic Vec backing expires before the later physical Part/Mark
/// header growth. Charge the maximum known source-lifetime peak, not the
/// fictitious sum of both distinct allocator transient peaks.
fn source_sequential_header_overlap_extra(
    diag_source_peak_with_old:usize,
    diag_source_final_live:usize,
    physical_header_old_overlap:usize,
    index_vec_live:usize,
)->usize {
    diag_source_peak_with_old.saturating_sub(diag_source_final_live)
        .max(physical_header_old_overlap)
        .saturating_add(index_vec_live)
}
/// The temporary page reservation list names existing source cells only.
/// u32::MAX is reserved for diagnostic pending sentinels and is never a
/// legal physically configured cell. Original Part/Mark/route indices stay
/// wide and unchanged; this is an auxiliary source-only temporary array.
fn checked_page_destination_index(id:usize)->PyResult<u32> {
    let narrow=u32::try_from(id)
        .map_err(|_|budget("projected physical source cell index exceeds u32"))?;
    if narrow==u32::MAX {
        return Err(budget("projected physical source cell index collides with sentinel"));
    }
    Ok(narrow)
}
impl RoadWorkBudget {
    /// Post-prediction ownership boundary: old per-Part scan temporaries
    /// are dead, but live packet queue and Motion shells are still reserved.
    fn retire_completed_motion_scan(&mut self, live_queue_and_motion_bytes:usize) {
        self.expired_motion_scan_credit=self.row_scan_scratch_bytes
            .saturating_sub(live_queue_and_motion_bytes);
    }
    /// Called exactly once, after prediction queues have been constructed
    /// by clone_packet from this immutable source and before service begins.
    /// Only +infinity readiness is admitted: no tolerance or finite time
    /// comparison is used to predict whether a packet might be served.
    fn witness_frozen_queue_owners(
        &mut self,source:&RoadState,queues:&[Vec<(Packet,f64)>]
    )->PyResult<()> {
        if self.limit.is_none() {return Ok(());}
        if self.frozen_queue_payload_credit!=0 {
            return Err(arithmetic("frozen queue ownership already witnessed"));
        }
        if source.cells.len()!=queues.len()
            || source.cells.iter().zip(queues).any(|(c,q)|c.packets.len()!=q.len()) {
            return Err(arithmetic("frozen queue source shape differs"));
        }
        let mut witnesses=0usize;
        for (cell,queue) in source.cells.iter().zip(queues) {
            for (original,(candidate,ready)) in cell.packets.iter().zip(queue) {
                if *ready==f64::INFINITY {
                    original.parts.visit_shared_backings(&candidate.parts,|_,_,_| {
                        witnesses=witnesses.saturating_add(1);
                    });
                }
            }
        }
        if witnesses==0 {return Ok(());}
        // One small descriptor per actually matching packet backing, not
        // per Part. sort_unstable is in place. The temporary Vec is dropped
        // before applying any credit; both requested and observed capacities
        // are checked while the old full candidate allowance is still live.
        type Witness=(u8,usize,usize);
        let allowance=std::mem::size_of::<Vec<Witness>>().saturating_add(128);
        self.require(witnesses.saturating_mul(std::mem::size_of::<Witness>())
            .saturating_add(allowance),"frozen queue Arc census")?;
        let mut backing=checkpoint_vec::<Witness>(witnesses)?;
        self.require(backing.capacity().saturating_mul(std::mem::size_of::<Witness>())
            .saturating_add(allowance),"frozen queue Arc census")?;
        for (cell,queue) in source.cells.iter().zip(queues) {
            for (original,(candidate,ready)) in cell.packets.iter().zip(queue) {
                if *ready==f64::INFINITY {
                    original.parts.visit_shared_backings(&candidate.parts,|kind,ptr,bytes| {
                        backing.push((kind,ptr,bytes));
                    });
                }
            }
        }
        debug_assert_eq!(backing.len(),witnesses);
        backing.sort_unstable_by_key(|&(kind,ptr,_)|(kind,ptr));
        let mut previous=None;
        let mut credit=0usize;
        for &(kind,ptr,bytes) in &backing {
            if previous!=Some((kind,ptr)) {
                credit=credit.saturating_add(bytes);
                previous=Some((kind,ptr));
            }
        }
        drop(backing);
        self.frozen_queue_payload_credit=credit;
        crate::v1_trace::add("arc.frozen_queue_unique_payload_credit",credit as u64);
        Ok(())
    }
    fn pack_parts(&self, parts: Vec<Part>) -> PyResult<PacketParts> {
        PacketParts::pack(parts, |bytes| {
            self.require(bytes, "packet interval packing")
        })
    }
    /// Called ONLY after source-order combine has returned, source/Mark pages
    /// are dropped and descriptor ownership is frozen. The index and combined
    /// output scratch pair from combine is no longer alive. The *one* live
    /// Vec<Part> is charged by its observed capacity while new CorePart rows
    /// coexist during immutable packet conversion. Early pack calls retain
    /// the full unchanged original budget.
    fn pack_parts_after_completed_combine(&self, parts: Vec<Part>) -> PyResult<PacketParts> {
        if self.incoming_descriptor_live_bytes.is_none() {
            return self.pack_parts(parts);
        }
        let source_bytes = parts.capacity().saturating_mul(std::mem::size_of::<Part>());
        PacketParts::pack(parts, |core_bytes| {
            self.require_with_no_active_combine(
                core_bytes, "packet interval packing", Some(source_bytes)
            )
        })
    }

    /// The original raw incoming Part/Mark pages have been physically
    /// released after source-order combine_chunked_parts has returned.
    /// The current cell owns ONE exact Vec<Part> (observed capacity),
    /// never the two hypothetical full maximum-cell combine workspaces
    /// reserved for a different source lifetime in the global tick budget.
    ///
    /// This scoped replacement applies to the ENTIRE interval splitter,
    /// including index preflight, edge allocation and active interval
    /// selection. The split itself separately charges every actual selected
    /// interval row and retained candidate packet through interval_transient.
    /// Restore global base even if a resource/physical error aborts splitting.
    fn with_completed_source_interval<T>(
        &mut self,source_part_capacity_bytes:usize,
        operation:impl FnOnce(&mut Self)->PyResult<T>,
    )->PyResult<T>{
        // Unbounded standalone callers never build the optional accounting
        // registry. Their original physical splitter must still execute.
        if self.limit.is_none() {return operation(self);}
        if self.incoming_descriptor_live_bytes.is_none() {
            return Err(arithmetic(
                "interval source may not replace live precombine descriptor budget"));
        }
        let old_base=self.base;
        self.base=old_base.saturating_sub(self.transfer_exclusive_cell_scratch)
            .saturating_add(source_part_capacity_bytes);
        let result=operation(self);
        self.base=old_base;
        result
    }

    /// Source-final cell packet *slot* reservation happens AFTER the entire
    /// interval splitter returned. Its one source Vec<Part> was consumed,
    /// its active selected-row workspaces have ended, and the earlier two
    /// max-cell combine buffers were released even before the splitter.
    /// Every actual retained interval packet is still charged by
    /// interval_retained; the current old/new Vec<Packet> growth is passed
    /// in extra. Keep global tick/base fully unchanged outside this phase.
    fn require_completed_interval_cell_slot(&mut self, slot_overlap:usize)->PyResult<()>{
        if self.limit.is_none() {return Ok(());}
        if self.incoming_descriptor_live_bytes.is_none()
            || self.interval_transient!=0 {
            return Err(arithmetic("cell slot source interval lifetime not ended"));
        }
        let previous=self.base;
        self.base=previous.saturating_sub(self.transfer_exclusive_cell_scratch);
        let checked=self.require(slot_overlap,"cell packet reservation");
        self.base=previous;
        checked
    }
    fn require(&self, extra: usize, phase: &str) -> PyResult<()> {
        self.require_with_no_active_combine(extra, phase, None)
    }
    fn require_with_no_active_combine(
        &self, extra: usize, phase: &str, source_part_bytes: Option<usize>
    ) -> PyResult<()> {
        // In a coupled transition the road-step event buffers are charged by
        // lifetime; the sink envelope is charged after the step returns.
        let event_bytes = self.service_events.map_or_else(
            || {
                self.events
                    .saturating_mul(2 * std::mem::size_of::<EventRow>())
            },
            |service| service.road_step_bytes_for_tier(self.events,self.compact_events,self.narrow_events),
        );
        let incoming_bytes=if self.incoming_direct_cell_rows.is_some() {
            event_backed_incoming_page_charge(
                self.incoming_page_cells,self.incoming_live_pages,
                self.incoming_direct_live_pages,self.incoming_descriptor_live_bytes,
            )
        }else if self.incoming_cell_rows.is_some(){
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
        // The original two-max-cell combine scratch is not present
        // during transfer preflight, while packing a remainder under an
        // observed temporary incoming descriptor census, or in a completed
        // direct source packet conversion. Only such explicit no-combine
        // call sites pass the measured simultaneously live Part Vec size.
        // All other phases, including active splitting, retain the envelope.
        let no_active_combine_pack = phase=="packet interval packing"
            && self.incoming_descriptor_live_bytes.is_some()
            && source_part_bytes.is_some();
        let phase_base=if phase=="transfer candidates"
            || phase=="transfer header reservation" {
            self.base.saturating_sub(self.transfer_exclusive_cell_scratch)
        } else if no_active_combine_pack {
            // The old two-max-cell combine buffers are either future
            // (pending remainder) or dead (completed direct pack); charge
            // the current source Part Vec instead, plus the new Core buffer.
            self.base.saturating_sub(self.transfer_exclusive_cell_scratch)
                .saturating_add(source_part_bytes.unwrap_or(0))
        } else {self.base};
        // The initial tick preflight is unchanged. This adjustment is set
        // only after every prediction output was consumed in source order.
        let expired = if phase=="tick preflight" {0}
            else {self.expired_motion_scan_credit};
        let frozen=if phase=="tick preflight" {0}
            else {self.frozen_queue_payload_credit};
        let phase_base=phase_base.saturating_sub(expired).saturating_sub(frozen);
        let required =
            phase_base
                .saturating_add(event_bytes)
                .saturating_add(incoming_bytes)
                .saturating_add(self.incoming_outer_bytes)
                .saturating_add(self.interval_retained)
                .saturating_add(self.interval_transient)
                .saturating_add(self.diagnostic_source_live_bytes)
                .saturating_add(extra);
        if let Some(limit) = self.limit {
            if crate::v1_trace::guard(
                "road_work",
                phase,
                required,
                limit,
                &[
                    ("base", phase_base),
                    ("retired_motion_row_scan_credit",expired),
                    ("frozen_queue_source_payload_credit",frozen),
                    ("diagnostic_source_actual_capacity_bytes",self.diagnostic_source_live_bytes),
                    ("full_source_base", self.base),
                    ("transfer_exclusive_cell_scratch",
                        if phase=="transfer candidates" {
                            self.transfer_exclusive_cell_scratch
                        }else{0}),
                    ("packet_no_active_combine_reserve_replaced",
                        if no_active_combine_pack {self.transfer_exclusive_cell_scratch} else {0}),
                    ("packet_current_live_source_part_bytes",
                        if no_active_combine_pack {source_part_bytes.unwrap_or(0)} else {0}),
                    ("event_bytes", event_bytes),
                    ("incoming_rows", self.incoming),
                    ("incoming_live_pages",self.incoming_live_pages),
                    ("incoming_event_backed",usize::from(self.incoming_direct_cell_rows.is_some())),
                    ("incoming_direct_spill_live_pages",self.incoming_direct_live_pages),
                    ("incoming_actual_outer_bytes",self.incoming_outer_bytes),
                    ("incoming_actual_page_charge",incoming_bytes),
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
    fn release_incoming(&mut self,cell:usize,expired_rows:usize)->PyResult<()> {
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
        if let Some(direct)=&mut self.incoming_direct_cell_rows {
            let prior=direct.get_mut(cell).ok_or_else(||
                arithmetic("expired direct spill outside source registry"))?;
            self.incoming_direct_live_pages=self.incoming_direct_live_pages
                .checked_sub(prior.div_ceil(INCOMING_PART_CHUNK)).ok_or_else(||
                    arithmetic("expired direct spill pages exceed charged owners"))?;
            *prior=0;
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
    )->PyResult<()> {
        self.project_transfer(events,destinations,None)?;
        self.require(0,"transfer candidates")
    }
    /// Pure source count projection before the corresponding Part/Mark pages
    /// are actually appended. The optional list contains only destinations
    /// that will acquire a new 128-row page during this single source head.
    fn project_transfer(
        &mut self,events:usize,destinations:impl IntoIterator<Item=usize>,
        mut new_page_cells:Option<&mut Vec<u32>>,
    )->PyResult<()> {
        if self.incoming_descriptor_live_bytes.is_some() {
            return Err(arithmetic("incoming page descriptor storage frozen after last source append"));
        }
        self.events=self.events.saturating_add(events);
        if let Some(tracked)=&mut self.incoming_cell_rows {
            for i in destinations {
                let count=tracked.get_mut(i).ok_or_else(||
                    arithmetic("incoming predicted destination outside original cell registry"))?;
                let mut needs_header=*count % INCOMING_PART_CHUNK==0;
                if needs_header {
                    self.incoming_live_pages=self.incoming_live_pages.saturating_add(1);
                }
                // The road service call always declares a nonempty source
                // packet; pending insertion declares zero EventRows. Count
                // every pending direct payload before its physical append.
                if events==0 {
                    if let Some(direct)=&mut self.incoming_direct_cell_rows {
                        let d=direct.get_mut(i).ok_or_else(||
                            arithmetic("pending spill source destination outside registry"))?;
                        if *d % INCOMING_PART_CHUNK==0 {
                            self.incoming_direct_live_pages=
                                self.incoming_direct_live_pages.saturating_add(1);
                            needs_header=true;
                        }
                        *d=d.saturating_add(1);
                    }
                }
                if needs_header {
                    if let Some(ref mut cell_ids)=new_page_cells {
                        push_checked(cell_ids,checked_page_destination_index(i)?)?;
                    }
                }
                *count=count.saturating_add(1);
                self.incoming=self.incoming.saturating_add(1);
            }
        } else {
            for _ in destinations {
                self.incoming=self.incoming.saturating_add(1);
            }
        }
        Ok(())
    }
    /// Existing compatibility path, without a diagnostic source lineage
    /// projection. The instrumented original driver below must pass its
    /// real diagnostic source vectors for a source-bound guard.
    /// Physical two-phase header preallocation for exactly this transfer.
    /// No original Part/Mark or EventRow values are created or changed here.
    /// Both header vectors reserve before source append so no header Vec can
    /// reallocate during the subsequent physical Part/Mark page insertion.
    /// Charge ALL actually allocated header capacity and one possible old
    /// header backing overlapping the new one during this serial reservation.
    /// If the allocator overallocates, its ACTUAL post-reserve capacity is
    /// charged, never a guessed capacity; 8GiB process cap remains hard.
    fn transfer_indexed_with_live_headers(
        &mut self,events:usize,destinations:impl IntoIterator<Item=usize>,
        incoming:&mut [ChunkedParts],marks:&mut [ChunkedMarks],
    )->PyResult<()> {
        self.transfer_indexed_with_live_diagnostics(
            events,destinations,incoming,marks,None
        )
    }
    fn transfer_indexed_with_live_diagnostics(
        &mut self,events:usize,destinations:impl IntoIterator<Item=usize>,
        incoming:&mut [ChunkedParts],marks:&mut [ChunkedMarks],
        diagnostic:Option<&mut Vec<ChunkedDiagnosticSource>>,
    )->PyResult<()> {
        if self.incoming_cell_rows.is_none() {
            return self.transfer_indexed(events,destinations);
        }
        // Before projection these must match actual complete previous appends.
        self.observed_incoming_descriptor_bytes(incoming,marks)?;
        let before_events=self.events;
        let before_pages=self.incoming_live_pages;
        let before_direct_pages=self.incoming_direct_live_pages;
        // Source-only page header projection needs cell IDs, not wide
        // physical Part/Mark rows. The original cell registry is bounded
        // by the immutable native V03 source and every ID is checked below.
        let mut new_page_cells:Vec<u32>=Vec::new();
        self.project_transfer(events,destinations,Some(&mut new_page_cells))?;
        let mut old_physical_header_overlap=0usize;
        let mut diagnostic_reservation_peak_bytes=0usize;
        // These source-only diagnostic rows are alive throughout transfer,
        // even though each old source per-Part motion scan is already dead.
        // Reserve their actual destination capacities BEFORE new page/events
        // are appended. Old/new diagnostic backing overlap happens in this
        // same serial header-reservation phase, not the future raw page phase.
        if let Some(src) = diagnostic {
            if !src.is_empty() {
                let tracked=self.incoming_cell_rows.as_ref().ok_or_else(||
                    arithmetic("diagnostic source counts have no current registry"))?;
                if src.len()!=tracked.len() {
                    return Err(arithmetic("diagnostic source registry size differs"));
                }
                let mut diagnostic_live_bytes=src.iter()
                    .map(|v|v.capacity_bytes())
                    .sum::<usize>()
                    .saturating_add(src.capacity().saturating_mul(
                        std::mem::size_of::<ChunkedDiagnosticSource>()
                    ));
                diagnostic_reservation_peak_bytes=diagnostic_live_bytes;
                for (i,(existing,&projected)) in src.iter_mut().zip(tracked.iter()).enumerate(){
                    if existing.len()>projected || existing.len()!=incoming[i].len() {
                        return Err(arithmetic("diagnostic source row alignment differs"));
                    }
                    if projected>existing.capacity_rows(){
                        let previous_bytes=existing.capacity_bytes();
                        // Actual old Vec<Vec<_>> header, not the former
                        // large per-cell contiguous data backing, may overlap.
                        let previous_header_overlap=existing.reserve_source_rows(projected)?;
                        if existing.capacity_rows()<projected {
                            return Err(budget("diagnostic source page projection invalid"));
                        }
                        let new_bytes=existing.capacity_bytes();
                        diagnostic_live_bytes=diagnostic_live_bytes.saturating_add(
                            new_bytes.saturating_sub(previous_bytes)
                        );
                        diagnostic_reservation_peak_bytes=diagnostic_reservation_peak_bytes.max(
                            diagnostic_live_bytes.saturating_add(previous_header_overlap)
                        );
                    }
                }
                let independently_measured=src.iter()
                    .map(|v|v.capacity_bytes())
                    .sum::<usize>()
                    .saturating_add(src.capacity().saturating_mul(
                        std::mem::size_of::<ChunkedDiagnosticSource>()
                    ));
                if diagnostic_live_bytes!=independently_measured {
                    return Err(arithmetic("diagnostic source allocation census diverges"));
                }
                self.diagnostic_source_live_bytes=independently_measured;
            }
        }
        for &source_cell in &new_page_cells {
            let cell=source_cell as usize; // checked before physical reservation.
            let target=self.incoming_cell_rows.as_ref()
                .and_then(|v|v.get(cell)).ok_or_else(||
                    arithmetic("new source page destination outside registry"))?
                .div_ceil(INCOMING_PART_CHUNK);
            let p=incoming.get_mut(cell).ok_or_else(||
                arithmetic("missing Part page descriptor destination"))?;
            old_physical_header_overlap=old_physical_header_overlap
                .max(p.reserve_header_slots(target)?);
            if let Some(direct)=&self.incoming_direct_cell_rows {
                let spill=direct[cell].div_ceil(INCOMING_PART_CHUNK);
                old_physical_header_overlap=old_physical_header_overlap
                    .max(p.reserve_direct_header_slots(spill)?);
            }
            let m=marks.get_mut(cell).ok_or_else(||
                arithmetic("missing Mark page descriptor destination"))?;
            let old_cap=m.chunks.capacity();
            if target>old_cap {
                m.chunks.try_reserve_exact(target.saturating_sub(m.chunks.len()))
                    .map_err(|_|budget("native source Mark page header reservation unavailable"))?;
                if m.chunks.capacity()<target {
                    return Err(budget("native source Mark descriptor reservation capacity invalid"));
                }
                old_physical_header_overlap=old_physical_header_overlap.max(
                    old_cap.saturating_mul(std::mem::size_of::<Vec<Mark>>())
                );
            }
        }
        let actual_headers:usize=incoming.iter().zip(marks.iter()).map(|(p,m)|
            p.descriptor_capacity()
                .saturating_mul(std::mem::size_of::<Vec<Part>>())
                .saturating_add(m.chunks.capacity()
                    .saturating_mul(std::mem::size_of::<Vec<Mark>>()))
        ).sum();
        // Index list may itself be reallocated during the projection;
        // its old/new backing does not coexist with any header reservation.
        let extra=source_sequential_header_overlap_extra(
            diagnostic_reservation_peak_bytes,self.diagnostic_source_live_bytes,
            old_physical_header_overlap,
            new_page_cells.capacity().saturating_mul(2*std::mem::size_of::<u32>())
        );
        crate::v1_trace::add("road_work.sequential_source_diag_reallocation_peak",
                             diagnostic_reservation_peak_bytes as u64);
        crate::v1_trace::add("road_work.sequential_source_old_physical_header_peak",
                             old_physical_header_overlap as u64);
        self.incoming_descriptor_live_bytes=Some(actual_headers);
        // These are two sequential, non-overlapping allocator lifetimes:
        // (A) old physical Part/Mark pages + old EventRows, with the newly
        // reserved header Vec and its one old/new reallocation overlap;
        // (B) projected new Part/Mark and EventRows AFTER the call returns,
        // when the temporary source index Vec and old header have dropped.
        // They must be checked as max(A,B), not the fictitious sum A+B.
        let projected_events=self.events;
        let projected_pages=self.incoming_live_pages;
        let projected_direct_pages=self.incoming_direct_live_pages;
        self.events=before_events;
        self.incoming_live_pages=before_pages;
        self.incoming_direct_live_pages=before_direct_pages;
        let header_check=self.require_with_no_active_combine(
            extra,"transfer header reservation",None
        );
        self.events=projected_events;
        self.incoming_live_pages=projected_pages;
        self.incoming_direct_live_pages=projected_direct_pages;
        let status=if header_check.is_ok() {
            self.require_with_no_active_combine(0,"transfer candidates",None)
        } else { header_check };
        // Later physical append/packet operations again use mutable headers.
        self.incoming_descriptor_live_bytes=None;
        status
    }
    /// The raw Part/Mark page header Vecs are *momentarily* stable during
    /// packet remainder conversion, but remain appendable on the next
    /// pending source iteration. Verify exact current lengths and capacities
    /// before allowing the no-growth-time source bound.
    fn observed_incoming_descriptor_bytes(
        &self,parts:&[ChunkedParts],marks:&[ChunkedMarks],
    )->PyResult<usize> {
        let Some(tracked)=&self.incoming_cell_rows else {
            return Err(arithmetic("incoming source destination registry unavailable"));
        };
        if parts.len()!=tracked.len() || marks.len()!=tracked.len() {
            return Err(arithmetic("incoming Part Mark registry count mismatch"));
        }
        let mut rows=0usize;
        let mut pages=0usize;
        let mut direct_pages=0usize;
        let mut descriptors=0usize;
        for i in 0..tracked.len() {
            let (p,m)=(&parts[i],&marks[i]);
            if p.len()!=m.len() || p.len()!=tracked[i]
                || p.capacity()!=m.capacity()
                || p.capacity()!=p.len().div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK {
                return Err(arithmetic("incoming current Part Mark fixed-page counts differ"));
            }
            if p.event_backed!=self.incoming_direct_cell_rows.is_some() {
                return Err(arithmetic("incoming source representation differs from admitted owner"));
            }
            if let Some(direct)=&self.incoming_direct_cell_rows {
                if direct.len()!=tracked.len() || p.direct_len!=direct[i]
                    || p.direct_capacity()!=direct[i].div_ceil(INCOMING_PART_CHUNK)*INCOMING_PART_CHUNK {
                    return Err(arithmetic("incoming direct spill capacity differs from source projection"));
                }
                direct_pages=direct_pages.saturating_add(
                    p.direct_capacity()/INCOMING_PART_CHUNK);
            }
            rows=rows.saturating_add(p.len());
            pages=pages.saturating_add(p.capacity()/INCOMING_PART_CHUNK);
            descriptors=descriptors.saturating_add(
                p.descriptor_capacity().saturating_mul(std::mem::size_of::<Vec<Part>>())
                .saturating_add(m.chunks.capacity()
                    .saturating_mul(std::mem::size_of::<Vec<Mark>>()))
            );
        }
        if rows!=self.incoming || pages!=self.incoming_live_pages
            || direct_pages!=self.incoming_direct_live_pages {
            return Err(arithmetic("incoming live page census differs from source preflight"));
        }
        Ok(descriptors)
    }
    /// The pending remainder's CorePart conversion does not append new raw
    /// Part/Mark pages. Charge exactly their *current* real descriptor
    /// capacities for this one allocation, without freezing later pending
    /// appends. Always restore the growth-time envelope after the call,
    /// including if the original packet reservation fails.
    fn pack_parts_with_live_descriptors(
        &mut self,parts:Vec<Part>,
        incoming:&[ChunkedParts],marks:&[ChunkedMarks],
    )->PyResult<PacketParts> {
        if self.incoming_cell_rows.is_none() {
            return self.pack_parts(parts);
        }
        if self.incoming_descriptor_live_bytes.is_some() {
            return Err(arithmetic("pending descriptor preflight already frozen"));
        }
        let actual=self.observed_incoming_descriptor_bytes(incoming,marks)?;
        // No max-cell combine scratch exists during this source transfer
        // remainder pack. Its old reserve is future-only. Charge the exact
        // currently live original Part Vec along with the simultaneously
        // allocated CorePart buffer before allocating the latter.
        let source_part_bytes=parts.capacity().saturating_mul(std::mem::size_of::<Part>());
        self.incoming_descriptor_live_bytes=Some(actual);
        let result=PacketParts::pack(parts,|core_bytes| {
            self.require_with_no_active_combine(
                core_bytes,"packet interval packing",Some(source_part_bytes)
            )
        });
        // Critically, a transfer may append more raw source pages next.
        // Restore the growth-time envelope on both Ok and Err.
        self.incoming_descriptor_live_bytes=None;
        result
    }

    /// Source-phase boundary: every road-service and pending original raw
    /// destination Part+Mark append has finished, no further one can grow.
    /// Both real outer Vec<Vec<T>> capacities can now be read EXACTLY for
    /// later packet interval splitting and packing preflights.
    fn lock_completed_incoming_descriptors(
        &mut self,parts:&[ChunkedParts],marks:&[ChunkedMarks],
    )->PyResult<()> {
        let Some(tracked)=&self.incoming_cell_rows else {return Ok(())};
        if self.incoming_descriptor_live_bytes.is_some()
            || parts.len()!=tracked.len() || marks.len()!=tracked.len() {
            return Err(arithmetic("incoming descriptor fixed source registry differs"));
        }
        let descriptor_bytes=self.observed_incoming_descriptor_bytes(parts,marks)?;
        self.incoming_descriptor_live_bytes=Some(descriptor_bytes);
        crate::v1_trace::add("road_work.locked_descriptor_payload_bytes",descriptor_bytes as u64);
        Ok(())
    }
    fn interval(&mut self, transient: usize) -> PyResult<()> {
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
fn check_storage_limit(limit: Option<usize>, required: usize, phase: &str) -> PyResult<()> {
    if let Some(limit) = limit {
        if required > limit {
            return Err(budget(&format!(
                "native road storage budget exceeded: phase={phase}, required_bytes={required}, budget_bytes={limit}")));
        }
    }
    Ok(())
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
    /// Allocation-free conservative credit for Arc payloads guaranteed to be
    /// live in BOTH owners at corresponding packet slots.
    ///
    /// Matching pairs never reuse the same owner slot, so each Arc pair
    /// witnesses one duplicated payload even when several slots share an
    /// allocation internally.  It is a lower bound on redundant payload and
    /// never counts coincidentally equal Part values in distinct allocations.
    /// Exactly shared, IMMUTABLE packet payload allocations across two
    /// simultaneous original road states. Each ArcInner pointer of each
    /// distinct concrete layout is counted AT MOST ONCE, even when a given
    /// immutable keyset is referenced by thousands of independent packets.
    /// No equality of contents, tags, age or scalar moments creates credit.
    /// Only data payload Vec::capacity() bytes get credited, never metadata.
    pub(crate) fn paired_shared_payload_lower_bound(&self,other:&RoadState)->usize {
        fn each_backing(parts:&PacketParts,mut visit:impl FnMut(u8,usize,usize)){
            match parts {
                PacketParts::Uniform{rows,..}=>visit(
                    0,Arc::as_ptr(rows) as usize,
                    rows.capacity().saturating_mul(std::mem::size_of::<CorePart>())),
                PacketParts::Mixed(rows)=>visit(
                    1,Arc::as_ptr(rows) as usize,
                    rows.capacity().saturating_mul(std::mem::size_of::<Part>())),
                PacketParts::SharedKeys{keys,moments,..}=>{
                    visit(2,Arc::as_ptr(keys) as usize,
                          keys.capacity().saturating_mul(std::mem::size_of::<(u32,u32)>()));
                    visit(3,Arc::as_ptr(moments) as usize,
                          moments.capacity().saturating_mul(std::mem::size_of::<(f64,f64)>()));
                },
            }
        }
        let mut first=HashMap::<(u8,usize),usize>::new();
        for packet in self.cells.iter().flat_map(|c|&c.packets)
            .chain(self.pending.iter().flatten())
        {
            each_backing(&packet.parts,|kind,ptr,bytes|{
                first.entry((kind,ptr)).or_insert(bytes);
            });
        }
        let mut credited=0usize;
        for packet in other.cells.iter().flat_map(|c|&c.packets)
            .chain(other.pending.iter().flatten())
        {
            each_backing(&packet.parts,|kind,ptr,_|{
                if let Some(bytes)=first.remove(&(kind,ptr)){
                    credited=credited.saturating_add(bytes);
                }
            });
        }
        credited
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
    pub(crate) fn intern_exact_keysets(&mut self) -> PyResult<usize> {
        let mut groups:Vec<ExactKeyGroup>=Vec::new();
        let mut lookup:HashMap<(usize,u64),Vec<usize>>=HashMap::new();
        let mut assignments:Vec<Option<usize>>=Vec::new();
        let mut unique_old_backings:HashSet<(u8,usize)>=HashSet::new();
        // First pass is strictly read-only. Canonical keys are OWNED, not
        // borrowed from self, so the second mutation pass cannot invalidate
        // a representative or confuse Arc pointer identities.
        for packet in self.cells.iter().flat_map(|c|&c.packets)
            .chain(self.pending.iter().flatten()) {
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
            let id=if let Some(id)=found {id} else {
                let key=match &packet.parts {
                    PacketParts::Uniform{rows,..}=>{
                        let mut tmp=checkpoint_vec(rows.len())?;
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
        for packet in self.cells.iter_mut().flat_map(|c|&mut c.packets)
            .chain(self.pending.iter_mut().flatten()) {
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
    pub(crate) fn checkpoint_decode_envelope(&self) -> (usize, usize) {
        let stats = self.debug_stats();
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
#[pyclass]
pub struct V1Road {
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
    storage_budget: Option<usize>,
    retained_input_bytes: usize,
    service_event_accounting: Option<ServiceEventAccounting>,
    event_resolution: Mutex<EventResolutionStats>,
    event_budget: Option<usize>,
    intervals: bool,
    state: RoadState,
}
fn val(s: &str) -> PyErr {
    PyValueError::new_err(s.to_owned())
}
fn arithmetic(s: &str) -> PyErr {
    PyArithmeticError::new_err(s.to_owned())
}
fn budget(s: &str) -> PyErr {
    PyMemoryError::new_err(s.to_owned())
}
// Expansion summation, including the round-to-even correction used by math.fsum.
fn sum<I: IntoIterator<Item = f64>>(values: I) -> f64 {
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
/// Validator-local expansion sums retain exactly the original fsum insertion
/// order without first retaining every mass in an additional Vec. This budget
/// charges the actual accumulator capacities, including old/new overlap before
/// a partial buffer grows. No bound on the number of expansion components is
/// assumed, and the retained-owner fallback remains the original 3*max.
struct ValidationScratch {
    limit: Option<usize>,
    owner_bytes: usize,
    live_bytes: std::cell::Cell<usize>,
    peak_bytes: std::cell::Cell<usize>,
}
impl ValidationScratch {
    fn new(limit:Option<usize>,owner_bytes:usize,fixed_bytes:usize)->PyResult<Self> {
        let out=Self{limit,owner_bytes,live_bytes:std::cell::Cell::new(fixed_bytes),
            peak_bytes:std::cell::Cell::new(fixed_bytes)};
        out.require(0)?;
        Ok(out)
    }
    fn require(&self,extra:usize)->PyResult<()> {
        let scratch=self.live_bytes.get().saturating_add(extra);
        self.peak_bytes.set(self.peak_bytes.get().max(scratch));
        check_storage_limit(self.limit,self.owner_bytes.saturating_add(scratch),
            "state validation workspace")
    }
    fn replace_buffer(&self,old_capacity:usize,new_capacity:usize) {
        self.live_bytes.set(self.live_bytes.get()
            .saturating_sub(old_capacity.saturating_mul(8))
            .saturating_add(new_capacity.saturating_mul(8)));
    }
}
struct ValidationSum<'a> {
    partials:Vec<f64>,
    work:&'a ValidationScratch,
}
impl<'a> ValidationSum<'a> {
    fn new(work:&'a ValidationScratch)->Self {Self{partials:Vec::new(),work}}
    fn push(&mut self,mut x:f64)->PyResult<()> {
        let p=&mut self.partials;
        let mut i=0;
        for j in 0..p.len() {
            let mut y=p[j];
            if x.abs()<y.abs() {std::mem::swap(&mut x,&mut y);}
            let hi=x+y;
            let lo=y-(hi-x);
            if lo!=0.0 {p[i]=lo;i+=1;}
            x=hi;
        }
        p.truncate(i);
        if x!=0.0 {
            if p.len()==p.capacity() {
                let wanted=p.capacity().saturating_mul(2).max(4);
                // The old allocation is still live while the new buffer is
                // reserved. Reserve the full new capacity, not merely delta.
                self.work.require(wanted.saturating_mul(8).saturating_add(32))?;
                let mut next=checkpoint_vec(wanted)?;
                // Vec capacity is observable. Charge allocator-provided extra
                // capacity before retaining it; opaque allocator metadata is
                // outside structural accounting and under the process limit.
                self.work.require(next.capacity().saturating_mul(8).saturating_add(32))?;
                next.extend_from_slice(p);
                self.work.replace_buffer(p.capacity(),next.capacity());
                *p=next;
            }
            p.push(x);
        }
        Ok(())
    }
    fn finish(mut self)->f64 {
        let p=&mut self.partials;
        let mut hi=0.0;
        let mut lo=0.0;
        if let Some(x)=p.pop() {
            hi=x;
            while let Some(x)=p.pop() {
                let y=hi;
                hi=y+x;
                lo=x-(hi-y);
                if lo!=0.0 {break;}
            }
            if !p.is_empty() && ((lo<0.0 && p[p.len()-1]<0.0)
                || (lo>0.0 && p[p.len()-1]>0.0)) {
                let y=lo*2.0;
                let x=hi+y;
                if y==x-hi {hi=x;}
            }
        }
        hi
    }
}
impl Drop for ValidationSum<'_> {
    fn drop(&mut self) {self.work.replace_buffer(self.partials.capacity(),0);}
}
fn validation_sum(values:impl IntoIterator<Item=f64>,work:&ValidationScratch)->PyResult<f64> {
    let mut value=ValidationSum::new(work);
    for x in values {value.push(x)?;}
    Ok(value.finish())
}

fn finite_nonnegative(x: f64) -> bool {
    x.is_finite() && x >= 0.0
}
fn mass(p: &Packet) -> f64 {
    sum(p.parts.iter().map(|p| p.mass))
}
fn push_checked<T>(rows: &mut Vec<T>, row: T) -> PyResult<()> {
    if rows.len() == rows.capacity() {
        rows.try_reserve(1)
            .map_err(|_| budget("native road allocation unavailable"))?;
    }
    rows.push(row);
    Ok(())
}
fn clone_packet(packet: &Packet) -> PyResult<Packet> {
    Ok(Packet {
        target: packet.target,
        parts: packet.parts.clone_checked()?,
    })
}
fn clone_packets(packets: &[Packet]) -> PyResult<Vec<Packet>> {
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
fn portion(parts: &PacketParts, f: f64) -> PyResult<Vec<Part>> {
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
    fn new(universe: usize) -> PyResult<Self> {
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
fn count_sweep_row_kinds(parts: &[Part]) -> PyResult<(usize, usize)> {
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
    let index=std::mem::size_of::<u32>();
    // All f64 endpoint words remain borrowed from the unchanged physical
    // Part source. Store ONLY each source row's checked u32 index. Point
    // current_points retains its original full usize downstream ABI.
    nonpoint.saturating_mul(2 * index)
        .saturating_add(point.saturating_mul(index+std::mem::size_of::<usize>()))
        .saturating_add(
            n.div_ceil(64).saturating_add(n.div_ceil(4096))
                .saturating_mul(std::mem::size_of::<u64>()),
        )
        .saturating_add(256)
}

/// Check the *actual original Part row index* before narrowing, rather than
/// silently losing upper bits on a large source. All physical tag/offset and
/// two IEEE endpoint words remain in the unchanged source Part.
fn sweep_index_from_usize(i:usize)->PyResult<u32> {
    u32::try_from(i).map_err(|_|
        budget("sweep source Part row index exceeds u32")
    )
}

struct IntervalActiveSweep<'a> {
    parts: &'a [Part],
    starts: Vec<u32>,
    ends: Vec<u32>,
    points: Vec<u32>,
    active: ActiveIndexBits,
    current_points: Vec<usize>,
    next_start: usize,
    next_end: usize,
    next_point: usize,
}

impl<'a> IntervalActiveSweep<'a> {
    #[cfg(test)]
    fn new(parts: &'a [Part]) -> PyResult<Self> {
        let (nonpoint, point) = count_sweep_row_kinds(parts)?;
        Self::new_counted(parts, nonpoint, point)
    }

    fn new_counted(parts: &'a [Part], nonpoint: usize, point: usize) -> PyResult<Self> {
        debug_assert_eq!(nonpoint.checked_add(point), Some(parts.len()));
        // len <= u32::MAX also bounds every valid [0,len) row index.
        // This check is BEFORE any fallible full-source sweep allocation.
        sweep_index_from_usize(parts.len())?;
        let mut starts = checkpoint_vec(nonpoint)?;
        let mut ends = checkpoint_vec(nonpoint)?;
        let mut points = checkpoint_vec(point)?;
        for (i, p) in parts.iter().enumerate() {
            let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
            let index = i as u32; // proven valid by whole source length above.
            if pa == pb {
                points.push(index);
            } else if pb > pa {
                starts.push(index);
                ends.push(index);
            } else {
                return Err(val("invalid finite native interval during sweep"));
            }
        }
        // Read original IEEE f64 endpoints from the actual source on demand.
        // total_cmp distinguishes +/-zero and index secondary tie order is
        // bit-identical to the previous stored (f64, usize) descriptor.
        starts.sort_unstable_by(|&i,&j|{
            parts[i as usize].a.unwrap()
                .total_cmp(&parts[j as usize].a.unwrap()).then(i.cmp(&j))
        });
        ends.sort_unstable_by(|&i,&j|{
            parts[i as usize].b.unwrap()
                .total_cmp(&parts[j as usize].b.unwrap()).then(i.cmp(&j))
        });
        points.sort_unstable_by(|&i,&j|{
            parts[i as usize].a.unwrap()
                .total_cmp(&parts[j as usize].a.unwrap()).then(i.cmp(&j))
        });
        Ok(Self {
            parts,starts,ends,points,
            active: ActiveIndexBits::new(parts.len())?,
            // Exact bounded capacity, no Vec-doubling after the work guard.
            current_points: checkpoint_vec(point)?,
            next_start: 0, next_end: 0, next_point: 0,
        })
    }

    fn advance(&mut self, a: f64) {
        // Ended intervals must retire before newly started intervals enter.
        while self.next_end < self.ends.len()
            && self.parts[self.ends[self.next_end] as usize].b.unwrap()<=a {
            let source_index=self.ends[self.next_end] as usize;
            self.active.remove(&source_index);
            self.next_end+=1;
        }
        while self.next_start < self.starts.len()
            && self.parts[self.starts[self.next_start] as usize].a.unwrap()<=a {
            self.active.insert(self.starts[self.next_start] as usize);
            self.next_start+=1;
        }
        self.current_points.clear();
        while self.next_point < self.points.len()
            && self.parts[self.points[self.next_point] as usize].a.unwrap()<=a {
            let i=self.points[self.next_point] as usize;
            let time=self.parts[i].a.unwrap();
            if time==a {
                self.current_points.push(i);
            }
            self.next_point+=1;
        }
        // Sorting the source indices is mandatory when the edge set collapses
        // two signed-zero endpoint groups into one numeric edge.
        self.current_points.sort_unstable();
    }
}

/// Iterate unique numeric endpoint classes of three already sorted event
/// streams. Exactly the original sort_unstable(total_cmp)+dedup(PartialEq)
/// order: the zero representative must use -0 when any original endpoint
/// has the negative-zero sign bit, including a point with a=+0,b=-0.
fn visit_unique_sweep_edges(
    sweep: &IntervalActiveSweep<'_>,
    has_negative_zero: bool,
    mut emit: impl FnMut(f64) -> PyResult<()>,
) -> PyResult<usize> {
    let streams = [
        sweep.starts.as_slice(),
        sweep.ends.as_slice(),
        sweep.points.as_slice(),
    ];
    // Exact source endpoint accessor; no temporary full f64 timestamp array.
    let clock_of=|kind:usize,index:u32|->f64 {
        let source=&sweep.parts[index as usize];
        match kind {
            0 => source.a.unwrap(),
            1 => source.b.unwrap(),
            _ => source.a.unwrap(),
        }
    };
    let mut offsets = [0usize; 3];
    let mut count=0usize;
    loop {
        let mut next: Option<f64> = None;
        for j in 0..3 {
            if let Some(&source_index)=streams[j].get(offsets[j]) {
                let value=clock_of(j,source_index);
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
                .is_some_and(|&i| clock_of(j,i)==time) {
                offsets[j]+=1;
            }
        }
    }
    Ok(count)
}

fn unique_sweep_edges(
    parts: &[Part],
    sweep: &IntervalActiveSweep<'_>,
    before_allocate: impl FnOnce(usize) -> PyResult<()>,
) -> PyResult<Vec<f64>> {
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
/// Only diagnostic source-lineage keys, never actual physical Part rows.
/// On this fixed 64-bit original runtime the old (usize,usize,u64) was 24B.
/// The bounded V03 road/cell registry and original head index must both be
/// provably below u32::MAX (which is reserved for pending-only provenance).
/// This injective key map preserves bitwise rate identity and BTreeSet order.
type CompactDiagnosticSource=(u32,u32,u64);
/// Trace-only lineage owner, physically separate from all FIFO Part/Mark,
/// EventRow and checkpoint buffers. Fixed-size pages prevent huge contiguous
/// Vec::try_reserve reallocations of millions of per-cell source identifiers.
/// Original rate-bit identity and per-cell insertion order remain unchanged.
const DIAGNOSTIC_SOURCE_CHUNK:usize=1024;
#[derive(Default)]
struct ChunkedDiagnosticSource {
    chunks:Vec<Vec<CompactDiagnosticSource>>,
    len:usize,
    /// Exact observed per-page Vec::capacity bytes, maintained incrementally.
    /// Avoid an O(total historical pages) rescan for each source head update.
    payload_allocated_bytes:usize,
}
impl ChunkedDiagnosticSource {
    fn len(&self)->usize {self.len}
    fn capacity_rows(&self)->usize {
        self.chunks.len().saturating_mul(DIAGNOSTIC_SOURCE_CHUNK)
    }
    fn capacity_bytes(&self)->usize {
        self.chunks.capacity().saturating_mul(
            std::mem::size_of::<Vec<CompactDiagnosticSource>>()
        ).saturating_add(self.payload_allocated_bytes)
    }
    /// One independent end-of-source physical capacity audit. Do not repeat
    /// this O(number of pages) computation inside every transfer head.
    fn verify_capacity_bytes(&self)->PyResult<()> {
        let actual=self.chunks.iter().map(|p|
            p.capacity().saturating_mul(std::mem::size_of::<CompactDiagnosticSource>())
        ).sum::<usize>();
        if self.payload_allocated_bytes!=actual {
            Err(arithmetic("paged diagnostic source tracked payload diverges"))
        } else {Ok(())}
    }
    /// Return old page-registry backing that may coexist with the new one
    /// during exactly ONE sequential reservation. Each original diagnostic
    /// data page is pre-reserved with fixed length, never grown in place.
    fn reserve_source_rows(&mut self,target:usize)->PyResult<usize>{
        let required=target.div_ceil(DIAGNOSTIC_SOURCE_CHUNK);
        let mut overlap=0usize;
        if required>self.chunks.capacity() {
            overlap=self.chunks.capacity().saturating_mul(
                std::mem::size_of::<Vec<CompactDiagnosticSource>>()
            );
            self.chunks.try_reserve_exact(required.saturating_sub(self.chunks.len()))
                .map_err(|_|budget("diagnostic source page header reserve unavailable"))?;
            if self.chunks.capacity()<required {
                return Err(budget("diagnostic source header allocator capacity inconsistent"));
            }
        }
        while self.chunks.len()<required {
            let mut page=Vec::new();
            page.try_reserve_exact(DIAGNOSTIC_SOURCE_CHUNK)
                .map_err(|_|budget("diagnostic source page payload reserve unavailable"))?;
            if page.capacity()<DIAGNOSTIC_SOURCE_CHUNK {
                return Err(budget("diagnostic source page allocator capacity inconsistent"));
            }
            let allocated=page.capacity().saturating_mul(
                std::mem::size_of::<CompactDiagnosticSource>()
            );
            self.chunks.push(page);
            self.payload_allocated_bytes=self.payload_allocated_bytes.saturating_add(allocated);
        }
        Ok(overlap)
    }
    fn push(&mut self,row:CompactDiagnosticSource)->PyResult<()> {
        if self.len>=self.capacity_rows() {
            self.reserve_source_rows(self.len.saturating_add(1))?;
        }
        let idx=self.len/DIAGNOSTIC_SOURCE_CHUNK;
        let offset=self.len%DIAGNOSTIC_SOURCE_CHUNK;
        let page=self.chunks.get_mut(idx)
            .ok_or_else(||arithmetic("diagnostic source missing fixed page"))?;
        if page.len()!=offset {
            return Err(arithmetic("diagnostic source page alignment differs"));
        }
        page.push(row);
        self.len=self.len.saturating_add(1);
        Ok(())
    }
    fn extend(&mut self,items:impl IntoIterator<Item=CompactDiagnosticSource>)->PyResult<()>{
        for item in items {self.push(item)?;}
        Ok(())
    }
    fn iter(&self)->impl Iterator<Item=&CompactDiagnosticSource> {
        self.chunks.iter().flat_map(|c|c.iter())
    }
}
fn compact_diagnostic_source_id(
    cell:usize,head:usize,rate_bits:u64,
)->PyResult<CompactDiagnosticSource>{
    let cell=u32::try_from(cell).map_err(|_|
        budget("diagnostic original source cell index exceeds u32"))?;
    if cell==u32::MAX {
        return Err(budget("diagnostic original cell collides with pending sentinel"));
    }
    let head=u32::try_from(head).map_err(|_|
        budget("diagnostic original source head index exceeds u32"))?;
    Ok((cell,head,rate_bits))
}
fn pending_diagnostic_source_id(head:usize)->PyResult<CompactDiagnosticSource>{
    let head=u32::try_from(head).map_err(|_|
        budget("pending diagnostic source index exceeds u32"))?;
    Ok((u32::MAX,head,0))
}

/// Diagnostic: group one cell's incoming rows by non-point interval (a,b) and
/// count maximal runs of time-contiguous intervals whose contributing source
/// set {(cell, head position, rate bits)} is identical. Such runs have
/// proportional route mixtures and equal ready time, so they are exactly
/// mergeable in real arithmetic. Counting only.
fn exact_merge_census(parts: impl Iterator<Item=Part>, src: impl Iterator<Item=CompactDiagnosticSource>) {
    use std::collections::BTreeSet;
    let mut by: BTreeMap<(u64, u64), BTreeSet<CompactDiagnosticSource>> = BTreeMap::new();
    let mut points = 0u64;
    for (p, s) in parts.zip(src) {
        let (a, b) = (p.a.unwrap_or(f64::NAN), p.b.unwrap_or(f64::NAN));
        if !(b > a) {
            points += 1;
            continue;
        }
        by.entry((a.to_bits(), b.to_bits())).or_default().insert(s);
    }
    let mut runs = 0u64;
    let mut prev: Option<(f64, &BTreeSet<CompactDiagnosticSource>)> = None;
    let mut ordered: Vec<(f64, f64, &BTreeSet<CompactDiagnosticSource>)> = by
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

/// A serviced Part reuses the already-stored event's tag, mass, birth and
/// interval endpoints. Offset is independent and copied exactly. Pending
/// rows use the reserved event code and index a separately stored full Part.
#[derive(Clone,Copy)]
struct IncomingRowRef {
    event:u32,
    offset_or_direct:u32,
}
fn reserve_part_page_headers<T>(headers:&mut Vec<Vec<T>>,pages:usize)->PyResult<usize> {
    if pages<=headers.capacity() {return Ok(0);}
    let old=headers.capacity().saturating_mul(std::mem::size_of::<Vec<T>>());
    headers.try_reserve_exact(pages.saturating_sub(headers.len()))
        .map_err(|_|budget("native incoming page header reservation unavailable"))?;
    if headers.capacity()<pages {
        return Err(budget("native incoming page descriptor capacity invalid"));
    }
    Ok(old)
}
/// Original order is retained in every mode. Capped, representable interval
/// service rows use event references; pending/direct rows keep their original
/// compact Part payload in a separately charged spill. Noninterval, wide and
/// uncapped paths retain the original direct representation.
const INCOMING_PART_CHUNK:usize=128;
#[derive(Default)]
struct ChunkedParts {
    chunks:Vec<Vec<Part>>,
    compact_chunks:Vec<Vec<CompactIncomingPart>>,
    compressed:bool,
    len:usize,
    event_refs:Vec<Vec<IncomingRowRef>>,
    event_backed:bool,
    direct_len:usize,
    event_source:Option<Weak<()>>,
}
impl ChunkedParts {
    fn new(compressed:bool)->Self {Self{compressed,..Self::default()}}
    fn event_backed()->Self {Self{compressed:true,event_backed:true,..Self::default()}}
    fn len(&self)->usize {self.len}
    fn is_empty(&self)->bool {self.len==0}
    fn capacity(&self)->usize {
        if self.event_backed {self.event_refs.iter().map(Vec::capacity).sum()}
        else if self.compressed {self.compact_chunks.iter().map(Vec::capacity).sum()}
        else {self.chunks.iter().map(Vec::capacity).sum()}
    }
    fn direct_capacity(&self)->usize {
        if self.event_backed {self.compact_chunks.iter().map(Vec::capacity).sum()}else{0}
    }
    fn descriptor_capacity(&self)->usize {
        if self.event_backed {
            self.event_refs.capacity().saturating_add(self.compact_chunks.capacity())
        }else if self.compressed {self.compact_chunks.capacity()}else{self.chunks.capacity()}
    }
    fn reserve_header_slots(&mut self,pages:usize)->PyResult<usize> {
        if self.event_backed {reserve_part_page_headers(&mut self.event_refs,pages)}
        else if self.compressed {reserve_part_page_headers(&mut self.compact_chunks,pages)}
        else {reserve_part_page_headers(&mut self.chunks,pages)}
    }
    fn reserve_direct_header_slots(&mut self,pages:usize)->PyResult<usize> {
        if !self.event_backed {
            if pages!=0 {return Err(arithmetic("direct spill projected for non-reference owner"));}
            return Ok(0);
        }
        reserve_part_page_headers(&mut self.compact_chunks,pages)
    }
    fn physical_capacity_bytes(&self)->usize {
        if self.event_backed {
            self.capacity().saturating_mul(std::mem::size_of::<IncomingRowRef>())
                .saturating_add(self.direct_capacity()
                    .saturating_mul(std::mem::size_of::<CompactIncomingPart>()))
        }else{
            self.capacity().saturating_mul(if self.compressed {
                std::mem::size_of::<CompactIncomingPart>()
            }else{std::mem::size_of::<Part>()})
        }
    }
    fn iter(&self)->impl Iterator<Item=Part>+'_ {
        assert!(!self.event_backed,"event-backed incoming requires its source view");
        self.chunks.iter().flat_map(|c|c.iter().copied())
            .chain(self.compact_chunks.iter().flat_map(|c|c.iter().copied().map(CompactIncomingPart::unpack)))
    }
    fn get(&self,i:usize)->Part {
        assert!(!self.event_backed,"event-backed incoming requires its source view");
        if self.compressed {
            self.compact_chunks[i/INCOMING_PART_CHUNK][i%INCOMING_PART_CHUNK].unpack()
        }else{
            self.chunks[i/INCOMING_PART_CHUNK][i%INCOMING_PART_CHUNK]
        }
    }
    /// The returned view borrows both owners. Weak only verifies identity;
    /// it is this borrow that prevents event data from expiring during reads.
    fn view<'a>(&'a self,events:&'a ChunkedEvents)->PyResult<IncomingPartView<'a>> {
        if let Some(source)=&self.event_source {
            if !Weak::ptr_eq(source,&Arc::downgrade(&events.source_token)) {
                return Err(arithmetic("incoming event reference belongs to a different source store"));
            }
        }
        Ok(IncomingPartView{parts:self,events:Some(events)})
    }
    fn push_reference(&mut self,row:IncomingRowRef)->PyResult<()> {
        if self.event_refs.last().is_none_or(|c|c.len()==INCOMING_PART_CHUNK) {
            let page=checkpoint_vec(INCOMING_PART_CHUNK)?;
            if page.capacity()!=INCOMING_PART_CHUNK {
                return Err(budget("incoming reference fixed page capacity differs"));
            }
            push_checked(&mut self.event_refs,page)?;
        }
        self.event_refs.last_mut().expect("reference page allocated").push(row);
        self.len+=1;
        Ok(())
    }
    fn push_serviced(&mut self,event_index:usize,p:Part,events:&ChunkedEvents)->PyResult<()> {
        if !self.event_backed {return self.push_checked(p);}
        let event=u32::try_from(event_index).ok().filter(|&i|i!=u32::MAX)
            .ok_or_else(||arithmetic("incoming event index outside checked reference domain"))?;
        let offset=u32::try_from(p.offset)
            .map_err(|_|arithmetic("incoming source offset outside checked reference domain"))?;
        let e=events.get_checked(event_index)
            .ok_or_else(||arithmetic("incoming event index is not an appended source row"))?;
        if e.0!=p.tag || e.2.is_none()
            || e.3.to_bits()!=p.mass.to_bits() || e.6.to_bits()!=p.birth.to_bits()
            || !e.4.is_finite() || !e.5.is_finite()
            || p.a.0!=e.4.to_bits() || p.b.0!=e.5.to_bits() {
            return Err(arithmetic("incoming reference does not preserve original Part bits"));
        }
        if let Some(source)=&self.event_source {
            if source.as_ptr()!=Arc::as_ptr(&events.source_token) {
                return Err(arithmetic("incoming reference source store changed"));
            }
        }else{
            self.event_source=Some(Arc::downgrade(&events.source_token));
        }
        self.push_reference(IncomingRowRef{event,offset_or_direct:offset})
    }
    fn push_checked(&mut self,p:Part)->PyResult<()> {
        if self.compressed {
            let encoded=CompactIncomingPart::try_new(p).ok_or_else(||
                arithmetic("compact incoming source index contract differs"))?;
            let direct=if self.event_backed {
                Some(u32::try_from(self.direct_len).ok().filter(|&i|i!=u32::MAX)
                    .ok_or_else(||arithmetic("pending direct reference index overflow"))?)
            }else{None};
            if self.compact_chunks.last().is_none_or(|c|c.len()==INCOMING_PART_CHUNK) {
                let page=checkpoint_vec(INCOMING_PART_CHUNK)?;
                if page.capacity()!=INCOMING_PART_CHUNK {
                    return Err(budget("compact incoming fixed page capacity differs"));
                }
                push_checked(&mut self.compact_chunks,page)?;
            }
            self.compact_chunks.last_mut().expect("compact incoming page allocated").push(encoded);
            if let Some(index)=direct {
                self.direct_len+=1;
                return self.push_reference(IncomingRowRef{
                    event:u32::MAX,offset_or_direct:index,
                });
            }
        }else{
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
    fn extend_parts(&mut self,parts:impl IntoIterator<Item=Part>)->PyResult<()> {
        for p in parts {self.push_checked(p)?;}
        Ok(())
    }
}
#[derive(Clone,Copy)]
struct IncomingPartView<'a> {
    parts:&'a ChunkedParts,
    events:Option<&'a ChunkedEvents>,
}
impl<'a> IncomingPartView<'a> {
    fn len(self)->usize {self.parts.len()}
    fn get(self,i:usize)->Part {
        if !self.parts.event_backed {return self.parts.get(i);}
        let row=self.parts.event_refs[i/INCOMING_PART_CHUNK][i%INCOMING_PART_CHUNK];
        if row.event==u32::MAX {
            let direct=row.offset_or_direct as usize;
            return self.parts.compact_chunks[direct/INCOMING_PART_CHUNK]
                [direct%INCOMING_PART_CHUNK].unpack();
        }
        let e=self.events.expect("reference view owns event borrow")
            .get_checked(row.event as usize).expect("validated appended event reference");
        Part{tag:e.0,offset:row.offset_or_direct as usize,mass:e.3,birth:e.6,
            a:PackedTime(e.4.to_bits()),b:PackedTime(e.5.to_bits())}
    }
    fn iter(self)->impl Iterator<Item=Part>+'a {
        (0..self.len()).map(move|i|self.get(i))
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
    fn push_checked(&mut self, mark: Mark) -> PyResult<()> {
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

/// All primary rows retain their original append order and one Mark. A
/// pending row additionally owns a full compact Part in the direct spill.
/// Every capacity is a separately projected exact 128-row allocation.
fn event_backed_incoming_page_charge(
    cells:usize,primary_pages:usize,direct_pages:usize,actual_headers:Option<usize>,
)->usize {
    let primary=primary_pages.saturating_mul(INCOMING_PART_CHUNK)
        .saturating_mul(std::mem::size_of::<IncomingRowRef>()+std::mem::size_of::<Mark>());
    let spill=direct_pages.saturating_mul(INCOMING_PART_CHUNK)
        .saturating_mul(std::mem::size_of::<CompactIncomingPart>());
    let counters=cells.saturating_mul(2*std::mem::size_of::<usize>())
        .saturating_add(2*128);
    let all_pages=primary_pages.saturating_mul(2).saturating_add(direct_pages);
    let descriptors=actual_headers.unwrap_or_else(||all_pages.saturating_mul(
        2*std::mem::size_of::<Vec<Part>>()
    ));
    // Every primary/Mark/spill page keeps its allocation padding too.
    primary.saturating_add(spill).saturating_add(counters)
        .saturating_add(descriptors).saturating_add(all_pages.saturating_mul(128))
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
)->PyResult<usize> {
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

/// The original combine key, source-index tie order and sum() operations
/// evaluated against stable page indices without flattening the source.
fn combine_chunked_parts(parts: &ChunkedParts) -> PyResult<Vec<Part>> {
    if parts.event_backed {
        return Err(arithmetic("event-backed combination requires source event view"));
    }
    combine_incoming_view(IncomingPartView{parts,events:None})
}
fn combine_incoming_view(parts:IncomingPartView<'_>)->PyResult<Vec<Part>> {
    let key = |p: &Part| {
        (p.tag, p.offset, p.a.map_or(u64::MAX, f64::to_bits),
         p.b.map_or(u64::MAX, f64::to_bits))
    };
    let mut indices=checkpoint_vec(parts.len())?;
    indices.extend((0..parts.len()).filter(|&i|parts.get(i).mass > 0.0));
    indices.sort_unstable_by(|&a,&b| {
        key(&parts.get(a)).cmp(&key(&parts.get(b))).then(a.cmp(&b))
    });
    let groups = usize::from(!indices.is_empty())
        + indices.windows(2)
            .filter(|p|key(&parts.get(p[0])) != key(&parts.get(p[1])))
            .count();
    let mut out=checkpoint_vec(groups)?;
    let mut start=0;
    while start < indices.len() {
        let mut end=start+1;
        while end < indices.len()
            && key(&parts.get(indices[start]))==key(&parts.get(indices[end])) {
            end+=1;
        }
        let mut item=parts.get(indices[start]);
        item.mass=sum(indices[start..end].iter().map(|&i|parts.get(i).mass));
        item.birth=sum(indices[start..end].iter().map(|&i|parts.get(i).birth));
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

fn combine(parts: Vec<Part>) -> PyResult<Vec<Part>> {
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
) -> PyResult<Vec<T>> {
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
) -> PyResult<Vec<Part>> {
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
) -> PyResult<Vec<CorePart>> {
    combine_interval_mapped(parts, selected, selected_count, a, b, compact_core_part)
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
fn combine_uniform_point_core(parts: &[Part], source_indices: &[usize]) -> PyResult<Vec<CorePart>> {
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
    fn passage(&self, d: f64) -> PyResult<f64> {
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
    pub(crate) fn owned_storage_bytes(&self) -> usize {
        self.state.retained_storage_bytes()
    }
    /// Constructor-only identity finalization after retained accounting. The
    /// engine remeasures this String's capacity after binding its final policy.
    pub(crate) fn bind_storage_identity(&mut self, identity: String) -> PyResult<()> {
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
    pub(crate) fn write_state<W: Write>(&self, w: &mut W) -> PyResult<()> {
        write_len(w, self.identity.len())?;
        w.write_all(self.identity.as_bytes())
            .map_err(|e| PyIOError::new_err(e.to_string()))?;
        let s = &self.state;
        write_f64(w, s.t)?;
        write_len(w, s.cells.len())?;
        for c in &s.cells {
            for &v in &c.v {
                write_f64(w, v)?;
            }
            self.write_packets(w, &c.packets)?;
            write_len(w, c.latent.len())?;
            for (&k, &v) in &c.latent {
                write_len(w, k)?;
                write_f64(w, v)?;
            }
        }
        write_len(w, s.pending.len())?;
        for q in &s.pending {
            self.write_packets(w, q)?;
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
    fn write_packets<W: Write>(&self, w: &mut W, q: &[Packet]) -> PyResult<()> {
        write_len(w, q.len())?;
        for p in q {
            write_f64(w, p.target)?;
            write_len(w, p.parts.len())?;
            for p in &p.parts {
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
            }
        }
        Ok(())
    }
    fn read_packets<R: Read>(
        &self,
        r: &mut R,
        remaining: &mut usize,
        work: &mut RoadDecodeBudget,
    ) -> PyResult<Vec<Packet>> {
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
            work.reserve(
                m.saturating_mul(std::mem::size_of::<Part>()),
                m.saturating_mul(16),
            )?;
            let mut parts = checkpoint_vec(m)?;
            for _ in 0..m {
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
                parts.push(Part {
                    tag,
                    offset,
                    mass,
                    birth,
                    a: PackedTime::new(interval[0])?,
                    b: PackedTime::new(interval[1])?,
                });
            }
            q.push(Packet {
                target,
                parts: work.pack_parts(parts)?,
            });
        }
        Ok(q)
    }
    pub(crate) fn read_state<R: Read>(&self, r: &mut R) -> PyResult<RoadState> {
        read_exact_len(r, self.identity.len())?;
        let mut identity = vec![0; self.identity.len()];
        r.read_exact(&mut identity)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;
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
            validation: 0,
        };
        // Include empty tree roots and both packet-queue buffer allowances for
        // every cell, before constructing the first outer vector.
        work.reserve(
            self.groups
                .len()
                .saturating_mul(std::mem::size_of::<Cell>() + 256 + 2 * 32),
            self.groups.len().saturating_mul(32),
        )?;
        let mut cells = checkpoint_vec(self.groups.len())?;
        for _ in &self.groups {
            let mut v = [0.; 8];
            for x in &mut v {
                *x = read_f64(r)?;
            }
            let packets = self.read_packets(r, &mut remaining, &mut work)?;
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
        let mut pending = checkpoint_vec(self.groups.len())?;
        for _ in &self.groups {
            pending.push(self.read_packets(r, &mut remaining, &mut work)?);
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
        let mut ledger = checkpoint_vec(self.classes.len())?;
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
        self.check_state(&state)?;
        // State restoration is a strict source-bound, post-decode lifetime.
        // Exact ordered-keyset interning replaces independent full CorePart
        // payloads with actually shared immutable key arrays only in capped
        // native runs. Reconstructed Part values and wire stay identical.
        if self.storage_budget.is_some() {
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
    pub(crate) fn owned_time(&self) -> f64 {
        self.state.t
    }
    /// Future self.capture() clones the current immutable PacketParts Arc
    /// backings rather than physically re-allocating those row payloads.
    /// Use ACTUAL live immutable allocation identities only. This is the
    /// deduplicated unique data payload, not a bound on shell clones or RSS.
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
    pub(crate) fn set_phase_storage_budget(&mut self, bytes: usize) -> PyResult<()> {
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
        original_input_road_shared: Option<(f64,usize)>,
    ) {
        self.service_event_accounting = self.storage_budget.map(|_| ServiceEventAccounting {
            input_bytes,
            current_bytes: input_bytes,
            shared_input_current,
            max_tag_bytes,
            original_input_road_shared,
        });
    }
    /// The engine calls this only after restoring the exact original
    /// NativeWholeState source, which clones the immutable Arc backings.
    pub(crate) fn committed_input_source_arc_credit(&self,source:&RoadState)->usize {
        self.state.paired_shared_payload_lower_bound(source)
    }
    /// During the same joint road-step call, service finish and journey
    /// finish hold the same 3 road-state owners as postroad flat EventRows.
    /// Reuse their actual Arc pointer-backed source identity (not equality).
    pub(crate) fn source_joint_road_owner_charge(
        &self,candidate:&RoadState,supplied_retained:usize,
        original_source_verified:Option<(f64,usize)>,
    )->(usize,usize,usize) {
        source_road_service_joint_live_owner_charge(
            &self.state,candidate,supplied_retained,original_source_verified)
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
    fn can_narrow_candidate_events(&self)->bool {
        self.can_compact_candidate_events()
            && self.groups.len()<=u16::MAX as usize
    }
    fn can_reference_incoming_events(&self)->bool {
        self.intervals && self.can_compact_incoming_parts()
            && self.can_compact_candidate_events()
            && self.checkpoint_event_limit()<u32::MAX as usize
    }
    pub(crate) fn can_compact_candidate_events(&self)->bool {
        // All route tags and source/destination cell indices derive from
        // these configured registries. Reserve u32::MAX for dest=None.
        self.storage_budget.is_some()
            && self.routes.len() < u32::MAX as usize
            && self.groups.len() < u32::MAX as usize
    }
    fn work_budget(&self, state: &RoadState, offers: &[Offer]) -> PyResult<RoadWorkBudget> {
        if self.storage_budget.is_none() {
            return Ok(RoadWorkBudget {
                limit: None,
                base: 0,
                transfer_exclusive_cell_scratch:0,
                row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
                events: 0,
                incoming: 0,
                incoming_page_cells: self.groups.len(),
                incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
                compact_events: self.can_compact_candidate_events(),
            narrow_events:self.can_narrow_candidate_events(),
                compact_incoming: self.can_compact_incoming_parts(),
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
        // A self comparison cannot establish sharing with the original
        // caller snapshot after an earlier tick committed. The whole engine
        // records the real restore-time source/committed Arc intersection;
        // its witness expires when the committed physical clock changes.
        // Standalone paths without this source witness receive no credit.
        let exact_shared=if self.retained_input_bytes>0
            && std::ptr::eq(state,&self.state) {
            self.service_event_accounting
                .and_then(|a|a.original_input_road_shared)
                .map_or(0,|(clock,credit)|if clock==state.t {
                    credit.min(supplied_retained).min(self.retained_input_bytes)
                }else{0})
        }else{0};
        // Keep historical trace attribution, but an experimental flag may
        // not manufacture an absent or expired original-source witness.
        let optin=std::env::var("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET")
            .ok().as_deref()==Some("source_pair_only");
        let experimental_credit=if optin {exact_shared}else{0};
        let paired_credit=exact_shared.max(experimental_credit);
        crate::v1_trace::add("arc.default_pointer_verified_credit",exact_shared as u64);
        crate::v1_trace::add("arc.experimental_paired_credit",experimental_credit as u64);
        let combine_scratch=stats.max_cell_parts
            .saturating_mul(2*std::mem::size_of::<Part>());
        let base = maximum_retained
            .saturating_mul(3)
            .saturating_sub(paired_credit)
            .saturating_add(rows.saturating_mul(4 * std::mem::size_of::<f64>()))
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
                    ("rows", rows),
                    ("offers", offers.len()),
                    ("max_cell_parts", stats.max_cell_parts),
                    ("groups", groups),
                    ("classes", self.classes.len()),
                    ("paired_arc_credit", paired_credit),
                    ("default_pointer_verified_credit",exact_shared),
                    ("experimental_pointer_verified_credit",experimental_credit),
                ],
            );
        }
        let work = RoadWorkBudget {
            limit: self.storage_budget,
            base,
            transfer_exclusive_cell_scratch:combine_scratch,
            row_scan_scratch_bytes:rows.saturating_mul(4*std::mem::size_of::<f64>()),expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events: 0,
            incoming: 0,
            incoming_page_cells: self.groups.len(),
            incoming_cell_rows:Some(vec![0;self.groups.len()]),incoming_live_pages:0,
            incoming_direct_cell_rows:self.can_reference_incoming_events()
                .then(||vec![0;self.groups.len()]),
            incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events: self.can_compact_candidate_events(),
            narrow_events:self.can_narrow_candidate_events(),
            compact_incoming: self.can_compact_incoming_parts(),
            interval_retained: 0,
            interval_transient: 0,
            service_events: self.service_event_accounting,
        };
        work.require(0, "tick preflight")?;
        Ok(work)
    }
    /// Called only after the entire road step_state frame returns. At this
    /// point old incoming/Mark, queue and interval sweep workspaces are dead.
    /// Do not reuse their obsolete RoadWorkBudget lifetime in the flat phase.
    fn materialize_event_after_road(
        &self, candidate:&mut RoadState, pages:ChunkedEvents,
    )->PyResult<Vec<EventRow>> {
        if let Some(limit)=self.storage_budget {
            let committed_retained=self.state.retained_storage_bytes();
            let supplied_retained=self.retained_input_bytes;
            let candidate_retained=candidate.retained_storage_bytes();
            let original_verified=self.service_event_accounting
                .and_then(|v|v.original_input_road_shared);
            let (road_owners,source_arc_credit,candidate_arc_credit)=
                postroad_source_verified_arc_owner_charge(
                    &self.state,candidate,supplied_retained,original_verified);
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
                    ("source_input_actual_shared_arc_credit",source_arc_credit),
                    ("committed_candidate_actual_shared_arc_credit",candidate_arc_credit),
                    ("committed_road_retained_bytes",committed_retained),
                    ("supplied_road_retained_bytes",supplied_retained),
                    ("candidate_road_retained_bytes",candidate_retained),
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
        // The entire raw event page carrier is dropped before creating
        // new keyset allocations. The original final flat EventRows persist.
        let flat=pages.into_flat_checked()?;
        if let Some(limit)=self.storage_budget {
            let stats=candidate.debug_stats();
            let committed_retained=self.state.retained_storage_bytes();
            let supplied_retained=self.retained_input_bytes;
            let candidate_retained=candidate.retained_storage_bytes();
            let owner_sum=postroad_continuous_owner_sum(
                committed_retained,supplied_retained,candidate_retained,
            );
            let old_events=self.service_event_accounting.map_or(0,|v|
                v.input_bytes.saturating_add(
                    if v.shared_input_current {0} else {v.current_bytes}
                ));
            let packets=stats.cell_packets.saturating_add(stats.pending_packets);
            let required=postroad_continuous_keyset_peak_bytes(
                owner_sum,old_events,flat.len(),stats.uniform_parts,packets,
            );
            // A global canonicalization is optional metadata compression.
            // Its high conservative temporary-copy peak must NOT invalidate
            // an already computed, physically admissible RoadState.
            // Postroad flat EventRow materialization was separately checked
            // above, and subsequent simulation checkpoints have hard caps.
            crate::v1_trace::guard(
                "road_post","optional keyset interning estimate",required,limit,
                &[("committed_road_retained",committed_retained),
                  ("supplied_input_road_retained",supplied_retained),
                  ("candidate_road_retained",candidate_retained),
                  ("road_owner_sum",owner_sum),("old_event_bytes",old_events),
                  ("flat_event_rows",flat.len()),("candidate_uniform_rows",stats.uniform_parts),
                  ("candidate_packets",packets)],
            );
            let before=candidate.retained_storage_bytes();
            let (changed,deferred)=maybe_intern_exact_keysets(candidate,limit,required)?;
            if deferred {
                crate::v1_trace::add("keyset.surgical_deferred_due_to_budget",1);
                crate::v1_trace::add("keyset.surgical_estimated_required_bytes",required as u64);
            } else {
                let after=candidate.retained_storage_bytes();
                crate::v1_trace::add("keyset.continuous_converted",changed as u64);
                crate::v1_trace::add("keyset.continuous_saved_bytes",before.saturating_sub(after) as u64);
            }
        }
        Ok(flat)
    }

    /// Whole-engine path transfers the actual pages directly to the service
    /// state. No flat EventRow allocation coexists with or replaces them.
    fn preserve_event_after_road(
        &self,candidate:&mut RoadState,pages:ChunkedEvents,
    )->PyResult<ChunkedEvents> {
        if let Some(limit)=self.storage_budget {
            let verified=self.service_event_accounting.and_then(|v|v.original_input_road_shared);
            let (road_owners,_,_)=postroad_source_verified_arc_owner_charge(
                &self.state,candidate,self.retained_input_bytes,verified);
            let old_events=self.service_event_accounting.map_or(0,|v|
                v.input_bytes.saturating_add(if v.shared_input_current {0} else {v.current_bytes}));
            let event_bytes=pages.storage_bytes();
            let required=road_owners.saturating_add(old_events).saturating_add(event_bytes);
            check_storage_limit(Some(limit),required,"persistent event pages after road")?;
            crate::v1_trace::add("events.persistent_payload_rows",pages.len() as u64);
            crate::v1_trace::add("events.persistent_storage_bytes",event_bytes as u64);
            let stats=candidate.debug_stats();
            let packets=stats.cell_packets.saturating_add(stats.pending_packets);
            let owner_sum=postroad_continuous_owner_sum(
                self.state.retained_storage_bytes(),self.retained_input_bytes,
                candidate.retained_storage_bytes());
            let intern_required=owner_sum.saturating_add(old_events)
                .saturating_add(event_bytes)
                .saturating_add(stats.uniform_parts.saturating_mul(std::mem::size_of::<CorePart>()))
                .saturating_add(packets.saturating_mul(512)).saturating_add(3*32);
            let before=candidate.retained_storage_bytes();
            let (changed,deferred)=maybe_intern_exact_keysets(candidate,limit,intern_required)?;
            if deferred {
                crate::v1_trace::add("keyset.surgical_deferred_due_to_budget",1);
                crate::v1_trace::add("keyset.surgical_estimated_required_bytes",intern_required as u64);
            } else {
                crate::v1_trace::add("keyset.continuous_converted",changed as u64);
                crate::v1_trace::add("keyset.continuous_saved_bytes",
                    before.saturating_sub(candidate.retained_storage_bytes()) as u64);
            }
        }
        Ok(pages)
    }

    pub(crate) fn owned_step(&mut self, dt: f64, offers: Vec<Offer>) -> PyResult<Vec<EventRow>> {
        self.begin_call_storage_accounting();
        let (mut s, pages) = self.step_state(&self.state, dt, offers)?;
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
    ) -> PyResult<(RoadState, ChunkedEvents)> {
        let (mut s,pages)=self.step_state(&self.state,dt,offers)?;
        let e=self.preserve_event_after_road(&mut s,pages)?;
        Ok((s,e))
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
    fn motion(&self, i: usize, c: &Cell, dt: f64, factor: f64) -> PyResult<Motion> {
        let mut counts: BTreeMap<usize, Vec<f64>> = BTreeMap::new();
        for packet in &c.packets {
            for p in &packet.parts {
                push_checked(counts.entry(self.class(&p)).or_default(), p.mass)?;
            }
        }
        let counts: BTreeMap<usize, f64> = counts.into_iter().map(|(k, v)| (k, sum(v))).collect();
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
    ) -> PyResult<Vec<Packet>> {
        // Live for the whole call; each interval adds its own rows (the
        // selected-row Vec, combine's index and output) and the packet list
        // with room for its doubling reallocation. Only packed rows that are
        // pushed to the output outlive their interval.
        // The previous implementation first allocated 2*n f64 endpoints
        // and sorted/deduped them. The sorted event streams now yield exactly
        // k unique numeric edges, so no 2*n endpoint buffer ever exists.
        let (nonpoint_rows, point_rows) = count_sweep_row_kinds(&parts)?;
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
        let mut out = vec![];
        let mut records = 0;
        for (k, &a) in edges.iter().enumerate() {
            sweep.advance(a);
            let count = sweep.current_points.len();
            let uniform_point = compactable_source
                && all_point_endpoint_bits_identical(&parts, &sweep.current_points);
            // Homogeneous byte-identical point endpoints need only the final
            // CorePart buffer and source index array (40B/selected row);
            // mixed signed-zero or other bit-distinct endpoints retain the
            // exact original materialized path and its 104B/row guard.
            work.interval(transient(count, out.len(), !uniform_point))?;
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
                    parts.allocated_bytes().saturating_add(std::mem::size_of::<Packet>()),
                );
                push_checked(&mut out, Packet { target, parts })?;
            }
            if k + 1 < edges.len() {
                let b = edges[k + 1];
                let count = sweep.active.len();
                work.interval(transient(count, out.len(), false))?;
                // The original source indices are already ascending; avoid
                // materializing a second full-size interval split buffer.
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
                            .saturating_add(std::mem::size_of::<Packet>()),
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
            interval_merge_census(&out);
        }
        Ok(out)
    }
    fn rates(
        &self,
        heads: &BTreeMap<usize, BTreeMap<usize, f64>>,
        send: &BTreeMap<usize, f64>,
        receive: &BTreeMap<usize, f64>,
    ) -> PyResult<BTreeMap<usize, f64>> {
        let mut q: BTreeMap<usize, f64> = heads.keys().map(|&i| (i, 0.)).collect();
        let mut active: Vec<usize> = heads.keys().copied().filter(|i| send[i] > 0.).collect();
        while !active.is_empty() {
            let mut bounds: Vec<f64> = active
                .iter()
                .map(|i| (send[i] - q[i]) / self.groups[*i][5])
                .collect();
            for (&j, &supply) in receive {
                let slope = sum(active
                    .iter()
                    .map(|i| heads[i].get(&j).copied().unwrap_or(0.) * self.groups[*i][5]));
                if slope > 0. {
                    let used = sum(heads
                        .iter()
                        .map(|(&i, b)| b.get(&j).copied().unwrap_or(0.) * q[&i]));
                    bounds.push((supply - used).max(0.) / slope);
                }
            }
            let step = bounds.into_iter().fold(f64::INFINITY, f64::min).max(0.);
            for &i in &active {
                *q.get_mut(&i).unwrap() += step * self.groups[i][5];
            }
            let saturated: Vec<usize> = receive
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
    fn check_state(&self, s: &RoadState) -> PyResult<()> {
        if s.cells.len() != self.groups.len()
            || s.pending.len() != self.groups.len()
            || s.ledger.len() != self.classes.len()
            || !finite_nonnegative(s.t)
            || s.totals.iter().any(|v| !finite_nonnegative(*v))
        {
            return Err(val("invalid native road state schema/ledger"));
        }
        let owner_bytes=if self.storage_budget.is_some() {
            s.retained_storage_bytes().max(self.retained_input_bytes).saturating_mul(3)
        }else{0};
        let fixed=self.classes.len().saturating_mul(std::mem::size_of::<ValidationSum>()+32)
            .saturating_add(256);
        let validation=ValidationScratch::new(self.storage_budget,owner_bytes,fixed)?;
        let mut stored=checkpoint_vec(self.classes.len())?;
        for _ in &self.classes {stored.push(ValidationSum::new(&validation));}
        let actual_fixed=stored.capacity().saturating_mul(std::mem::size_of::<ValidationSum>()+32)
            .saturating_add(256);
        validation.live_bytes.set(actual_fixed);
        validation.require(0)?;
        let mut all=ValidationSum::new(&validation);
        let mut residence=ValidationSum::new(&validation);
        let mut records = 0;
        for (i, c) in s.cells.iter().enumerate() {
            if !c.v[0].is_finite()
                || !c.v[1].is_finite()
                || !(0.0..=1.0).contains(&c.v[1])
                || c.v[2..].iter().any(|x| !finite_nonnegative(*x))
                || c.latent.iter().any(|(k, x)| {
                    *k >= self.classes.len() || !x.is_finite() || !(0.0..=1.0).contains(x)
                })
            {
                return Err(val("invalid native cell state"));
            }
            if c.packets
                .windows(2)
                .any(|w| w[0].target > w[1].target + 1e-10)
                || s.pending[i].windows(2).any(|w| w[0].target > w[1].target)
            {
                return Err(arithmetic("packet/source order"));
            }
            let mut occupancy=ValidationSum::new(&validation);
            for packet in &c.packets {
                occupancy.push(validation_sum(packet.parts.iter().map(|p|p.mass),&validation)?)?;
            }
            let occ=occupancy.finish();
            if (c.v[2] - c.v[3] - occ).abs() > 1e-9 * c.v[2].max(1.) {
                return Err(arithmetic("cell mass ledger"));
            }
            let occupied=validation_sum(c.packets.iter().flat_map(|packet|
                packet.parts.iter().map(|p|p.mass*self.footprint(p.tag))),&validation)?;
            if occupied > self.groups[i][4] + 1e-9 * self.groups[i][4].max(1.) {
                return Err(arithmetic("cell storage"));
            }
            residence.push((c.v[2] - c.v[3]) * s.t - c.v[4] + c.v[5])?;
            all.push(occ)?;
            for (pending, packets) in [(false, &c.packets), (true, &s.pending[i])] {
                for packet in packets {
                    if packet.parts.is_empty()
                        || !packet.target.is_finite()
                        || (pending && !(0.0..=s.t).contains(&packet.target))
                    {
                        return Err(val("empty/invalid native packet"));
                    }
                    for p in &packet.parts {
                        records += 1;
                        if p.tag >= self.routes.len()
                            || !p.mass.is_finite()
                            || p.mass <= 0.
                            || !finite_nonnegative(p.birth)
                            || p.birth > p.mass * s.t + 1e-8
                        {
                            return Err(val("invalid homogeneous native part"));
                        }
                        if self.path(p.tag).get(p.offset) != Some(&i) {
                            return Err(val("native route suffix mismatch"));
                        }
                        if p.a.is_some() != p.b.is_some()
                            || p.a.is_some_and(|a| {
                                !a.is_finite()
                                    || a < 0.
                                    || !p.b.unwrap().is_finite()
                                    || a > p.b.unwrap()
                                    || p.b.unwrap() > s.t + 1e-9
                            })
                        {
                            return Err(val("invalid native entry interval"));
                        }
                        stored[self.class(&p)].push(p.mass)?;
                    }
                    if pending {
                        all.push(validation_sum(packet.parts.iter().map(|p|p.mass),&validation)?)?;
                    }
                }
            }
        }
        if records > self.record_budget {
            return Err(budget("packet state budget"));
        }
        let tol = 1e-9 * s.totals[0].max(1.);
        if (s.totals[0] - s.totals[1] - all.finish()).abs() > tol {
            return Err(arithmetic("network mass ledger"));
        }
        let total_residence = residence.finish() + s.totals[4] + s.totals[5] + s.totals[6];
        let system = (s.totals[0] - s.totals[1]) * s.t - s.totals[2] + s.totals[3];
        if (total_residence - system).abs() > 1e-8 * total_residence.max(1.) {
            return Err(arithmetic("residence ledger"));
        }
        for (l, class_sum) in s.ledger.iter().zip(stored.into_iter()) {
            if l.iter().any(|x| !finite_nonnegative(*x))
                || (l[0] - l[1] - class_sum.finish()).abs() > 1e-9 * l[0].max(1.)
            {
                return Err(arithmetic("class mass/ledger mismatch"));
            }
        }
        for (a, b) in [(0, 0), (1, 1), (2, 4), (4, 5)] {
            let observed = validation_sum(s.ledger.iter().map(|l| l[a]),&validation)?;
            if (observed - s.totals[b]).abs() > 1e-8 * observed.max(s.totals[b]).max(1.) {
                return Err(arithmetic("class/global ledger mismatch"));
            }
        }
        crate::v1_trace::add("validation.actual_peak_scratch_bytes",validation.peak_bytes.get() as u64);
        Ok(())
    }
    fn step_state(
        &self,
        s: &RoadState,
        dt: f64,
        offers: Vec<Offer>,
    ) -> PyResult<(RoadState, ChunkedEvents)> {
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
        let mut work = self.work_budget(s, &offers)?;
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
                .collect::<PyResult<_>>()?,
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
                    parts: work.pack_parts(combine(p)?)?,
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
        let predictions = ordered_map(n, 32, |i| -> PyResult<_> {
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
        // All predictions have been consumed, and temporary per-Part f64
        // source scans from motion() and check_state() are no longer alive.
        // Measure still-live queue slots and conservatively reserve the
        // per-class Motion map owners before retiring the old scan envelope.
        let live_queue_slots:usize=queues.iter()
            .map(|q|q.capacity().saturating_mul(std::mem::size_of::<(Packet,f64)>()))
            .sum();
        let live_motion_shells=motions.capacity().saturating_mul(std::mem::size_of::<Motion>());
        let live_outer_queue=queues.capacity()
            .saturating_mul(std::mem::size_of::<Vec<(Packet,f64)>>());
        let perclass_motion_owner=self.groups.len().saturating_mul(
            self.classes.len().saturating_mul(1024).saturating_add(1024)
        );
        work.retire_completed_motion_scan(
            live_queue_slots.saturating_add(live_motion_shells)
                .saturating_add(live_outer_queue)
                .saturating_add(perclass_motion_owner)
        );
        // +infinity packets were cloned from this exact immutable source.
        // EventClock::after_ready excludes them at every finite cursor;
        // they survive unchanged and cannot enter a remainder conversion.
        work.witness_frozen_queue_owners(s,&queues)?;
        let mut position = vec![0; n];
        // Diagnostic only: previous serve per cell (head position, rate bits, end time).
        let mut last_serve: Vec<Option<(usize, u64, f64)>> = if crate::v1_trace::enabled() {
            vec![None; n]
        } else {
            Vec::new()
        };
        let mut events = ChunkedEvents::new(self.can_compact_candidate_events());
        let compact_incoming=self.can_compact_incoming_parts();
        let event_backed=self.can_reference_incoming_events();
        let shell_reserve=n.saturating_mul(
            std::mem::size_of::<ChunkedParts>()+std::mem::size_of::<ChunkedMarks>()
        ).saturating_add(2*128);
        work.require(shell_reserve,"incoming owner shells")?;
        let mut incoming: Vec<ChunkedParts> = (0..n)
            .map(|_|if event_backed {ChunkedParts::event_backed()}
                else{ChunkedParts::new(compact_incoming)}).collect();
        // Diagnostic only: source (cell, head position, rate bits) per incoming row.
        let mut incoming_src: Vec<ChunkedDiagnosticSource> = if crate::v1_trace::enabled() {
            (0..n).map(|_|ChunkedDiagnosticSource::default()).collect()
        } else {
            Vec::new()
        };
        let mut marks: Vec<ChunkedMarks> = (0..n)
            .map(|_| ChunkedMarks::default()).collect();
        work.incoming_outer_bytes=incoming.capacity()
            .saturating_mul(std::mem::size_of::<ChunkedParts>())
            .saturating_add(marks.capacity().saturating_mul(std::mem::size_of::<ChunkedMarks>()))
            .saturating_add(2*128);
        work.require(0,"incoming owner shells")?;
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
                let mut heads: BTreeMap<usize, ()> = BTreeMap::new();
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
                    heads.insert(i, ());
                    let mut dest: BTreeMap<usize, Vec<f64>> = BTreeMap::new();
                    let mut ds: BTreeMap<usize, Vec<f64>> = BTreeMap::new();
                    for p in &packet.parts {
                        let j = self.dest(&p).unwrap_or(n);
                        push_checked(dest.entry(j).or_default(), p.mass)?;
                        push_checked(ds.entry(j).or_default(), p.mass * self.footprint(p.tag))?;
                    }
                    let pm = mass(packet);
                    beta.insert(i, dest.into_iter().map(|(j, v)| (j, sum(v) / pm)).collect());
                    beta_space.insert(i, ds.into_iter().map(|(j, v)| (j, sum(v) / pm)).collect());
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
                    let limit = mass(&queues[i][position[i]].0) / r;
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
                        let fraction = (rate * h / mass(&queues[i][position[i]].0)).min(1.);
                        fraction == 1. || 1. - fraction < 1e-14
                    });
                if h <= 0. || (subulp && !clock.active && !retires_head) {
                    // Construct diagnostics only on failure. Keep the event
                    // candidates, reduction order and rejection rule unchanged.
                    let head_context: Vec<_> = rates
                        .iter()
                        .map(|(&i, &rate)| {
                            let (packet, ready) = &queues[i][position[i]];
                            let head_mass = mass(packet);
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
                    let mut fraction = (rate * h / mass(packet)).min(1.);
                    if 1. - fraction < 1e-14 {
                        fraction = 1.;
                    }
                    let incoming_count=served_parts(&packet.parts,fraction)
                        .filter(|part|self.dest(part).is_some()).count();
                    work.transfer_indexed_with_live_diagnostics(
                        packet.parts.len(),
                        served_parts(&packet.parts,fraction)
                            .filter_map(|part|self.dest(&part)),
                        &mut incoming,&mut marks,Some(&mut incoming_src),
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
                    // Exactly original IEEE mass/birth transform + source order.
                    for mut p in served_parts(&packet.parts, fraction) {
                        let k = self.class(&p);
                        out.ledger[k][3] += p.mass * (local_mid - ready).max(0.);
                        let j = self.dest(&p);
                        // This is the actual append index, never the
                        // conservative projected EventRow admission count.
                        let event_index=events.len();
                        events.push_checked(
                            (p.tag, i, j, p.mass, start_time, end_time, p.birth),
                        )?;
                        if let Some(j) = j {
                            free[j] = (free[j] - p.mass).max(0.);
                            space[j] = (space[j] - p.mass * self.footprint(p.tag)).max(0.);
                            out.ledger[k][4] += p.mass * (end - mid);
                            hold += p.mass * (end - mid);
                            let m = &motions[i];
                            let rate = self.classes[k][8] + m.hazards[&k];
                            let p0 = m.initial[&k];
                            let latent = if rate == 0. {
                                p0
                            } else {
                                p0 + (self.classes[k][8] / rate - p0)
                                    * (-(-rate * local_mid).exp_m1())
                            };
                            marks[j].push_checked(
                                compact_mark(m.sample(local_mid).1, latent),
                            )?;
                            p.offset += 1;
                            if self.intervals {
                                p.a = PackedTime::new(Some(start_time))?;
                                p.b = PackedTime::new(Some(end_time))?;
                            }
                            incoming[j].push_serviced(event_index,p,&events)?;
                            if !incoming_src.is_empty() {
                                incoming_src[j].push(compact_diagnostic_source_id(
                                    i,position[i],rate.to_bits()
                                )?)?;
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
                        let remainder=work.pack_parts_with_live_descriptors(
                            portion(&packet.parts,1.-fraction)?,&incoming,&marks,
                        )?;
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
        if work.limit.is_some() && crate::v1_trace::enabled() {
            let incoming_cap: usize = incoming.iter().map(ChunkedParts::capacity).sum();
            let incoming_real_payload:usize=incoming.iter().map(ChunkedParts::physical_capacity_bytes).sum();
            let marks_cap: usize = marks.iter().map(ChunkedMarks::capacity).sum();
            let incoming_len: usize = incoming.iter().map(ChunkedParts::len).sum();
            crate::v1_trace::guard(
                "road_actual",
                "transfer buffers",
                events.physical_capacity_bytes()
                    .saturating_add(incoming_real_payload)
                    .saturating_add(marks_cap.saturating_mul(std::mem::size_of::<Mark>())) ,
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
            let mut active = vec![false; self.classes.len()];
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
                    work.transfer_indexed_with_live_diagnostics(
                        0,std::iter::repeat(i).take(expected_pending),
                        &mut incoming,&mut marks,Some(&mut incoming_src),
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
                for part in &mut parts {
                    let k = self.class(&part);
                    if self.intervals {
                        part.a = PackedTime::new(Some(end))?;
                        part.b = PackedTime::new(Some(end))?;
                    }
                    marks[i].push_checked(
                        compact_mark(self.classes[k][11], self.classes[k][7]),
                    )?;
                }
                // Paged appends do not reallocate previous incoming Part rows.
                if !incoming_src.is_empty() {
                    let k = incoming_src[i].len();
                    let id=pending_diagnostic_source_id(k)?;
                    incoming_src[i].extend((0..parts.len()).map(|_| id))?;
                }
                incoming[i].extend_parts(parts)?;
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
        work.lock_completed_incoming_descriptors(&incoming,&marks)?;
        for i in 0..n {
            if !incoming_src.is_empty() && !incoming[i].is_empty() {
                exact_merge_census(incoming[i].view(&events)?.iter(), incoming_src[i].iter().copied());
            }
            // Diagnostic-only input sequence is consumed and is not retained
            // for any original physical source calculation in a later cell.
            if !incoming_src.is_empty() {
                incoming_src[i].verify_capacity_bytes()?;
                let bytes=incoming_src[i].capacity_bytes();
                work.diagnostic_source_live_bytes=work.diagnostic_source_live_bytes
                    .saturating_sub(bytes);
                drop(std::mem::take(&mut incoming_src[i]));
            }
            // One compact mark accompanies exactly one source-order incoming
            // Part (both road service and pending-offer insertion paths).
            // Never call combine before consuming the aligned raw rows.
            let raw_rows = incoming[i].len();
            if raw_rows != marks[i].len() {
                return Err(arithmetic("incoming Part/Mark source-order alignment differs"));
            }
            let old = self.occupancy(&out.cells[i]);
            let weighted_speed = sum(
                incoming[i]
                    .view(&events)?.iter()
                    .zip(marks[i].iter())
                    .map(|(part, mark)| part.mass * mark.0),
            );
            let mut byclass: BTreeMap<usize, Vec<(f64, f64)>> = BTreeMap::new();
            // Original fsum class input order: all unchanged survivor rows,
            // followed by each received mark in original append order.
            for packet in &out.cells[i].packets {
                for p in &packet.parts {
                    let k = self.class(&p);
                    push_checked(
                        byclass.entry(k).or_default(),
                        (p.mass, out.cells[i].latent[&k]),
                    )?;
                }
            }
            for (part, mark) in incoming[i].view(&events)?.iter().zip(marks[i].iter()) {
                let k = self.class(&part);
                push_checked(byclass.entry(k).or_default(), (part.mass, mark.1))?;
            }
            // Only now may equal-key incoming Parts be combined.
            let source = std::mem::take(&mut incoming[i]);
            let parts = combine_incoming_view(source.view(&events)?)?;
            // All source-order f64 and Mark-dependent physical moments have
            // now been computed, and source combination finished. Physically
            // drop BOTH raw owner families before reducing the bound seen by
            // later interval-packet and cell reservation checks.
            let expired_marks = std::mem::take(&mut marks[i]);
            let expired = release_consumed_incoming_pair(
                &mut work,i,source,expired_marks,
            )?;
            debug_assert_eq!(expired,raw_rows);
            if crate::v1_trace::enabled() && raw_rows > 0 {
                crate::v1_trace::add("entry.raw_rows", raw_rows as u64);
                crate::v1_trace::add("entry.combined_rows", parts.len() as u64);
            }
            let added = sum(parts.iter().map(|p| p.mass));
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
                        sum(v.iter().map(|(m, p)| m * p)) / sum(v.iter().map(|(m, _)| *m)),
                    )
                })
                .collect();
            let target = out.cells[i].v[0] + self.groups[i][0];
            let packets = if self.intervals {
                // This exact original single cell's combined Vec<Part>
                // remains live until the interval splitter returns. The
                // raw Part/Mark page pairs were source-dropped above.
                let actual_source_bytes=parts.capacity()
                    .saturating_mul(std::mem::size_of::<Part>());
                work.with_completed_source_interval(actual_source_bytes,|active_work|
                    self.interval_packets(parts,target,active_work)
                )?
            } else {
                vec![Packet {
                    target,
                    parts: work.pack_parts_after_completed_combine(parts)?,
                }]
            };
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
            let physical_slot_overlap=packets
                .capacity()
                .saturating_add(old_capacity)
                .saturating_add(grown)
                .saturating_mul(slot);
            if self.intervals {
                work.require_completed_interval_cell_slot(physical_slot_overlap)?;
            } else {
                work.require(physical_slot_overlap,"cell packet reservation")?;
            }
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
    ) -> PyResult<Vec<Packet>> {
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
    fn from_row(&self, row: StateRow) -> PyResult<RoadState> {
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
#[pymethods]
impl V1Road {
    /// Explicit byte-budget mode; legacy constructor record guards remain the
    /// default. Configuration is atomic and never mutates physical state.
    pub(crate) fn configure_storage_budget(&mut self, bytes: usize) -> PyResult<()> {
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
    fn storage_limits(&self) -> (Option<usize>, usize, usize, Option<usize>) {
        (
            self.storage_budget,
            self.record_budget,
            self.checkpoint_event_limit(),
            self.event_budget,
        )
    }
    fn event_resolution_diagnostics(&self) -> (u64, f64, f64, f64) {
        self.event_resolution_stats()
    }
    fn storage_layout_bytes(&self) -> (usize, usize, usize, usize) {
        (
            std::mem::size_of::<CorePart>(),
            std::mem::size_of::<Part>(),
            std::mem::size_of::<Packet>(),
            std::mem::size_of::<EventRow>(),
        )
    }
    fn packet_storage_counts(&self) -> (usize, usize, usize, usize) {
        let stats = self.state.debug_stats();
        (
            stats.uniform_packets,
            stats.mixed_packets,
            stats.uniform_parts,
            stats.mixed_parts,
        )
    }
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (identity, dt, groups, signals, routes, classes, incoming, windows, record_budget, event_budget, intervals))]
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
    ) -> PyResult<Self> {
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
    fn snapshot(&self) -> StateRow {
        self.row()
    }
    fn restore(&mut self, row: StateRow) -> PyResult<()> {
        let s = self.from_row(row)?;
        self.state = s;
        self.retained_input_bytes = 0;
        self.service_event_accounting = None;
        Ok(())
    }
    fn reset(&mut self, t: f64) -> PyResult<()> {
        if !finite_nonnegative(t) || (t / self.dt - (t / self.dt).round()).abs() > 1e-9 {
            return Err(val("nonnegative grid-aligned time origin"));
        }
        self.state = self.blank(t);
        self.retained_input_bytes = 0;
        self.service_event_accounting = None;
        Ok(())
    }
    fn step(&mut self, py: Python<'_>, dt: f64, offers: Vec<Offer>) -> PyResult<Vec<EventRow>> {
        self.begin_call_storage_accounting();
        let (mut s, pages) = py.allow_threads(|| self.step_state(&self.state, dt, offers))?;
        let e=self.materialize_event_after_road(&mut s,pages)?;
        self.state = s;
        Ok(e)
    }
    fn advance_batch(
        &mut self,
        py: Python<'_>,
        steps: Vec<(f64, Vec<Offer>)>,
    ) -> PyResult<Vec<Vec<EventRow>>> {
        // Each successful interval commits; failures retain the last valid interval.
        self.begin_call_storage_accounting();
        let mut events = vec![];
        for (dt, offers) in steps {
            let (mut s, pages) = py.allow_threads(|| self.step_state(&self.state, dt, offers))?;
            let e=self.materialize_event_after_road(&mut s,pages)?;
            self.state = s;
            events.push(e);
        }
        Ok(events)
    }
    fn registry_sizes(&self) -> (usize, usize, usize) {
        (self.routes.len(), self.paths.len(), self.groups.len())
    }
}

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
    ) -> PyResult<Self> {
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
        let mut r = Self {
            identity,
            dt,
            groups,
            signals,
            paths,
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
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events: 0,
            incoming: 0,
            incoming_page_cells: 0,
            incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events: false,narrow_events:false,
            compact_incoming: false,
            interval_retained: 0,
            interval_transient: 0,
            service_events: None,
        }
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
            original_input_road_shared: None,
        };
        let rows = 10_000;
        assert_eq!(
            a.road_step_bytes(rows),
            3_000 + persistent_event_candidate_upper_bytes(rows,false)
        );
        assert_eq!(a.road_step_bytes(0), 3_000+event_store_shell_bytes());
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
            original_input_road_shared: None,
        };
        let separate = ServiceEventAccounting {
            shared_input_current: false, ..one
        };
        let candidate = 10usize;
        // Candidate is now physically held in fixed-size event pages.
        // Sharing of old committed input/current events remains pointer based.
        let candidate_bytes = persistent_event_candidate_upper_bytes(candidate,false);
        assert_eq!(one.road_step_bytes(candidate), 8192 + candidate_bytes);
        assert_eq!(separate.road_step_bytes(candidate), 2 * 8192 + candidate_bytes);
        assert_eq!(one.road_step_bytes(0), 8192 + event_store_shell_bytes());
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
            // Legacy pre-event-index envelope charged 56B/source row.
            // The source-backed narrow event indices now own 8B/nonpoint
            // and 12B/point; do not retain the intermediate 16B pair
            // assumption (32B/nonpoint, 24B/point) in this regression.
            let old = n*56 + (n.div_ceil(64)+n.div_ceil(4096))*8 + 256;
            let reduced = exact_sweep_event_index_bytes(n,u,q);
            assert_eq!(old - reduced, 48*u+44*q);
            assert!(reduced <= old);
        }
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
        assert_eq!(page,582_644_120);
        assert_eq!(old-page,1_164_583_816);
        assert_eq!(paged_event_candidate_bytes(0),96);
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
            +exact_rows*std::mem::size_of::<EventRow>()+96;
        assert_eq!(actual,expected);
        assert!(actual<5_188_657_743usize);
        assert!(actual>original_road_snapshots+old_events);
    }

    #[test]
    fn no_event_history_uses_no_candidate_rows_or_flattening()
    {
        assert_eq!(postroad_event_materialization_bytes(11,23,0,0,0),11+23+96);
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
            assert!(p.physical_capacity_bytes()<=p.capacity()*48);
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
        assert_eq!(paged_compact_event_candidate_bytes(0),96);
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
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:n,incoming_page_cells:1586,
            incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,narrow_events:false,compact_incoming:true,
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
        let original_metadata=3*32;
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
        assert_eq!(old(short)-paged_compact_event_candidate_bytes(short),139_200);
        assert_eq!(old(long)-paged_compact_event_candidate_bytes(long),46_512);
        assert!(139_200>6_609);
        assert!(46_512>11_513);
    }
    #[test]
    fn physical_page_chunk_capacity_matches_checked_narrow_tier() {
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
            assert!(pages.compact_chunks.iter()
                .all(|page|matches!(page,CompactEventPage::Narrow(_))));
            assert_eq!(pages.physical_capacity_bytes(),
                n.div_ceil(EVENT_PAGE_ROWS)*EVENT_PAGE_ROWS
                  *std::mem::size_of::<NarrowEventRow>());
        }
    }
}

#[cfg(test)]
mod exact_incoming_cell_page_liveness_tests {
    use super::*;

    fn work(g:usize)->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(100_000_000),base:0,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,
            incoming_page_cells:g,compact_events:true,narrow_events:false,compact_incoming:true,
            incoming_cell_rows:Some(vec![0;g]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
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
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,
            incoming_page_cells:3,
            incoming_cell_rows:Some(vec![0;3]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,narrow_events:false,compact_incoming:true,
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
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,
            incoming_page_cells:3,
            incoming_cell_rows:Some(vec![0;3]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,narrow_events:false,compact_incoming:true,
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
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:0,
            incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:false,narrow_events:false,compact_incoming:false,
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
mod original_completed_source_exact_packet_admission_tests {
    use super::*;
    fn budget()->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(930),base:1000,transfer_exclusive_cell_scratch:150,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:0,
            incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:Some(0),
            compact_events:false,narrow_events:false,compact_incoming:false,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    fn part()->Part{
        Part{tag:1,offset:0,mass:0.25,birth:-0.0,
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap()}
    }
    #[test]
    fn completed_source_charges_real_part_vec_and_simultaneous_core_before_pack(){
        let w=budget();
        assert!(w.require(0,"packet interval packing").is_err());
        let packed=w.pack_parts_after_completed_combine(vec![part()]).unwrap();
        assert!(packed.is_uniform());
        let decoded:Vec<_>=packed.iter().collect();
        assert_eq!(decoded.len(),1);
        assert_eq!(decoded[0].mass.to_bits(),0.25f64.to_bits());
        assert_eq!(decoded[0].birth.to_bits(),(-0.0f64).to_bits());
    }
    #[test]
    fn no_unearned_source_scratch_credit_outside_completed_conversion(){
        let mut w=budget();
        w.incoming_descriptor_live_bytes=None;
        assert!(w.pack_parts_after_completed_combine(vec![part()]).is_err());
        w.incoming_descriptor_live_bytes=Some(0);
        w.transfer_exclusive_cell_scratch=0;
        assert!(w.pack_parts_after_completed_combine(vec![part()]).is_err());
        w.transfer_exclusive_cell_scratch=150;
        assert!(w.pack_parts_after_completed_combine(vec![part();3]).is_err());
    }
}

#[cfg(test)]
mod original_precombine_pending_remainder_lifetime_tests {
    use super::*;
    fn part() -> Part {
        Part { tag:1, offset:0, mass:0.25, birth:-0.0,
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap() }
    }
    fn budget() -> RoadWorkBudget {
        RoadWorkBudget {
            // Exact source counter Vec adds 136B: old 1160B, new 1058B.
            limit:Some(1100),base:1000,transfer_exclusive_cell_scratch:150,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:1,
            incoming_cell_rows:Some(vec![0]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,narrow_events:false,compact_incoming:true,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    #[test]
    fn future_combine_cannot_block_live_pending_packet_and_exact_two_buffers_are_charged() {
        let mut w=budget();
        let incoming=vec![ChunkedParts::new(true)];
        let marks=vec![ChunkedMarks::default()];
        assert!(w.require(24,"packet interval packing").is_err());
        let packed=w.pack_parts_with_live_descriptors(vec![part()],&incoming,&marks).unwrap();
        let rows:Vec<_>=packed.iter().collect();
        assert_eq!(rows.len(),1);
        assert_eq!(rows[0].birth.to_bits(),(-0.0f64).to_bits());
        assert!(w.incoming_descriptor_live_bytes.is_none());
        // Ordinary future combine reserve is unchanged after this call.
        assert!(w.require(24,"packet interval packing").is_err());
    }
    #[test]
    fn rejected_pending_pack_restores_descriptor_growth_guard_and_future_preflights() {
        let mut w=budget();
        w.limit=Some(900);
        let incoming=vec![ChunkedParts::new(true)];
        let marks=vec![ChunkedMarks::default()];
        assert!(w.pack_parts_with_live_descriptors(vec![part()],&incoming,&marks).is_err());
        assert!(w.incoming_descriptor_live_bytes.is_none());
        assert!(w.require(0,"packet interval packing").is_err());
    }
}

#[cfg(test)]
mod transfer_live_header_budget_constructive_tests {
    use super::*;

    fn work()->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(36_600),base:0,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:3,compact_events:true,narrow_events:false,
            compact_incoming:true,incoming_cell_rows:Some(vec![0;3]),
            incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,incoming_descriptor_live_bytes:None,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    fn part()->Part {
        Part{tag:1,offset:0,mass:1.,birth:0.,
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap()}
    }
    #[test]
    fn actual_page_headers_replace_fictitious_all_cell_double_reservation() {
        let mut w=work();
        let mut parts:Vec<ChunkedParts>=(0..3).map(|_|ChunkedParts::new(true)).collect();
        let mut marks:Vec<ChunkedMarks>=(0..3).map(|_|ChunkedMarks::default()).collect();
        let dests=(0..129).map(|_|0usize)
            .chain(std::iter::once(1usize))
            .chain((0..256).map(|_|2usize));
        let old=segmented_incoming_exact_cell_pages_charge(386,3,5,true,None);
        assert!(old>w.limit.unwrap());
        assert!(w.transfer_indexed_with_live_headers(0,dests,&mut parts,&mut marks).is_ok());
        for (j,n) in [(0usize,129),(1,1),(2,256)] {
            for _ in 0..n {
                let p=part();
                parts[j].push_checked(p).unwrap();
                marks[j].push_checked(compact_mark(p.mass,p.birth)).unwrap();
            }
        }
        assert_eq!(w.incoming,386);
        assert_eq!(w.incoming_cell_rows.as_ref().unwrap(),&vec![129,1,256]);
        assert!(w.observed_incoming_descriptor_bytes(&parts,&marks).is_ok());
        assert!(w.incoming_descriptor_live_bytes.is_none());
    }
}

#[cfg(test)]
mod transfer_header_growth_overlap_adversarial_tests {
    use super::*;
    fn part()->Part {
        Part{tag:1,offset:0,mass:1.,birth:0.,
            a:PackedTime::new(Some(0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap()}
    }
    #[test]
    fn old_header_growth_and_future_raw_payload_are_in_disjoint_source_phases() {
        let mut w=RoadWorkBudget {
            limit:Some(100_000_000),base:0,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:1,
            incoming_cell_rows:Some(vec![0]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,narrow_events:false,compact_incoming:true,
            interval_retained:0,interval_transient:0,service_events:None,
        };
        let mut incoming=vec![ChunkedParts::new(true)];
        let mut marks=vec![ChunkedMarks::default()];
        w.transfer_indexed_with_live_headers(
            0,std::iter::repeat(0usize).take(4*INCOMING_PART_CHUNK),
            &mut incoming,&mut marks,
        ).unwrap();
        for _ in 0..4*INCOMING_PART_CHUNK {
            incoming[0].push_checked(part()).unwrap();
            marks[0].push_checked(compact_mark(1.,0.)).unwrap();
        }
        assert_eq!(incoming[0].descriptor_capacity(),4);
        assert_eq!(marks[0].chunks.capacity(),4);
        // A fifth page needs header growth from capacity 4 to at least 5
        // in both Part and Mark. A naive one-phase guard co-charged the
        // OLD header and the FUTURE 128-row Part/Mark payload, even though
        // source appends occur only after this pre-reservation has returned.
        // The phase-separated source guard must accept this exact 36,300 B
        // budget, and still count old+new header overlap in phase A.
        w.limit=Some(36_300);
        let status=w.transfer_indexed_with_live_headers(
            0,std::iter::once(0usize),&mut incoming,&mut marks,
        );
        assert!(status.is_ok());
        assert!(w.incoming_descriptor_live_bytes.is_none());
        assert!(incoming[0].descriptor_capacity()>=5);
        assert!(marks[0].chunks.capacity()>=5);
        // A successful header preflight only authorizes the next physical
        // source append; it is not a completed original physics tick.
    }
}

#[cfg(test)]
mod transfer_header_temporal_nonoverlap_regression_tests {
    use super::*;
    #[test]
    fn event_pages_and_raw_pages_need_not_coexist_with_old_header_realloc_scratch() {
        let mut w=RoadWorkBudget {
            limit:Some(49_070),base:0,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:3,
            incoming_cell_rows:Some(vec![0;3]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:false,narrow_events:false,compact_incoming:true,
            interval_retained:0,interval_transient:0,service_events:None,
        };
        let mut parts:Vec<ChunkedParts>=(0..3).map(|_|ChunkedParts::new(true)).collect();
        let mut marks:Vec<ChunkedMarks>=(0..3).map(|_|ChunkedMarks::default()).collect();
        let dests=(0..129).map(|_|0usize)
            .chain(std::iter::once(1usize))
            .chain((0..256).map(|_|2usize));
        let status=w.transfer_indexed_with_live_headers(100,dests,&mut parts,&mut marks);
        // Original one-peak guard overcharged the future 35,840-byte raw
        // page payload alongside header-reservation-only overlap.
        assert!(status.is_ok());
        assert_eq!(w.events,100);
        assert_eq!(w.incoming_live_pages,5);
        assert!(w.incoming_descriptor_live_bytes.is_none());
    }
}

#[cfg(test)]
mod expired_motion_rows_source_lifetime_tests {
    use super::*;
    #[test]
    fn old_motion_scan_workspace_expires_only_after_all_predictions_consumed() {
        let mut w=RoadWorkBudget {
            limit:Some(900),base:1000,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:400,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:0,
            incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:false,narrow_events:false,compact_incoming:false,
            interval_retained:0,interval_transient:0,service_events:None,
        };
        assert!(w.require(0,"tick preflight").is_err());
        assert!(w.require(0,"transfer candidates").is_err());
        // Queue and Motion shell owners measured after original prediction
        // output is consumed. Never grant an unearned 400B credit.
        w.retire_completed_motion_scan(250);
        assert_eq!(w.expired_motion_scan_credit,150);
        assert!(w.require(0,"transfer candidates").is_ok());
        assert!(w.require(0,"packet interval packing").is_ok());
        assert!(w.require(0,"tick preflight").is_err());
    }
    #[test]
    fn no_credit_when_live_shells_exceed_old_scratch_allowance() {
        let mut w=RoadWorkBudget {
            limit:Some(900),base:1000,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:400,expired_motion_scan_credit:0,diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:0,
            incoming_cell_rows:None,incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:false,narrow_events:false,compact_incoming:false,
            interval_retained:0,interval_transient:0,service_events:None,
        };
        w.retire_completed_motion_scan(450);
        assert_eq!(w.expired_motion_scan_credit,0);
        assert!(w.require(0,"transfer candidates").is_err());
    }
}

#[cfg(test)]
mod diagnostic_lineage_after_motion_expiry_source_tests {
    use super::*;
    #[test]
    fn expired_old_motion_scan_does_not_discard_real_trace_source_lineage_storage() {
        let mut w=RoadWorkBudget {
            limit:Some(100_000_000),base:1000,
            transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:400,expired_motion_scan_credit:0,
            diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:3,
            incoming_cell_rows:Some(vec![0;3]),incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,
            compact_events:true,narrow_events:false,compact_incoming:true,
            interval_retained:0,interval_transient:0,service_events:None,
        };
        let mut incoming:Vec<ChunkedParts>=(0..3).map(|_|ChunkedParts::new(true)).collect();
        let mut marks:Vec<ChunkedMarks>=(0..3).map(|_|ChunkedMarks::default()).collect();
        let mut source:Vec<ChunkedDiagnosticSource>=(0..3)
            .map(|_|ChunkedDiagnosticSource::default()).collect();
        w.retire_completed_motion_scan(250);
        assert_eq!(w.expired_motion_scan_credit,150);
        let ids=(0..129).map(|_|0usize)
            .chain(std::iter::once(1usize))
            .chain((0..256).map(|_|2usize));
        w.transfer_indexed_with_live_diagnostics(0,ids,&mut incoming,&mut marks,Some(&mut source)).unwrap();
        assert_eq!(w.incoming,386);
        let n=std::mem::size_of::<CompactDiagnosticSource>();
        let physically_allocated=source.iter().map(|v|v.capacity_bytes()).sum::<usize>()
            +source.capacity()*std::mem::size_of::<ChunkedDiagnosticSource>();
        assert_eq!(w.diagnostic_source_live_bytes,physically_allocated);
        assert!(physically_allocated>=386*n);
        assert!(w.incoming_descriptor_live_bytes.is_none());
        for (j,m) in [(0usize,129usize),(1,1),(2,256)]{
            for i in 0..m{
                let value=Part {
                    tag:i%7,offset:0,mass:0.25,birth:-0.0,
                    a:PackedTime::new(Some(0.)).unwrap(),
                    b:PackedTime::new(Some(1.)).unwrap()
                };
                incoming[j].push_checked(value).unwrap();
                marks[j].push_checked(compact_mark(0.25,0.)).unwrap();
                source[j].push(compact_diagnostic_source_id(j,i,13u64).unwrap()).unwrap();
            }
        }
        w.transfer_indexed_with_live_diagnostics(0,[0usize],&mut incoming,&mut marks,Some(&mut source)).unwrap();
        let now=w.diagnostic_source_live_bytes;
        assert!(now>=physically_allocated);
        assert!(now>0);
        let incoming_bound=segmented_incoming_exact_cell_pages_charge(
            w.incoming,w.incoming_page_cells,w.incoming_live_pages,true,None,
        );
        let required=1000-150+incoming_bound+now;
        w.limit=Some(required-1);
        assert!(w.require(0,"transfer candidates").is_err());
        w.limit=Some(required);
        assert!(w.require(0,"transfer candidates").is_ok());
        assert_eq!(incoming[0].get(0).mass.to_bits(),0.25f64.to_bits());
        assert_eq!(incoming[0].get(0).birth.to_bits(),(-0.0f64).to_bits());
    }
}

#[cfg(test)]
mod postroad_three_concrete_owner_materialization_tests {
    use super::*;
    #[test]
    fn original_postroad_100k_three_distinct_owner_sizes_are_not_three_maxima() {
        // Original Valley t25700 source-only input & committed road copies
        // are smaller than the newly constructed t25710 candidate. This is
        // a source ownership fact, not a permission to alter the numeric cap.
        let c=630_653_248usize;
        let input=630_653_248usize;
        let new=877_913_216usize;
        let owners=postroad_materialization_owner_bytes(c,input,new);
        assert_eq!(owners,c+input+new);
        assert!(owners<3*new);
        let old=postroad_event_materialization_bytes(
            3*new,923_664_448,836_763_648,8192,17_429_035
        );
        let corrected=postroad_event_materialization_bytes(
            owners,923_664_448,836_763_648,8192,17_429_035
        );
        let original_cap=5_025_214_575usize;
        assert!(old>original_cap);
        assert!(corrected<original_cap);
        assert!(old-corrected>=494_519_936);
    }
}

#[cfg(test)]
mod surgical_optional_keyset_gate_20261122_tests {
    use super::*;
    fn p(x:f64)->PacketParts{
        PacketParts::Uniform {
            a:PackedTime::new(Some(-0.)).unwrap(),
            b:PackedTime::new(Some(1.)).unwrap(),
            rows:Arc::new((0..32).map(|j|CorePart{
                tag:(j%17) as u32,offset:(j/17) as u32,
                mass: if j==0{f64::from_bits(1)}else{x+j as f64},
                birth: if j==0{-0.0}else{x*j as f64/3.},
            }).collect()),
        }
    }
    fn state()->RoadState{
        RoadState {t:1.,cells:vec![Cell{v:[0.;8],packets:
            vec![Packet{target:0.,parts:p(0.25)},Packet{target:1.,parts:p(0.5)}],
            latent:BTreeMap::new()}],pending:vec![vec![]],
            totals:[0.;7],ledger:vec![]}
    }
    fn bits(s:&RoadState)->Vec<Vec<(usize,usize,u64,u64,u64,u64)>> {
        s.cells[0].packets.iter().map(|p|p.parts.iter().map(|v|
            (v.tag,v.offset,v.mass.to_bits(),v.birth.to_bits(),v.a.0,v.b.0)
        ).collect()).collect()
    }
    #[test]
    fn under_budget_optional_keyset_defers_without_touching_original_physics() {
        let mut s=state();
        let expected=bits(&s);
        let (changed,deferred)=maybe_intern_exact_keysets(&mut s,1000,1001).unwrap();
        assert_eq!(changed,0);
        assert!(deferred);
        assert_eq!(bits(&s),expected);
        assert!(s.cells[0].packets.iter().all(|p|
            matches!(p.parts,PacketParts::Uniform{..})));
        let (changed,deferred)=maybe_intern_exact_keysets(&mut s,1001,1001).unwrap();
        assert!(changed>=2 && !deferred);
        assert_eq!(bits(&s),expected);
        assert!(matches!(s.cells[0].packets[0].parts,PacketParts::SharedKeys{..}));
        assert!(matches!(s.cells[0].packets[1].parts,PacketParts::SharedKeys{..}));
    }
}

#[cfg(test)]
mod v03_compact_source_diagnostic_r10_20261122_tests {
    use super::*;

    #[test]
    fn nonphysical_lineage_key_is_exact_injective_16_bytes_instead_of_24() {
        assert_eq!(std::mem::size_of::<(usize,usize,u64)>(),24);
        assert_eq!(std::mem::size_of::<CompactDiagnosticSource>(),16);
        let value=compact_diagnostic_source_id(1585,16_777_217,0x8000_0000_0000_0000).unwrap();
        assert_eq!(value,(1585u32,16_777_217u32,0x8000_0000_0000_0000u64));
        assert!(compact_diagnostic_source_id(
            (u32::MAX as usize)+1,1,0).is_err());
        assert!(compact_diagnostic_source_id(
            1,(u32::MAX as usize)+1,0).is_err());
    }
    #[test]
    fn pending_sentinel_and_lexicographic_source_set_order_preserved() {
        let compact=vec![
            compact_diagnostic_source_id(3,4,0).unwrap(),
            compact_diagnostic_source_id(0,9,u64::MAX).unwrap(),
            pending_diagnostic_source_id(11).unwrap(),
            compact_diagnostic_source_id(3,4,1).unwrap(),
        ];
        assert_eq!(compact[2],(u32::MAX,11u32,0u64));
        let mut order=compact.clone();
        order.sort();
        let mut reference=vec![
            (3usize,4usize,0u64),
            (0usize,9usize,u64::MAX),
            (usize::MAX,11usize,0u64),
            (3usize,4usize,1u64),
        ];
        reference.sort();
        let expanded:Vec<_>=order.iter().map(|&(cell,head,rate)|
            (if cell==u32::MAX {usize::MAX}else{cell as usize},head as usize,rate)
        ).collect();
        assert_eq!(expanded,reference);
    }
}

#[cfg(test)]
mod v03_sequential_source_header_peaks_20261122_tests {
    use super::*;
    #[test]
    fn source_diag_reallocation_old_overlap_expires_before_header_realloc() {
        // During sequential diag reservations, 3 MiB of old backing may be
        // briefly live, but this buffer dies before later diag destinations
        // are grown to the FINAL source capacities. At Part/Mark header
        // growth only one physical old header allocation may overlap.
        let diag_final=409_447_072usize;
        let actual_source_diag_peak=409_451_168usize;
        let old_part_header=3_063_872usize;
        let scratch=20_080usize;
        let true_max_peak_extra=source_sequential_header_overlap_extra(
            actual_source_diag_peak,diag_final,old_part_header,scratch,
        );
        assert_eq!(true_max_peak_extra,3_083_952);
        let fictitious_pile=3_063_872+4_096+scratch;
        assert!(true_max_peak_extra<=fictitious_pile);
        // If Part/Mark never reallocates, the final diag source alone does
        // NOT co-exist with the old 3MiB diag backing; measured max matters.
        assert_eq!(source_sequential_header_overlap_extra(
            diag_final+4_096,diag_final,0,scratch),24_176);
    }
    #[test]
    fn real_old_plus_new_header_growth_must_still_be_charged_in_full() {
        assert_eq!(source_sequential_header_overlap_extra(1000,500,400,0),500);
        assert_eq!(source_sequential_header_overlap_extra(300,500,400,0),400);
        assert_eq!(source_sequential_header_overlap_extra(0,0,0,0),0);
    }
}

#[cfg(test)]
mod v03_paged_source_lineage_surgical_20261122_tests {
    use super::*;
    #[test]
    fn diagnostic_source_pages_retain_all_lineage_keys_and_order_across_boundaries() {
        let mut source=ChunkedDiagnosticSource::default();
        let target=3*DIAGNOSTIC_SOURCE_CHUNK+17;
        source.reserve_source_rows(target).unwrap();
        assert!(source.capacity_rows()>=target);
        assert!(source.capacity_bytes()>=target*
            std::mem::size_of::<CompactDiagnosticSource>());
        for k in 0..target {
            source.push(compact_diagnostic_source_id(
                k%31,k/31,(k as u64) ^ 0x8000_0000_0000_0000
            ).unwrap()).unwrap();
        }
        assert_eq!(source.len(),target);
        assert!(source.verify_capacity_bytes().is_ok());
        for (i,&source_row) in source.iter().enumerate() {
            assert_eq!(source_row,(
                (i%31) as u32,(i/31) as u32,
                (i as u64)^0x8000_0000_0000_0000
            ));
        }
        source.push(pending_diagnostic_source_id(target).unwrap()).unwrap();
        assert_eq!(source.len(),target+1);
        assert!(source.capacity_bytes()<2*target*
            std::mem::size_of::<CompactDiagnosticSource>()
            + 3*DIAGNOSTIC_SOURCE_CHUNK*
              std::mem::size_of::<CompactDiagnosticSource>());
    }
    #[test]
    fn only_a_bounded_page_header_can_reallocate_not_a_giant_contiguous_lineage_vec() {
        let mut source=ChunkedDiagnosticSource::default();
        let mut largest_previous_header=0;
        let mut observed_max_payload=0;
        for i in 1..=32 {
            let old=source.capacity_bytes();
            let overlap=source.reserve_source_rows(
                i*DIAGNOSTIC_SOURCE_CHUNK).unwrap();
            largest_previous_header=largest_previous_header.max(overlap);
            observed_max_payload=observed_max_payload.max(source.capacity_bytes());
            assert!(source.capacity_bytes()>=old);
        }
        assert!(largest_previous_header<
            DIAGNOSTIC_SOURCE_CHUNK*std::mem::size_of::<CompactDiagnosticSource>());
        assert!(observed_max_payload>0);
    }
}

#[cfg(test)]
mod v03_exact_narrow_source_sweep_20261122_tests {
    use super::*;
    #[test]
    fn exact_event_index_preflight_reduces_real_100k_source_metadata_not_physical_parts() {
        assert_eq!(std::mem::size_of::<u32>(),4);
        let n=2_000_000usize;
        let bits=n.div_ceil(64).saturating_add(n.div_ceil(4096))*8;
        assert_eq!(exact_sweep_event_index_bytes(n,n,0),n*8+bits+256);
        assert_eq!(exact_sweep_event_index_bytes(n,0,n),n*12+bits+256);
        assert_eq!(sweep_index_from_usize(u32::MAX as usize).unwrap(),u32::MAX);
        assert!(sweep_index_from_usize((u32::MAX as usize)+1).is_err());
    }

    #[test]
    fn original_signed_zero_event_order_and_index_tie_bits_unchanged() {
        let part=|a:f64,b:f64|Part{
            tag:0,offset:0,mass:0.125,birth:-0.0,
            a:PackedTime::new(Some(a)).unwrap(),
            b:PackedTime::new(Some(b)).unwrap(),
        };
        let rows=vec![
            part(-0.,2.),part(0.,1.),part(-0.,-0.),
            part(0.,0.),part(1.,2.),part(2.,2.),
        ];
        let sw=IntervalActiveSweep::new(&rows).unwrap();
        assert_eq!(sw.starts,[0u32,1u32,4u32]);
        assert_eq!(sw.ends,[1u32,0u32,4u32]);
        assert_eq!(sw.points,[2u32,3u32,5u32]);
        let times=sw.starts.iter().map(|&i|rows[i as usize].a.unwrap().to_bits()).collect::<Vec<_>>();
        assert_eq!(times,vec![(-0.0f64).to_bits(),0.0f64.to_bits(),1.0f64.to_bits()]);
        let original=rows.iter().map(|p|(p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)).collect::<Vec<_>>();
        assert_eq!(original[0].1,(-0.0f64).to_bits());
        assert_eq!(original[2].2,(-0.0f64).to_bits());
    }
}

#[cfg(test)]
mod v03_surgical_exact_interval_owner_lifetime_20261122_tests {
    use super::*;

    fn bounded_source(cap:usize)->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(cap),base:1000,
            transfer_exclusive_cell_scratch:400,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,
            diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:0,
            incoming_cell_rows:Some(Vec::new()),
            incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:Some(0),
            compact_events:false,narrow_events:false,compact_incoming:false,
            interval_retained:0,interval_transient:0,
            service_events:None,
        }
    }
    #[test]
    fn completed_cell_combine_replaces_both_hypothetical_max_scratch_with_one_real_source() {
        let incoming=segmented_incoming_exact_cell_pages_charge(
            0,0,0,false,Some(0));
        let actual=750+20+incoming;
        let mut work=bounded_source(actual);
        // In other phases the OLD conservative full source budget remains.
        assert!(work.require(20,"indexed sweep preflight").is_err());
        let result=work.with_completed_source_interval(150,|w|{
            assert_eq!(w.base,750);
            w.require(20,"indexed sweep preflight")?;
            w.require(20,"interval edges and indexed sweep")?;
            Ok(17)
        });
        assert_eq!(result.unwrap(),17);
        assert_eq!(work.base,1000);
        assert!(work.require(20,"indexed sweep preflight").is_err());
    }
    #[test]
    fn scoped_source_reverts_on_resource_failure_and_keeps_true_one_byte_gate() {
        let incoming=segmented_incoming_exact_cell_pages_charge(
            0,0,0,false,Some(0));
        let actual=750+20+incoming;
        let mut work=bounded_source(actual-1);
        let failure=work.with_completed_source_interval(150,|w|{
            w.require(20,"indexed sweep preflight")
        });
        assert!(failure.is_err());
        assert_eq!(work.base,1000);
    }
    #[test]
    fn unverified_precombine_phase_may_not_claim_source_expiry() {
        let mut work=bounded_source(770);
        work.incoming_descriptor_live_bytes=None;
        assert!(work.with_completed_source_interval(150,|w|{
            w.require(20,"indexed sweep preflight")
        }).is_err());
        assert_eq!(work.base,1000);
    }
}

#[cfg(test)]
mod v03_cell_packet_after_interval_exact_source_20261122_tests {
    use super::*;

    fn make_budget(limit:usize)->RoadWorkBudget {
        RoadWorkBudget {
            limit:Some(limit),base:1000,transfer_exclusive_cell_scratch:400,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,
            diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,events:0,incoming:0,
            incoming_page_cells:0,incoming_cell_rows:Some(Vec::new()),
            incoming_live_pages:0,incoming_direct_cell_rows:None,incoming_direct_live_pages:0,incoming_outer_bytes:0,incoming_descriptor_live_bytes:Some(0),
            compact_events:false,narrow_events:false,compact_incoming:false,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }
    #[test]
    fn old_combine_not_simultaneous_with_true_cell_packet_slot_growth() {
        let incoming=segmented_incoming_exact_cell_pages_charge(
            0,0,0,false,Some(0));
        let source_required=600+20+incoming;
        let mut work=make_budget(source_required);
        assert!(work.require(20,"cell packet reservation").is_err());
        assert!(work.require_completed_interval_cell_slot(20).is_ok());
        assert_eq!(work.base,1000);
        assert!(work.require(20,"cell packet reservation").is_err());
    }
    #[test]
    fn truly_insufficient_cell_slot_budget_rejected_and_full_base_restored() {
        let incoming=segmented_incoming_exact_cell_pages_charge(
            0,0,0,false,Some(0));
        let mut work=make_budget(600+20+incoming-1);
        assert!(work.require_completed_interval_cell_slot(20).is_err());
        assert_eq!(work.base,1000);
    }
    #[test]
    fn active_interval_or_unfrozen_source_cannot_claim_source_scratch_expired() {
        let mut work=make_budget(10000);
        work.interval_transient=1;
        assert!(work.require_completed_interval_cell_slot(20).is_err());
        work.interval_transient=0;
        work.incoming_descriptor_live_bytes=None;
        assert!(work.require_completed_interval_cell_slot(20).is_err());
        assert_eq!(work.base,1000);
    }
}

#[cfg(test)]
mod v03_original_postroad_actual_shared_arc_source_20261122_tests {
    use super::*;
    fn state()->RoadState {
        let parts=PacketParts::pack(vec![Part{
            tag:1,offset:0,mass:f64::from_bits(1),birth:-0.0,
            a:PackedTime::new(Some(1.0)).unwrap(),
            b:PackedTime::new(Some(2.0)).unwrap(),
        }], |_|Ok(())).unwrap();
        RoadState {
            t:2.0,cells:vec![Cell{v:[0.;8],
                packets:vec![Packet{target:3.0,parts}],
                latent:BTreeMap::new()}],
            pending:vec![vec![]],totals:[0.;7],ledger:vec![],
        }
    }
    #[test]
    fn true_source_current_candidate_arc_alias_credit_charges_once_only() {
        let supplied=state();
        let committed=supplied.clone();
        let candidate=committed.clone();
        let credit=committed.paired_shared_payload_lower_bound(&supplied);
        let shared=committed.paired_shared_payload_lower_bound(&candidate);
        assert_eq!(credit,std::mem::size_of::<CorePart>());
        assert_eq!(credit,shared);
        let (charged,src,cand)=postroad_source_verified_arc_owner_charge(
            &committed,&candidate,supplied.retained_storage_bytes(),
            Some((supplied.t,credit)),
        );
        let old=postroad_materialization_owner_bytes(
            committed.retained_storage_bytes(),supplied.retained_storage_bytes(),
            candidate.retained_storage_bytes(),
        );
        assert_eq!(src,credit);
        assert_eq!(cand,shared);
        assert_eq!(charged+credit+shared,old);
        assert!(charged<old);
    }
    #[test]
    fn independent_identical_values_and_stale_input_clock_cannot_claim_arcs() {
        let src=state();
        let committed=state();
        let candidate=state();
        let old=postroad_materialization_owner_bytes(
            committed.retained_storage_bytes(),src.retained_storage_bytes(),
            candidate.retained_storage_bytes());
        let (charged,a,b)=postroad_source_verified_arc_owner_charge(
            &committed,&candidate,src.retained_storage_bytes(),
            Some((src.t,committed.paired_shared_payload_lower_bound(&src))));
        assert_eq!((charged,a,b),(old,0,0));
        let shared=committed.clone();
        let (charged2,a2,b2)=postroad_source_verified_arc_owner_charge(
            &committed,&shared,src.retained_storage_bytes(),
            Some((src.t-10.0,1024*1024)));
        assert_eq!(a2,0);
        assert_eq!(b2,std::mem::size_of::<CorePart>());
        assert_eq!(charged2+b2,old);
    }
}

#[cfg(test)]
mod v03_service_live_source_arc_owner_20261122_tests {
    use super::*;
    #[test]
    fn coupled_service_owner_requires_three_real_owners_and_two_proven_overlaps() {
        let packet=PacketParts::pack(vec![Part{
            tag:1,offset:0,mass:1.0,birth:0.0,
            a:PackedTime::new(Some(1.0)).unwrap(),
            b:PackedTime::new(Some(1.0)).unwrap(),
        }], |_|Ok(())).unwrap();
        let old=RoadState{
            t:1.0,cells:vec![Cell{
                v:[0.;8],packets:vec![Packet{target:3.0,parts:packet}],
                latent:BTreeMap::new(),
            }],pending:vec![vec![]],totals:[0.;7],ledger:vec![],
        };
        let new=old.clone();
        let original=old.clone();
        let overlap=old.paired_shared_payload_lower_bound(&original);
        assert!(overlap>0);
        let (charge,a,b)=source_road_service_joint_live_owner_charge(
            &old,&new,original.retained_storage_bytes(),Some((original.t,overlap))
        );
        assert_eq!(a,b);
        assert_eq!(a,std::mem::size_of::<CorePart>());
        assert_eq!(charge+2*a,old.retained_storage_bytes()*3);
        let (without_source,c,_)=source_road_service_joint_live_owner_charge(
            &old,&new,original.retained_storage_bytes(),None);
        assert_eq!(c,0);
        assert_eq!(without_source,charge+a);
    }
}

#[cfg(test)]
mod v03_replay_length_guard_diagnostic_20261122_tests {
    use super::*;
    use std::io::Cursor;
    #[test]
    fn physically_saved_wire_replay_reports_exact_length_and_current_guard() {
        pyo3::prepare_freethreaded_python();
        let mut stream=Cursor::new(25u64.to_le_bytes().to_vec());
        let err=read_len(&mut stream,20).unwrap_err();
        let message=err.to_string();
        assert!(message.contains("native checkpoint length exceeds configuration/budget"));
        assert!(message.contains("observed_length=25"));
        assert!(message.contains("allowed_length=20"));
    }
    #[test]
    fn structural_original_length_cap_remains_enforced() {
        let mut stream=Cursor::new(20u64.to_le_bytes().to_vec());
        assert_eq!(read_len(&mut stream,20).unwrap(),20);
        let mut stream=Cursor::new(21u64.to_le_bytes().to_vec());
        assert!(read_len(&mut stream,20).is_err());
    }
}

#[cfg(test)]
mod v03_checked_compact_page_destination_projection_20261122_tests {
    use super::*;
    #[test]
    fn real_original_header_projection_uses_four_byte_checked_cell_index() {
        assert_eq!(std::mem::size_of::<usize>(),8);
        assert_eq!(std::mem::size_of::<u32>(),4);
        assert_eq!(checked_page_destination_index(0).unwrap(),0);
        assert_eq!(checked_page_destination_index(1435).unwrap(),1435);
        assert_eq!(checked_page_destination_index(u32::MAX as usize-1).unwrap(),u32::MAX-1);
        assert!(checked_page_destination_index(u32::MAX as usize).is_err());
        assert!(checked_page_destination_index(u32::MAX as usize+1).is_err());
    }
    #[test]
    fn legacy_physical_header_reservations_keep_full_original_cell_order() {
        let mut actual=Vec::new();
        for cell in [4usize,3,4,4,1,2,9,3,2,0] {
            actual.push(checked_page_destination_index(cell).unwrap());
        }
        assert_eq!(actual,vec![4u32,3,4,4,1,2,9,3,2,0]);
        assert_eq!(actual.iter().map(|&i|i as usize).collect::<Vec<_>>(),
                   vec![4usize,3,4,4,1,2,9,3,2,0]);
    }
}

#[cfg(test)]
mod persistent_event_page_contract_20261123_tests {
    use super::*;
    fn row(i:usize)->EventRow {
        (i%19,i%11,if i%7==0 {None} else {Some(i%23)},
         if i%3==0 {f64::from_bits(1)} else {0.125},
         if i%5==0 {-0.0} else {2.0},3.0,0.25)
    }
    fn bits(e:EventRow)->(usize,usize,Option<usize>,[u64;4]) {
        (e.0,e.1,e.2,[e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits()])
    }
    #[test]
    fn decoded_pages_keep_bits_order_exact_final_capacity_and_upper_bound() {
        for compact in [false,true] {
            for n in [0usize,1,4095,4096,4097,8193,20011] {
                let mut store=ChunkedEvents::new(compact);
                for i in 0..n {store.push_decoded_checked(row(i),n).unwrap();}
                assert_eq!(store.len(),n);
                assert_eq!(store.capacity(),n);
                assert_eq!(store.iter().map(bits).collect::<Vec<_>>(),
                           (0..n).map(row).map(bits).collect::<Vec<_>>());
                assert!(store.storage_bytes()<=decoded_event_store_upper_bytes(n,compact));
            }
        }
    }
    #[test]
    fn wide_registry_mode_preserves_usize_and_reserved_none_distinction() {
        let original=(u32::MAX as usize+1,u32::MAX as usize+2,
                      Some(u32::MAX as usize),-0.0,1.0,2.0,f64::from_bits(1));
        let mut wide=ChunkedEvents::new(false);
        wide.push_decoded_checked(original,1).unwrap();
        assert_eq!(bits(wide.iter().next().unwrap()),bits(original));
        let mut compact=ChunkedEvents::new(true);
        assert!(compact.push_decoded_checked(original,1).is_err());
        assert_eq!(compact.len(),0);
        let boundary=(u32::MAX as usize,u32::MAX as usize,Some(u32::MAX as usize-1),
                      1.0,2.0,3.0,4.0);
        compact.push_decoded_checked(boundary,1).unwrap();
        assert_eq!(bits(compact.iter().next().unwrap()),bits(boundary));
    }
    #[test]
    fn existing_page_backings_survive_persistent_candidate_growth() {
        let mut store=ChunkedEvents::new(true);
        for i in 0..4096 {store.push_checked(row(i)).unwrap();}
        let pointer=store.compact_chunks[0].as_ptr();
        for i in 4096..8193 {store.push_checked(row(i)).unwrap();}
        assert_eq!(pointer,store.compact_chunks[0].as_ptr());
        assert!(store.storage_bytes()<=persistent_event_candidate_upper_bytes(8193,true));
        assert_eq!(store.physical_capacity_bytes(),3*4096*std::mem::size_of::<NarrowEventRow>());
        assert!(decoded_event_store_upper_bytes(20_270_113,true)
                <20_270_113usize*64);
    }
}

#[cfg(test)]
mod v03_frozen_queue_source_ownership_20261123_tests {
    use super::*;

    fn source_road() -> V1Road {
        let mut road=V1Road::new(
            "frozen-queue-source-owner".to_string(),1.0,
            vec![vec![1_000_000.0,1.0,100_000.0,100_000.0,100_000.0,1.0]],
            vec![None],vec![(vec![0],0)],vec![vec![1.0;13]],
            vec![vec![0]],vec![],100_000,Some(100_000),true,
        ).unwrap();
        let packed=|count:usize| PacketParts::pack(
            (0..count).map(|_|Part{
                tag:0,offset:0,mass:1.0/256.0,birth:-0.0,
                a:PackedTime::new(Some(-0.0)).unwrap(),
                b:PackedTime::new(Some(0.0)).unwrap(),
            }).collect(), |_|Ok(())
        ).unwrap();
        road.state.cells[0].packets=vec![
            Packet{target:0.0,parts:packed(128)},
            Packet{target:1_000_000.0,parts:packed(4096)},
        ];
        road.state.cells[0].v[2]=4224.0/256.0;
        road.state.cells[0].v[7]=1.0;
        road.state.cells[0].latent.insert(0,0.0);
        road.state.totals[0]=4224.0/256.0;
        road.state.ledger[0][0]=4224.0/256.0;
        road
    }

    #[test]
    fn later_tick_cannot_reuse_original_restore_clock_arc_overlap() {
        pyo3::prepare_freethreaded_python();
        let mut road=source_road();
        road.set_phase_storage_budget(1_000_000_000).unwrap();
        road.begin_call_storage_accounting();
        let held_original=road.state.clone();
        let verified=road.committed_input_source_arc_credit(&held_original);
        assert!(verified>0);
        road.configure_service_event_accounting(
            0,0,true,Some((held_original.t,verified)),
        );
        let first=road.work_budget(&road.state,&[]).unwrap().base;
        // The previous source proof names clock zero; self identity at a
        // later committed clock cannot establish sharing with held_original.
        road.state.t=1.0;
        let later=road.work_budget(&road.state,&[]).unwrap().base;
        assert_eq!(later,first+verified,
            "the old input proof must expire even when state == self.state");
    }

    fn queue(source:&RoadState,readiness:&[f64])->Vec<Vec<(Packet,f64)>> {
        assert_eq!(source.cells.len(),1);
        assert_eq!(source.cells[0].packets.len(),readiness.len());
        vec![source.cells[0].packets.iter().zip(readiness)
            .map(|(p,&ready)|(clone_packet(p).unwrap(),ready)).collect()]
    }

    fn admitted_work(road:&mut V1Road)->RoadWorkBudget {
        road.set_phase_storage_budget(1_000_000_000).unwrap();
        road.work_budget(&road.state,&[]).unwrap()
    }

    #[test]
    fn only_pointer_shared_infinite_readiness_backings_are_credited_once() {
        let mut road=source_road();
        let frozen=road.state.cells[0].packets[1].parts.clone();
        road.state.cells[0].packets.push(Packet{target:2_000_000.0,parts:frozen.clone()});
        let mut q=queue(&road.state,&[0.0,f64::INFINITY,f64::INFINITY]);
        let mut work=admitted_work(&mut road);
        work.witness_frozen_queue_owners(&road.state,&q).unwrap();
        assert_eq!(work.frozen_queue_payload_credit,frozen.allocated_bytes());
        // A same-valued independently allocated owner is never an alias.
        q[0][1].0.parts=PacketParts::pack(frozen.iter().collect(),|_|Ok(())).unwrap();
        q[0][2].1=10_000.0; // even certainly late finite values receive no credit
        let mut independent=admitted_work(&mut road);
        independent.witness_frozen_queue_owners(&road.state,&q).unwrap();
        assert_eq!(independent.frozen_queue_payload_credit,0);
        q[0][0].1=f64::NEG_INFINITY;
        let mut negative=admitted_work(&mut road);
        negative.witness_frozen_queue_owners(&road.state,&q).unwrap();
        assert_eq!(negative.frozen_queue_payload_credit,0);
    }

    #[test]
    fn shared_keys_duplicate_only_once_and_wide_backing_keeps_actual_capacity() {
        let mut road=source_road();
        let keys=Arc::new(vec![(0u32,0u32),(0,0)]);
        let moments=Arc::new(vec![(0.25,-0.0),(0.75,0.0)]);
        let times=PackedTime::new(Some(0.0)).unwrap();
        let shared=PacketParts::SharedKeys{
            a:times,b:times,keys:keys.clone(),moments:moments.clone(),
        };
        let second=PacketParts::SharedKeys{
            a:times,b:times,keys:keys.clone(),
            moments:Arc::new(vec![(0.125,0.0),(0.875,0.0)]),
        };
        let mut wide_rows=checkpoint_vec::<Part>(23).unwrap();
        wide_rows.push(Part{
            tag:u32::MAX as usize+1,offset:0,mass:1.0,birth:-0.0,a:times,b:times,
        });
        let wide=PacketParts::pack(wide_rows,|_|Ok(())).unwrap();
        assert!(matches!(wide,PacketParts::Mixed(_)));
        road.state.cells[0].packets=vec![shared.clone(),shared,second,wide]
            .into_iter().map(|parts|Packet{target:1_000_000.0,parts}).collect();
        let q=queue(&road.state,&[f64::INFINITY;4]);
        let expected=RoadState::arc_backing_union(&[&road.state]).unique_payload_bytes;
        let mut work=admitted_work(&mut road);
        work.witness_frozen_queue_owners(&road.state,&q).unwrap();
        assert_eq!(work.frozen_queue_payload_credit,expected);
        assert!(expected>23*std::mem::size_of::<Part>());
        // All numerical payloads, including signed zero, remain untouched.
        assert_eq!(moments[0].1.to_bits(),(-0.0f64).to_bits());
    }

    #[test]
    fn census_scratch_is_admitted_before_credit_and_guard_remains_exact() {
        pyo3::prepare_freethreaded_python();
        let mut road=source_road();
        let q=queue(&road.state,&[0.0,f64::INFINITY]);
        let mut blocked=admitted_work(&mut road);
        blocked.limit=Some(0);
        let error=blocked.witness_frozen_queue_owners(&road.state,&q).unwrap_err();
        assert!(error.to_string().contains("frozen queue Arc census"));
        assert_eq!(blocked.frozen_queue_payload_credit,0);
        let mut work=admitted_work(&mut road);
        work.witness_frozen_queue_owners(&road.state,&q).unwrap();
        let credit=work.frozen_queue_payload_credit;
        assert!(credit>0);
        // Observe the actual demand through the same native guard, then
        // verify the unchanged byte cap admits equality and rejects +1 B.
        work.limit=Some(0);
        let err=work.require(0,"transfer candidates").unwrap_err().to_string();
        let demand=err.split("required_bytes=").nth(1).unwrap()
            .split(',').next().unwrap().parse::<usize>().unwrap();
        work.limit=Some(demand);
        assert!(work.require(0,"transfer candidates").is_ok());
        assert!(work.require(1,"transfer candidates").is_err());
        work.frozen_queue_payload_credit=0;
        assert!(work.require(0,"transfer candidates").is_err());
        assert!(credit<work.base);
    }

    #[test]
    fn infinite_queue_witness_preserves_full_tick_wire_event_bits_and_input() {
        pyo3::prepare_freethreaded_python();
        let mut reference=source_road();
        let mut bounded=source_road();
        reference.check_state(&reference.state).unwrap();
        bounded.set_phase_storage_budget(1_000_000_000).unwrap();
        bounded.begin_call_storage_accounting();
        let source=bounded.state.clone();
        let overlap=bounded.committed_input_source_arc_credit(&source);
        bounded.configure_service_event_accounting(0,0,true,Some((source.t,overlap)));
        let mut input_wire=Vec::new();
        bounded.write_state(&mut input_wire).unwrap();
        let (ref_state,ref_pages)=reference.step_state(&reference.state,1.0,vec![]).unwrap();
        let (new_state,new_pages)=bounded.propose_owned_step(1.0,vec![]).unwrap();
        let bits=|e:EventRow|(e.0,e.1,e.2,e.3.to_bits(),e.4.to_bits(),
            e.5.to_bits(),e.6.to_bits());
        assert_eq!(ref_pages.iter().map(bits).collect::<Vec<_>>(),
            new_pages.iter().map(bits).collect::<Vec<_>>());
        assert_eq!(new_pages.len(),128);
        let mut still_input=Vec::new();
        bounded.write_state(&mut still_input).unwrap();
        assert_eq!(input_wire,still_input,"propose must preserve its immutable source");
        assert!(Arc::ptr_eq(
            match &source.cells[0].packets[1].parts {PacketParts::Uniform{rows,..}=>rows,_=>unreachable!()},
            match &new_state.cells[0].packets[0].parts {PacketParts::Uniform{rows,..}=>rows,_=>unreachable!()},
        ));
        reference.state=ref_state;
        bounded.state=new_state;
        let mut reference_wire=Vec::new();
        let mut candidate_wire=Vec::new();
        reference.write_state(&mut reference_wire).unwrap();
        bounded.write_state(&mut candidate_wire).unwrap();
        assert_eq!(reference_wire,candidate_wire);
    }

    #[test]
    fn infinite_readiness_never_becomes_a_head_at_any_finite_clock() {
        for (hi,lo,active) in [(0.0,0.0,false),(1.0,0.0,false),
            (25_720.0,-f64::EPSILON,true),(f64::MAX,0.0,true)] {
            let clock=EventClock{hi,lo,active,..EventClock::default()};
            assert!(clock.after_ready(f64::INFINITY));
        }
    }
}

#[cfg(test)]
mod v03_event_backed_incoming_20261123_tests {
    use super::*;

    fn transfer_road(limit:Option<usize>)->V1Road {
        let sources=100usize;
        let rows=100usize;
        let mut road=V1Road::new(
            "event-backed-incoming-source".to_string(),1.0,
            vec![vec![1_000_000.0,1.0,100_000.0,100_000.0,100_000.0,1.0];sources+1],
            vec![None;sources+1],
            (0..sources).map(|i|(vec![i,sources],0)).collect(),
            vec![vec![1.0;13]],vec![(0..sources+1).collect()],vec![],
            100_000,Some(100_000),true,
        ).unwrap();
        for i in 0..sources {
            let payload=PacketParts::pack((0..rows).map(|_|Part{
                tag:i,offset:0,mass:1.0/256.0,birth:-0.0,
                a:PackedTime::new(Some(-0.0)).unwrap(),
                b:PackedTime::new(Some(0.0)).unwrap(),
            }).collect(),|_|Ok(())).unwrap();
            road.state.cells[i].packets.push(Packet{target:0.0,parts:payload});
            road.state.cells[i].v[2]=rows as f64/256.0;
            road.state.cells[i].v[7]=1.0;
            road.state.cells[i].latent.insert(0,0.0);
        }
        road.state.totals[0]=(sources*rows) as f64/256.0;
        road.state.ledger[0][0]=road.state.totals[0];
        if let Some(limit)=limit {
            road.set_phase_storage_budget(limit).unwrap();
            road.begin_call_storage_accounting();
            let original=road.state.clone();
            let overlap=road.committed_input_source_arc_credit(&original);
            road.configure_service_event_accounting(0,0,true,Some((original.t,overlap)));
        }
        road
    }

    #[test]
    fn original_service_transfer_fits_cap_by_reusing_event_bits() {
        pyo3::prepare_freethreaded_python();
        let road=transfer_road(Some(2_300_000));
        let result=road.propose_owned_step(1.0,vec![]);
        if let Err(ref error)=result {
            panic!("original 10000-row source should fit unchanged cap: {error}");
        }
        let (candidate,events)=result.unwrap();
        assert_eq!(events.len(),10_000);
        assert_eq!(candidate.t,1.0);
        assert_eq!(road.state.t,0.0);
        road.check_state(&candidate).unwrap();
    }

    fn part_bits(p:Part)->(usize,usize,u64,u64,u64,u64) {
        (p.tag,p.offset,p.mass.to_bits(),p.birth.to_bits(),p.a.0,p.b.0)
    }
    fn event_bits(e:EventRow)->(usize,usize,Option<usize>,u64,u64,u64,u64) {
        (e.0,e.1,e.2,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits())
    }
    fn row(i:usize)->Part {
        Part{tag:i%19,offset:i%7,
            mass:match i%5 {0=>f64::from_bits(1),1=>1e-100,2=>1e100,_=>0.125},
            birth:if i%2==0 {-0.0}else{0.25},
            a:PackedTime::new(Some(if i%2==0 {-0.0}else{0.0})).unwrap(),
            b:PackedTime::new(Some((i%3+1) as f64)).unwrap()}
    }
    fn source_event(p:Part)->EventRow {
        (p.tag,2,Some(3),p.mass,p.a.unwrap(),p.b.unwrap(),p.birth)
    }
    fn reference_work(cells:usize)->RoadWorkBudget {
        RoadWorkBudget{
            limit:Some(1_000_000_000),base:0,transfer_exclusive_cell_scratch:0,
            row_scan_scratch_bytes:0,expired_motion_scan_credit:0,
            diagnostic_source_live_bytes:0,frozen_queue_payload_credit:0,
            events:0,incoming:0,incoming_page_cells:cells,
            incoming_cell_rows:Some(vec![0;cells]),incoming_live_pages:0,
            incoming_direct_cell_rows:Some(vec![0;cells]),
            incoming_direct_live_pages:0,incoming_outer_bytes:0,
            incoming_descriptor_live_bytes:None,compact_events:true,narrow_events:false,compact_incoming:true,
            interval_retained:0,interval_transient:0,service_events:None,
        }
    }

    #[test]
    fn service_reference_pages_read_exact_four_f64_payloads_and_pending_spill() {
        let mut events=ChunkedEvents::new(true);
        let mut incoming=ChunkedParts::event_backed();
        let mut original=Vec::new();
        for i in 0..(2*EVENT_PAGE_ROWS+17) {
            let p=row(i);
            let actual=events.len();
            events.push_checked(source_event(p)).unwrap();
            incoming.push_serviced(actual,p,&events).unwrap();
            original.push(p);
        }
        assert_eq!(std::mem::size_of::<IncomingRowRef>(),8);
        assert_eq!(incoming.direct_len,0);
        assert_eq!(incoming.physical_capacity_bytes(),incoming.capacity()*8);
        // Event values are not recomputed when pages or the owner move.
        let moved_events=events;
        for i in 0..133 {
            let mut p=row(i+5);
            p.a=PackedTime::new(None).unwrap();
            p.b=PackedTime::new(None).unwrap();
            incoming.push_checked(p).unwrap();
            original.push(p);
        }
        let view=incoming.view(&moved_events).unwrap();
        assert_eq!(view.iter().map(part_bits).collect::<Vec<_>>(),
            original.iter().copied().map(part_bits).collect::<Vec<_>>());
        assert_eq!(incoming.direct_len,133);
        assert_eq!(incoming.direct_capacity(),256);
        assert_eq!(incoming.physical_capacity_bytes(),
            incoming.capacity()*8+incoming.direct_capacity()*40);
        assert!(incoming.physical_capacity_bytes()<incoming.capacity()*40);
        let direct=combine(original).unwrap();
        let shared=combine_incoming_view(view).unwrap();
        assert_eq!(direct.into_iter().map(part_bits).collect::<Vec<_>>(),
            shared.into_iter().map(part_bits).collect::<Vec<_>>());
    }

    #[test]
    fn actual_reference_spill_pages_descriptors_and_release_match_projection() {
        let mut work=reference_work(3);
        let mut events=ChunkedEvents::new(true);
        let mut incoming:Vec<_>=(0..3).map(|_|ChunkedParts::event_backed()).collect();
        let mut marks:Vec<_>=(0..3).map(|_|ChunkedMarks::default()).collect();
        let mut expected=vec![Vec::new();3];
        let mut serial=0usize;
        for batch in [127usize,1,129,4000,19] {
            let destinations:Vec<_>=(0..batch).map(|k|(k+serial)%3).collect();
            // Deliberately overproject EventRows, as underflow-filtered
            // original service may do. References must use actual append
            // indices and never this admission counter.
            work.transfer_indexed_with_live_headers(batch+3,destinations.iter().copied(),
                &mut incoming,&mut marks).unwrap();
            for cell in destinations {
                let p=row(serial);
                let index=events.len();
                events.push_checked(source_event(p)).unwrap();
                incoming[cell].push_serviced(index,p,&events).unwrap();
                marks[cell].push_checked((1.25,0.375)).unwrap();
                expected[cell].push(p);
                serial+=1;
            }
            work.observed_incoming_descriptor_bytes(&incoming,&marks).unwrap();
        }
        assert!(work.events>events.len());
        for (cell,count) in [(2usize,1usize),(0,129),(2,128),(1,257)] {
            work.transfer_indexed_with_live_headers(0,std::iter::repeat(cell).take(count),
                &mut incoming,&mut marks).unwrap();
            for _ in 0..count {
                let mut p=row(serial);
                p.a=PackedTime::new(None).unwrap();
                p.b=PackedTime::new(None).unwrap();
                incoming[cell].push_checked(p).unwrap();
                marks[cell].push_checked((2.5,0.625)).unwrap();
                expected[cell].push(p);
                serial+=1;
            }
            work.observed_incoming_descriptor_bytes(&incoming,&marks).unwrap();
        }
        work.lock_completed_incoming_descriptors(&incoming,&marks).unwrap();
        let header:usize=incoming.iter().zip(&marks).map(|(p,m)|
            p.descriptor_capacity()*std::mem::size_of::<Vec<Part>>()
            +m.chunks.capacity()*std::mem::size_of::<Vec<Mark>>()).sum();
        let physical:usize=incoming.iter().zip(&marks).map(|(p,m)|
            p.physical_capacity_bytes()+m.capacity()*std::mem::size_of::<Mark>()).sum();
        assert_eq!(work.incoming_descriptor_live_bytes,Some(header));
        let charged=event_backed_incoming_page_charge(
            3,work.incoming_live_pages,work.incoming_direct_live_pages,Some(header));
        assert!(charged>=physical+header);
        for cell in 0..3 {
            let source=std::mem::take(&mut incoming[cell]);
            let mark=std::mem::take(&mut marks[cell]);
            let got=source.view(&events).unwrap().iter().map(part_bits).collect::<Vec<_>>();
            assert_eq!(got,expected[cell].iter().copied().map(part_bits).collect::<Vec<_>>());
            release_consumed_incoming_pair(&mut work,cell,source,mark).unwrap();
        }
        assert_eq!(work.incoming,0);
        assert_eq!(work.incoming_live_pages,0);
        assert_eq!(work.incoming_direct_live_pages,0);
        assert_eq!(work.incoming_descriptor_live_bytes,Some(0));
        assert!(work.incoming_direct_cell_rows.unwrap().iter().all(|&n|n==0));
    }

    #[test]
    fn wrong_expired_mismatched_and_unappended_event_sources_are_rejected() {
        pyo3::prepare_freethreaded_python();
        let mut events=ChunkedEvents::new(true);
        let p=row(4);
        events.push_checked(source_event(p)).unwrap();
        let mut incoming=ChunkedParts::event_backed();
        assert!(incoming.push_serviced(1,p,&events).is_err());
        assert!(incoming.push_serviced(u32::MAX as usize,p,&events).is_err());
        let mut wrong=p;
        wrong.birth=0.0; // source contains -0.0
        assert!(incoming.push_serviced(0,wrong,&events).is_err());
        assert_eq!(incoming.len(),0);
        incoming.push_serviced(0,p,&events).unwrap();
        let mut unrelated=ChunkedEvents::new(true);
        unrelated.push_checked(source_event(p)).unwrap();
        assert!(incoming.view(&unrelated).is_err());
        assert!(incoming.push_serviced(0,p,&unrelated).is_err());
        assert_eq!(incoming.len(),1);
        let weak=incoming.event_source.as_ref().unwrap().clone();
        {
            let view=incoming.view(&events).unwrap();
            assert_eq!(part_bits(view.get(0)),part_bits(p));
        }
        drop(events);
        assert!(weak.upgrade().is_none(),"Weak identity must not retain event data owner");
        assert!(incoming.view(&unrelated).is_err());
        assert!(combine_chunked_parts(&incoming).is_err());
    }

    #[test]
    fn decoded_short_last_page_and_source_identity_storage_remain_bounded() {
        let mut events=ChunkedEvents::new(true);
        let p=row(6);
        events.push_decoded_checked(source_event(p),1).unwrap();
        assert!(events.storage_bytes()<=decoded_event_store_upper_bytes(1,true));
        let next=row(7);
        events.push_checked(source_event(next)).unwrap();
        assert!(!events.fixed_page_indexing);
        assert_eq!(event_bits(events.get_checked(0).unwrap()),event_bits(source_event(p)));
        assert_eq!(event_bits(events.get_checked(1).unwrap()),event_bits(source_event(next)));
        assert!(events.get_checked(2).is_none());
        let mut incoming=ChunkedParts::event_backed();
        incoming.push_serviced(1,next,&events).unwrap();
        assert_eq!(part_bits(incoming.view(&events).unwrap().get(0)),part_bits(next));
        // Both the externally shared carrier Arc and the distinct token Arc
        // have separately retained control/padding in the empty bound.
        assert!(event_store_shell_bytes()>=std::mem::size_of::<ChunkedEvents>()
            +4*std::mem::size_of::<usize>()+256);
    }

    #[test]
    fn noninterval_unbounded_and_wide_paths_keep_original_direct_parts() {
        let mut road=transfer_road(None);
        assert!(!road.can_reference_incoming_events());
        road.set_phase_storage_budget(1_000_000_000).unwrap();
        road.intervals=false;
        assert!(!road.can_reference_incoming_events());
        road.intervals=true;
        road.set_phase_storage_budget((u32::MAX as usize+1)*std::mem::size_of::<EventRow>()).unwrap();
        assert!(!road.can_reference_incoming_events());
        let mut direct=ChunkedParts::new(false);
        let mut p=row(2);
        p.tag=u32::MAX as usize+1;
        p.offset=u32::MAX as usize+2;
        p.a=PackedTime::new(None).unwrap();
        p.b=PackedTime::new(None).unwrap();
        // A direct fallback does not depend on an event index or interval.
        direct.push_serviced(usize::MAX,p,&ChunkedEvents::default()).unwrap();
        assert_eq!(part_bits(direct.get(0)),part_bits(p));
        assert_eq!(direct.physical_capacity_bytes(),
            INCOMING_PART_CHUNK*std::mem::size_of::<Part>());
    }

    #[test]
    fn partial_service_pending_and_reference_path_preserve_input_and_final_wire() {
        pyo3::prepare_freethreaded_python();
        let mut original=transfer_road(None);
        let mut proposed=transfer_road(Some(1_000_000_000));
        for road in [&mut original,&mut proposed] {
            for group in &mut road.groups[..100] {group[3]=0.1;}
        }
        let offers=vec![(0usize,0.125,-0.0,None,None)];
        let mut input=Vec::new();
        proposed.write_state(&mut input).unwrap();
        let (old_state,old_events)=original.propose_owned_step(1.0,offers.clone()).unwrap();
        let (new_state,new_events)=proposed.propose_owned_step(1.0,offers).unwrap();
        assert_eq!(old_events.iter().map(event_bits).collect::<Vec<_>>(),
            new_events.iter().map(event_bits).collect::<Vec<_>>());
        let mut unchanged=Vec::new();
        proposed.write_state(&mut unchanged).unwrap();
        assert_eq!(input,unchanged);
        original.state=old_state;
        proposed.state=new_state;
        let mut old_wire=Vec::new();
        let mut new_wire=Vec::new();
        original.write_state(&mut old_wire).unwrap();
        proposed.write_state(&mut new_wire).unwrap();
        assert_eq!(old_wire,new_wire);
        assert_eq!(proposed.state.t,1.0);
        assert_eq!(new_events.len(),10_000);
    }

    #[test]
    fn narrow_original_event_payload_is_40_bytes_per_decoded_row() {
        let count=20_011usize;
        let mut events=ChunkedEvents::new(true);
        for i in 0..count {
            events.push_decoded_checked(source_event(row(i)),count).unwrap();
        }
        assert_eq!(events.physical_capacity_bytes(),count*40);
    }
    #[test]
    fn narrow_original_event_storage_passes_same_2000000_byte_physical_cap() {
        pyo3::prepare_freethreaded_python();
        let road=transfer_road(Some(2_000_000));
        let result=road.propose_owned_step(1.0,vec![]);
        if let Err(ref error)=result {
            panic!("original source requires exact narrow event storage: {error}");
        }
        let (candidate,events)=result.unwrap();
        assert_eq!(candidate.t,1.0);
        assert_eq!(events.len(),10_000);
        assert_eq!(road.state.t,0.0);
        road.check_state(&candidate).unwrap();
    }
}

#[cfg(test)]
mod v03_narrow_event_tier_20261123_tests {
    use super::*;
    use crate::v1_journey::NativeServiceCore;
    use std::io::Cursor;

    fn e(i:usize)->EventRow {
        (i%501,i%1586,if i%13==0 {None}else{Some(i%1586)},
            if i%7==0 {f64::from_bits(1)}else{0.125},
            if i%2==0 {-0.0}else{1.0},2.0,
            if i%3==0 {-0.0}else{f64::from_bits(3)})
    }
    fn bits(x:EventRow)->(usize,usize,Option<usize>,[u64;4]) {
        (x.0,x.1,x.2,[x.3.to_bits(),x.4.to_bits(),x.5.to_bits(),x.6.to_bits()])
    }
    #[test]
    fn narrow_40_standard_48_and_wide_64_preserve_exact_code_boundaries() {
        assert_eq!(std::mem::size_of::<NarrowEventRow>(),40);
        assert_eq!(std::mem::size_of::<CompactEventRow>(),48);
        assert_eq!(std::mem::size_of::<EventRow>(),64);
        for row in [e(0),e(1),(u32::MAX as usize,u16::MAX as usize,None,
            f64::from_bits(1),-0.0,0.0,f64::from_bits(3)),
            (1,65534,Some(65534),1.0,2.0,3.0,4.0)] {
            assert_eq!(bits(NarrowEventRow::try_new(row).unwrap().unpack()),bits(row));
        }
        for row in [(1,65535,Some(65535),1.0,2.0,3.0,4.0),
            (1,65536,None,1.0,2.0,3.0,4.0)] {
            assert!(NarrowEventRow::try_new(row).is_none());
            assert_eq!(bits(CompactEventRow::try_new(row).unwrap().unpack()),bits(row));
            let mut store=ChunkedEvents::new(true);
            store.push_decoded_checked(row,1).unwrap();
            assert_eq!(store.physical_capacity_bytes(),48);
            assert_eq!(bits(store.get_checked(0).unwrap()),bits(row));
        }
        let wide=(u32::MAX as usize+1,usize::MAX,Some(usize::MAX),
            0.25,-0.0,1.0,f64::from_bits(1));
        assert!(NarrowEventRow::try_new(wide).is_none());
        assert!(CompactEventRow::try_new(wide).is_none());
        let mut store=ChunkedEvents::new(false);
        store.push_decoded_checked(wide,1).unwrap();
        assert_eq!(store.physical_capacity_bytes(),64);
        assert_eq!(bits(store.get_checked(0).unwrap()),bits(wide));
    }

    #[test]
    fn partial_page_promotion_keeps_older_backings_order_and_incoming_indices() {
        let mut events=ChunkedEvents::new(true);
        let mut expected=Vec::new();
        for i in 0..EVENT_PAGE_ROWS {
            let row=e(i);
            events.push_checked(row).unwrap();
            expected.push(row);
        }
        let first_pointer=events.compact_chunks[0].as_ptr();
        let row=(17,2,Some(3),0.25,-0.0,1.0,f64::from_bits(3));
        let referenced_index=events.len();
        events.push_checked(row).unwrap();
        expected.push(row);
        let original_part=Part{tag:row.0,offset:7,mass:row.3,birth:row.6,
            a:PackedTime(row.4.to_bits()),b:PackedTime(row.5.to_bits())};
        let mut incoming=ChunkedParts::event_backed();
        incoming.push_serviced(referenced_index,original_part,&events).unwrap();
        assert!(matches!(events.compact_chunks[1],CompactEventPage::Narrow(_)));
        let wider=(17,70000,Some(65535),0.5,0.0,1.0,-0.0);
        events.push_checked(wider).unwrap();
        expected.push(wider);
        assert!(matches!(events.compact_chunks[1],CompactEventPage::Standard(_)));
        assert_eq!(first_pointer,events.compact_chunks[0].as_ptr());
        let got=incoming.view(&events).unwrap().get(0);
        assert_eq!((got.tag,got.offset,got.mass.to_bits(),got.birth.to_bits(),got.a.0,got.b.0),
            (original_part.tag,original_part.offset,original_part.mass.to_bits(),
             original_part.birth.to_bits(),original_part.a.0,original_part.b.0));
        for i in events.len()..(2*EVENT_PAGE_ROWS+7) {
            let row=e(i);
            events.push_checked(row).unwrap();
            expected.push(row);
        }
        assert!(matches!(events.compact_chunks[2],CompactEventPage::Narrow(_)));
        assert_eq!(events.iter().map(bits).collect::<Vec<_>>(),
            expected.iter().copied().map(bits).collect::<Vec<_>>());
        assert!(events.storage_bytes()<=persistent_event_candidate_upper_bytes(events.len(),true));
        assert_eq!(events.physical_capacity_bytes(),EVENT_PAGE_ROWS*(40+48+40));
        assert_eq!(events.into_flat_checked().unwrap().into_iter().map(bits).collect::<Vec<_>>(),
            expected.into_iter().map(bits).collect::<Vec<_>>());
    }

    #[test]
    fn actual_service_wire_decode_matches_future_generic_admission_and_all_tiers() {
        pyo3::prepare_freethreaded_python();
        for (compact,mixed) in [(true,false),(true,true),(false,true)] {
            let n=2*EVENT_PAGE_ROWS+7;
            let mut store=ChunkedEvents::new(compact);
            for i in 0..n {
                let mut row=e(i);
                if mixed && i==EVENT_PAGE_ROWS+3 {
                    row.1=70000;
                    row.2=Some(65535);
                }
                store.push_checked(row).unwrap();
            }
            // The future predictor uses exactly the same generic bound as
            // native load's before-payload event row-ceiling calculation.
            let future=store.decode_storage_upper_bytes();
            assert_eq!(future,decoded_event_store_upper_bytes(n,compact));
            let mut service=NativeServiceCore::new(vec![],vec![],vec![],vec![]).unwrap();
            let dense=service.checkpoint().0;
            service.install_state((dense,Arc::new(store)));
            let mut original_wire=Vec::new();
            service.write_state(&mut original_wire).unwrap();
            let decoded=service.read_state(&mut Cursor::new(&original_wire),n,compact).unwrap();
            assert!(decoded.1.storage_bytes()<=future);
            assert_eq!(decoded.1.capacity(),n);
            assert_eq!(service.checkpoint().1.iter().map(bits).collect::<Vec<_>>(),
                decoded.1.iter().map(bits).collect::<Vec<_>>());
            assert!(service.read_state(&mut Cursor::new(&original_wire),n-1,compact).is_err());
            service.install_state(decoded);
            let mut replay_wire=Vec::new();
            service.write_state(&mut replay_wire).unwrap();
            assert_eq!(original_wire,replay_wire);
            if compact && !mixed {assert_eq!(service.checkpoint().1.physical_capacity_bytes(),n*40);}
        }
    }

    #[test]
    fn unknown_decode_and_append_bounds_include_full_promotion_overlap() {
        for n in [1usize,17,4095,4096,4097,20011] {
            let generic=decoded_event_store_upper_bytes(n,true);
            let proven=event_store_upper_bytes(n,true,true);
            assert_eq!(generic-proven,
                n*(std::mem::size_of::<CompactEventRow>()-std::mem::size_of::<NarrowEventRow>())
                +n.min(EVENT_PAGE_ROWS)*std::mem::size_of::<NarrowEventRow>());
            let mut store=ChunkedEvents::new(true);
            for i in 0..n {
                let mut row=e(i);
                // Force a partial-page promotion before final decode count.
                if i==n/2 {row.2=Some(65535);}
                store.push_decoded_checked(row,n).unwrap();
                assert!(store.storage_bytes()<=generic);
            }
            let retained=store.storage_bytes();
            assert!(retained<=store.decode_storage_upper_bytes());
            assert!(generic>=n*48);
        }
    }
}


#[cfg(test)]
mod v03_validation_stream_20261123_tests {
    use super::*;

    fn populated() -> V1Road {
        let mut road=V1Road::new(
            "validation-stream-source".into(),1.0,
            vec![vec![1_000_000.0,1.0,100_000.0,100_000.0,100_000.0,1.0]],
            vec![None],vec![(vec![0],0)],vec![vec![1.0;13]],vec![vec![0]],
            vec![],100_000,Some(100_000),true,
        ).unwrap();
        let parts=PacketParts::pack((0..10_000).map(|_|Part{
            tag:0,offset:0,mass:1.0/256.0,birth:-0.0,
            a:PackedTime::new(Some(-0.0)).unwrap(),
            b:PackedTime::new(Some(0.0)).unwrap(),
        }).collect(),|_|Ok(())).unwrap();
        road.state.cells[0].packets.push(Packet{target:1_000_000.0,parts});
        road.state.cells[0].v[2]=10_000.0/256.0;
        road.state.totals[0]=road.state.cells[0].v[2];
        road.state.ledger[0][0]=road.state.totals[0];
        road
    }

    #[test]
    fn validator_streams_rows_at_unchanged_retained_owner_allowance() {
        pyo3::prepare_freethreaded_python();
        let mut road=populated();
        road.check_state(&road.state).unwrap();
        let retained=road.state.retained_storage_bytes();
        // The physical owner fallback is UNCHANGED. The additional 8192 B
        // supports validation scratch, not a 160000 B materialized row list.
        let cap=retained.saturating_mul(3)+8192;
        road.set_phase_storage_budget(cap).unwrap();
        let mut before=Vec::new();
        road.write_state(&mut before).unwrap();
        let result=road.check_state(&road.state);
        assert!(result.is_ok(),"10000 valid rows must stream under original owner cap: {result:?}");
        let mut after=Vec::new();
        road.write_state(&mut after).unwrap();
        assert_eq!(before,after);
    }

    #[test]
    fn validation_expansion_matches_materialized_fsum_bits() {
        let mut cases=vec![vec![],vec![-0.0,0.0],vec![1e16,1.0,-1e16],
            vec![f64::from_bits(1),f64::from_bits(1),-f64::from_bits(1)],
            vec![1.0,f64::EPSILON/2.0,f64::EPSILON/4.0],
            vec![1e100,1.0,1e-100,-1e100,-1.0],
            vec![f64::INFINITY],vec![f64::NEG_INFINITY],
            vec![f64::INFINITY,f64::NEG_INFINITY],vec![f64::NAN]];
        let mut state=0x91a8_762c_0031_22b5u64;
        for count in [1,2,7,32,257,4096] {
            for _ in 0..20 {
                let mut values=Vec::new();
                for _ in 0..count {
                    state=state.wrapping_mul(6364136223846793005).wrapping_add(1);
                    let exponent=((state>>12)%2001) as i32-1000;
                    let sign=if state&1==0 {1.0}else{-1.0};
                    values.push(sign*(1.0+((state>>24)&1023) as f64/1024.0)*2.0f64.powi(exponent));
                }
                cases.push(values);
            }
        }
        for values in cases {
            let expected=sum(values.iter().copied());
            let work=ValidationScratch::new(None,0,0).unwrap();
            let actual=validation_sum(values.iter().copied(),&work).unwrap();
            assert_eq!(expected.to_bits(),actual.to_bits(),"{} values",values.len());
            assert_eq!(work.live_bytes.get(),0,"finished sums release scratch credit");
        }
    }

    #[test]
    fn validation_expansion_charges_old_new_growth_before_allocation() {
        pyo3::prepare_freethreaded_python();
        let work=ValidationScratch::new(Some(96),0,0).unwrap();
        let mut value=ValidationSum::new(&work);
        for exponent in [-900,-700,-500,-300] {value.push(2.0f64.powi(exponent)).unwrap();}
        assert_eq!(value.partials.capacity(),4);
        assert_eq!(work.live_bytes.get(),32);
        let error=value.push(2.0f64.powi(-100)).unwrap_err().to_string();
        assert!(error.contains("required_bytes=128"),"{error}");
        assert_eq!(value.partials.capacity(),4,"rejected growth cannot allocate");
        assert_eq!(work.live_bytes.get(),32);
        drop(value);
        assert_eq!(work.live_bytes.get(),0);
        let exact=ValidationScratch::new(Some(128),0,0).unwrap();
        let mut value=ValidationSum::new(&exact);
        for exponent in [-900,-700,-500,-300,-100] {value.push(2.0f64.powi(exponent)).unwrap();}
        assert_eq!(value.partials.capacity(),8);
        assert_eq!(exact.live_bytes.get(),64);
        assert_eq!(exact.peak_bytes.get(),128);
    }

    #[test]
    fn validation_sums_account_for_simultaneous_class_buffers() {
        pyo3::prepare_freethreaded_python();
        let work=ValidationScratch::new(Some(95),0,0).unwrap();
        let mut a=ValidationSum::new(&work);
        a.push(1.0).unwrap();
        let mut b=ValidationSum::new(&work);
        assert!(b.push(1.0).unwrap_err().to_string().contains("required_bytes=96"));
        assert_eq!(work.live_bytes.get(),32);
        drop(a);
        b.push(1.0).unwrap();
        assert_eq!(b.finish().to_bits(),1.0f64.to_bits());
        assert_eq!(work.live_bytes.get(),0);
    }

    #[test]
    fn validator_retains_original_three_owner_fallback() {
        pyo3::prepare_freethreaded_python();
        let mut road=populated();
        road.retained_input_bytes=1_000_000;
        road.set_phase_storage_budget(2_999_999).unwrap();
        let error=road.check_state(&road.state).unwrap_err().to_string();
        assert!(error.contains("state validation workspace"));
        assert!(error.contains("required_bytes=3000320"),"{error}");
    }

    #[test]
    fn streaming_validator_keeps_ledger_interval_and_record_rejection() {
        pyo3::prepare_freethreaded_python();
        for case in 0..6 {
            let mut road=populated();
            road.set_phase_storage_budget(10_000_000).unwrap();
            let expected=match case {
                0=>{road.state.cells[0].v[2]+=1.0;"cell mass ledger"},
                1=>{road.state.totals[0]+=1.0;"network mass ledger"},
                2=>{road.state.ledger[0][0]+=1.0;"class mass/ledger mismatch"},
                3=>{road.state.cells[0].packets[0].target=f64::NAN;"empty/invalid native packet"},
                4=>{road.record_budget=9_999;"packet state budget"},
                _=>{road.state.cells[0].packets[0].parts=PacketParts::pack(
                    road.state.cells[0].packets[0].parts.iter().map(|mut p|{
                        p.birth=1.0;p
                    }).collect(),|_|Ok(())).unwrap();"invalid homogeneous native part"},
            };
            let error=road.check_state(&road.state).unwrap_err().to_string();
            assert!(error.contains(expected),"case {case}: {error}");
        }
    }
}
