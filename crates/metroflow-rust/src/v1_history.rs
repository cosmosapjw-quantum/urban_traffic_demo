//! Lossless completion receipts with persistent, bounded-copy append blocks.
//!
//! Raw receipt order/times are retained for checkpoint interchange.  Cached
//! non-overlapping floating-point expansions accelerate sums without replacing
//! the receipt clock distribution by a rounded aggregate.  An empty history is
//! one nullable Arc, and a rollback clone never copies historical rows.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::sync::Arc;

const BLOCK_ROWS: usize = 64;
type Receipt = (f64, f64);

/// An exact floating-point expansion, finalized with the same half-even
/// correction as CPython math.fsum and the existing journey ledger helper.
#[derive(Clone, Default)]
struct Expansion(Vec<f64>);

impl Expansion {
    fn add(&mut self, mut x: f64) -> Result<(), &'static str> {
        let mut i = 0;
        for j in 0..self.0.len() {
            let mut y = self.0[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            if !hi.is_finite() {
                return Err("native receipt sum overflow");
            }
            let lo = y - (hi - x);
            if lo != 0.0 {
                self.0[i] = lo;
                i += 1;
            }
            x = hi;
        }
        self.0.truncate(i);
        if x != 0.0 {
            self.0.push(x);
        }
        Ok(())
    }

    fn merge(&mut self, other: &Self) {
        for &x in &other.0 {
            // Both expansions are disjoint subsets of a history whose finite
            // positive total has already been checked on append.
            self.add(x).expect("validated receipt subset overflow");
        }
    }

