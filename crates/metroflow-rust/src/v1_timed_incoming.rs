//! Exact incoming Part/Mark storage with shared per-service class controls.
//!
//! This module changes only the transient carrier. Row arithmetic, source append
//! order, routing and midpoint samples remain owned by v1_road. The caller enables
//! it only for the bounded, interval-preserving compact-registry path.
//!
//! A control table is append-only and belongs to one road-step workspace. Every
//! row must be decoded with the SAME table used by push_checked. Moving either
//! owner preserves all indices; dropping a cell never drops the shared table.

use super::{arithmetic, budget, checkpoint_vec, Mark, PackedTime, Part};
use pyo3::prelude::PyResult;
use std::mem::size_of;

pub(super) const TIMED_INCOMING_CHUNK: usize = 128;

#[derive(Clone, Copy)]
#[repr(C)]
struct Control {
    a: PackedTime,
    b: PackedTime,
    speed: f64,
    latent: f64,
}

#[derive(Clone, Copy)]
#[repr(C)]
struct Row {
    mass: f64,
    birth: f64,
    tag: u32,
    offset: u32,
    control: u32,
}

// The native producer's preflight uses 32 bytes per row/control. Keep that
// allocation contract a compile-time requirement, including on other targets.
const _: [(); 32] = [(); size_of::<Row>()];
const _: [(); 32] = [(); size_of::<Control>()];

/// No per-row heap allocations. All non-final pages contain exactly 128 values.
/// Descriptor growth is explicit, so preflight does not guess Vec's growth rule.
struct Pages<T> {
    chunks: Vec<Vec<T>>,
    len: usize,
}

impl<T> Default for Pages<T> {
    fn default() -> Self {
        Self {
            chunks: Vec::new(),
            len: 0,
        }
    }
}

fn checked_add(a: usize, b: usize) -> PyResult<usize> {
    a.checked_add(b)
        .ok_or_else(|| budget("timed incoming allocation length overflow"))
}

fn checked_mul(a: usize, b: usize) -> PyResult<usize> {
    a.checked_mul(b)
        .ok_or_else(|| budget("timed incoming allocation byte overflow"))
}

fn pages_for(len: usize) -> usize {
    len / TIMED_INCOMING_CHUNK + usize::from(len % TIMED_INCOMING_CHUNK != 0)
}

/// Total payload + descriptor peak for this carrier, INCLUDING existing storage.
/// Actual row-page allocator metadata and the outer carrier object's storage are
/// deliberately excluded; the caller accounts for those separately.
/// The old and replacement descriptor Vec coexist during an explicit growth.
fn projected_pages_bytes(
    len: usize,
    descriptor_capacity: usize,
    additional: usize,
    element_bytes: usize,
) -> PyResult<usize> {
    let new_len = checked_add(len, additional)?;
    let needed_pages = pages_for(new_len);
    let slots = checked_mul(needed_pages, TIMED_INCOMING_CHUNK)?;
    let payload = checked_mul(slots, element_bytes)?;
    let peak_headers = if needed_pages <= descriptor_capacity {
        descriptor_capacity
    } else {
        // Explicit growth below maintains capacities 0, 4, 8, 16, ... .
        // Compute the last (largest) old + replacement pair in O(1), even
        // when projecting a whole batch that crosses several growths.
        let target = needed_pages
            .checked_next_power_of_two()
            .ok_or_else(|| budget("timed incoming descriptor capacity overflow"))?
            .max(4);
        let previous = if target == 4 { 0 } else { target / 2 };
        checked_add(previous, target)?
    };
    checked_add(payload, checked_mul(peak_headers, size_of::<Vec<u8>>())?)
}

impl<T> Pages<T> {
    fn capacity(&self) -> usize {
        // Fixed page invariant: O(1), including when called on every service.
        self.chunks.len().saturating_mul(TIMED_INCOMING_CHUNK)
    }

    fn physical_capacity_bytes(&self) -> usize {
        self.capacity().saturating_mul(size_of::<T>())
    }

    fn allocated_bytes(&self) -> usize {
        self.physical_capacity_bytes()
            .saturating_add(self.chunks.capacity().saturating_mul(size_of::<Vec<T>>()))
    }

    fn projected_append_bytes(&self, additional: usize) -> PyResult<usize> {
        projected_pages_bytes(self.len, self.chunks.capacity(), additional, size_of::<T>())
    }

