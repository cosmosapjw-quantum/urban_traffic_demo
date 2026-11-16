//! Persistent exact access rows. Immutable blocks keep rollback clones cheap;
//! cached readiness skips only blocks whose every original predicate is false.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::sync::Arc;

pub(crate) type Access = (usize, f64, f64, f64);
const BLOCK_ROWS: usize = 256;
const ALLOCATION_PADDING: usize = 128;

struct Block {
    rows: Vec<Access>,
    min_ready: f64,
    max_ready: f64,
    max_leg: usize,
    max_born: f64,
    valid: bool,
}
impl Clone for Block {
    fn clone(&self) -> Self {
        let mut rows = Vec::with_capacity(self.rows.capacity());
        rows.extend_from_slice(&self.rows);
        Self {
            rows,
            min_ready: self.min_ready,
            max_ready: self.max_ready,
            max_leg: self.max_leg,
            max_born: self.max_born,
            valid: self.valid,
        }
    }
}
impl Block {
    fn new(rows: Vec<Access>) -> Self {
        let mut min_ready = f64::INFINITY;
        let mut max_ready = f64::NEG_INFINITY;
        for a in &rows {
            let ready = a.2 + a.3;
            min_ready = min_ready.min(ready);
            max_ready = max_ready.max(ready);
        }
        let max_leg = rows.iter().map(|a| a.0).max().unwrap_or(0);
        let max_born = rows.iter().map(|a| a.2).fold(0., f64::max);
        let valid = rows.iter().all(valid);
        Self {
            rows,
            min_ready,
            max_ready,
            max_leg,
            max_born,
            valid,
        }
    }
    fn storage_bytes(&self) -> usize {
        std::mem::size_of::<Self>()
            + 2 * std::mem::size_of::<usize>()
            + self.rows.capacity() * std::mem::size_of::<Access>()
            + ALLOCATION_PADDING
    }
}

#[derive(Clone, Default)]
pub(crate) struct StageQueue {
    blocks: Vec<Arc<Block>>,
    len: usize,
    payload_bytes: usize,
    capacity_rows: usize,
}
impl StageQueue {
    pub(crate) fn new() -> Self {
        Self::default()
    }
    pub(crate) fn len(&self) -> usize {
        self.len
    }
    pub(crate) fn is_empty(&self) -> bool {
        self.len == 0
    }
    pub(crate) fn capacity(&self) -> usize {
        self.capacity_rows
    }
    pub(crate) fn block_count(&self) -> usize {
        self.blocks.len()
    }
    pub(crate) fn storage_bytes(&self) -> usize {
        self.payload_bytes
            + self.blocks.capacity() * std::mem::size_of::<Arc<Block>>()
            + if self.blocks.capacity() != 0 {
                ALLOCATION_PADDING
            } else {
                0
            }
    }
    /// Upper bound after appending, including a possible full tail copy and
    /// geometric pointer-registry growth. Caller charges live snapshot copies.
    pub(crate) fn append_upper_bytes(&self, additional: usize) -> usize {
        if additional == 0 {
            return self.storage_bytes();
        }
        let blocks = additional.div_ceil(BLOCK_ROWS).saturating_add(1);
        let block_bytes = std::mem::size_of::<Block>()
            + 2 * std::mem::size_of::<usize>()
            + BLOCK_ROWS * std::mem::size_of::<Access>()
            + ALLOCATION_PADDING;
        self.payload_bytes
            .saturating_add(blocks.saturating_mul(block_bytes))
            .saturating_add(
                self.blocks
                    .capacity()
                    .max(self.blocks.len().saturating_add(blocks).saturating_mul(2))
                    .saturating_mul(std::mem::size_of::<Arc<Block>>()),
            )
            .saturating_add(ALLOCATION_PADDING)
    }
    pub(crate) fn push(&mut self, row: Access) {
        if self
            .blocks
            .last()
            .is_none_or(|b| b.rows.len() == BLOCK_ROWS)
        {
            self.blocks
                .push(Arc::new(Block::new(Vec::with_capacity(4))));
            let block = self.blocks.last().unwrap();
            self.payload_bytes += block.storage_bytes();
            self.capacity_rows += block.rows.capacity();
        }
        let head = self.blocks.last_mut().unwrap();
        let old_bytes = head.storage_bytes();
        let old_capacity = head.rows.capacity();
        let block = Arc::make_mut(head);
        block.rows.push(row);
        let ready = row.2 + row.3;
        block.min_ready = block.min_ready.min(ready);
        block.max_ready = block.max_ready.max(ready);
        block.max_leg = block.max_leg.max(row.0);
        block.max_born = block.max_born.max(row.2);
        block.valid &= valid(&row);
        self.payload_bytes = self.payload_bytes - old_bytes + block.storage_bytes();
        self.capacity_rows = self.capacity_rows - old_capacity + block.rows.capacity();
        self.len += 1;
    }
    pub(crate) fn extend(&mut self, rows: impl IntoIterator<Item = Access>) {
        for row in rows {
            self.push(row);
        }
    }
    pub(crate) fn iter(&self) -> impl Iterator<Item = &Access> {
        self.blocks.iter().flat_map(|b| b.rows.iter())
    }
    pub(crate) fn to_vec(&self) -> Vec<Access> {
        self.iter().copied().collect()
    }
    pub(crate) fn valid_at(&self, legs: usize, time: f64) -> bool {
        self.blocks
            .iter()
            .all(|b| b.valid && b.max_leg < legs && b.max_born <= time + 1e-8)
    }
    pub(crate) fn due_count(&self, deadline: f64) -> usize {
        self.blocks
            .iter()
            .map(|b| {
                if b.min_ready > deadline {
                    0
                } else if b.max_ready <= deadline {
                    b.rows.len()
                } else {
                    b.rows.iter().filter(|a| a.2 + a.3 <= deadline).count()
                }
            })
            .sum()
    }
    /// Invoke callbacks in original global insertion order. Rows are not
    /// sorted, aggregated, rounded, expired, or removed before their predicate.
    pub(crate) fn retire_due(&mut self, deadline: f64, mut finish: impl FnMut(&Access)) -> usize {
        let old = std::mem::take(&mut self.blocks);
        let mut blocks = Vec::with_capacity(old.len());
        let mut retired = 0;
        let mut payload_bytes = 0;
        let mut capacity_rows = 0;
        for block in old {
            let keep = if block.min_ready > deadline {
                Some(block)
            } else if block.max_ready <= deadline {
                for row in &block.rows {
                    finish(row);
                }
                retired += block.rows.len();
                None
            } else {
                let mut remaining = Vec::with_capacity(block.rows.len());
                for row in &block.rows {
                    if row.2 + row.3 <= deadline {
                        finish(row);
                        retired += 1;
                    } else {
                        remaining.push(*row);
                    }
                }
                if remaining.is_empty() {
                    None
                } else {
                    Some(Arc::new(Block::new(remaining)))
                }
            };
            if let Some(block) = keep {
                payload_bytes += block.storage_bytes();
                capacity_rows += block.rows.capacity();
                blocks.push(block);
            }
        }
        self.len -= retired;
        self.blocks = blocks;
        self.payload_bytes = payload_bytes;
        self.capacity_rows = capacity_rows;
        self.compact_registry();
        retired
    }
    pub(crate) fn compact_registry(&mut self) {
        if self.blocks.is_empty() {
            self.blocks = Vec::new();
        } else if self.blocks.capacity() > 4096 && self.blocks.capacity() / 4 > self.blocks.len() {
            self.blocks.shrink_to_fit();
        }
    }
    fn shared_rows(&self, other: &Self) -> usize {
        // Inspection only; sort integer pointers instead of comparing O(B^2).
        let mut pointers: Vec<_> = other
            .blocks
            .iter()
            .map(|b| Arc::as_ptr(b) as usize)
            .collect();
        pointers.sort_unstable();
        self.blocks
            .iter()
            .filter(|b| pointers.binary_search(&(Arc::as_ptr(b) as usize)).is_ok())
            .map(|b| b.rows.len())
            .sum()
    }
}
impl From<Vec<Access>> for StageQueue {
    fn from(rows: Vec<Access>) -> Self {
        let mut q = Self::new();
        q.extend(rows);
        q
    }
}
pub(crate) struct StageIter<'a> {
    blocks: std::slice::Iter<'a, Arc<Block>>,
    rows: Option<std::slice::Iter<'a, Access>>,
}
impl<'a> Iterator for StageIter<'a> {
    type Item = &'a Access;
    fn next(&mut self) -> Option<Self::Item> {
        loop {
            if let Some(row) = self.rows.as_mut().and_then(Iterator::next) {
                return Some(row);
            }
            self.rows = Some(self.blocks.next()?.rows.iter());
        }
    }
}
impl<'a> IntoIterator for &'a StageQueue {
    type Item = &'a Access;
    type IntoIter = StageIter<'a>;
    fn into_iter(self) -> Self::IntoIter {
        StageIter {
            blocks: self.blocks.iter(),
            rows: None,
        }
    }
}