    fn total(&self) -> f64 {
        let mut n = self.0.len();
        if n == 0 {
            return 0.0;
        }
        n -= 1;
        let mut hi = self.0[n];
        let mut lo = 0.0;
        while n > 0 {
            n -= 1;
            let x = hi;
            let y = self.0[n];
            hi = x + y;
            lo = y - (hi - x);
            if lo != 0.0 {
                break;
            }
        }
        if n > 0 {
            let last = self.0[n - 1];
            if (lo < 0.0 && last < 0.0) || (lo > 0.0 && last > 0.0) {
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

struct Block {
    previous: Option<Arc<Block>>,
    rows: Vec<Receipt>,
    count: usize,
    min_time: f64,
    max_time: f64,
    block_min_time: f64,
    block_max_time: f64,
    sum: Expansion,
    block_sum: Expansion,
    storage_bytes: usize,
}

impl Clone for Block {
    fn clone(&self) -> Self {
        // Match geometric Vec growth without eagerly allocating 64 rows for
        // the many calendar legs that currently have only one completion.
        let mut rows = Vec::with_capacity(self.rows.len().max(4).next_power_of_two());
        rows.extend_from_slice(&self.rows);
        let mut block = Self {
            previous: self.previous.clone(),
            rows,
            count: self.count,
            min_time: self.min_time,
            max_time: self.max_time,
            block_min_time: self.block_min_time,
            block_max_time: self.block_max_time,
            sum: self.sum.clone(),
            block_sum: self.block_sum.clone(),
            storage_bytes: 0,
        };
        block.refresh_storage_bytes();
        block
    }
}
impl Block {
    fn own_storage_bytes(&self) -> usize {
        std::mem::size_of::<Self>()
            + 2 * std::mem::size_of::<usize>()
            + 128
            + self.rows.capacity() * std::mem::size_of::<Receipt>()
            + (self.sum.0.capacity() + self.block_sum.0.capacity()) * std::mem::size_of::<f64>()
    }
    fn refresh_storage_bytes(&mut self) {
        self.storage_bytes = self
            .previous
            .as_ref()
            .map_or(0, |b| b.storage_bytes)
            .saturating_add(self.own_storage_bytes());
    }
}

/// Clone is O(1). Append copies at most BLOCK_ROWS prior raw rows; no raw row is
/// pruned, rounded, time-bucketed, or omitted from the logical record budget.
#[derive(Clone, Default)]
pub(crate) struct ReceiptHistory(Option<Arc<Block>>);

impl ReceiptHistory {
    pub(crate) fn new() -> Self {
        Self::default()
    }

    pub(crate) fn from_rows(rows: Vec<Receipt>) -> Result<Self, &'static str> {
        let mut history = Self::new();
        for row in rows {
            history.push(row)?;
        }
        Ok(history)
    }

    pub(crate) fn len(&self) -> usize {
        self.0.as_ref().map_or(0, |b| b.count)
    }

    /// Conservatively charged allocator capacity, cached over the persistent
    /// prefix. Shared blocks are counted once per logical history snapshot.
    pub(crate) fn storage_bytes(&self) -> usize {
        self.0.as_ref().map_or(0, |b| b.storage_bytes)
    }
    pub(crate) fn append_upper_bytes(&self) -> usize {
        let (sum_capacity, block_capacity) = self
            .0
            .as_ref()
            .map_or((0, 0), |b| (b.sum.0.capacity(), b.block_sum.0.capacity()));
        let own = std::mem::size_of::<Block>()
            + 2 * std::mem::size_of::<usize>()
            + 128
            + BLOCK_ROWS * std::mem::size_of::<Receipt>()
            + (sum_capacity.saturating_mul(2).saturating_add(4)
                + block_capacity.saturating_mul(2).saturating_add(4))
                * std::mem::size_of::<f64>();
        self.storage_bytes().saturating_add(own)
    }

    pub(crate) fn push(&mut self, row: Receipt) -> Result<(), &'static str> {
        if !row.0.is_finite() || row.0 < 0.0 || !row.1.is_finite() || row.1 <= 0.0 {
            return Err("invalid native completion receipt");
        }
        let mut sum = self
            .0
            .as_ref()
            .map_or_else(Expansion::default, |b| b.sum.clone());
        sum.add(row.1)?;
        if !sum.total().is_finite() {
            return Err("native receipt sum overflow");
        }
        match &mut self.0 {
            Some(head) if head.rows.len() < BLOCK_ROWS => {
                let block = Arc::make_mut(head);
                block.block_sum.add(row.1)?;
                block.rows.push(row);
                block.count += 1;
                block.min_time = block.min_time.min(row.0);
                block.max_time = block.max_time.max(row.0);
                block.block_min_time = block.block_min_time.min(row.0);
                block.block_max_time = block.block_max_time.max(row.0);
                block.sum = sum;
                block.refresh_storage_bytes();
            }
            _ => {
                let previous = self.0.take();
                let count = previous.as_ref().map_or(1, |b| b.count + 1);
                let min_time = previous.as_ref().map_or(row.0, |b| b.min_time.min(row.0));
                let max_time = previous.as_ref().map_or(row.0, |b| b.max_time.max(row.0));
                let mut rows = Vec::with_capacity(4);
                rows.push(row);
                let mut block = Block {
                    previous,
                    rows,
                    count,
                    min_time,
                    max_time,
                    block_min_time: row.0,
                    block_max_time: row.0,
                    sum,
                    block_sum: Expansion(vec![row.1]),
                    storage_bytes: 0,
                };
                block.refresh_storage_bytes();
                self.0 = Some(Arc::new(block));
            }
        }
        Ok(())
    }

    pub(crate) fn total(&self) -> f64 {
        self.0.as_ref().map_or(0.0, |b| b.sum.total())
    }

    /// Every raw row was checked at construction/append; checking a new clock
    /// therefore needs only the maximum original completion time.
    pub(crate) fn valid_at(&self, now: f64) -> bool {
        now.is_finite() && now >= 0.0 && self.0.as_ref().map_or(true, |b| b.max_time <= now)
    }

    /// Keep the oracle's `(receipt_time + dwell) <= now` predicate verbatim.
    /// Subtracting dwell from now would change eligibility at rounding edges.
    /// Prefix and block extrema work even for unsorted restored receipts.
    pub(crate) fn eligible(&self, dwell: f64, now: f64) -> f64 {
        let mut result = Expansion::default();
        let mut cursor = self.0.as_deref();
        while let Some(block) = cursor {
            if block.max_time + dwell <= now {
                result.merge(&block.sum);
                break;
            }
            if block.min_time + dwell > now {
                break;
            }
            if block.block_max_time + dwell <= now {
                result.merge(&block.block_sum);
            } else if !(block.block_min_time + dwell > now) {
                for &(time, fraction) in &block.rows {
                    if time + dwell <= now {
                        result
                            .add(fraction)
                            .expect("validated receipt subset overflow");
                    }
                }
            }
            cursor = block.previous.as_deref();
        }
        result.total()
    }

    /// Raw insertion-order iteration is reserved for interoperability. Runtime
    /// validation and eligibility use the cached methods above instead.
    pub(crate) fn iter(&self) -> impl Iterator<Item = &Receipt> {
        let mut blocks = Vec::new();
        let mut cursor = self.0.as_deref();
        while let Some(block) = cursor {
            blocks.push(block);
            cursor = block.previous.as_deref();
        }
        blocks.into_iter().rev().flat_map(|block| block.rows.iter())
    }

    pub(crate) fn to_vec(&self) -> Vec<Receipt> {
        let mut result = Vec::with_capacity(self.len());
        result.extend(self.iter().copied());
        result
    }

    fn block_count(&self) -> usize {
        self.len().div_ceil(BLOCK_ROWS)
    }

    fn shared_prefix_rows(&self, other: &Self) -> usize {
        let mut a = self.0.as_ref();
        let mut b = other.0.as_ref();
        while let (Some(left), Some(right)) = (a, b) {
            if Arc::ptr_eq(left, right) {
                return left.count;
            }
            if left.count >= right.count {
                a = left.previous.as_ref();
            } else {
                b = right.previous.as_ref();
            }
        }
        0
    }
}

impl Drop for ReceiptHistory {
    fn drop(&mut self) {
        // Avoid recursive Arc-chain destruction for a long-lived calendar.
        let mut cursor = self.0.take();
        while let Some(head) = cursor {
            match Arc::try_unwrap(head) {
                Ok(mut block) => cursor = block.previous.take(),
                Err(_) => break,
            }
        }
    }
}

/// Small native inspection surface for independently verifying the numerical
/// and structural-sharing contract; the runtime uses ReceiptHistory directly.
#[pyclass]
pub struct NativeReceiptHistory {
    history: ReceiptHistory,
}

#[pymethods]
impl NativeReceiptHistory {
    #[new]
    fn new(rows: Vec<Receipt>) -> PyResult<Self> {
        Ok(Self {
            history: ReceiptHistory::from_rows(rows).map_err(PyValueError::new_err)?,
        })
    }

    fn append(&mut self, time: f64, fraction: f64) -> PyResult<()> {
        self.history
            .push((time, fraction))
            .map_err(PyValueError::new_err)
    }

    fn fork(&self) -> Self {
        Self {
            history: self.history.clone(),
        }
    }

    fn snapshot(&self) -> Vec<Receipt> {
        self.history.to_vec()
    }

    fn total(&self) -> f64 {
        self.history.total()
    }

    fn eligible(&self, dwell: f64, now: f64) -> PyResult<f64> {
        if !dwell.is_finite() || dwell < 0.0 || !now.is_finite() || now < 0.0 {
            return Err(PyValueError::new_err("invalid native eligibility clock"));
        }
        Ok(self.history.eligible(dwell, now))
    }

    fn valid_at(&self, now: f64) -> bool {
        self.history.valid_at(now)
    }

    fn __len__(&self) -> usize {
        self.history.len()
    }

    fn storage_shape(&self) -> (usize, usize, usize) {
        (
            std::mem::size_of::<ReceiptHistory>(),
            self.history.block_count(),
            BLOCK_ROWS,
        )
    }

    fn shared_prefix_rows(&self, other: &Self) -> usize {
        self.history.shared_prefix_rows(&other.history)
    }

    fn storage_bytes(&self) -> usize {
        self.history.storage_bytes()
    }
    fn append_upper_bytes(&self) -> usize {
        self.history.append_upper_bytes()
    }
}