    fn get(&self, index: usize) -> Option<&T> {
        if index >= self.len {
            return None;
        }
        self.chunks
            .get(index / TIMED_INCOMING_CHUNK)?
            .get(index % TIMED_INCOMING_CHUNK)
    }

    fn push_checked(&mut self, value: T) -> PyResult<()> {
        let next_len = checked_add(self.len, 1)?;
        if self.len % TIMED_INCOMING_CHUNK == 0 {
            let page = checkpoint_vec(TIMED_INCOMING_CHUNK)?;
            if page.capacity() != TIMED_INCOMING_CHUNK {
                return Err(budget("timed incoming fixed page capacity differs"));
            }
            if self.chunks.len() == self.chunks.capacity() {
                let target = checked_mul(self.chunks.capacity(), 2)?.max(4);
                let mut replacement = checkpoint_vec(target)?;
                if replacement.capacity() != target {
                    return Err(budget("timed incoming descriptor capacity differs"));
                }
                // The old headers stay allocated until assignment. Page payloads
                // are moved by their Vec descriptors, never copied or reallocated.
                replacement.append(&mut self.chunks);
                self.chunks = replacement;
            }
            self.chunks.push(page);
        }
        self.chunks
            .last_mut()
            .expect("timed incoming page allocated")
            .push(value);
        self.len = next_len;
        Ok(())
    }
}

/// Shared across all destination cells in one road step. No interning policy is
/// imposed here: the producer can cache one ID per class per serve, or reuse an
/// earlier ID only after comparing all four original f64/PackedTime bit patterns.
#[derive(Default)]
pub(super) struct TimedIncomingControls {
    pages: Pages<Control>,
}

impl TimedIncomingControls {
    pub(super) fn new() -> Self {
        Self::default()
    }

    pub(super) fn len(&self) -> usize {
        self.pages.len
    }

    pub(super) fn capacity(&self) -> usize {
        self.pages.capacity()
    }

    pub(super) fn descriptor_capacity(&self) -> usize {
        self.pages.chunks.capacity()
    }

    pub(super) fn physical_capacity_bytes(&self) -> usize {
        self.pages.physical_capacity_bytes()
    }

    pub(super) fn allocated_bytes(&self) -> usize {
        self.pages.allocated_bytes()
    }

    pub(super) fn projected_append_bytes(&self, additional: usize) -> PyResult<usize> {
        let new_len = checked_add(self.len(), additional)?;
        if new_len as u128 > u32::MAX as u128 + 1 {
            return Err(budget("timed incoming control index capacity exhausted"));
        }
        self.pages.projected_append_bytes(additional)
    }

    pub(super) fn push_checked(
        &mut self,
        a: PackedTime,
        b: PackedTime,
        mark: Mark,
    ) -> PyResult<u32> {
        let id = u32::try_from(self.len())
            .map_err(|_| budget("timed incoming control index capacity exhausted"))?;
        self.pages.push_checked(Control {
            a,
            b,
            speed: mark.0,
            latent: mark.1,
        })?;
        Ok(id)
    }

    /// IDs come from push_checked or a validated TimedIncomingRows append.
    /// The original append-only table must remain alive through every decode.
    pub(super) fn get(&self, id: u32) -> (PackedTime, PackedTime, Mark) {
        let c = self
            .pages
            .get(id as usize)
            .expect("timed incoming control ID validated on append");
        (c.a, c.b, (c.speed, c.latent))
    }
}

#[derive(Default)]
pub(super) struct TimedIncomingRows {
    pages: Pages<Row>,
}

impl TimedIncomingRows {
    pub(super) fn new() -> Self {
        Self::default()
    }

    pub(super) fn len(&self) -> usize {
        self.pages.len
    }

    pub(super) fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub(super) fn capacity(&self) -> usize {
        self.pages.capacity()
    }

    pub(super) fn descriptor_capacity(&self) -> usize {
        self.pages.chunks.capacity()
    }

    pub(super) fn physical_capacity_bytes(&self) -> usize {
        self.pages.physical_capacity_bytes()
    }

    pub(super) fn allocated_bytes(&self) -> usize {
        self.pages.allocated_bytes()
    }