#[pyclass]
pub struct NativeStageQueue {
    queue: StageQueue,
}
fn valid(row: &Access) -> bool {
    row.1.is_finite()
        && row.1 > 0.
        && row.2.is_finite()
        && row.2 >= 0.
        && row.3.is_finite()
        && row.3 >= 0.
}
#[pymethods]
impl NativeStageQueue {
    #[new]
    fn new(rows: Vec<Access>) -> PyResult<Self> {
        if !rows.iter().all(valid) {
            return Err(PyValueError::new_err("invalid native stage row"));
        }
        Ok(Self { queue: rows.into() })
    }
    fn fork(&self) -> Self {
        Self {
            queue: self.queue.clone(),
        }
    }
    fn append(&mut self, row: Access) -> PyResult<()> {
        if !valid(&row) {
            return Err(PyValueError::new_err("invalid native stage row"));
        }
        self.queue.push(row);
        Ok(())
    }
    fn snapshot(&self) -> Vec<Access> {
        self.queue.to_vec()
    }
    fn retire_due(&mut self, deadline: f64) -> PyResult<Vec<Access>> {
        if !deadline.is_finite() || deadline < 0. {
            return Err(PyValueError::new_err("invalid native stage deadline"));
        }
        let mut rows = Vec::new();
        self.queue.retire_due(deadline, |a| rows.push(*a));
        Ok(rows)
    }
    fn due_count(&self, deadline: f64) -> PyResult<usize> {
        if !deadline.is_finite() || deadline < 0. {
            return Err(PyValueError::new_err("invalid native stage deadline"));
        }
        Ok(self.queue.due_count(deadline))
    }
    fn append_upper_bytes(&self, additional: usize) -> usize {
        self.queue.append_upper_bytes(additional)
    }
    fn storage_shape(&self) -> (usize, usize, usize, usize) {
        (
            self.queue.len(),
            self.queue.block_count(),
            self.queue.capacity(),
            self.queue.storage_bytes(),
        )
    }
    fn shared_rows(&self, other: &Self) -> usize {
        self.queue.shared_rows(&other.queue)
    }
}
