//! Rust owner of the V1 T02/T04 finite-response FIFO packet state.
//! Registry paths are interned; tags retain independent observable ledgers.
use crate::v1_parallel::ordered_map;
use pyo3::exceptions::{PyArithmeticError, PyIOError, PyMemoryError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::{BTreeMap, HashMap};
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};

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
        return Err(val("native checkpoint length exceeds configuration/budget"));
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

/// Rows per fixed-capacity event chunk and headers per header chunk. Chunks
/// are reserved exactly once and never grow, so the event stream is never
/// copied into a doubled allocation while it is being filled.
pub(crate) const EVENT_ROW_CHUNK: usize = 1 << 16;
pub(crate) const EVENT_HEADER_CHUNK: usize = 1 << 12;
const NO_DESTINATION: usize = usize::MAX;
/// Fields shared by consecutive rows of one service batch.
#[derive(Clone, Copy)]
struct EventHeader {
    source: usize,
    start: f64,
    end: f64,
    first: usize,
}
/// Per-row fields; `dest == NO_DESTINATION` encodes a sink (None).
#[derive(Clone, Copy)]
struct EventCore {
    tag: usize,
    dest: usize,
    mass: f64,
    birth: f64,
}
/// Ordered road event stream with common batch headers. Consecutive rows with
/// equal `source` and bit-equal `start`/`end` share one header. Every stored
/// field keeps its original bits and `iter()` yields exactly the original
/// `EventRow` sequence, so wire order and values are unchanged.
#[derive(Clone, Default)]
pub(crate) struct EventStore {
    headers: Vec<Vec<EventHeader>>,
    rows: Vec<Vec<EventCore>>,
    len: usize,
    header_len: usize,
}
impl EventStore {
    pub(crate) fn len(&self) -> usize {
        self.len
    }
    pub(crate) fn is_empty(&self) -> bool {
        self.len == 0
    }
    pub(crate) fn header_count(&self) -> usize {
        self.header_len
    }
    fn header(&self, k: usize) -> &EventHeader {
        &self.headers[k / EVENT_HEADER_CHUNK][k % EVENT_HEADER_CHUNK]
    }
    fn core(&self, r: usize) -> &EventCore {
        &self.rows[r / EVENT_ROW_CHUNK][r % EVENT_ROW_CHUNK]
    }
    pub(crate) fn push(&mut self, e: EventRow) -> PyResult<()> {
        let (tag, source, dest, mass, start, end, birth) = e;
        let dest = match dest {
            None => NO_DESTINATION,
            Some(NO_DESTINATION) => return Err(val("event destination collides with sink sentinel")),
            Some(j) => j,
        };
        let same = self.header_len > 0 && {
            let h = self.header(self.header_len - 1);
            h.source == source
                && h.start.to_bits() == start.to_bits()
                && h.end.to_bits() == end.to_bits()
        };
        if !same {
            if self.header_len % EVENT_HEADER_CHUNK == 0 {
                let mut chunk = Vec::new();
                chunk
                    .try_reserve_exact(EVENT_HEADER_CHUNK)
                    .map_err(|_| budget("native road event header allocation unavailable"))?;
                push_checked(&mut self.headers, chunk)?;
            }
            let first = self.len;
            self.headers
                .last_mut()
                .expect("header chunk")
                .push(EventHeader { source, start, end, first });
            self.header_len += 1;
        }
        if self.len % EVENT_ROW_CHUNK == 0 {
            let mut chunk = Vec::new();
            chunk
                .try_reserve_exact(EVENT_ROW_CHUNK)
                .map_err(|_| budget("native road event allocation unavailable"))?;
            push_checked(&mut self.rows, chunk)?;
        }
        self.rows
            .last_mut()
            .expect("row chunk")
            .push(EventCore { tag, dest, mass, birth });
        self.len += 1;
        Ok(())
    }
    pub(crate) fn iter(&self) -> EventIter<'_> {
        EventIter {
            store: self,
            row: 0,
            header: 0,
        }
    }
    pub(crate) fn to_rows(&self) -> PyResult<Vec<EventRow>> {
        let mut out = checkpoint_vec(self.len)?;
        out.extend(self.iter());
        Ok(out)
    }
    pub(crate) fn from_rows(rows: impl IntoIterator<Item = EventRow>) -> PyResult<Self> {
        let mut out = Self::default();
        for e in rows {
            out.push(e)?;
        }
        Ok(out)
    }
    /// Owned allocation: chunk capacities and the two chunk-pointer vectors.
    pub(crate) fn allocated_bytes(&self) -> usize {
        let rows: usize = self.rows.iter().map(Vec::capacity).sum();
        let headers: usize = self.headers.iter().map(Vec::capacity).sum();
        rows.saturating_mul(std::mem::size_of::<EventCore>())
            .saturating_add(headers.saturating_mul(std::mem::size_of::<EventHeader>()))
            .saturating_add(
                self.rows
                    .capacity()
                    .saturating_add(self.headers.capacity())
                    .saturating_mul(std::mem::size_of::<Vec<EventCore>>()),
            )
    }
    /// Upper bound of the live allocation while a store with `rows` rows and at
    /// most `headers` headers is being filled: whole chunks (reserved exactly)
    /// plus each chunk-pointer vector during a doubling (old and new coexist).
    pub(crate) fn upper_bytes(rows: usize, headers: usize) -> usize {
        if rows == 0 {
            return 0;
        }
        let row_chunks = rows.div_ceil(EVENT_ROW_CHUNK);
        let header_chunks = headers.clamp(1, rows).div_ceil(EVENT_HEADER_CHUNK);
        let pointer = std::mem::size_of::<Vec<EventCore>>();
        row_chunks
            .saturating_mul(EVENT_ROW_CHUNK * std::mem::size_of::<EventCore>())
            .saturating_add(
                header_chunks.saturating_mul(EVENT_HEADER_CHUNK * std::mem::size_of::<EventHeader>()),
            )
            .saturating_add(row_chunks.max(4).saturating_mul(3 * pointer))
            .saturating_add(header_chunks.max(4).saturating_mul(3 * pointer))
    }
    /// Largest row count whose worst-case store (one header per row) fits.
    pub(crate) fn max_rows_within(bytes: usize) -> usize {
        let per_row = std::mem::size_of::<EventCore>() + std::mem::size_of::<EventHeader>();
        let slack = EVENT_ROW_CHUNK * std::mem::size_of::<EventCore>()
            + EVENT_HEADER_CHUNK * std::mem::size_of::<EventHeader>()
            + 24 * std::mem::size_of::<Vec<EventCore>>();
        // One extra byte per row covers the chunk-pointer vectors (< 1 B/row).
        bytes.saturating_sub(slack) / (per_row + 1)
    }
}
pub(crate) struct EventIter<'a> {
    store: &'a EventStore,
    row: usize,
    header: usize,
}
impl Iterator for EventIter<'_> {
    type Item = EventRow;
    fn next(&mut self) -> Option<EventRow> {
        let s = self.store;
        if self.row >= s.len {
            return None;
        }
        while self.header + 1 < s.header_len && s.header(self.header + 1).first <= self.row {
            self.header += 1;
        }
        let h = s.header(self.header);
        let c = s.core(self.row);
        self.row += 1;
        let dest = if c.dest == NO_DESTINATION { None } else { Some(c.dest) };
        Some((c.tag, h.source, dest, c.mass, h.start, h.end, c.birth))
    }
    fn size_hint(&self) -> (usize, Option<usize>) {
        let n = self.store.len - self.row;
        (n, Some(n))
    }
}
type Mark = (usize, f64, f64, f64);
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
    tag: usize,
    offset: usize,
    mass: f64,
    birth: f64,
}
/// Name of the opt-in road category representation. It is appended to the
/// road identity after the entry-projection policy and changes checkpoint
/// wire meaning, accounting binding and floating-point operation order.
pub(crate) const MARK_BLOCK_POLICY: &str = "mark_block_scaled_v1";
/// One immutable category row of a mark block. `entry` is the row's own
/// entry-time centroid (s); it is used only when a term carries no common
/// entry time of its own.
#[derive(Clone, Copy)]
struct BlockRow {
    tag: u32,
    offset: u32,
    mass: f64,
    birth: f64,
    entry: f64,
}
/// Immutable category block (`mark_block_scaled_v1`). Rows are strictly
/// sorted by their remaining route suffix `path[offset..]` and then tag, so
/// every route-prefix view of the block is one contiguous row range and the
/// rows of a view are ordered by their next movement. Shared by `Arc`; the
/// deterministic `id` (not the address) orders terms and keys checkpoints.
pub(crate) struct MarkBlock {
    id: u64,
    cell: usize,
    min_mass: f64,
    rows: Vec<BlockRow>,
}
impl MarkBlock {
    /// Unique allocation of one block: header, Arc counters and row buffer.
    fn allocated_bytes(&self) -> usize {
        std::mem::size_of::<Self>()
            .saturating_add(2 * std::mem::size_of::<usize>())
            .saturating_add(self.rows.capacity().saturating_mul(std::mem::size_of::<BlockRow>()))
    }
}
/// A positive scalar multiple of one route-prefix view of a block. Logical
/// rows are `(tag, offset + shift, lambda*mass, lambda*birth, entry)`, where
/// entry is the term's common entry time, or the row's own when NaN.
#[derive(Clone)]
struct Term {
    block: Arc<MarkBlock>,
    lo: u32,
    hi: u32,
    shift: u32,
    lambda: f64,
    entry: f64,
}
impl Term {
    fn rows(&self) -> &[BlockRow] {
        &self.block.rows[self.lo as usize..self.hi as usize]
    }
    fn key(&self) -> (u64, u32, u32, u32) {
        (self.block.id, self.lo, self.hi, self.shift)
    }
    fn logical(&self, r: &BlockRow) -> Part {
        let entry = if self.entry.is_nan() { r.entry } else { self.entry };
        Part {
            tag: r.tag as usize,
            offset: r.offset as usize + self.shift as usize,
            mass: self.lambda * r.mass,
            birth: self.lambda * r.birth,
            a: PackedTime(entry.to_bits()),
            b: PackedTime(entry.to_bits()),
        }
    }
}
/// A positive coefficient must keep every logical row mass a normal positive
/// number. Underflow is an explicit failure, never a silent mass deletion.
fn check_coefficient(lambda: f64, block: &MarkBlock) -> PyResult<()> {
    if !lambda.is_finite() || lambda <= 0. || !(lambda * block.min_mass >= f64::MIN_POSITIVE) {
        return Err(arithmetic(&format!(
            "mark block coefficient underflow or nonfinite: lambda={lambda:?}, min_mass={:?}; positive category mass is not representable",
            block.min_mass)));
    }
    Ok(())
}
/// A served term arriving at a receiving cell during [a, b].
#[derive(Clone)]
struct Contribution {
    term: Term,
    a: f64,
    b: f64,
}
#[derive(Clone)]
enum PacketParts {
    Uniform {
        a: PackedTime,
        b: PackedTime,
        rows: Vec<CorePart>,
    },
    Mixed(Vec<Part>),
    /// `mark_block_scaled_v1`: terms sorted by key; `rows` caches the number
    /// of logical rows (sum of view lengths).
    Shared { terms: Vec<Term>, rows: usize },
}
impl PacketParts {
    fn pack(
        parts: Vec<Part>,
        before_allocate: impl FnOnce(usize) -> PyResult<()>,
    ) -> PyResult<Self> {
        let shared = parts
            .first()
            .map(|p| (p.a, p.b))
            .filter(|&(a, b)| parts.iter().all(|p| p.a.0 == a.0 && p.b.0 == b.0));
        if let Some((a, b)) = shared {
            // Both buffers coexist until conversion completes. The caller
            // charges the new CorePart allocation before it is attempted.
            before_allocate(parts.len().saturating_mul(std::mem::size_of::<CorePart>()))?;
            let mut rows = checkpoint_vec(parts.len())?;
            rows.extend(parts.into_iter().map(|p| CorePart {
                tag: p.tag,
                offset: p.offset,
                mass: p.mass,
                birth: p.birth,
            }));
            Ok(Self::Uniform { a, b, rows })
        } else {
            Ok(Self::Mixed(parts))
        }
    }
    fn clone_checked(&self) -> PyResult<Self> {
        match self {
            Self::Uniform { a, b, rows } => {
                let mut copied = checkpoint_vec(rows.len())?;
                copied.extend_from_slice(rows);
                Ok(Self::Uniform {
                    a: *a,
                    b: *b,
                    rows: copied,
                })
            }
            Self::Mixed(rows) => {
                let mut copied = checkpoint_vec(rows.len())?;
                copied.extend_from_slice(rows);
                Ok(Self::Mixed(copied))
            }
            Self::Shared { terms, rows } => {
                let mut copied = checkpoint_vec(terms.len())?;
                copied.extend(terms.iter().cloned());
                Ok(Self::Shared { terms: copied, rows: *rows })
            }
        }
    }
    fn shared_terms(&self) -> Option<&[Term]> {
        match self {
            Self::Shared { terms, .. } => Some(terms),
            _ => None,
        }
    }
    fn is_shared(&self) -> bool {
        matches!(self, Self::Shared { .. })
    }
    /// Remainder of a partial service: every coefficient is multiplied by
    /// `g` in place. The caller owns this workspace copy; a failure aborts
    /// the whole proposed transition.
    fn scale_shared(&mut self, g: f64) -> PyResult<()> {
        if let Self::Shared { terms, .. } = self {
            for t in terms.iter_mut() {
                let lambda = t.lambda * g;
                check_coefficient(lambda, &t.block)?;
                t.lambda = lambda;
            }
        }
        Ok(())
    }
    fn len(&self) -> usize {
        match self {
            Self::Uniform { rows, .. } => rows.len(),
            Self::Mixed(rows) => rows.len(),
            Self::Shared { rows, .. } => *rows,
        }
    }
    fn is_empty(&self) -> bool {
        self.len() == 0
    }
    fn capacity(&self) -> usize {
        match self {
            Self::Uniform { rows, .. } => rows.capacity(),
            Self::Mixed(rows) => rows.capacity(),
            Self::Shared { terms, .. } => terms.capacity(),
        }
    }
    fn is_uniform(&self) -> bool {
        matches!(self, Self::Uniform { .. })
    }
    fn allocated_bytes(&self) -> usize {
        match self {
            Self::Uniform { rows, .. } => rows
                .capacity()
                .saturating_mul(std::mem::size_of::<CorePart>()),
            Self::Mixed(rows) => rows.capacity().saturating_mul(std::mem::size_of::<Part>()),
            // Shared block payloads are counted once per state census.
            Self::Shared { terms, .. } => terms.capacity().saturating_mul(std::mem::size_of::<Term>()),
        }
    }
    fn iter(&self) -> PartIter<'_> {
        match self {
            Self::Uniform { a, b, rows } => PartIter::Uniform {
                a: *a,
                b: *b,
                rows: rows.iter(),
            },
            Self::Mixed(rows) => PartIter::Mixed(rows.iter()),
            Self::Shared { terms, rows } => PartIter::Shared {
                terms,
                term: 0,
                row: 0,
                left: *rows,
            },
        }
    }
}
enum PartIter<'a> {
    Uniform {
        a: PackedTime,
        b: PackedTime,
        rows: std::slice::Iter<'a, CorePart>,
    },
    Mixed(std::slice::Iter<'a, Part>),
    /// Lazily materialized logical rows, term by term.
    Shared {
        terms: &'a [Term],
        term: usize,
        row: usize,
        left: usize,
    },
}
impl Iterator for PartIter<'_> {
    type Item = Part;
    fn next(&mut self) -> Option<Part> {
        match self {
            Self::Uniform { a, b, rows } => rows.next().map(|p| Part {
                tag: p.tag,
                offset: p.offset,
                mass: p.mass,
                birth: p.birth,
                a: *a,
                b: *b,
            }),
            Self::Mixed(rows) => rows.next().copied(),
            Self::Shared { terms, term, row, left } => loop {
                let t = terms.get(*term)?;
                if let Some(r) = t.rows().get(*row) {
                    *row += 1;
                    *left -= 1;
                    break Some(t.logical(r));
                }
                *term += 1;
                *row = 0;
            },
        }
    }
    fn size_hint(&self) -> (usize, Option<usize>) {
        let n = match self {
            Self::Uniform { rows, .. } => rows.len(),
            Self::Mixed(rows) => rows.len(),
            Self::Shared { left, .. } => *left,
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
    /// Next deterministic mark-block id (`mark_block_scaled_v1` only; 0 and
    /// unused by the row representation).
    next_block: u64,
    /// Unique shared block payload reachable from this immutable state,
    /// computed once when the state is built or decoded.
    census: SharedCensus,
}
/// Reachable mark-block payload of one state. Blocks shared by several terms
/// (or several packets) are counted once; blocks also reachable from another
/// state are still counted in each state, which is conservative.
#[derive(Clone, Copy, Default)]
pub(crate) struct SharedCensus {
    pub(crate) blocks: usize,
    pub(crate) block_rows: usize,
    pub(crate) block_bytes: usize,
    pub(crate) terms: usize,
    pub(crate) max_block_rows: usize,
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
    /// Packets in the shared representation and their logical rows.
    pub(crate) shared_packets: usize,
    pub(crate) shared_parts: usize,
    pub(crate) census: SharedCensus,
}

/// Conservative structural working allowance, not an allocator/RSS theorem.
/// Captures one supplied immutable snapshot, the committed owner, a candidate,
/// and the large source/transfer/splitting workspaces. Unrelated user-retained
/// snapshots and allocator metadata remain covered by the process limit.
struct RoadWorkBudget {
    limit: Option<usize>,
    base: usize,
    events: usize,
    /// Upper bound on batch headers (one per service call with rows).
    event_headers: usize,
    incoming: usize,
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
    max_tag_bytes: usize,
}
impl ServiceEventAccounting {
    /// Event buffers live during the road step: the call-input and current
    /// committed buffers (charged separately, never assumed shared) and the
    /// push-built candidate, whose doubling reallocation briefly holds the old
    /// and the new allocation (< 3 rows' worth; minimum four rows).
    fn road_step_bytes(self, generated_rows: usize, headers: usize) -> usize {
        // Candidate stream: fixed exact-capacity chunks, so no doubled copy
        // of the rows; only the small chunk-pointer vectors grow.
        self.input_bytes
            .saturating_add(self.current_bytes)
            .saturating_add(EventStore::upper_bytes(generated_rows, headers))
            .saturating_add(3 * 32)
    }
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
/// Diagnostics describe only the latest validated proposed road transition.
/// They are not checkpoint state or a network trajectory-error estimate.
#[derive(Default, Clone, Copy)]
struct ProjectionStats {
    input_parts: usize,
    output_parts: usize,
    cohorts: usize,
    protected_support_boundaries: usize,
    local_w1_bound: f64,
    /// mark_block_scaled_v1 only: served term contributions, output terms
    /// and rows of the new immutable blocks created by this transition.
    input_contributions: usize,
    output_terms: usize,
    new_block_rows: usize,
}
pub(crate) fn projection_identity(identity: &str, width: f64) -> String {
    if width > 0. {
        format!("{identity}:entry_projection_support_v1:{:016x}", width.to_bits())
    } else {
        identity.to_owned()
    }
}
/// Projection identity plus the optional road representation policy. The row
/// representation keeps the unchanged projection identity.
pub(crate) fn representation_identity(identity: &str, width: f64, mark_blocks: bool) -> String {
    let base = projection_identity(identity, width);
    if mark_blocks {
        format!("{base}:{MARK_BLOCK_POLICY}")
    } else {
        base
    }
}
/// Parse the public representation selector.
pub(crate) fn parse_representation(name: &str) -> PyResult<bool> {
    match name {
        "rows" => Ok(false),
        MARK_BLOCK_POLICY => Ok(true),
        _ => Err(val("unknown road_representation; expected 'rows' or 'mark_block_scaled_v1'")),
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
impl RoadWorkBudget {
    fn pack_parts(&self, parts: Vec<Part>) -> PyResult<PacketParts> {
        PacketParts::pack(parts, |bytes| {
            self.require(bytes, "packet interval packing")
        })
    }
    fn require(&self, extra: usize, phase: &str) -> PyResult<()> {
        // In a coupled transition the road-step event buffers are charged by
        // lifetime; the sink envelope is charged after the step returns.
        let event_bytes = self.service_events.map_or_else(
            || EventStore::upper_bytes(self.events, self.event_headers).saturating_mul(2),
            |service| service.road_step_bytes(self.events, self.event_headers),
        );
        let required =
            self.base
                .saturating_add(event_bytes)
                .saturating_add(self.incoming.saturating_mul(
                    2 * (std::mem::size_of::<Part>() + std::mem::size_of::<Mark>()),
                ))
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
                    ("base", self.base),
                    ("event_bytes", event_bytes),
                    ("event_headers", self.event_headers),
                    ("incoming_rows", self.incoming),
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
    fn transfer(&mut self, events: usize, incoming: usize) -> PyResult<()> {
        self.events = self.events.saturating_add(events);
        if events > 0 {
            self.event_headers = self.event_headers.saturating_add(1);
        }
        self.incoming = self.incoming.saturating_add(incoming);
        self.require(0, "transfer candidates")
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
        for queue in self
            .cells
            .iter()
            .map(|cell| &cell.packets)
            .chain(&self.pending)
        {
            out.packet_capacity += queue.capacity();
            for packet in queue {
                out.part_capacity += packet.parts.capacity();
                out.vector_capacity_bytes += packet.parts.allocated_bytes();
                if packet.parts.is_shared() {
                    out.shared_packets += 1;
                    out.shared_parts += packet.parts.len();
                } else if packet.parts.is_uniform() {
                    out.uniform_packets += 1;
                    out.uniform_parts += packet.parts.len();
                } else {
                    out.mixed_packets += 1;
                    out.mixed_parts += packet.parts.len();
                }
            }
        }
        out.vector_capacity_bytes += out.packet_capacity * std::mem::size_of::<Packet>();
        out.census = self.census;
        out
    }
    /// Recompute the unique shared payload. Called once per built or decoded
    /// state (never on the row representation's hot path: no shared packets
    /// means no work beyond the packet scan).
    pub(crate) fn refresh_census(&mut self) -> PyResult<()> {
        let mut seen: std::collections::HashSet<u64> = std::collections::HashSet::new();
        let mut census = SharedCensus::default();
        for packet in self
            .cells
            .iter()
            .flat_map(|c| &c.packets)
            .chain(self.pending.iter().flatten())
        {
            if let Some(terms) = packet.parts.shared_terms() {
                census.terms += terms.len();
                for t in terms {
                    if seen.insert(t.block.id) {
                        census.blocks += 1;
                        census.block_rows += t.block.rows.len();
                        census.max_block_rows = census.max_block_rows.max(t.block.rows.len());
                        census.block_bytes = census.block_bytes.saturating_add(t.block.allocated_bytes());
                    }
                }
            }
        }
        // The id set is transient scratch; charge it with the payload.
        census.block_bytes = census
            .block_bytes
            .saturating_add(seen.capacity().saturating_mul(2 * std::mem::size_of::<u64>()));
        self.census = census;
        Ok(())
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
            .saturating_add(3)
            .saturating_add(stats.census.blocks);
        stats
            .vector_capacity_bytes
            .saturating_add(stats.census.block_bytes)
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
        // mark_block_scaled_v1: the decode pool map holds one node per block
        // and each block row is validated once (0 for the row representation).
        let validation = stats
            .cell_parts
            .saturating_add(stats.pending_parts)
            .saturating_add(stats.census.block_rows)
            .saturating_add(stats.census.blocks.saturating_mul(8))
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
    entry_projection_width_s: f64,
    projection_stats: Mutex<ProjectionStats>,
    event_budget: Option<usize>,
    intervals: bool,
    /// `mark_block_scaled_v1`: entry-projected cohorts share immutable
    /// category blocks with scalar coefficients (named numerical policy).
    mark_blocks: bool,
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
/// Diagnostic: group one cell's incoming rows by non-point interval (a,b) and
/// count maximal runs of time-contiguous intervals whose contributing source
/// set {(cell, head position, rate bits)} is identical. Such runs have
/// proportional route mixtures and equal ready time, so they are exactly
/// mergeable in real arithmetic. Counting only.
fn exact_merge_census(parts: &[Part], src: &[(usize, usize, u64)]) {
    use std::collections::BTreeSet;
    let mut by: BTreeMap<(u64, u64), BTreeSet<(usize, usize, u64)>> = BTreeMap::new();
    let mut points = 0u64;
    for (p, s) in parts.iter().zip(src) {
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
        if self.mark_blocks {
            // mark_block_scaled_v1 wire section: the block counter and every
            // reachable immutable block once, by increasing id; packets then
            // refer to blocks by id. The row representation's wire is unchanged.
            write_u64(w, s.next_block)?;
            let mut pool: BTreeMap<u64, &MarkBlock> = BTreeMap::new();
            for packet in s.cells.iter().flat_map(|c| &c.packets).chain(s.pending.iter().flatten()) {
                for t in packet.parts.shared_terms().unwrap_or(&[]) {
                    pool.insert(t.block.id, &t.block);
                }
            }
            write_len(w, pool.len())?;
            for (id, block) in pool {
                write_u64(w, id)?;
                write_len(w, block.cell)?;
                write_len(w, block.rows.len())?;
                for r in &block.rows {
                    write_len(w, r.tag as usize)?;
                    write_len(w, r.offset as usize)?;
                    write_f64(w, r.mass)?;
                    write_f64(w, r.birth)?;
                    write_f64(w, r.entry)?;
                }
            }
        }
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
            if self.mark_blocks {
                if let Some(terms) = p.parts.shared_terms() {
                    write_u64(w, 1)?;
                    write_len(w, terms.len())?;
                    for t in terms {
                        write_u64(w, t.block.id)?;
                        write_len(w, t.lo as usize)?;
                        write_len(w, t.hi as usize)?;
                        write_len(w, t.shift as usize)?;
                        write_f64(w, t.lambda)?;
                        write_f64(w, t.entry)?;
                    }
                    continue;
                }
                write_u64(w, 0)?;
            }
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
        pool: &mut BTreeMap<u64, (Arc<MarkBlock>, bool)>,
        cell: usize,
    ) -> PyResult<Vec<Packet>> {
        let n = read_len(r, *remaining)?;
        work.reserve(
            n.saturating_mul(std::mem::size_of::<Packet>() + 32),
            n.saturating_mul(32),
        )?;
        let mut q = checkpoint_vec(n)?;
        for _ in 0..n {
            let target = read_f64(r)?;
            if self.mark_blocks {
                match read_u64(r)? {
                    0 => {}
                    1 => {
                        let parts = self.read_shared_parts(r, remaining, work, pool, cell)?;
                        q.push(Packet { target, parts });
                        continue;
                    }
                    _ => return Err(val("native checkpoint packet representation differs")),
                }
            }
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
    /// Decode one block pool (mark_block_scaled_v1) with full validation:
    /// ids strictly increasing below the counter, rows positive and finite,
    /// at their block's cell, and strictly sorted by (route suffix, tag).
    fn read_block_pool<R: Read>(
        &self,
        r: &mut R,
        next_block: u64,
        remaining: &mut usize,
        work: &mut RoadDecodeBudget,
    ) -> PyResult<BTreeMap<u64, (Arc<MarkBlock>, bool)>> {
        let count = read_len(r, *remaining)?;
        let mut pool = BTreeMap::new();
        let mut previous: Option<u64> = None;
        for _ in 0..count {
            let id = read_u64(r)?;
            if id >= next_block || previous.is_some_and(|p| id <= p) {
                return Err(val("native checkpoint mark block id differs"));
            }
            previous = Some(id);
            let cell = read_len(r, self.groups.len().saturating_sub(1))?;
            let n = read_len(r, (*remaining).min(u32::MAX as usize))?;
            if n == 0 {
                return Err(val("empty native checkpoint mark block"));
            }
            *remaining -= n;
            work.reserve(
                n.saturating_mul(std::mem::size_of::<BlockRow>())
                    .saturating_add(std::mem::size_of::<MarkBlock>() + 2 * std::mem::size_of::<usize>() + 64),
                n.saturating_mul(16),
            )?;
            let mut rows: Vec<BlockRow> = checkpoint_vec(n)?;
            let mut min_mass = f64::INFINITY;
            for _ in 0..n {
                let tag = read_len(r, self.routes.len().saturating_sub(1))?;
                let path = self.path(tag);
                let offset = read_len(r, path.len().saturating_sub(1))?;
                let (mass, birth, entry) = (read_f64(r)?, read_f64(r)?, read_f64(r)?);
                if path[offset] != cell
                    || !mass.is_finite()
                    || mass <= 0.
                    || !finite_nonnegative(birth)
                    || !finite_nonnegative(entry)
                {
                    return Err(val("invalid native checkpoint mark block row"));
                }
                min_mass = min_mass.min(mass);
                rows.push(BlockRow { tag: tag as u32, offset: offset as u32, mass, birth, entry });
            }
            if rows.windows(2).any(|w| {
                self.suffix(&w[0]).cmp(self.suffix(&w[1])).then(w[0].tag.cmp(&w[1].tag))
                    != std::cmp::Ordering::Less
            }) {
                return Err(val("native checkpoint mark block order differs"));
            }
            pool.insert(id, (Arc::new(MarkBlock { id, cell, min_mass, rows }), false));
        }
        Ok(pool)
    }
    /// Decode one shared packet. Every term must reference a pooled block by
    /// id, select a nonempty range whose rows share their route prefix up to
    /// this cell, and keep positive representable logical masses.
    fn read_shared_parts<R: Read>(
        &self,
        r: &mut R,
        remaining: &mut usize,
        work: &mut RoadDecodeBudget,
        pool: &mut BTreeMap<u64, (Arc<MarkBlock>, bool)>,
        cell: usize,
    ) -> PyResult<PacketParts> {
        let m = read_len(r, *remaining)?;
        if m == 0 {
            return Err(val("empty native checkpoint packet"));
        }
        work.reserve(m.saturating_mul(std::mem::size_of::<Term>()), m.saturating_mul(16))?;
        let mut terms: Vec<Term> = checkpoint_vec(m)?;
        let mut logical = 0usize;
        for _ in 0..m {
            let id = read_u64(r)?;
            let Some((block, used)) = pool.get_mut(&id) else {
                return Err(val("native checkpoint mark block reference differs"));
            };
            *used = true;
            let block = block.clone();
            let lo = read_len(r, block.rows.len())?;
            let hi = read_len(r, block.rows.len())?;
            let shift = read_len(r, u32::MAX as usize)?;
            let (lambda, entry) = (read_f64(r)?, read_f64(r)?);
            if lo >= hi || !(entry.is_nan() || finite_nonnegative(entry)) {
                return Err(val("invalid native checkpoint mark block term"));
            }
            check_coefficient(lambda, &block).map_err(|_| val("invalid native checkpoint mark block coefficient"))?;
            let first = &block.rows[lo];
            let prefix = self.suffix(first);
            if shift >= prefix.len() || prefix[shift] != cell {
                return Err(val("native checkpoint mark block view differs"));
            }
            for row in &block.rows[lo..hi] {
                let suffix = self.suffix(row);
                if suffix.len() <= shift || suffix[..=shift] != prefix[..=shift] {
                    return Err(val("native checkpoint mark block view differs"));
                }
            }
            if hi - lo > *remaining {
                return Err(budget("packet state budget"));
            }
            *remaining -= hi - lo;
            logical += hi - lo;
            terms.push(Term { block, lo: lo as u32, hi: hi as u32, shift: shift as u32, lambda, entry });
        }
        if terms.windows(2).any(|w| w[0].key() >= w[1].key()) {
            return Err(val("native checkpoint mark block term order differs"));
        }
        Ok(PacketParts::Shared { terms, rows: logical })
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
        let next_block = if self.mark_blocks { read_u64(r)? } else { 0 };
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
        let mut pool = if self.mark_blocks {
            self.read_block_pool(r, next_block, &mut remaining, &mut work)?
        } else {
            BTreeMap::new()
        };
        read_exact_len(r, self.groups.len())?;
        // Include empty tree roots and both packet-queue buffer allowances for
        // every cell, before constructing the first outer vector.
        work.reserve(
            self.groups
                .len()
                .saturating_mul(std::mem::size_of::<Cell>() + 256 + 2 * 32),
            self.groups.len().saturating_mul(32),
        )?;
        let mut cells = checkpoint_vec(self.groups.len())?;
        for cell in 0..self.groups.len() {
            let mut v = [0.; 8];
            for x in &mut v {
                *x = read_f64(r)?;
            }
            let packets = self.read_packets(r, &mut remaining, &mut work, &mut pool, cell)?;
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
        for cell in 0..self.groups.len() {
            pending.push(self.read_packets(r, &mut remaining, &mut work, &mut pool, cell)?);
        }
        if pool.values().any(|(_, used)| !used) {
            return Err(val("native checkpoint mark block is unreferenced"));
        }
        drop(pool);
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
        let state = RoadState {
            t,
            cells,
            pending,
            totals,
            ledger,
            next_block,
            census: SharedCensus::default(),
        };
        let mut state = state;
        if self.mark_blocks {
            state.refresh_census()?;
        }
        self.check_state(&state)?;
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
    pub(crate) fn checkpoint(&self) -> RoadState {
        self.state.clone()
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
    ) {
        self.service_event_accounting = self.storage_budget.map(|_| ServiceEventAccounting {
            input_bytes,
            current_bytes: input_bytes,
            max_tag_bytes,
        });
    }
    pub(crate) fn service_sink_tag_bytes(&self) -> Option<usize> {
        self.service_event_accounting.map(|a| a.max_tag_bytes)
    }
    pub(crate) fn set_service_event_current_bytes(&mut self, current_bytes: usize) {
        if let Some(accounting) = &mut self.service_event_accounting {
            accounting.current_bytes = current_bytes;
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
    fn work_budget(&self, state: &RoadState, offers: &[Offer]) -> PyResult<RoadWorkBudget> {
        if self.storage_budget.is_none() {
            return Ok(RoadWorkBudget {
                limit: None,
                base: 0,
                events: 0,
                event_headers: 0,
                incoming: 0,
                interval_retained: 0,
                interval_transient: 0,
                service_events: None,
            });
        }
        let stats = state.debug_stats();
        let rows = stats.cell_parts.saturating_add(stats.pending_parts);
        let groups = self.groups.len();
        let base = state
            .retained_storage_bytes()
            .max(self.retained_input_bytes)
            .saturating_mul(3)
            .saturating_add(rows.saturating_mul(4 * std::mem::size_of::<f64>()))
            .saturating_add(
                offers
                    .len()
                    .saturating_mul(4 * std::mem::size_of::<Part>() + std::mem::size_of::<Offer>()),
            )
            .saturating_add(
                stats
                    .max_cell_parts
                    .saturating_mul(2 * std::mem::size_of::<Part>()),
            )
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
                ],
            );
        }
        let work = RoadWorkBudget {
            limit: self.storage_budget,
            base,
            events: 0,
            event_headers: 0,
            incoming: 0,
            interval_retained: 0,
            interval_transient: 0,
            service_events: self.service_event_accounting,
        };
        work.require(0, "tick preflight")?;
        Ok(work)
    }
    pub(crate) fn owned_step(&mut self, dt: f64, offers: Vec<Offer>) -> PyResult<EventStore> {
        self.begin_call_storage_accounting();
        let (s, e) = self.step_state(&self.state, dt, offers)?;
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
    ) -> PyResult<(RoadState, EventStore)> {
        self.step_state(&self.state, dt, offers)
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
    /// Next cell of a block row viewed at `shift`; None leaves the network.
    fn next_cell(&self, r: &BlockRow, shift: u32) -> Option<usize> {
        self.path(r.tag as usize)
            .get(r.offset as usize + shift as usize + 1)
            .copied()
    }
    fn suffix(&self, r: &BlockRow) -> &[usize] {
        &self.path(r.tag as usize)[r.offset as usize..]
    }
    /// Contiguous next-movement groups `(start, end, next)` of one view.
    /// Rows of a view share their route prefix, so the sorted suffix order
    /// makes every next movement one run.
    fn view_groups<'a>(&'a self, t: &'a Term) -> impl Iterator<Item = (usize, usize, Option<usize>)> + 'a {
        let rows = t.rows();
        let mut start = 0;
        std::iter::from_fn(move || {
            if start >= rows.len() {
                return None;
            }
            let next = self.next_cell(&rows[start], t.shift);
            let len = rows[start..].partition_point(|r| self.next_cell(r, t.shift) == next);
            let group = (start, start + len, next);
            start += len;
            Some(group)
        })
    }
    /// One partial service of a shared head (`mark_block_scaled_v1`).
    /// Returns the served logical rows merged by (tag, offset) for the event
    /// and ledger stream, and one contribution per (term, next movement) for
    /// the receiving cells. Each served coefficient is `lambda * fraction`;
    /// event masses use exactly the coefficient carried by the contribution.
    fn shared_serve(
        &self,
        terms: &[Term],
        logical: usize,
        fraction: f64,
        work: &RoadWorkBudget,
    ) -> PyResult<(Vec<Part>, Vec<(usize, Term)>)> {
        // Raw logical rows, their sort and the merged output coexist.
        work.require(
            logical
                .saturating_mul(2 * std::mem::size_of::<Part>())
                .saturating_add(terms.len().saturating_mul(4 * std::mem::size_of::<(usize, Term)>())),
            "mark block service materialization",
        )?;
        let mut raw: Vec<Part> = checkpoint_vec(logical)?;
        let mut contributions: Vec<(usize, Term)> = Vec::new();
        for t in terms {
            let served = t.lambda * fraction;
            check_coefficient(served, &t.block)?;
            for r in t.rows() {
                raw.push(Part {
                    tag: r.tag as usize,
                    offset: r.offset as usize + t.shift as usize,
                    mass: served * r.mass,
                    birth: served * r.birth,
                    a: PackedTime(PackedTime::NONE),
                    b: PackedTime(PackedTime::NONE),
                });
            }
            for (start, end, next) in self.view_groups(t) {
                if let Some(j) = next {
                    let shift = t
                        .shift
                        .checked_add(1)
                        .ok_or_else(|| val("mark block route offset overflow"))?;
                    push_checked(
                        &mut contributions,
                        (
                            j,
                            Term {
                                block: t.block.clone(),
                                lo: t.lo + start as u32,
                                hi: t.lo + end as u32,
                                shift,
                                lambda: served,
                                entry: f64::NAN,
                            },
                        ),
                    )?;
                }
            }
        }
        // fsum is correctly rounded, so equal-key group sums do not depend on
        // the unstable sort's tie order.
        raw.sort_unstable_by(|a, b| (a.tag, a.offset).cmp(&(b.tag, b.offset)));
        let groups = usize::from(!raw.is_empty())
            + raw
                .windows(2)
                .filter(|w| (w[0].tag, w[0].offset) != (w[1].tag, w[1].offset))
                .count();
        let mut out = checkpoint_vec(groups)?;
        let mut start = 0;
        while start < raw.len() {
            let mut end = start + 1;
            while end < raw.len() && (raw[end].tag, raw[end].offset) == (raw[start].tag, raw[start].offset) {
                end += 1;
            }
            let mut part = raw[start];
            if end - start > 1 {
                part.mass = sum(raw[start..end].iter().map(|p| p.mass));
                part.birth = sum(raw[start..end].iter().map(|p| p.birth));
            }
            out.push(part);
            start = end;
        }
        Ok((out, contributions))
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
            next_block: 0,
            census: SharedCensus::default(),
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
    /// Project one admission target. Endpoint events select only movement-support
    /// changes; integrating into fixed bins never re-splits centroid cohorts.
    fn projected_packets(
        &self,
        parts: Vec<Part>,
        target: f64,
        work: &mut RoadWorkBudget,
        stats: &mut ProjectionStats,
    ) -> PyResult<Vec<Packet>> {
        let n = parts.len();
        if n == 0 {
            return Ok(Vec::new());
        }
        let h = self.entry_projection_width_s;
        let mut lo = f64::INFINITY;
        let mut hi = f64::NEG_INFINITY;
        for p in &parts {
            let (a, b) = (p.a.unwrap(), p.b.unwrap());
            if !p.mass.is_finite() || p.mass <= 0. || !p.birth.is_finite() || b < a {
                return Err(arithmetic("invalid positive entry projection measure"));
            }
            lo = lo.min(a);
            hi = hi.max(b);
            if b > a {
                if a + h <= a || b - h >= b {
                    return Err(arithmetic("entry projection width is unrepresentable at entry clock"));
                }
            }
        }
        let edge_count = n.checked_mul(3).and_then(|v| v.checked_add(2))
            .ok_or_else(|| budget("entry projection boundary capacity overflow"))?;
        let base_bytes = n.saturating_mul(2 * std::mem::size_of::<(f64, usize, bool)>())
            .saturating_add(n.saturating_mul(2 * std::mem::size_of::<(f64, f64)>()))
            .saturating_add(self.groups.len().saturating_add(1).saturating_mul(std::mem::size_of::<usize>()))
            .saturating_add(parts.capacity().saturating_mul(std::mem::size_of::<Part>()));
        let mut fixed_bytes = base_bytes.saturating_add(edge_count.saturating_mul(std::mem::size_of::<f64>()));
        work.interval(fixed_bytes)?;
        let mut events = checkpoint_vec(n.saturating_mul(2))?;
        let mut edges = checkpoint_vec(edge_count)?;
        edges.extend([lo, hi]);
        for p in &parts {
            let (a, b) = (p.a.unwrap(), p.b.unwrap());
            if a == b {
                edges.push(a);
            } else {
                let movement = self.paths[self.routes[p.tag].0].get(p.offset + 1)
                    .copied().unwrap_or(self.groups.len());
                events.push((a, movement, true));
                events.push((b, movement, false));
            }
        }
        events.sort_unstable_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
        let mut counts = checkpoint_vec(self.groups.len() + 1)?;
        counts.resize(self.groups.len() + 1, 0usize);
        let mut runs = checkpoint_vec(n.saturating_mul(2))?;
        let mut run_start = None;
        let mut active_movements = 0usize;
        let event_first = events.first().map(|e| e.0).unwrap_or(lo);
        let event_last = events.last().map(|e| e.0).unwrap_or(hi);
        let mut i = 0;
        let mut protected = 0usize;
        while i < events.len() {
            let t = events[i].0;
            let mut changed = false;
            while i < events.len() && events[i].0 == t {
                let movement = events[i].1;
                let mut starts = 0usize;
                let mut ends = 0usize;
                while i < events.len() && events[i].0 == t && events[i].1 == movement {
                    if events[i].2 { starts += 1; } else { ends += 1; }
                    i += 1;
                }
                let before = counts[movement];
                let after = before.checked_add(starts).and_then(|v| v.checked_sub(ends))
                    .ok_or_else(|| arithmetic("entry projection support count overflow"))?;
                changed |= (before > 0) != (after > 0);
                if before == 0 && after > 0 { active_movements += 1; }
                if before > 0 && after == 0 { active_movements -= 1; }
                counts[movement] = after;
            }
            if changed {
                edges.push(t);
                if t > event_first && t < event_last { protected += 1; }
                if let Some(start) = run_start { runs.push((start, t)); }
                run_start = if active_movements > 0 { Some(t) } else { None };
            }
        }
        // Generate mesh boundaries only on nonempty support runs. Empty time
        // gaps do not consume memory or cause a false record-budget refusal.
        for (left, right) in runs {
            let mut first = (left / h).floor() + 1.;
            let last = (right / h).ceil();
            if !first.is_finite() || !last.is_finite() || first + 1. == first || last + 1. == last {
                return Err(arithmetic("entry projection grid index is unrepresentable"));
            }
            if first * h <= left { first += 1.; }
            let count = (last - first).max(0.);
            if count >= usize::MAX as f64 {
                return Err(budget("entry projection grid exceeds addressable capacity"));
            }
            let count = count as usize;
            // Each interior boundary in a nonempty run requires at least one
            // positive output row; refuse before allocation when impossible.
            if count > self.record_budget {
                return Err(budget("entry projection grid record budget"));
            }
            let needed = edges.len().checked_add(count)
                .ok_or_else(|| budget("entry projection grid capacity overflow"))?;
            if needed > edges.capacity() {
                let required = needed.saturating_mul(std::mem::size_of::<f64>());
                work.interval(fixed_bytes.saturating_add(required))?;
                edges.try_reserve_exact(count)
                    .map_err(|_| budget("entry projection grid allocation unavailable"))?;
                fixed_bytes = base_bytes.saturating_add(edges.capacity().saturating_mul(std::mem::size_of::<f64>()));
                work.interval(fixed_bytes)?;
            }
            let mut previous = left;
            for j in 0..count {
                let edge = (first + j as f64) * h;
                if !edge.is_finite() || edge <= previous {
                    return Err(arithmetic("entry projection grid boundary does not advance"));
                }
                if edge < right { edges.push(edge); }
                previous = edge;
            }
        }
        edges.sort_unstable_by(f64::total_cmp);
        edges.dedup();
        // Per-segment pieces, output rows and summation scratch. Packet vectors
        // grow fallibly under a conservative old+new capacity envelope.
        let segment_bytes = n.saturating_mul(320);
        let mut out: Vec<Packet> = Vec::new();
        let mut records = 0usize;
        let mut local_bound = 0.;
        for (edge_index, &a) in edges.iter().enumerate() {
            work.interval(fixed_bytes.saturating_add(segment_bytes).saturating_add(
                out.len().saturating_add(1).max(4).saturating_mul(3 * std::mem::size_of::<Packet>())
            ))?;
            // Preserve the exact point law: equal-time rows form the same
            // exchangeable packet as interval_packets, ahead of [a,b].
            let count = parts.iter().filter(|p| p.a == Some(a) && p.b == Some(a)).count();
            if count > 0 {
                let mut points = checkpoint_vec(count)?;
                points.extend(parts.iter().filter(|p| p.a == Some(a) && p.b == Some(a)).copied());
                let rows = combine(points)?;
                self.push_projected_packet(&mut out, rows, target, work, &mut records)?;
            }
            let Some(&b) = edges.get(edge_index + 1) else { continue; };
            let mut pieces: Vec<(usize, usize, f64, f64, f64, f64, f64)> = checkpoint_vec(n)?;
            for p in &parts {
                let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
                let (x, y) = (a.max(pa), b.min(pb));
                if y <= x || pb <= pa { continue; }
                let fraction = (y - x) / (pb - pa);
                let mass = p.mass * fraction;
                let birth = p.birth * fraction;
                let relative_entry = mass * ((x - a) + (y - x) / 2.);
                if mass <= 0. || !mass.is_finite() || !birth.is_finite() || !relative_entry.is_finite() {
                    return Err(arithmetic("entry projection positive piece underflow or nonfinite moment"));
                }
                pieces.push((p.tag, p.offset, mass, birth, relative_entry, x, y));
            }
            if pieces.is_empty() { continue; }
            pieces.sort_unstable_by_key(|p| (p.0, p.1));
            // Mixed cohorts keep this buffer, so reserve categories rather
            // than input pieces; otherwise duplicate pieces retain excess
            // capacity even though their moments have been aggregated.
            let category_count = 1 + pieces.windows(2)
                .filter(|pair| (pair[0].0, pair[0].1) != (pair[1].0, pair[1].1)).count();
            let mut rows = checkpoint_vec(category_count)?;
            let mut cursor = 0;
            while cursor < pieces.len() {
                let start = cursor;
                let key = (pieces[start].0, pieces[start].1);
                while cursor < pieces.len() && (pieces[cursor].0, pieces[cursor].1) == key {
                    cursor += 1;
                }
                let selected = &pieces[start..cursor];
                let mass = sum(selected.iter().map(|p| p.2));
                let birth = sum(selected.iter().map(|p| p.3));
                let relative_entry = sum(selected.iter().map(|p| p.4));
                let min_time = selected.iter().map(|p| p.5).fold(f64::INFINITY, f64::min);
                let max_time = selected.iter().map(|p| p.6).fold(f64::NEG_INFINITY, f64::max);
                let centroid = a + relative_entry / mass;
                if !mass.is_finite() || !birth.is_finite() || !centroid.is_finite()
                    || centroid < min_time || centroid > max_time {
                    return Err(arithmetic("entry projection aggregate moment is unrepresentable"));
                }
                // A local real-arithmetic W1 upper bound, not a propagated
                // traffic error. Outward summation avoids rounding it downward.
                let bound = mass * ((max_time - min_time) / 2.);
                if !bound.is_finite() {
                    return Err(arithmetic("entry projection local transport bound overflow"));
                }
                local_bound = upper_add(local_bound, bound);
                let time = PackedTime::new(Some(centroid))?;
                rows.push(Part { tag: key.0, offset: key.1, mass, birth, a: time, b: time });
            }
            self.push_projected_packet(&mut out, rows, target, work, &mut records)?;
        }
        stats.input_parts = stats.input_parts.saturating_add(n);
        stats.output_parts = stats.output_parts.saturating_add(records);
        stats.cohorts = stats.cohorts.saturating_add(out.len());
        stats.protected_support_boundaries = stats.protected_support_boundaries.saturating_add(protected);
        stats.local_w1_bound = upper_add(stats.local_w1_bound, local_bound);
        work.end_interval();
        Ok(out)
    }
    /// Build one immutable block from combined rows (unique (tag, offset)),
    /// charging its payload before allocation. Rows keep their own entry
    /// centroids; the caller wraps the block in a unit-coefficient term.
    fn new_block(
        &self,
        rows: Vec<Part>,
        cell: usize,
        next_block: &mut u64,
        work: &RoadWorkBudget,
    ) -> PyResult<Arc<MarkBlock>> {
        if rows.is_empty() || rows.len() > u32::MAX as usize {
            return Err(budget("mark block row count is not representable"));
        }
        work.require(
            rows.len()
                .saturating_mul(std::mem::size_of::<BlockRow>())
                .saturating_add(std::mem::size_of::<MarkBlock>() + 64),
            "mark block allocation",
        )?;
        let mut block_rows: Vec<BlockRow> = checkpoint_vec(rows.len())?;
        let mut min_mass = f64::INFINITY;
        for p in rows {
            let (Ok(tag), Ok(offset)) = (u32::try_from(p.tag), u32::try_from(p.offset)) else {
                return Err(val("mark block tag or route offset is not representable"));
            };
            let entry = p.a.unwrap();
            if !(p.mass > 0.) || !p.mass.is_finite() || !p.birth.is_finite() || !entry.is_finite() {
                return Err(arithmetic("invalid mark block row"));
            }
            min_mass = min_mass.min(p.mass);
            block_rows.push(BlockRow { tag, offset, mass: p.mass, birth: p.birth, entry });
        }
        block_rows.sort_unstable_by(|x, y| self.suffix(x).cmp(self.suffix(y)).then(x.tag.cmp(&y.tag)));
        let id = *next_block;
        *next_block = next_block
            .checked_add(1)
            .ok_or_else(|| val("mark block id overflow"))?;
        Ok(Arc::new(MarkBlock { id, cell, min_mass, rows: block_rows }))
    }
    /// Distinct next movements of a view; `groups.len()` encodes leaving.
    fn view_movements<'a>(&'a self, t: &'a Term) -> impl Iterator<Item = usize> + 'a {
        let n = self.groups.len();
        self.view_groups(t).map(move |(_, _, next)| next.unwrap_or(n))
    }
    /// `mark_block_scaled_v1` form of `projected_packets`. The time edges,
    /// support barriers, atoms and grid are the same as for rows: a view's
    /// distinct next movements change support exactly when its rows would.
    /// Within one segment, contributions of the same view sum their clipped
    /// coefficients `gamma*lambda` and entry moments; different views stay
    /// separate terms (no hidden low-rank fit). Legacy row inputs (source
    /// admissions, or row packets served under this policy) are combined as
    /// before and become one new immutable block per output cohort.
    #[allow(clippy::too_many_arguments)]
    fn projected_shared(
        &self,
        parts: Vec<Part>,
        contributions: Vec<Contribution>,
        target: f64,
        cell: usize,
        work: &mut RoadWorkBudget,
        stats: &mut ProjectionStats,
        next_block: &mut u64,
    ) -> PyResult<Vec<Packet>> {
        let n = parts.len();
        let m = contributions.len();
        if n == 0 && m == 0 {
            return Ok(Vec::new());
        }
        let h = self.entry_projection_width_s;
        let mut lo = f64::INFINITY;
        let mut hi = f64::NEG_INFINITY;
        for p in &parts {
            let (a, b) = (p.a.unwrap(), p.b.unwrap());
            if !p.mass.is_finite() || p.mass <= 0. || !p.birth.is_finite() || b < a {
                return Err(arithmetic("invalid positive entry projection measure"));
            }
            lo = lo.min(a);
            hi = hi.max(b);
            if b > a && (a + h <= a || b - h >= b) {
                return Err(arithmetic("entry projection width is unrepresentable at entry clock"));
            }
        }
        let mut movement_events = 0usize;
        for c in &contributions {
            let (a, b) = (c.a, c.b);
            if !a.is_finite() || !b.is_finite() || b < a {
                return Err(arithmetic("invalid positive entry projection measure"));
            }
            check_coefficient(c.term.lambda, &c.term.block)?;
            lo = lo.min(a);
            hi = hi.max(b);
            if b > a {
                if a + h <= a || b - h >= b {
                    return Err(arithmetic("entry projection width is unrepresentable at entry clock"));
                }
                movement_events = movement_events.saturating_add(2 * self.view_movements(&c.term).count());
            }
        }
        let inputs = n + m;
        let event_count = n.saturating_mul(2).saturating_add(movement_events);
        let edge_count = inputs
            .checked_add(event_count)
            .and_then(|v| v.checked_add(2))
            .ok_or_else(|| budget("entry projection boundary capacity overflow"))?;
        let base_bytes = event_count
            .saturating_mul(std::mem::size_of::<(f64, usize, bool)>())
            .saturating_add(n.saturating_mul(2 * std::mem::size_of::<(f64, f64)>()))
            .saturating_add(self.groups.len().saturating_add(1).saturating_mul(std::mem::size_of::<usize>()))
            .saturating_add(parts.capacity().saturating_mul(std::mem::size_of::<Part>()))
            .saturating_add(contributions.capacity().saturating_mul(std::mem::size_of::<Contribution>()));
        let mut fixed_bytes = base_bytes.saturating_add(edge_count.saturating_mul(std::mem::size_of::<f64>()));
        work.interval(fixed_bytes)?;
        let mut events = checkpoint_vec(event_count)?;
        let mut edges = checkpoint_vec(edge_count)?;
        edges.extend([lo, hi]);
        for p in &parts {
            let (a, b) = (p.a.unwrap(), p.b.unwrap());
            if a == b {
                edges.push(a);
            } else {
                let movement = self.paths[self.routes[p.tag].0]
                    .get(p.offset + 1)
                    .copied()
                    .unwrap_or(self.groups.len());
                events.push((a, movement, true));
                events.push((b, movement, false));
            }
        }
        for c in &contributions {
            if c.a == c.b {
                edges.push(c.a);
            } else {
                for movement in self.view_movements(&c.term) {
                    events.push((c.a, movement, true));
                    events.push((c.b, movement, false));
                }
            }
        }
        events.sort_unstable_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
        let mut counts = checkpoint_vec(self.groups.len() + 1)?;
        counts.resize(self.groups.len() + 1, 0usize);
        let mut runs = checkpoint_vec(event_count)?;
        let mut run_start = None;
        let mut active_movements = 0usize;
        let event_first = events.first().map(|e| e.0).unwrap_or(lo);
        let event_last = events.last().map(|e| e.0).unwrap_or(hi);
        let mut i = 0;
        let mut protected = 0usize;
        while i < events.len() {
            let t = events[i].0;
            let mut changed = false;
            while i < events.len() && events[i].0 == t {
                let movement = events[i].1;
                let mut starts = 0usize;
                let mut ends = 0usize;
                while i < events.len() && events[i].0 == t && events[i].1 == movement {
                    if events[i].2 { starts += 1; } else { ends += 1; }
                    i += 1;
                }
                let before = counts[movement];
                let after = before.checked_add(starts).and_then(|v| v.checked_sub(ends))
                    .ok_or_else(|| arithmetic("entry projection support count overflow"))?;
                changed |= (before > 0) != (after > 0);
                if before == 0 && after > 0 { active_movements += 1; }
                if before > 0 && after == 0 { active_movements -= 1; }
                counts[movement] = after;
            }
            if changed {
                edges.push(t);
                if t > event_first && t < event_last { protected += 1; }
                if let Some(start) = run_start { runs.push((start, t)); }
                run_start = if active_movements > 0 { Some(t) } else { None };
            }
        }
        drop(events);
        for (left, right) in runs {
            let mut first = (left / h).floor() + 1.;
            let last = (right / h).ceil();
            if !first.is_finite() || !last.is_finite() || first + 1. == first || last + 1. == last {
                return Err(arithmetic("entry projection grid index is unrepresentable"));
            }
            if first * h <= left { first += 1.; }
            let count = (last - first).max(0.);
            if count >= usize::MAX as f64 {
                return Err(budget("entry projection grid exceeds addressable capacity"));
            }
            let count = count as usize;
            if count > self.record_budget {
                return Err(budget("entry projection grid record budget"));
            }
            let needed = edges.len().checked_add(count)
                .ok_or_else(|| budget("entry projection grid capacity overflow"))?;
            if needed > edges.capacity() {
                let required = needed.saturating_mul(std::mem::size_of::<f64>());
                work.interval(fixed_bytes.saturating_add(required))?;
                edges.try_reserve_exact(count)
                    .map_err(|_| budget("entry projection grid allocation unavailable"))?;
                fixed_bytes = base_bytes.saturating_add(edges.capacity().saturating_mul(std::mem::size_of::<f64>()));
                work.interval(fixed_bytes)?;
            }
            let mut previous = left;
            for j in 0..count {
                let edge = (first + j as f64) * h;
                if !edge.is_finite() || edge <= previous {
                    return Err(arithmetic("entry projection grid boundary does not advance"));
                }
                if edge < right { edges.push(edge); }
                previous = edge;
            }
        }
        edges.sort_unstable_by(f64::total_cmp);
        edges.dedup();
        // Per-segment row pieces (as for rows) and term pieces, their key
        // sort and the packed output: a conservative per-input envelope.
        let segment_bytes = n.saturating_mul(320).saturating_add(m.saturating_mul(
            2 * std::mem::size_of::<(usize, f64, f64, f64, f64)>() + 2 * std::mem::size_of::<Term>()));
        let mut out: Vec<Packet> = Vec::new();
        let mut records = 0usize;
        let mut local_bound = 0.;
        let mut terms_out = 0usize;
        let mut new_block_rows = 0usize;
        for (edge_index, &a) in edges.iter().enumerate() {
            work.interval(fixed_bytes.saturating_add(segment_bytes).saturating_add(
                out.len().saturating_add(1).max(4).saturating_mul(3 * std::mem::size_of::<Packet>())
            ))?;
            // Atoms at this edge: one exchangeable packet ahead of [a, b].
            let count = parts.iter().filter(|p| p.a == Some(a) && p.b == Some(a)).count();
            let point_terms = contributions.iter().filter(|c| c.a == a && c.b == a).count();
            if count > 0 || point_terms > 0 {
                let mut terms: Vec<Term> = Vec::new();
                if count > 0 {
                    let mut points = checkpoint_vec(count)?;
                    points.extend(parts.iter().filter(|p| p.a == Some(a) && p.b == Some(a)).copied());
                    let rows = combine(points)?;
                    new_block_rows += rows.len();
                    let block = self.new_block(rows, cell, next_block, work)?;
                    let hi = block.rows.len() as u32;
                    push_checked(&mut terms, Term { block, lo: 0, hi, shift: 0, lambda: 1., entry: f64::NAN })?;
                }
                if point_terms > 0 {
                    let mut pieces: Vec<(usize, f64)> = checkpoint_vec(point_terms)?;
                    pieces.extend(contributions.iter().enumerate()
                        .filter(|(_, c)| c.a == a && c.b == a)
                        .map(|(k, c)| (k, c.term.lambda)));
                    self.merge_term_pieces(&contributions, pieces.into_iter().map(|(k, l)| (k, l, 0., a, a)).collect(), a, &mut terms, &mut local_bound)?;
                }
                terms_out += terms.len();
                self.push_shared_packet(&mut out, terms, target, work, &mut records)?;
            }
            let Some(&b) = edges.get(edge_index + 1) else { continue; };
            let mut terms: Vec<Term> = Vec::new();
            // Row pieces: the unchanged row projection arithmetic.
            let mut pieces: Vec<(usize, usize, f64, f64, f64, f64, f64)> = checkpoint_vec(n)?;
            for p in &parts {
                let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
                let (x, y) = (a.max(pa), b.min(pb));
                if y <= x || pb <= pa { continue; }
                let fraction = (y - x) / (pb - pa);
                let mass = p.mass * fraction;
                let birth = p.birth * fraction;
                let relative_entry = mass * ((x - a) + (y - x) / 2.);
                if mass <= 0. || !mass.is_finite() || !birth.is_finite() || !relative_entry.is_finite() {
                    return Err(arithmetic("entry projection positive piece underflow or nonfinite moment"));
                }
                pieces.push((p.tag, p.offset, mass, birth, relative_entry, x, y));
            }
            if !pieces.is_empty() {
                pieces.sort_unstable_by_key(|p| (p.0, p.1));
                let category_count = 1 + pieces.windows(2)
                    .filter(|pair| (pair[0].0, pair[0].1) != (pair[1].0, pair[1].1)).count();
                let mut rows = checkpoint_vec(category_count)?;
                let mut cursor = 0;
                while cursor < pieces.len() {
                    let start = cursor;
                    let key = (pieces[start].0, pieces[start].1);
                    while cursor < pieces.len() && (pieces[cursor].0, pieces[cursor].1) == key {
                        cursor += 1;
                    }
                    let selected = &pieces[start..cursor];
                    let mass = sum(selected.iter().map(|p| p.2));
                    let birth = sum(selected.iter().map(|p| p.3));
                    let relative_entry = sum(selected.iter().map(|p| p.4));
                    let min_time = selected.iter().map(|p| p.5).fold(f64::INFINITY, f64::min);
                    let max_time = selected.iter().map(|p| p.6).fold(f64::NEG_INFINITY, f64::max);
                    let centroid = a + relative_entry / mass;
                    if !mass.is_finite() || !birth.is_finite() || !centroid.is_finite()
                        || centroid < min_time || centroid > max_time {
                        return Err(arithmetic("entry projection aggregate moment is unrepresentable"));
                    }
                    let bound = mass * ((max_time - min_time) / 2.);
                    if !bound.is_finite() {
                        return Err(arithmetic("entry projection local transport bound overflow"));
                    }
                    local_bound = upper_add(local_bound, bound);
                    let time = PackedTime::new(Some(centroid))?;
                    rows.push(Part { tag: key.0, offset: key.1, mass, birth, a: time, b: time });
                }
                drop(pieces);
                new_block_rows += rows.len();
                let block = self.new_block(rows, cell, next_block, work)?;
                let hi = block.rows.len() as u32;
                push_checked(&mut terms, Term { block, lo: 0, hi, shift: 0, lambda: 1., entry: f64::NAN })?;
            }
            // Term pieces: clipped coefficient gamma*lambda, entry moment
            // relative to the segment start (the row arithmetic per term).
            let mut term_pieces: Vec<(usize, f64, f64, f64, f64)> = Vec::new();
            for (k, c) in contributions.iter().enumerate() {
                let (pa, pb) = (c.a, c.b);
                let (x, y) = (a.max(pa), b.min(pb));
                if y <= x || pb <= pa { continue; }
                let fraction = (y - x) / (pb - pa);
                let lambda = c.term.lambda * fraction;
                check_coefficient(lambda, &c.term.block)?;
                let relative_entry = lambda * ((x - a) + (y - x) / 2.);
                if !relative_entry.is_finite() {
                    return Err(arithmetic("entry projection positive piece underflow or nonfinite moment"));
                }
                push_checked(&mut term_pieces, (k, lambda, relative_entry, x, y))?;
            }
            if !term_pieces.is_empty() {
                self.merge_term_pieces(&contributions, term_pieces, a, &mut terms, &mut local_bound)?;
            }
            if terms.is_empty() { continue; }
            terms_out += terms.len();
            self.push_shared_packet(&mut out, terms, target, work, &mut records)?;
        }
        stats.input_parts = stats.input_parts.saturating_add(inputs);
        stats.output_parts = stats.output_parts.saturating_add(records);
        stats.cohorts = stats.cohorts.saturating_add(out.len());
        stats.protected_support_boundaries = stats.protected_support_boundaries.saturating_add(protected);
        stats.local_w1_bound = upper_add(stats.local_w1_bound, local_bound);
        stats.input_contributions = stats.input_contributions.saturating_add(m);
        stats.output_terms = stats.output_terms.saturating_add(terms_out);
        stats.new_block_rows = stats.new_block_rows.saturating_add(new_block_rows);
        work.end_interval();
        Ok(out)
    }
    /// Group term pieces `(contribution, lambda, relative_entry, x, y)` by
    /// view key, summing coefficients and entry moments with fsum, and append
    /// one term per view with its common entry centroid `a + R/Lambda`.
    fn merge_term_pieces(
        &self,
        contributions: &[Contribution],
        mut pieces: Vec<(usize, f64, f64, f64, f64)>,
        a: f64,
        terms: &mut Vec<Term>,
        local_bound: &mut f64,
    ) -> PyResult<()> {
        pieces.sort_unstable_by(|x, y| contributions[x.0].term.key().cmp(&contributions[y.0].term.key()).then(x.0.cmp(&y.0)));
        let mut cursor = 0;
        while cursor < pieces.len() {
            let start = cursor;
            let key = contributions[pieces[start].0].term.key();
            while cursor < pieces.len() && contributions[pieces[cursor].0].term.key() == key {
                cursor += 1;
            }
            let selected = &pieces[start..cursor];
            let base = &contributions[selected[0].0].term;
            let lambda = sum(selected.iter().map(|p| p.1));
            let relative_entry = sum(selected.iter().map(|p| p.2));
            let min_time = selected.iter().map(|p| p.3).fold(f64::INFINITY, f64::min);
            let max_time = selected.iter().map(|p| p.4).fold(f64::NEG_INFINITY, f64::max);
            check_coefficient(lambda, &base.block)?;
            let centroid = a + relative_entry / lambda;
            if !centroid.is_finite() || centroid < min_time || centroid > max_time {
                return Err(arithmetic("entry projection aggregate moment is unrepresentable"));
            }
            if max_time > min_time {
                let view_mass = sum(base.rows().iter().map(|r| r.mass));
                let bound = lambda * view_mass * ((max_time - min_time) / 2.);
                if !bound.is_finite() {
                    return Err(arithmetic("entry projection local transport bound overflow"));
                }
                *local_bound = upper_add(*local_bound, bound);
            }
            push_checked(terms, Term {
                block: base.block.clone(),
                lo: base.lo,
                hi: base.hi,
                shift: base.shift,
                lambda,
                entry: centroid,
            })?;
        }
        Ok(())
    }
    fn push_shared_packet(
        &self,
        out: &mut Vec<Packet>,
        mut terms: Vec<Term>,
        target: f64,
        work: &mut RoadWorkBudget,
        records: &mut usize,
    ) -> PyResult<()> {
        terms.sort_unstable_by(|x, y| x.key().cmp(&y.key()));
        let new_rows: usize = terms
            .iter()
            .filter(|t| t.entry.is_nan())
            .map(|t| t.block.rows.len())
            .sum();
        *records = records.saturating_add(terms.len()).saturating_add(new_rows);
        if *records > self.record_budget {
            return Err(budget("entry projection record budget"));
        }
        work.require(out.len().saturating_add(1).max(4).saturating_mul(
            3 * std::mem::size_of::<Packet>()), "entry projection cohort reservation")?;
        let logical = terms.iter().map(|t| (t.hi - t.lo) as usize).sum();
        let mut packed = checkpoint_vec(terms.len())?;
        packed.extend(terms);
        let new_block_bytes: usize = packed
            .iter()
            .filter(|t| t.entry.is_nan())
            .map(|t| t.block.allocated_bytes())
            .sum();
        let parts = PacketParts::Shared { terms: packed, rows: logical };
        work.retain_interval(
            parts
                .allocated_bytes()
                .saturating_add(new_block_bytes)
                .saturating_add(std::mem::size_of::<Packet>()),
        );
        push_checked(out, Packet { target, parts })
    }
    fn push_projected_packet(
        &self,
        out: &mut Vec<Packet>,
        rows: Vec<Part>,
        target: f64,
        work: &mut RoadWorkBudget,
        records: &mut usize,
    ) -> PyResult<()> {
        *records = records.saturating_add(rows.len());
        if *records > self.record_budget {
            return Err(budget("entry projection record budget"));
        }
        work.require(out.len().saturating_add(1).max(4).saturating_mul(
            3 * std::mem::size_of::<Packet>()), "entry projection cohort reservation")?;
        let parts = work.pack_parts(rows)?;
        work.retain_interval(parts.allocated_bytes().saturating_add(std::mem::size_of::<Packet>()));
        push_checked(out, Packet { target, parts })
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
        let edge_bytes = parts.len().saturating_mul(2 * std::mem::size_of::<f64>());
        const ROW_BYTES: usize = 2 * std::mem::size_of::<Part>() + std::mem::size_of::<usize>();
        let transient = |count: usize, packets: usize| {
            edge_bytes
                .saturating_add(count.saturating_mul(ROW_BYTES))
                .saturating_add(
                    packets
                        .saturating_add(1)
                        .max(4)
                        .saturating_mul(3 * std::mem::size_of::<Packet>()),
                )
        };
        work.require(edge_bytes, "interval edges")?;
        let mut edges = checkpoint_vec(parts.len().saturating_mul(2))?;
        edges.extend(parts.iter().flat_map(|p| [p.a.unwrap(), p.b.unwrap()]));
        edges.sort_unstable_by(f64::total_cmp);
        edges.dedup();
        let mut out = vec![];
        let mut records = 0;
        for (k, &a) in edges.iter().enumerate() {
            let count = parts
                .iter()
                .filter(|p| p.a == Some(a) && p.b == Some(a))
                .count();
            work.interval(transient(count, out.len()))?;
            let mut point = checkpoint_vec(count)?;
            point.extend(
                parts
                    .iter()
                    .filter(|p| p.a == Some(a) && p.b == Some(a))
                    .cloned(),
            );
            let point = combine(point)?;
            if !point.is_empty() {
                records += point.len();
                let parts = work.pack_parts(point)?;
                work.retain_interval(
                    parts
                        .allocated_bytes()
                        .saturating_add(std::mem::size_of::<Packet>()),
                );
                push_checked(&mut out, Packet { target, parts })?;
            }
            if k + 1 < edges.len() {
                let b = edges[k + 1];
                let count = parts
                    .iter()
                    .filter(|p| p.a.unwrap() <= a && p.b.unwrap() >= b && p.b > p.a)
                    .count();
                work.interval(transient(count, out.len()))?;
                let mut split = checkpoint_vec(count)?;
                for p in &parts {
                    let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
                    if pa <= a && pb >= b && pb > pa {
                        let mut q = p.clone();
                        q.mass = q.mass * (b - a) / (pb - pa);
                        q.birth = q.birth * (b - a) / (pb - pa);
                        q.a = PackedTime::new(Some(a))?;
                        q.b = PackedTime::new(Some(b))?;
                        split.push(q);
                    }
                }
                let ps = combine(split)?;
                if !ps.is_empty() {
                    records += ps.len();
                    let parts = work.pack_parts(ps)?;
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
        if self.storage_budget.is_some() {
            let stats = s.debug_stats();
            let rows = stats.cell_parts.saturating_add(stats.pending_parts);
            let packets = stats.cell_packets.saturating_add(stats.pending_packets);
            let bytes = s
                .retained_storage_bytes()
                .max(self.retained_input_bytes)
                .saturating_mul(3)
                .saturating_add(rows.saturating_mul(16))
                .saturating_add(packets.saturating_add(s.cells.len()).saturating_mul(32));
            check_storage_limit(self.storage_budget, bytes, "state validation workspace")?;
        }
        let mut stored = vec![vec![]; self.classes.len()];
        let mut all = vec![];
        let mut residence = vec![];
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
            let occ = self.occupancy(c);
            if (c.v[2] - c.v[3] - occ).abs() > 1e-9 * c.v[2].max(1.) {
                return Err(arithmetic("cell mass ledger"));
            }
            if self.occupied(c) > self.groups[i][4] + 1e-9 * self.groups[i][4].max(1.) {
                return Err(arithmetic("cell storage"));
            }
            push_checked(&mut residence, (c.v[2] - c.v[3]) * s.t - c.v[4] + c.v[5])?;
            push_checked(&mut all, occ)?;
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
                        push_checked(&mut stored[self.class(&p)], p.mass)?;
                    }
                    if pending {
                        push_checked(&mut all, mass(packet))?;
                    }
                }
            }
        }
        if records > self.record_budget {
            return Err(budget("packet state budget"));
        }
        let tol = 1e-9 * s.totals[0].max(1.);
        if (s.totals[0] - s.totals[1] - sum(all)).abs() > tol {
            return Err(arithmetic("network mass ledger"));
        }
        let total_residence = sum(residence) + s.totals[4] + s.totals[5] + s.totals[6];
        let system = (s.totals[0] - s.totals[1]) * s.t - s.totals[2] + s.totals[3];
        if (total_residence - system).abs() > 1e-8 * total_residence.max(1.) {
            return Err(arithmetic("residence ledger"));
        }
        for (k, l) in s.ledger.iter().enumerate() {
            if l.iter().any(|x| !finite_nonnegative(*x))
                || (l[0] - l[1] - sum(stored[k].iter().copied())).abs() > 1e-9 * l[0].max(1.)
            {
                return Err(arithmetic("class mass/ledger mismatch"));
            }
        }
        for (a, b) in [(0, 0), (1, 1), (2, 4), (4, 5)] {
            let observed = sum(s.ledger.iter().map(|l| l[a]));
            if (observed - s.totals[b]).abs() > 1e-8 * observed.max(s.totals[b]).max(1.) {
                return Err(arithmetic("class/global ledger mismatch"));
            }
        }
        Ok(())
    }
    fn step_state(
        &self,
        s: &RoadState,
        dt: f64,
        offers: Vec<Offer>,
    ) -> PyResult<(RoadState, EventStore)> {
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
        let mut projection = ProjectionStats::default();
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
            next_block: s.next_block,
            census: SharedCensus::default(),
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
        let mut position = vec![0; n];
        // Diagnostic only: previous serve per cell (head position, rate bits, end time).
        let mut last_serve: Vec<Option<(usize, u64, f64)>> = if crate::v1_trace::enabled() {
            vec![None; n]
        } else {
            Vec::new()
        };
        let mut events = EventStore::default();
        let mut incoming: Vec<Vec<Part>> = vec![vec![]; n];
        // mark_block_scaled_v1: served terms per receiving cell.
        let mut incoming_terms: Vec<Vec<Contribution>> = vec![vec![]; n];
        // Diagnostic only: source (cell, head position, rate bits) per incoming row.
        let mut incoming_src: Vec<Vec<(usize, usize, u64)>> = if crate::v1_trace::enabled() {
            vec![vec![]; n]
        } else {
            Vec::new()
        };
        let mut marks: Vec<Vec<Mark>> = vec![vec![]; n];
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
                    t + (cursor + h) // DIAGNOSTIC: shared boundary with next start
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
                    let shared_head = self.mark_blocks && packet.parts.is_shared();
                    let (incoming_count, served, contributions) = if shared_head {
                        let terms = packet.parts.shared_terms().unwrap_or(&[]);
                        let (served, contributions) =
                            self.shared_serve(terms, packet.parts.len(), fraction, &work)?;
                        let incoming_count =
                            served.iter().filter(|part| self.dest(part).is_some()).count();
                        work.transfer(served.len(), incoming_count)?;
                        if self.storage_budget.is_some()
                            && events.len().saturating_add(served.len())
                                > self.checkpoint_event_limit()
                        {
                            return Err(budget("packet transfer budget"));
                        }
                        (incoming_count, served, contributions)
                    } else {
                        let incoming_count = packet
                            .parts
                            .iter()
                            .filter(|part| self.dest(part).is_some())
                            .count();
                        work.transfer(packet.parts.len(), incoming_count)?;
                        if self.storage_budget.is_some()
                            && events.len().saturating_add(packet.parts.len())
                                > self.checkpoint_event_limit()
                        {
                            return Err(budget("packet transfer budget"));
                        }
                        (incoming_count, portion(&packet.parts, fraction)?, Vec::new())
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
                        crate::v1_trace::add(class, served.len() as u64);
                        last_serve[i] = Some((position[i], rate.to_bits(), end_time));
                        crate::v1_trace::add("xfer.serve_rows", served.len() as u64);
                        crate::v1_trace::add("xfer.partial_serve", u64::from(fraction < 1.));
                        crate::v1_trace::add("xfer.serve_incoming_rows", incoming_count as u64);
                        crate::v1_trace::add(
                            "xfer.sink_rows",
                            served.len().saturating_sub(incoming_count) as u64,
                        );
                        if fraction < 1. {
                            crate::v1_trace::add("xfer.partial_rows", served.len() as u64);
                        }
                        crate::v1_trace::add("xfer.head_rows", packet.parts.len() as u64);
                    }
                    let remainder = if shared_head || fraction == 1. {
                        None
                    } else {
                        Some(portion(&packet.parts, 1. - fraction)?)
                    };
                    let sm = sum(served.iter().map(|p| p.mass));
                    if shared_head && fraction < 1. {
                        // The remainder is the same terms with scaled
                        // coefficients; no category row is copied.
                        queues[i][position[i]].0.parts.scale_shared(1. - fraction)?;
                    } else if let Some(parts) = remainder {
                        queues[i][position[i]].0.parts = work.pack_parts(parts)?;
                    } else {
                        position[i] += 1;
                        retired_heads += 1;
                    }
                    out.cells[i].v[3] += sm;
                    out.cells[i].v[5] += sm * mid;
                    for mut p in served {
                        let k = self.class(&p);
                        out.ledger[k][3] += p.mass * (local_mid - ready).max(0.);
                        let j = self.dest(&p);
                        events.push((p.tag, i, j, p.mass, start_time, end_time, p.birth))?;
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
                            push_checked(
                                &mut marks[j],
                                (k, p.mass, m.sample(local_mid).1, latent),
                            )?;
                            if !shared_head {
                                p.offset += 1;
                                if self.intervals {
                                    p.a = PackedTime::new(Some(start_time))?;
                                    p.b = PackedTime::new(Some(end_time))?;
                                }
                                push_checked(&mut incoming[j], p)?;
                                if !incoming_src.is_empty() {
                                    incoming_src[j].push((i, position[i], rate.to_bits()));
                                }
                            }
                        } else {
                            sink += p.mass;
                            out.ledger[k][1] += p.mass;
                            exit1 += p.mass * mid;
                        }
                    }
                    for (j, term) in contributions {
                        push_checked(
                            &mut incoming_terms[j],
                            Contribution {
                                term,
                                a: start_time,
                                b: end_time,
                            },
                        )?;
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
            let incoming_cap: usize = incoming.iter().map(Vec::capacity).sum();
            let marks_cap: usize = marks.iter().map(Vec::capacity).sum();
            let incoming_len: usize = incoming.iter().map(Vec::len).sum();
            crate::v1_trace::guard(
                "road_actual",
                "transfer buffers",
                events
                    .allocated_bytes()
                    .saturating_add(incoming_cap.saturating_mul(std::mem::size_of::<Part>()))
                    .saturating_add(marks_cap.saturating_mul(std::mem::size_of::<Mark>())),
                work.limit.unwrap_or(usize::MAX),
                &[
                    ("events_len", events.len()),
                    ("event_headers", events.header_count()),
                    ("incoming_len", incoming_len),
                    ("incoming_cap", incoming_cap),
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
                if f > 0.0 {
                    work.transfer(0, p.parts.len())?;
                }
                if crate::v1_trace::enabled() {
                    crate::v1_trace::add("pending.rows", p.parts.len() as u64);
                    if f > 0. && f < 1. {
                        crate::v1_trace::add("pending.partial_rows", p.parts.len() as u64);
                    }
                }
                let mut parts = portion(&p.parts, f)?;
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
                    push_checked(
                        &mut marks[i],
                        (k, part.mass, self.classes[k][11], self.classes[k][7]),
                    )?;
                }
                incoming[i]
                    .try_reserve(parts.len())
                    .map_err(|_| budget("native road incoming allocation unavailable"))?;
                if !incoming_src.is_empty() {
                    let k = incoming_src[i].len();
                    incoming_src[i].extend((0..parts.len()).map(|_| (usize::MAX, k, 0)));
                }
                incoming[i].extend(parts);
                if f < 1. {
                    push_checked(
                        &mut remain,
                        Packet {
                            target: p.target,
                            parts: work.pack_parts(portion(&p.parts, 1. - f)?)?,
                        },
                    )?;
                }
            }
            out.pending[i] = remain;
        }
        for i in 0..n {
            if !incoming_src.is_empty() && !incoming[i].is_empty() {
                exact_merge_census(&incoming[i], &incoming_src[i]);
            }
            let raw_rows = incoming[i].len();
            let parts = combine(std::mem::take(&mut incoming[i]))?;
            if crate::v1_trace::enabled() && raw_rows > 0 {
                crate::v1_trace::add("entry.raw_rows", raw_rows as u64);
                crate::v1_trace::add("entry.combined_rows", parts.len() as u64);
            }
            let contributions = std::mem::take(&mut incoming_terms[i]);
            let added = sum(parts.iter().map(|p| p.mass).chain(contributions.iter().flat_map(|c| {
                let lambda = c.term.lambda;
                c.term.rows().iter().map(move |r| lambda * r.mass)
            })));
            if added == 0. {
                continue;
            }
            let old = self.occupancy(&out.cells[i]);
            let speed =
                (old * out.cells[i].v[7] + sum(marks[i].iter().map(|m| m.1 * m.2))) / (old + added);
            let mut byclass: BTreeMap<usize, Vec<(f64, f64)>> = BTreeMap::new();
            for packet in &out.cells[i].packets {
                for p in &packet.parts {
                    let k = self.class(&p);
                    push_checked(
                        byclass.entry(k).or_default(),
                        (p.mass, out.cells[i].latent[&k]),
                    )?;
                }
            }
            for &(k, m, _, p) in &marks[i] {
                push_checked(byclass.entry(k).or_default(), (m, p))?;
            }
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
            let packets = if self.mark_blocks {
                self.projected_shared(
                    parts,
                    contributions,
                    target,
                    i,
                    &mut work,
                    &mut projection,
                    &mut out.next_block,
                )?
            } else if self.entry_projection_width_s > 0. {
                self.projected_packets(parts, target, &mut work, &mut projection)?
            } else if self.intervals {
                self.interval_packets(parts, target, &mut work)?
            } else {
                vec![Packet {
                    target,
                    parts: work.pack_parts(parts)?,
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
        for (j, v) in [born, sink, birth1, exit1, source_wait, hold, inherited]
            .into_iter()
            .enumerate()
        {
            out.totals[j] += v;
        }
        if self.mark_blocks {
            out.refresh_census()?;
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
        if self.entry_projection_width_s > 0. {
            *self.projection_stats.lock().unwrap_or_else(|e| e.into_inner()) = projection;
        }
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
            next_block: 0,
            census: SharedCensus::default(),
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
    pub(crate) fn projection_diagnostics(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let stats = *self.projection_stats.lock().unwrap_or_else(|e| e.into_inner());
        let out = PyDict::new(py);
        out.set_item("policy", if self.entry_projection_width_s > 0. { "entry_projection_support_v1" } else { "exact_intervals" })?;
        out.set_item("width_s", self.entry_projection_width_s)?;
        out.set_item("input_parts", stats.input_parts)?;
        out.set_item("output_parts", stats.output_parts)?;
        out.set_item("cohorts", stats.cohorts)?;
        out.set_item("protected_support_boundaries", stats.protected_support_boundaries)?;
        out.set_item("local_w1_bound_veh_s", stats.local_w1_bound)?;
        out.set_item("road_representation", self.road_representation())?;
        if self.mark_blocks {
            let census = self.state.census;
            out.set_item("input_contributions", stats.input_contributions)?;
            out.set_item("output_terms", stats.output_terms)?;
            out.set_item("new_block_rows", stats.new_block_rows)?;
            out.set_item("state_blocks", census.blocks)?;
            out.set_item("state_block_rows", census.block_rows)?;
            out.set_item("state_block_bytes", census.block_bytes)?;
            out.set_item("state_terms", census.terms)?;
        }
        out.set_item("scope", "latest validated proposed road transition in this runtime; may precede coupled rollback or describe a branch/replay; local time-measure projection cost, not network trajectory error; unchanged by failed road proposals and checkpoint restore")?;
        out.set_item("checkpointed", false)?;
        Ok(out.unbind())
    }
    #[getter]
    pub(crate) fn entry_projection_width_s(&self) -> f64 {
        self.entry_projection_width_s
    }
    #[getter]
    pub(crate) fn road_representation(&self) -> &'static str {
        if self.mark_blocks {
            MARK_BLOCK_POLICY
        } else {
            "rows"
        }
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
    #[pyo3(signature = (identity, dt, groups, signals, routes, classes, incoming, windows, record_budget, event_budget, intervals, entry_projection_width_s=0.0, road_representation="rows"))]
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
        entry_projection_width_s: f64,
        road_representation: &str,
    ) -> PyResult<Self> {
        let mark_blocks = parse_representation(road_representation)?;
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
            entry_projection_width_s,
            mark_blocks,
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
        let (s, e) = py.allow_threads(|| self.step_state(&self.state, dt, offers))?;
        self.state = s;
        // Explicit row-API boundary: materialize the ordered rows here only.
        e.to_rows()
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
            let (s, e) = py.allow_threads(|| self.step_state(&self.state, dt, offers))?;
            self.state = s;
            events.push(e.to_rows()?);
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
        entry_projection_width_s: f64,
        mark_blocks: bool,
    ) -> PyResult<Self> {
        if !entry_projection_width_s.is_finite() || entry_projection_width_s < 0. {
            return Err(val("entry_projection_width_s must be finite and nonnegative"));
        }
        if entry_projection_width_s > 0. && !intervals {
            return Err(val("entry projection requires preserved entry intervals"));
        }
        if mark_blocks && entry_projection_width_s <= 0. {
            return Err(val("mark_block_scaled_v1 requires a positive entry projection width"));
        }
        if identity.is_empty() {
            return Err(val("invalid native road configuration"));
        }
        let identity = representation_identity(&identity, entry_projection_width_s, mark_blocks);
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
            entry_projection_width_s,
            projection_stats: Mutex::new(ProjectionStats::default()),
            event_budget,
            intervals,
            mark_blocks,
            state: RoadState {
                t: 0.,
                cells: vec![],
                pending: vec![],
                totals: [0.; 7],
                ledger: vec![],
                next_block: 0,
                census: SharedCensus::default(),
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
            events: 0,
            event_headers: 0,
            incoming: 0,
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
            max_tag_bytes: 64,
        };
        let rows = 10_000;
        assert_eq!(
            a.road_step_bytes(rows, 100),
            3_000 + EventStore::upper_bytes(rows, 100) + 96
        );
        assert_eq!(a.road_step_bytes(0, 0), 3_096);
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
mod entry_projection_tests {
    use super::*;

    fn road(h: f64) -> V1Road {
        V1Road::new_shared_routes(
            "projection-test".into(), 1., vec![vec![100., 20., 100., 100., 1000., 1.]; 4],
            vec![None; 4], vec![vec![0, 1, 2], vec![0, 1, 3], vec![0, 3]],
            vec![(0, 0), (1, 0), (2, 0)],
            vec![vec![20., 1., 2., 3., 2., 1., 4., 0.5, 0.2, 0.3, 4., 10., 6.]],
            vec![vec![0], vec![1], vec![2], vec![3]], vec![], 10_000, None, true, h, false,
        ).unwrap()
    }
    fn part(tag: usize, mass: f64, birth: f64, a: f64, b: f64) -> Part {
        Part { tag, offset: 0, mass, birth,
            a: PackedTime::new(Some(a)).unwrap(), b: PackedTime::new(Some(b)).unwrap() }
    }
    fn work(limit: usize) -> RoadWorkBudget {
        RoadWorkBudget { limit: Some(limit), base: 0, events: 0, event_headers: 0, incoming: 0,
            interval_retained: 0, interval_transient: 0, service_events: None }
    }
    fn project(r: &V1Road, parts: Vec<Part>) -> (Vec<Packet>, ProjectionStats) {
        let mut stats = ProjectionStats::default();
        let out = r.projected_packets(parts, 100., &mut work(64 * 1024 * 1024), &mut stats).unwrap();
        (out, stats)
    }
    #[test]
    fn category_moments_and_later_route_divergence_are_retained() {
        let r = road(1.);
        // Different future routes share their immediate movement; changes of
        // multiplicity at .2 and .8 do not introduce support boundaries.
        let (out, stats) = project(&r, vec![part(0, 1., 2., 0., 1.), part(1, 2., 6., 0.2, 0.8)]);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].parts.len(), 2);
        let rows: Vec<_> = out[0].parts.iter().collect();
        assert_eq!((rows[0].tag, rows[1].tag), (0, 1));
        assert_eq!((rows[0].mass, rows[1].mass), (1., 2.));
        assert_eq!((rows[0].birth, rows[1].birth), (2., 6.));
        assert!((rows[0].a.unwrap() - 0.5).abs() < 1e-15);
        assert!((rows[1].a.unwrap() - 0.5).abs() < 1e-15);
        assert_eq!(stats.protected_support_boundaries, 0);
        assert!((stats.local_w1_bound - 1.1).abs() < 1e-14);
    }
    #[test]
    fn heterogeneous_support_and_tiny_suffix_create_barriers() {
        let r = road(10.);
        let tiny = 1e-100;
        let (out, stats) = project(&r, vec![part(0, 3., 0., 0., 3.), part(2, tiny, 0., 1., 2.)]);
        assert_eq!(out.len(), 3);
        assert_eq!(out.iter().map(|p| p.parts.len()).collect::<Vec<_>>(), vec![1, 2, 1]);
        assert_eq!(stats.protected_support_boundaries, 2);
        assert_eq!(out[1].parts.iter().find(|p| p.tag == 2).unwrap().mass, tiny);
        assert_eq!(out[0].parts.iter().next().unwrap().a.unwrap(), 0.5);
    }
    #[test]
    fn atoms_keep_bits_order_and_precede_right_segment() {
        let r = road(10.);
        let atom = part(0, 0.125, 0.0625, 0.5, 0.5);
        let (out, _) = project(&r, vec![part(0, 1., 0., 0., 1.), atom, part(1, 0.25, 0., 0.5, 0.5)]);
        assert_eq!(out.len(), 3);
        let saved = out[1].parts.iter().next().unwrap();
        assert_eq!(saved.mass.to_bits(), atom.mass.to_bits());
        assert_eq!(saved.birth.to_bits(), atom.birth.to_bits());
        assert_eq!(saved.a.0, atom.a.0);
        assert_eq!(out[1].parts.iter().nth(1).unwrap().tag, 1);
        assert_eq!(out[2].parts.iter().next().unwrap().a.unwrap(), 0.75);
    }
    #[test]
    fn irregular_split_preserves_tag_mass_birth_and_entry_moment() {
        let r = road(0.4);
        let input = vec![part(0, 3., 12., 0.1, 1.3), part(0, 2., 6., 0.2, 0.7), part(1, 0.7, 1.4, 0.1, 1.3)];
        let (out, _) = project(&r, input.clone());
        for tag in 0..2 {
            let expected: Vec<_> = input.iter().filter(|p| p.tag == tag).collect();
            let actual: Vec<_> = out.iter().flat_map(|p| p.parts.iter()).filter(|p| p.tag == tag).collect();
            for (a, b) in [
                (sum(actual.iter().map(|p| p.mass)), sum(expected.iter().map(|p| p.mass))),
                (sum(actual.iter().map(|p| p.birth)), sum(expected.iter().map(|p| p.birth))),
                (sum(actual.iter().map(|p| p.mass * p.a.unwrap())), sum(expected.iter().map(|p| p.mass * (p.a.unwrap() + (p.b.unwrap()-p.a.unwrap())/2.)))),
            ] { assert!((a-b).abs() < 1e-13); }
        }
    }
    #[test]
    fn underresolved_clock_and_positive_piece_underflow_fail() {
        let r = road(0.25);
        assert!(r.projected_packets(vec![part(0, 1., 0., 1e16, 1e16+2.)], 100., &mut work(1_000_000), &mut ProjectionStats::default()).is_err());
        let r = road(0.5);
        assert!(r.projected_packets(vec![part(0, f64::from_bits(1), 0., 0., 1.)], 100., &mut work(1_000_000), &mut ProjectionStats::default()).is_err());
    }
    #[test]
    fn empty_time_gaps_do_not_allocate_mesh() {
        let r = road(0.25);
        let (out, _) = project(&r, vec![part(0, 1., 0., 0., 1.), part(0, 1., 0., 1e12, 1e12+1.)]);
        assert_eq!(out.len(), 8);
    }
    #[test]
    fn projection_byte_budget_rejects_before_boundary_allocation() {
        let mut r = road(1e-6);
        r.record_budget = usize::MAX;
        assert!(r.projected_packets(vec![part(0, 1., 0., 0., 1.)], 100., &mut work(10_000), &mut ProjectionStats::default()).is_err());
        assert_eq!(r.state.t, 0.);
        assert!(r.state.cells.iter().all(|c| c.packets.is_empty()));
    }
}

#[cfg(test)]
mod event_store_tests {
    use super::*;

    fn rows(n: usize, batch: usize) -> Vec<EventRow> {
        let mut out = Vec::with_capacity(n);
        for r in 0..n {
            let b = r / batch;
            let dest = if r % 5 == 0 { None } else { Some(r % 97) };
            // Distinct bit patterns, including signed zero and subnormal mass.
            let mass = match r % 7 {
                0 => -0.0_f64.abs(),
                1 => f64::from_bits(1),
                _ => (r as f64).sqrt() * 1e-3,
            };
            out.push((r % 1013, b % 31, dest, mass, b as f64 * 0.1, b as f64 * 0.1 + 0.05, r as f64 * 1.5e-7));
        }
        out
    }

    fn same_bits(a: &EventRow, b: &EventRow) -> bool {
        a.0 == b.0
            && a.1 == b.1
            && a.2 == b.2
            && a.3.to_bits() == b.3.to_bits()
            && a.4.to_bits() == b.4.to_bits()
            && a.5.to_bits() == b.5.to_bits()
            && a.6.to_bits() == b.6.to_bits()
    }

    #[test]
    fn order_and_bits_survive_across_chunk_boundaries() {
        // Crosses both the row chunk and the header chunk boundaries.
        for (n, batch) in [(0, 1), (1, 1), (5, 2), (EVENT_ROW_CHUNK + 3, 61), (3 * EVENT_HEADER_CHUNK + 7, 1)] {
            let input = rows(n, batch);
            let store = EventStore::from_rows(input.iter().copied()).unwrap();
            assert_eq!(store.len(), n);
            let out: Vec<EventRow> = store.iter().collect();
            assert_eq!(out.len(), n);
            assert!(input.iter().zip(&out).all(|(a, b)| same_bits(a, b)));
            assert!(store.to_rows().unwrap().iter().zip(&input).all(|(a, b)| same_bits(a, b)));
        }
    }

    #[test]
    fn headers_only_merge_consecutive_equal_source_and_interval_bits() {
        let a = (1, 7, Some(2), 1.0, 0.5, 1.0, 0.0);
        let b = (2, 7, None, 2.0, 0.5, 1.0, 0.0);
        let c = (3, 8, Some(2), 3.0, 0.5, 1.0, 0.0); // other source
        let d = (4, 7, Some(2), 4.0, 0.5, 1.0, 0.0); // same key, not consecutive
        let z = (5, 7, Some(2), 5.0, -0.0, 1.0, 0.0); // -0.0 differs in bits from 0.0
        let y = (6, 7, Some(2), 6.0, 0.0, 1.0, 0.0);
        let s = EventStore::from_rows([a, b, c, d, z, y]).unwrap();
        assert_eq!(s.header_count(), 5);
        let out: Vec<EventRow> = s.iter().collect();
        for (x, y) in [a, b, c, d, z, y].iter().zip(&out) {
            assert!(same_bits(x, y));
        }
    }

    #[test]
    fn sink_sentinel_collision_is_rejected_without_partial_row() {
        let mut s = EventStore::default();
        s.push((1, 1, None, 1.0, 0.0, 1.0, 0.0)).unwrap();
        assert!(s.push((1, 1, Some(usize::MAX), 1.0, 0.0, 1.0, 0.0)).is_err());
        assert_eq!(s.len(), 1);
        assert_eq!(s.iter().count(), 1);
    }

    #[test]
    fn upper_bound_covers_actual_allocation_while_filling() {
        let input = rows(2 * EVENT_ROW_CHUNK + 11, 3);
        let mut s = EventStore::default();
        for (k, e) in input.iter().enumerate() {
            s.push(*e).unwrap();
            if k % 4093 == 0 || k + 1 == input.len() {
                assert!(s.allocated_bytes() <= EventStore::upper_bytes(s.len(), s.header_count()));
            }
        }
        // Worst case (one header per row) stays within the decode row limit.
        let budget = 10 * EVENT_ROW_CHUNK * 64;
        let n = EventStore::max_rows_within(budget);
        assert!(EventStore::upper_bytes(n, n) <= budget);
        assert_eq!(EventStore::upper_bytes(0, 0), 0);
    }
}

#[cfg(test)]
mod mark_block_tests {
    use super::*;

    const CAR: [f64; 13] = [20., 1., 2., 3., 2., 1., 4., 0.5, 0.2, 0.3, 4., 10., 6.];
    const TRUCK: [f64; 13] = [12., 0.8, 1., 2., 3., 1.5, 9., 0.6, 0.1, 0.2, 5., 8., 12.];

    /// Paths: 0 -> 1 -> 3 -> 4 and 0 -> 2 -> 3 -> 4 diverge at 0 and
    /// reconverge at 3; tag 4 leaves at 3. Cell 0 is a slow bottleneck so
    /// heads are partially served many times.
    fn road(mark: bool, h: f64) -> V1Road {
        let mut groups = vec![vec![100., 20., 10., 10., 1000., 1.]; 5];
        groups[0] = vec![60., 20., 10., 0.35, 1000., 1.];
        groups[3] = vec![60., 20., 10., 0.6, 1000., 1.];
        V1Road::new_shared_routes(
            "mark-block-test".into(), 1., groups, vec![None; 5],
            vec![vec![0, 1, 3, 4], vec![0, 2, 3, 4], vec![0, 1, 3]],
            vec![(0, 0), (1, 0), (0, 1), (1, 1), (2, 0)],
            vec![CAR.to_vec(), TRUCK.to_vec()],
            vec![vec![0], vec![1, 2], vec![3], vec![4]], vec![], 1_000_000, None, true, h, mark,
        ).unwrap()
    }
    fn offers(step: usize) -> Vec<Offer> {
        if step >= 12 {
            return vec![];
        }
        let s = step as f64;
        // Distinct birth marks; tag 4 is tiny but positive.
        vec![
            (0, 0.30 + 0.01 * s, 0.30 * s * 0.5, None, None),
            (1, 0.20, 0.20 * s * 0.25, None, None),
            (2, 0.07, 0., None, None),
            (3, 0.05 + 0.002 * s, 0.05 * s * 0.1, None, None),
            (4, 1e-9, 0., None, None),
        ]
    }
    fn advance(r: &mut V1Road, step: usize) -> EventStore {
        let (s, e) = r.propose_owned_step(1., offers(step)).unwrap();
        r.rollback(s);
        e
    }
    fn by_tag(s: &RoadState) -> BTreeMap<usize, (f64, f64)> {
        let mut out: BTreeMap<usize, (Vec<f64>, Vec<f64>)> = BTreeMap::new();
        for p in s.cells.iter().flat_map(|c| &c.packets).chain(s.pending.iter().flatten()) {
            for x in &p.parts {
                let e = out.entry(x.tag).or_default();
                e.0.push(x.mass);
                e.1.push(x.birth);
            }
        }
        out.into_iter().map(|(k, (m, b))| (k, (sum(m), sum(b)))).collect()
    }
    fn close(a: f64, b: f64, rel: f64) -> bool {
        (a - b).abs() <= rel * a.abs().max(b.abs()).max(1.)
    }
    fn wire(r: &V1Road) -> Vec<u8> {
        let mut w = Vec::new();
        r.write_state(&mut w).unwrap();
        w
    }

    #[test]
    fn shared_path_matches_rows_through_divergence_reconvergence_and_classes() {
        let (mut rows, mut mark) = (road(false, 0.25), road(true, 0.25));
        let mut saw_shared_partial = false;
        let mut saw_reconverged_views = false;
        let mut cohort_mismatch_steps = vec![];
        for step in 0..120 {
            let (ea, eb) = (advance(&mut rows, step), advance(&mut mark, step));
            // Events are linear in mass: per (tag, dest) totals agree.
            let agg = |e: &EventStore| {
                let mut m: BTreeMap<(usize, Option<usize>), Vec<f64>> = BTreeMap::new();
                for x in e.iter() {
                    m.entry((x.0, x.2)).or_default().push(x.3);
                }
                m.into_iter().map(|(k, v)| (k, sum(v))).collect::<BTreeMap<_, _>>()
            };
            let (ga, gb) = (agg(&ea), agg(&eb));
            assert_eq!(ga.keys().collect::<Vec<_>>(), gb.keys().collect::<Vec<_>>());
            for (k, v) in &ga {
                assert!(close(*v, gb[k], 1e-12), "event {k:?} {v} {}", gb[k]);
            }
            let (sa, sb) = (&rows.state, &mark.state);
            for j in 0..7 {
                assert!(close(sa.totals[j], sb.totals[j], 1e-12), "total {j}");
            }
            let worst = (0..2).flat_map(|k| (0..5).map(move |j| (k, j)))
                .map(|(k, j)| (sa.ledger[k][j] - sb.ledger[k][j]).abs() / sa.ledger[k][j].abs().max(1.))
                .fold(0., f64::max);
            if step < 34 {
                // Before the extra row-path cohort is served, all class
                // ledgers including queue wait agree to rounding.
                assert!(worst < 1e-14, "step {step}: {worst:e}");
            }
            for k in 0..2 {
                for j in 0..5 {
                    if j == 3 { continue; }
                    assert!(close(sa.ledger[k][j], sb.ledger[k][j], 1e-12), "step {step} class {k} ledger {j}: {} {} rel {:e}", sa.ledger[k][j], sb.ledger[k][j], (sa.ledger[k][j]-sb.ledger[k][j]).abs()/sa.ledger[k][j]);
                }
            }
            let (ta, tb) = (by_tag(sa), by_tag(sb));
            assert_eq!(ta.keys().collect::<Vec<_>>(), tb.keys().collect::<Vec<_>>());
            for (tag, (m, b)) in &ta {
                assert!(close(*m, tb[tag].0, 1e-12) && close(*b, tb[tag].1, 1e-12), "tag {tag}");
            }
            // Per-cell mass, birth and entry first moments agree. Cohort
            // counts may differ: an ulp-level difference of a junction event
            // end time toggles a protected support boundary (known defect
            // (b)/(c) of the V03 counterexample suite), see
            // `ulp_event_boundary_changes_cohort_count_not_observables`.
            for (ca, cb) in sa.cells.iter().zip(&sb.cells) {
                let m = |c: &Cell| sum(c.packets.iter().flat_map(|p| p.parts.iter().map(|x| x.mass)));
                let b = |c: &Cell| sum(c.packets.iter().flat_map(|p| p.parts.iter().map(|x| x.birth)));
                let e = |c: &Cell| sum(c.packets.iter().flat_map(|p| p.parts.iter().map(|x| x.mass * x.a.unwrap())));
                assert!(close(m(ca), m(cb), 1e-12) && close(b(ca), b(cb), 1e-12) && close(e(ca), e(cb), 1e-12));
                if ca.packets.len() != cb.packets.len() {
                    cohort_mismatch_steps.push(step);
                }
            }
            for p in &sb.cells[0].packets {
                saw_shared_partial |= p.parts.shared_terms().is_some_and(|t| t.iter().any(|t| t.lambda < 1.));
            }
            for p in &sb.cells[3].packets {
                if let Some(terms) = p.parts.shared_terms() {
                    let blocks: Vec<_> = terms.iter().map(|t| t.block.id).collect();
                    saw_reconverged_views |= terms.len() > 1
                        && blocks.windows(2).any(|w| w[0] == w[1]);
                }
            }
        }
        assert!(saw_shared_partial, "partial head service of a shared cohort was exercised");
        assert!(saw_reconverged_views, "one block reached cell 3 by two prefixes as distinct views");
        assert!(close(rows.state.totals[1], mark.state.totals[1], 1e-12));
        assert!(mark.state.totals[1] > 0.);
        // Observed on this fixture: only the ulp-boundary steps differ.
        assert_eq!(cohort_mismatch_steps, (25..34).collect::<Vec<_>>());
    }

    #[test]
    fn ulp_event_boundary_changes_cohort_count_not_observables() {
        // Step 25 of the shared fixture: the row path's consecutive serves of
        // cell 3 end at 25.698747293149196 and restart at 25.6987472931492
        // (one ulp gap), which the support scan reads as an empty-support
        // run and protects as a cohort boundary. The mark-block path's head
        // masses round differently, its event times are contiguous, and it
        // keeps one cohort. Both preserve the cell's measures (checked in the
        // test above); this records the cohort-count difference.
        let (mut rows, mut mark) = (road(false, 0.25), road(true, 0.25));
        for step in 0..26 {
            advance(&mut rows, step);
            advance(&mut mark, step);
        }
        assert_eq!(rows.state.cells[4].packets.len(), 4);
        assert_eq!(mark.state.cells[4].packets.len(), 3);
        // Counterexample kept (strict): serving that extra cohort changes the
        // event partition and hence the midpoint queue-wait quadrature
        // (class ledger [3]) by ~9e-8 relative, above the PLAN residence
        // tolerance 1e-8, while vehicle mass, birth and entry moments agree
        // to ~1e-16. Cause: the row path's ulp-boundary sensitivity, not mass
        // sharing. If defects (b)/(c) are fixed this assertion must be
        // revisited (it is expected to fail then).
        for step in 26..60 {
            advance(&mut rows, step);
            advance(&mut mark, step);
        }
        let rel = (rows.state.ledger[0][3] - mark.state.ledger[0][3]).abs() / rows.state.ledger[0][3];
        assert!(rel > 1e-8 && rel < 1e-6, "{rel:e}");
        for j in [0, 1, 2, 4] {
            let a = rows.state.ledger[0][j];
            assert!((a - mark.state.ledger[0][j]).abs() <= 1e-14 * a.max(1.));
        }
    }

    #[test]
    fn repeated_partial_service_scales_without_row_growth() {
        let r = road(true, 0.25);
        let rows: Vec<Part> = (0..5)
            .map(|tag| Part { tag, offset: 0, mass: 0.1 + tag as f64, birth: tag as f64,
                a: PackedTime::new(Some(0.)).unwrap(), b: PackedTime::new(Some(0.)).unwrap() })
            .collect();
        let mut next = 0;
        let w = RoadWorkBudget { limit: None, base: 0, events: 0, event_headers: 0, incoming: 0,
            interval_retained: 0, interval_transient: 0, service_events: None };
        let block = r.new_block(rows.clone(), 0, &mut next, &w).unwrap();
        let mut head = PacketParts::Shared {
            terms: vec![Term { block: block.clone(), lo: 0, hi: 5, shift: 0, lambda: 1., entry: 0.25 }],
            rows: 5,
        };
        let (m0, b0) = (sum(head.iter().map(|p| p.mass)), sum(head.iter().map(|p| p.birth)));
        let (mut served_m, mut served_b, mut served_e) = (vec![], vec![], vec![]);
        for k in 0..10_000 {
            let f = 1e-4 * (1. + (k % 7) as f64);
            let (served, contributions) = r.shared_serve(head.shared_terms().unwrap(), head.len(), f, &w).unwrap();
            assert_eq!(served.len(), 5);
            // Two next movements (cells 1 and 2) per term, no copy of rows.
            assert_eq!(contributions.len(), 2);
            assert!(contributions.iter().all(|(_, t)| Arc::ptr_eq(&t.block, &block)));
            served_m.extend(served.iter().map(|p| p.mass));
            served_b.extend(served.iter().map(|p| p.birth));
            served_e.extend(served.iter().map(|p| p.mass * 0.25));
            head.scale_shared(1. - f).unwrap();
            assert_eq!(head.shared_terms().unwrap().len(), 1);
        }
        // One block allocation shared by the head and nothing else retained.
        assert_eq!(Arc::strong_count(&block), 2);
        assert_eq!(head.allocated_bytes(), std::mem::size_of::<Term>());
        let rem_m = sum(head.iter().map(|p| p.mass));
        let rem_b = sum(head.iter().map(|p| p.birth));
        let rem_e = sum(head.iter().map(|p| p.mass * p.a.unwrap()));
        // Mass, birth and entry first moments are conserved to rounding of
        // 10^4 sequential scalings (each <= 1 ulp relative).
        assert!(close(sum(served_m.iter().copied().chain([rem_m])), m0, 1e-11));
        assert!(close(sum(served_b.iter().copied().chain([rem_b])), b0, 1e-11));
        assert!(close(sum(served_e.iter().copied().chain([rem_e])), m0 * 0.25, 1e-11));
    }

    #[test]
    fn tiny_coefficient_underflow_fails_explicitly() {
        let r = road(true, 0.25);
        let w = RoadWorkBudget { limit: None, base: 0, events: 0, event_headers: 0, incoming: 0,
            interval_retained: 0, interval_transient: 0, service_events: None };
        let mut next = 0;
        let tiny = vec![Part { tag: 0, offset: 0, mass: 1e-300, birth: 0.,
            a: PackedTime::new(Some(0.)).unwrap(), b: PackedTime::new(Some(0.)).unwrap() }];
        let block = r.new_block(tiny, 0, &mut next, &w).unwrap();
        let term = Term { block, lo: 0, hi: 1, shift: 0, lambda: 1., entry: f64::NAN };
        let mut head = PacketParts::Shared { terms: vec![term.clone()], rows: 1 };
        // lambda * 1e-300 below the smallest normal: the positive mass would
        // become subnormal/zero; this is refused rather than dropped.
        assert!(r.shared_serve(head.shared_terms().unwrap(), 1, 1e-10, &w).is_err());
        assert!(head.scale_shared(1e-10).is_err());
        // A representable coefficient still serves the positive mass.
        let (served, _) = r.shared_serve(&[term], 1, 0.5, &w).unwrap();
        assert!(served[0].mass > 0.);
        assert!(check_coefficient(0., &head.shared_terms().unwrap()[0].block).is_err());
        assert!(check_coefficient(f64::NAN, &head.shared_terms().unwrap()[0].block).is_err());
    }

    #[test]
    fn checkpoint_roundtrip_resumes_bit_identically_and_rejects_bad_references() {
        let mut a = road(true, 0.25);
        for step in 0..9 {
            advance(&mut a, step);
        }
        assert!(a.state.census.blocks > 0 && a.state.census.terms > 0);
        let saved = wire(&a);
        let mut b = road(true, 0.25);
        let decoded = b.read_state(&mut saved.as_slice()).unwrap();
        b.install_state(decoded);
        assert_eq!(wire(&b), saved);
        assert_eq!(b.state.census.block_bytes, a.state.census.block_bytes);
        for step in 9..60 {
            advance(&mut a, step);
            advance(&mut b, step);
            assert_eq!(wire(&a), wire(&b));
        }
        // The row representation cannot read the shared wire (binding).
        let rows = road(false, 0.25);
        assert!(rows.read_state(&mut saved.as_slice()).is_err());
        // Corrupt the first term's block reference: rejected, not repaired.
        let mut a = road(true, 0.25);
        for step in 0..9 {
            advance(&mut a, step);
        }
        let saved = wire(&a);
        let fresh = road(true, 0.25);
        let mut corrupt = saved.clone();
        // Overwrite the block counter with 0: every pooled id is then invalid.
        let at = 8 + a.identity.len() + 8;
        corrupt[at..at + 8].copy_from_slice(&0u64.to_le_bytes());
        assert!(fresh.read_state(&mut corrupt.as_slice()).is_err());
        assert!(fresh.read_state(&mut &saved[..saved.len() - 1]).is_err());
    }

    #[test]
    fn allocation_failure_rolls_back_without_state_change() {
        let mut r = road(true, 0.25);
        for step in 0..6 {
            advance(&mut r, step);
        }
        let before = wire(&r);
        // A budget that admits the committed state but not the next step.
        let retained = r.state.retained_storage_bytes();
        r.storage_budget = Some(retained.saturating_mul(3) + 1024);
        r.record_budget = 1_000_000;
        assert!(r.propose_owned_step(1., offers(6)).is_err());
        assert_eq!(wire(&r), before);
        // The same step succeeds once the budget admits it.
        r.storage_budget = Some(usize::MAX / 4);
        assert!(r.propose_owned_step(1., offers(6)).is_ok());
    }

    #[test]
    fn rows_default_is_unchanged_and_policy_requires_projection() {
        assert!(V1Road::new_shared_routes(
            "x".into(), 1., vec![vec![1., 1., 1., 1., 1., 1.]], vec![None], vec![vec![0]], vec![(0, 0)],
            vec![CAR.to_vec()], vec![vec![0]], vec![], 10, None, true, 0., true).is_err());
        let r = road(false, 0.25);
        assert_eq!(r.identity, projection_identity("mark-block-test", 0.25));
        let m = road(true, 0.25);
        assert_eq!(m.identity, format!("{}:{MARK_BLOCK_POLICY}", r.identity));
    }
}