    pub(super) fn projected_append_bytes(&self, additional: usize) -> PyResult<usize> {
        self.pages.projected_append_bytes(additional)
    }

    /// Part already has the original offset advancement and endpoint rewrite.
    /// Endpoint checks use bits, including signed zero and the None sentinel.
    /// The bounded compact-registry producer retains its wide legacy fallback.
    pub(super) fn push_checked(
        &mut self,
        part: Part,
        control: u32,
        controls: &TimedIncomingControls,
    ) -> PyResult<()> {
        let tag = u32::try_from(part.tag)
            .map_err(|_| arithmetic("timed incoming tag outside compact source"))?;
        let offset = u32::try_from(part.offset)
            .map_err(|_| arithmetic("timed incoming offset outside compact source"))?;
        let c = controls
            .pages
            .get(control as usize)
            .ok_or_else(|| arithmetic("timed incoming control outside original table"))?;
        if part.a.0 != c.a.0 || part.b.0 != c.b.0 {
            return Err(arithmetic("timed incoming control endpoint bits differ"));
        }
        self.pages.push_checked(Row {
            mass: part.mass,
            birth: part.birth,
            tag,
            offset,
            control,
        })
    }

    /// O(1) access for a validated source index, without allocating a row buffer.
    /// Decode with the same append-only control table used by push_checked.
    pub(super) fn get(&self, index: usize, controls: &TimedIncomingControls) -> (Part, Mark) {
        let row = self
            .pages
            .get(index)
            .expect("timed incoming row inside length");
        let (a, b, mark) = controls.get(row.control);
        (
            Part {
                tag: row.tag as usize,
                offset: row.offset as usize,
                mass: row.mass,
                birth: row.birth,
                a,
                b,
            },
            mark,
        )
    }

    /// Exact original append order; no row buffer is allocated while decoding.
    pub(super) fn iter<'a>(
        &'a self,
        controls: &'a TimedIncomingControls,
    ) -> impl ExactSizeIterator<Item = (Part, Mark)> + 'a {
        (0..self.len()).map(move |i| self.get(i, controls))
    }
}

#[cfg(test)]
mod tests {
    use super::super::{portion, sum, PacketParts};
    use super::*;

    fn part(tag: usize, offset: usize, mass: f64, birth: f64, a: f64, b: f64) -> Part {
        Part {
            tag,
            offset,
            mass,
            birth,
            a: PackedTime::new(Some(a)).unwrap(),
            b: PackedTime::new(Some(b)).unwrap(),
        }
    }

    fn bits(p: Part, m: Mark) -> (usize, usize, u64, u64, u64, u64, u64, u64) {
        (
            p.tag,
            p.offset,
            p.mass.to_bits(),
            p.birth.to_bits(),
            p.a.0,
            p.b.0,
            m.0.to_bits(),
            m.1.to_bits(),
        )
    }

    #[test]
    fn actual_rows_and_controls_are_32_bytes_and_keep_every_field_bit() {
        assert_eq!(size_of::<Row>(), 32);
        assert_eq!(size_of::<Control>(), 32);
        let mut controls = TimedIncomingControls::new();
        let mut rows = TimedIncomingRows::new();
        let cases = [
            (part(0, 1, 0.1, 0.03, -0.0, 2.0), (-0.0, 0.25)),
            (
                part(
                    u32::MAX as usize,
                    u32::MAX as usize,
                    f64::from_bits(1),
                    f64::from_bits(2),
                    0.0,
                    0.0,
                ),
                (f64::from_bits(3), 1.0),
            ),
            (
                Part {
                    a: PackedTime::new(None).unwrap(),
                    b: PackedTime::new(None).unwrap(),
                    ..part(5, 9, 1e200, 1e-200, 0.0, 1.0)
                },
                (0.7, f64::from_bits(0x3fd5555555555555)),
            ),
        ];
        for &(p, m) in &cases {
            let id = controls.push_checked(p.a, p.b, m).unwrap();
            rows.push_checked(p, id, &controls).unwrap();
        }
        assert_eq!(
            rows.iter(&controls)
                .map(|(p, m)| bits(p, m))
                .collect::<Vec<_>>(),
            cases
                .into_iter()
                .map(|(p, m)| bits(p, m))
                .collect::<Vec<_>>(),
        );
        assert_eq!(rows.capacity(), 128);
        assert_eq!(controls.capacity(), 128);
        assert_eq!(rows.physical_capacity_bytes(), 4096);
        assert_eq!(controls.physical_capacity_bytes(), 4096);
    }

