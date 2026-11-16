//! Rust owner of the V1 T02/T04 finite-response FIFO packet state.
//! Registry paths are interned; tags retain independent observable ledgers.
use crate::v1_parallel::ordered_map;
use pyo3::exceptions::{PyArithmeticError, PyIOError, PyMemoryError, PyValueError};
use pyo3::prelude::*;
use std::collections::{BTreeMap, HashMap};
use std::io::{Read, Write};
use std::sync::Mutex;

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
type Mark = (usize, f64, f64, f64);
#[derive(Clone)]
struct Part {
    tag: usize,
    offset: usize,
    mass: f64,
    birth: f64,
    a: Option<f64>,
    b: Option<f64>,
}
#[derive(Clone)]
struct Packet {
    target: f64,
    parts: Vec<Part>,
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
}

/// Conservative structural working allowance, not an allocator/RSS theorem.
/// Captures one supplied immutable snapshot, the committed owner, a candidate,
/// and the large source/transfer/splitting workspaces. Unrelated user-retained
/// snapshots and allocator metadata remain covered by the process limit.
struct RoadWorkBudget {
    limit: Option<usize>,
    base: usize,
    events: usize,
    incoming: usize,
    interval_rows: usize,
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
    fn reserve(&mut self, bytes: usize, validation: usize) -> PyResult<()> {
        self.decoded = self.decoded.saturating_add(bytes);
        self.validation = self.validation.saturating_add(validation);
        let required = self
            .decoded
            .max(self.retained_input)
            .saturating_mul(3)
            .saturating_add(self.validation);
        check_storage_limit(self.limit, required, "checkpoint decode preflight")
    }
}
impl RoadWorkBudget {
    fn require(&self, extra: usize, phase: &str) -> PyResult<()> {
        let required =
            self.base
                .saturating_add(
                    self.events
                        .saturating_mul(2 * std::mem::size_of::<EventRow>()),
                )
                .saturating_add(self.incoming.saturating_mul(
                    2 * (std::mem::size_of::<Part>() + std::mem::size_of::<Mark>()),
                ))
                .saturating_add(
                    self.interval_rows
                        .saturating_mul(3 * std::mem::size_of::<Part>()),
                )
                .saturating_add(extra);
        check_storage_limit(self.limit, required, phase)
    }
    fn transfer(&mut self, events: usize, incoming: usize) -> PyResult<()> {
        self.events = self.events.saturating_add(events);
        self.incoming = self.incoming.saturating_add(incoming);
        self.require(0, "transfer candidates")
    }
    fn interval(&mut self, rows: usize) -> PyResult<()> {
        self.interval_rows = self.interval_rows.saturating_add(rows);
        self.require(0, "entry interval split")
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
            }
        }
        out.vector_capacity_bytes += out.packet_capacity * std::mem::size_of::<Packet>()
            + out.part_capacity * std::mem::size_of::<Part>();
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
    let mut parts = checkpoint_vec(packet.parts.len())?;
    parts.extend_from_slice(&packet.parts);
    Ok(Packet {
        target: packet.target,
        parts,
    })
}
fn clone_packets(packets: &[Packet]) -> PyResult<Vec<Packet>> {
    let mut result = checkpoint_vec(packets.len())?;
    for packet in packets {
        result.push(clone_packet(packet)?);
    }
    Ok(result)
}
fn portion(parts: &[Part], f: f64) -> PyResult<Vec<Part>> {
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
                for v in [p.a, p.b] {
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
                    a: interval[0],
                    b: interval[1],
                });
            }
            q.push(Packet { target, parts });
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
        let state = RoadState {
            t,
            cells,
            pending,
            totals,
            ledger,
        };
        self.check_state(&state)?;
        Ok(state)
    }
    pub(crate) fn install_state(&mut self, state: RoadState) {
        self.rollback(state);
        self.retained_input_bytes = 0;
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
    pub(crate) fn begin_call_storage_accounting(&mut self) {
        self.retained_input_bytes = if self.storage_budget.is_some() {
            self.state.retained_storage_bytes()
        } else {
            0
        };
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
                incoming: 0,
                interval_rows: 0,
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
        let work = RoadWorkBudget {
            limit: self.storage_budget,
            base,
            events: 0,
            incoming: 0,
            interval_rows: 0,
        };
        work.require(0, "tick preflight")?;
        Ok(work)
    }
    pub(crate) fn owned_step(&mut self, dt: f64, offers: Vec<Offer>) -> PyResult<Vec<EventRow>> {
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
    ) -> PyResult<(RoadState, Vec<EventRow>)> {
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
                push_checked(counts.entry(self.class(p)).or_default(), p.mass)?;
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
        work.require(
            parts.len().saturating_mul(2 * std::mem::size_of::<f64>()),
            "interval edges",
        )?;
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
            work.interval(count)?;
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
                push_checked(
                    &mut out,
                    Packet {
                        target,
                        parts: point,
                    },
                )?;
            }
            if k + 1 < edges.len() {
                let b = edges[k + 1];
                let count = parts
                    .iter()
                    .filter(|p| p.a.unwrap() <= a && p.b.unwrap() >= b && p.b > p.a)
                    .count();
                work.interval(count)?;
                let mut split = checkpoint_vec(count)?;
                split.extend(parts.iter().filter_map(|p| {
                    let (pa, pb) = (p.a.unwrap(), p.b.unwrap());
                    if pa <= a && pb >= b && pb > pa {
                        let mut q = p.clone();
                        q.mass = q.mass * (b - a) / (pb - pa);
                        q.birth = q.birth * (b - a) / (pb - pa);
                        q.a = Some(a);
                        q.b = Some(b);
                        Some(q)
                    } else {
                        None
                    }
                }));
                let ps = combine(split)?;
                if !ps.is_empty() {
                    records += ps.len();
                    push_checked(&mut out, Packet { target, parts: ps })?;
                }
            }
            if records > self.record_budget {
                return Err(budget("entry interval record budget"));
            }
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
                        push_checked(&mut stored[self.class(p)], p.mass)?;
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
    ) -> PyResult<(RoadState, Vec<EventRow>)> {
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
                        a,
                        b: z,
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
                    parts: combine(p)?,
                },
            )?;
        }
        let source_wait = dt * sum(out.pending.iter().flat_map(|q| q.iter().map(mass)));
        for q in &out.pending {
            for packet in q {
                for p in &packet.parts {
                    out.ledger[self.class(p)][2] += dt * p.mass;
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
        let mut events = vec![];
        let mut incoming: Vec<Vec<Part>> = vec![vec![]; n];
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
                        let j = self.dest(p).unwrap_or(n);
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
                    let served = portion(&packet.parts, fraction)?;
                    let remainder = if fraction == 1. {
                        None
                    } else {
                        Some(portion(&packet.parts, 1. - fraction)?)
                    };
                    let sm = sum(served.iter().map(|p| p.mass));
                    if let Some(parts) = remainder {
                        queues[i][position[i]].0.parts = parts;
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
                        push_checked(
                            &mut events,
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
                            push_checked(
                                &mut marks[j],
                                (k, p.mass, m.sample(local_mid).1, latent),
                            )?;
                            p.offset += 1;
                            if self.intervals {
                                p.a = Some(start_time);
                                p.b = Some(end_time);
                            }
                            push_checked(&mut incoming[j], p)?;
                        } else {
                            sink += p.mass;
                            out.ledger[k][1] += p.mass;
                            exit1 += p.mass * mid;
                        }
                    }
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
        for i in 0..n {
            for (p, ready) in &queues[i][position[i]..] {
                for part in &p.parts {
                    out.ledger[self.class(part)][3] += part.mass * (dt - ready).max(0.);
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
                    active[self.class(x)] = true;
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
                let mut parts = portion(&p.parts, f)?;
                let m = sum(parts.iter().map(|p| p.mass));
                free[i] = (free[i] - m).max(0.);
                space[i] =
                    (space[i] - sum(parts.iter().map(|p| p.mass * self.footprint(p.tag)))).max(0.);
                for part in &mut parts {
                    let k = self.class(part);
                    if self.intervals {
                        part.a = Some(end);
                        part.b = Some(end);
                    }
                    push_checked(
                        &mut marks[i],
                        (k, part.mass, self.classes[k][11], self.classes[k][7]),
                    )?;
                }
                incoming[i]
                    .try_reserve(parts.len())
                    .map_err(|_| budget("native road incoming allocation unavailable"))?;
                incoming[i].extend(parts);
                if f < 1. {
                    push_checked(
                        &mut remain,
                        Packet {
                            target: p.target,
                            parts: portion(&p.parts, 1. - f)?,
                        },
                    )?;
                }
            }
            out.pending[i] = remain;
        }
        for i in 0..n {
            let parts = combine(std::mem::take(&mut incoming[i]))?;
            let added = sum(parts.iter().map(|p| p.mass));
            if added == 0. {
                continue;
            }
            let old = self.occupancy(&out.cells[i]);
            let speed =
                (old * out.cells[i].v[7] + sum(marks[i].iter().map(|m| m.1 * m.2))) / (old + added);
            let mut byclass: BTreeMap<usize, Vec<(f64, f64)>> = BTreeMap::new();
            for packet in &out.cells[i].packets {
                for p in &packet.parts {
                    let k = self.class(p);
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
            let packets = if self.intervals {
                self.interval_packets(parts, target, &mut work)?
            } else {
                vec![Packet { target, parts }]
            };
            out.cells[i]
                .packets
                .try_reserve(packets.len())
                .map_err(|_| budget("native road packet allocation unavailable"))?;
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
            check_storage_limit(
                self.storage_budget,
                retained.saturating_mul(3),
                "candidate and immutable snapshot",
            )?;
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
        Ok((out, events))
    }
    fn row(&self) -> StateRow {
        let s = &self.state;
        let part = |p: &Part| (p.tag, p.offset, p.mass, p.birth, p.a, p.b);
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
    fn from_row(&self, row: StateRow) -> PyResult<RoadState> {
        let (identity, t, cells, pending, totals, ledger) = row;
        if identity != self.identity {
            return Err(val("native road checkpoint binding differs"));
        }
        let part = |(tag, offset, mass, birth, a, b)| Part {
            tag,
            offset,
            mass,
            birth,
            a,
            b,
        };
        let packet = |(target, parts): PacketRow| Packet {
            target,
            parts: parts.into_iter().map(part).collect(),
        };
        let mut cs = vec![];
        for (v, p, l) in cells {
            let v: [f64; 8] = v.try_into().map_err(|_| val("cell row length"))?;
            let latent: BTreeMap<usize, f64> = l.iter().copied().collect();
            if latent.len() != l.len() {
                return Err(val("duplicate latent class"));
            }
            cs.push(Cell {
                v,
                packets: p.into_iter().map(packet).collect(),
                latent,
            });
        }
        let totals: [f64; 7] = totals.try_into().map_err(|_| val("totals row length"))?;
        let mut ls = vec![];
        for l in ledger {
            ls.push(l.try_into().map_err(|_| val("ledger row length"))?);
        }
        let s = RoadState {
            t,
            cells: cs,
            pending: pending
                .into_iter()
                .map(|q| q.into_iter().map(packet).collect())
                .collect(),
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
        Ok(())
    }
    fn reset(&mut self, t: f64) -> PyResult<()> {
        if !finite_nonnegative(t) || (t / self.dt - (t / self.dt).round()).abs() > 1e-9 {
            return Err(val("nonnegative grid-aligned time origin"));
        }
        self.state = self.blank(t);
        self.retained_input_bytes = 0;
        Ok(())
    }
    fn step(&mut self, py: Python<'_>, dt: f64, offers: Vec<Offer>) -> PyResult<Vec<EventRow>> {
        self.begin_call_storage_accounting();
        let (s, e) = py.allow_threads(|| self.step_state(&self.state, dt, offers))?;
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
            let (s, e) = py.allow_threads(|| self.step_state(&self.state, dt, offers))?;
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