    #[test]
    fn shared_class_controls_match_original_portion_and_ordered_mark_sums() {
        let source: Vec<_> = (0..1031)
            .map(|i| {
                part(
                    i % 17,
                    i % 5,
                    f64::from_bits(0x3fa0000000000000 + i as u64),
                    (i as f64 + 1.0) / 997.0,
                    -0.0,
                    3.0,
                )
            })
            .collect();
        let packed = PacketParts::pack(source, |_| Ok(())).unwrap();
        let mut controls = TimedIncomingControls::new();
        let mut rows = [TimedIncomingRows::new(), TimedIncomingRows::new()];
        let mut old: [Vec<(Part, Mark)>; 2] = [Vec::new(), Vec::new()];
        for event in 0..7 {
            let mut class_ids = [None; 3];
            for mut p in portion(&packed, 0.29).unwrap() {
                let class = p.tag % 3;
                let destination = p.tag % 2;
                let mark = (
                    f64::from_bits(0x3fb0000000000000 + event as u64),
                    f64::from_bits(0x3fd0000000000000 + class as u64),
                );
                p.offset += 1;
                p.a = PackedTime::new(Some(event as f64)).unwrap();
                p.b = PackedTime::new(Some(event as f64 + 0.5)).unwrap();
                let id = match class_ids[class] {
                    Some(id) => id,
                    None => {
                        let id = controls.push_checked(p.a, p.b, mark).unwrap();
                        class_ids[class] = Some(id);
                        id
                    }
                };
                rows[destination].push_checked(p, id, &controls).unwrap();
                old[destination].push((p, mark));
            }
        }
        assert_eq!(controls.len(), 21); // shared between the two destinations
        for destination in 0..2 {
            let actual = &rows[destination];
            let expected = &old[destination];
            assert_eq!(
                actual
                    .iter(&controls)
                    .map(|(p, m)| bits(p, m))
                    .collect::<Vec<_>>(),
                expected
                    .iter()
                    .map(|&(p, m)| bits(p, m))
                    .collect::<Vec<_>>(),
            );
            // Indexed combine visits the append-order source out of order.
            // Cover both sides of page boundaries and the partial final page.
            for index in [actual.len() - 1, 128, 0, actual.len() / 2, 127, 1, 256, 129] {
                let (p, m) = actual.get(index, &controls);
                let (iter_p, iter_m) = actual.iter(&controls).nth(index).unwrap();
                let (old_p, old_m) = expected[index];
                assert_eq!(bits(p, m), bits(iter_p, iter_m));
                assert_eq!(bits(p, m), bits(old_p, old_m));
            }
            assert_eq!(
                sum(actual.iter(&controls).map(|(p, m)| p.mass * m.0)).to_bits(),
                sum(expected.iter().map(|(p, m)| p.mass * m.0)).to_bits(),
            );
            for class in 0..3 {
                let numerator = |pairs: &[(Part, Mark)]| {
                    sum(pairs
                        .iter()
                        .filter(|(p, _)| p.tag % 3 == class)
                        .map(|(p, m)| p.mass * m.1))
                };
                let got = sum(actual
                    .iter(&controls)
                    .filter(|(p, _)| p.tag % 3 == class)
                    .map(|(p, m)| p.mass * m.1));
                assert_eq!(got.to_bits(), numerator(expected).to_bits());
            }
        }
    }

    #[test]
    fn projected_append_covers_every_prefix_and_real_descriptor_growth() {
        for initial in [0, 1, 127, 128, 129, 511, 512] {
            for additional in [0, 1, 127, 128, 129, 1025] {
                let mut controls = TimedIncomingControls::new();
                let mut rows = TimedIncomingRows::new();
                let p = part(1, 2, 0.1, 0.03, 1.0, 2.0);
                let id = controls.push_checked(p.a, p.b, (0.5, 0.75)).unwrap();
                for _ in 0..initial {
                    rows.push_checked(p, id, &controls).unwrap();
                }
                let upper = rows.projected_append_bytes(additional).unwrap();
                assert!(rows.allocated_bytes() <= upper);
                for _ in 0..additional {
                    assert!(rows.projected_append_bytes(1).unwrap() <= upper);
                    rows.push_checked(p, id, &controls).unwrap();
                    assert!(rows.allocated_bytes() <= upper);
                }
                assert_eq!(rows.capacity(), pages_for(rows.len()) * 128);
            }
        }
        // Four existing page descriptors grow to eight: both coexist.
        let predicted = projected_pages_bytes(512, 4, 1, 32).unwrap();
        assert_eq!(predicted, 5 * 128 * 32 + (4 + 8) * size_of::<Vec<Row>>());
        assert!(predicted > 5 * 128 * 32 + 8 * size_of::<Vec<Row>>());
        let mut controls = TimedIncomingControls::new();
        let a = PackedTime::new(Some(-0.0)).unwrap();
        let b = PackedTime::new(Some(3.0)).unwrap();
        let upper = controls.projected_append_bytes(1025).unwrap();
        for i in 0..1025 {
            assert!(controls.projected_append_bytes(1).unwrap() <= upper);
            controls.push_checked(a, b, (i as f64, 0.5)).unwrap();
            assert!(controls.allocated_bytes() <= upper);
        }
        assert_eq!(controls.capacity(), 9 * 128);
    }

    #[test]
    fn zero_projection_is_actual_storage_and_overflow_is_rejected() {
        let mut controls = TimedIncomingControls::new();
        let mut rows = TimedIncomingRows::new();
        assert_eq!(controls.projected_append_bytes(0).unwrap(), 0);
        assert_eq!(rows.projected_append_bytes(0).unwrap(), 0);
        assert!(controls.projected_append_bytes(usize::MAX).is_err());
        assert!(rows.projected_append_bytes(usize::MAX).is_err());
        let p = part(1, 2, 0.1, 0.02, 0.0, 1.0);
        let id = controls.push_checked(p.a, p.b, (0.5, 0.25)).unwrap();
        rows.push_checked(p, id, &controls).unwrap();
        assert_eq!(
            rows.projected_append_bytes(0).unwrap(),
            rows.allocated_bytes()
        );
        assert_eq!(
            controls.projected_append_bytes(0).unwrap(),
            controls.allocated_bytes()
        );
    }

    #[test]
    fn invalid_ids_wide_indices_and_changed_clock_bits_do_not_mutate_rows() {
        let mut controls = TimedIncomingControls::new();
        let mut rows = TimedIncomingRows::new();
        let p = part(1, 2, 0.1, 0.02, -0.0, 1.0);
        let id = controls.push_checked(p.a, p.b, (0.5, 0.25)).unwrap();
        assert!(rows.push_checked(p, id + 1, &controls).is_err());
        let changed = Part {
            a: PackedTime::new(Some(0.0)).unwrap(),
            ..p
        };
        assert!(rows.push_checked(changed, id, &controls).is_err());
        if usize::BITS > 32 {
            let wide = Part {
                tag: u32::MAX as usize + 1,
                ..p
            };
            assert!(rows.push_checked(wide, id, &controls).is_err());
        }
        assert_eq!(rows.len(), 0);
        assert_eq!(rows.allocated_bytes(), 0);
        assert_eq!(controls.len(), 1);
    }

    #[test]
    fn moving_and_dropping_one_cell_preserves_other_cells_and_global_controls() {
        let mut controls = TimedIncomingControls::new();
        let p = part(1, 2, 0.1, 0.02, -0.0, 1.0);
        let mark = (0.5, 0.25);
        let id = controls.push_checked(p.a, p.b, mark).unwrap();
        let mut first = TimedIncomingRows::new();
        let mut second = TimedIncomingRows::new();
        for _ in 0..129 {
            first.push_checked(p, id, &controls).unwrap();
            second.push_checked(p, id, &controls).unwrap();
        }
        let moved = std::mem::take(&mut first);
        assert!(first.is_empty());
        assert_eq!(first.capacity(), 0);
        assert_eq!(first.descriptor_capacity(), 0);
        assert_eq!(moved.iter(&controls).len(), 129);
        drop(moved);
        let moved_controls = controls;
        assert_eq!(moved_controls.len(), 1);
        assert_eq!(moved_controls.descriptor_capacity(), 4);
        assert!(second
            .iter(&moved_controls)
            .all(|(row, m)| bits(row, m) == bits(p, mark)));
    }
}
