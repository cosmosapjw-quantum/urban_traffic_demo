//! Lossless completion receipts with persistent, bounded-copy append blocks.
//!
//! Raw receipt order/times are retained for checkpoint interchange.  Cached
//! non-overlapping floating-point expansions accelerate sums without replacing
//! the receipt clock distribution by a rounded aggregate.  An empty history is
//! one nullable Arc, and a rollback clone never copies historical rows.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
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
    decoded_storage_upper: usize,
    decoded_working_upper: usize,
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
            decoded_storage_upper: 0,
            decoded_working_upper: self.decoded_working_upper,
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
        // Prefix sum is cloned/updated before every push, so its final
        // capacity is determined by the raw row sequence, independent of COW.
        // A fresh decoder can retain more block_sum slack than COW clones;
        // at most one expansion component is appended per block row.
        let block_capacity_upper = self.rows.len().max(4).next_power_of_two();
        let decoded_own = self
            .own_storage_bytes()
            .saturating_sub(self.block_sum.0.capacity() * std::mem::size_of::<f64>())
            .saturating_add(block_capacity_upper * std::mem::size_of::<f64>());
        self.decoded_storage_upper = self
            .previous
            .as_ref()
            .map_or(0, |b| b.decoded_storage_upper)
            .saturating_add(decoded_own);
        self.decoded_working_upper = self.decoded_working_upper.max(self.decoded_storage_upper);
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
    pub(crate) fn decoded_storage_upper_bytes(&self) -> usize {
        self.0.as_ref().map_or(0, |b| b.decoded_working_upper)
    }
    pub(crate) fn decoded_final_storage_upper_bytes(&self) -> usize {
        self.0.as_ref().map_or(0, |b| b.decoded_storage_upper)
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
        let (decoded_before, decoded_peak, sum_capacity, block_capacity) =
            self.0.as_ref().map_or((0, 0, 0, 0), |b| {
                (
                    b.decoded_storage_upper,
                    b.decoded_working_upper,
                    b.sum.0.capacity(),
                    b.rows.len().max(4).next_power_of_two(),
                )
            });
        let append_upper = std::mem::size_of::<Block>()
            + 2 * std::mem::size_of::<usize>()
            + 128
            + BLOCK_ROWS * std::mem::size_of::<Receipt>()
            + (sum_capacity.saturating_mul(2).saturating_add(4)
                + block_capacity.saturating_mul(2).saturating_add(4))
                * std::mem::size_of::<f64>();
        let decoded_working_upper = decoded_peak.max(decoded_before.saturating_add(append_upper));
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
                block.decoded_working_upper = decoded_working_upper;
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
                    decoded_storage_upper: 0,
                    decoded_working_upper,
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

    /// Research-only sufficient statistic at fixed child dwell horizon.
    /// Does not modify this immutable owner or claim historical-CDF equality.
    pub(crate) fn compact_mature(&self,now:f64,dwell:f64,scratch:usize)->CoreResult<Option<Self>>{
        if !now.is_finite()||now<0.||!dwell.is_finite()||dwell<0.{return Err(CoreError::value("invalid receipt maturity horizon"))}
        let Some(head)=&self.0 else{return Ok(None)};
        if head.count<2||head.min_time+dwell>now{return Ok(None)}
        let fixed=128*1024usize;
        if scratch<fixed{return Err(CoreError::resource("receipt compact scratch"))}
        let mut count=0usize;let mut mn=f64::INFINITY;let mut mx=0.0f64;
        let(mut mass,mut moment)=(Expansion::default(),Expansion::default());
        let mut cursor=Some(head.as_ref());
        while let Some(block)=cursor{
            for &(t,f) in &block.rows{if t+dwell<=now{
                count+=1;mn=mn.min(t);mx=mx.max(t);
                mass.add(f).map_err(CoreError::value)?;
                moment.add(t*f).map_err(CoreError::value)?;
            }}
            cursor=block.previous.as_deref();
        }
        if count<2{return Ok(None)}
        let m=mass.total();let b=moment.total();
        if !m.is_finite()||m<=0.||!b.is_finite(){return Err(CoreError::arithmetic("receipt centroid overflow"))}
        let t=(b/m).clamp(mn,mx);
        if !t.is_finite()||t+dwell>now{return Err(CoreError::arithmetic("receipt centroid not mature"))}
        // iter() retains a geometrically grown block-pointer vector only
        // when immature rows exist. Bound both its growth and new history
        // append allocations; old history stays live throughout.
        let pointer=if count==head.count{0}else{self.block_count().saturating_mul(4*std::mem::size_of::<&Block>()).saturating_add(128)};
        let available=scratch.checked_sub(fixed.saturating_add(pointer)).ok_or_else(||CoreError::resource("receipt compact pointer workspace"))?;
        let mut out=Self::new();
        let append=|out:&mut Self,row:Receipt|->CoreResult<()>{
            if out.append_upper_bytes()>available{return Err(CoreError::resource("receipt compact output budget"))}
            out.push(row).map_err(CoreError::value)?;
            if out.storage_bytes()>available{return Err(CoreError::resource("receipt compact actual bytes"))}
            Ok(())
        };
        append(&mut out,(t,m))?;
        if count<head.count{for &row in self.iter(){if row.0+dwell>now{append(&mut out,row)?;}}}
        let close=|a:f64,b:f64|a.is_finite()&&b.is_finite()&&(a-b).abs()<=1e-11*a.abs().max(b.abs())+4.*f64::from_bits(1);
        if !close(self.total(),out.total())||!close(b,t*m)||out.len()!=head.count-count+1{return Err(CoreError::arithmetic("receipt compact mass/moment invariant"))}
        Ok(Some(out))
    }
    // First observable tick of fixed-dwell eligibility. Check the actual
    // addition predicate, including binary64 boundary behavior.
    fn grid_key(t:f64,dwell:f64,dt:f64,now:f64)->CoreResult<u64>{
        if t+dwell<=now{return Ok(0)}
        let ready=t+dwell;
        let raw=(ready/dt).ceil();
        if !raw.is_finite()||raw<=0.||raw>1e9{return Err(CoreError::value("receipt grid key outside domain"))}
        let mut k=raw as u64;
        if ready>k as f64*dt{k+=1}
        if k>0&&ready<=(k-1)as f64*dt{k-=1}
        if ready>k as f64*dt||k==0||ready<=(k-1)as f64*dt{return Err(CoreError::arithmetic("receipt grid key predicate differs"))}
        Ok(k)
    }
    /// Fixed tick-grid sufficient statistic for one common child dwell.
    /// Grouping changes raw distribution, not sampled eligibility in real
    /// arithmetic. Each group's actual binary64 predicate is verified.
    pub(crate) fn compact_grid(&self,now:f64,dwell:f64,dt:f64,scratch:usize)->CoreResult<Option<Self>>{
        if !now.is_finite()||now<0.||!dwell.is_finite()||dwell<0.||!dt.is_finite()||dt<1.||dt.fract()!=0.||now%dt!=0.{return Err(CoreError::value("receipt grid domain"))}
        if self.len()<2{return Ok(None)}
        if self.0.as_ref().unwrap().max_time+dwell<=now{return self.compact_mature(now,dwell,scratch)}
        let n=self.len();
        let array=n.checked_mul(std::mem::size_of::<(u64,usize,f64,f64)>()).ok_or_else(||CoreError::resource("receipt grid array overflow"))?;
        let pointer=self.block_count().saturating_mul(4*std::mem::size_of::<&Block>()).saturating_add(128);
        let fixed=array.saturating_add(pointer).saturating_add(128*1024);
        let available=scratch.checked_sub(fixed).ok_or_else(||CoreError::resource("receipt grid scratch"))?;
        let mut rows=Vec::new();rows.try_reserve_exact(n).map_err(|_|CoreError::resource("receipt grid allocation"))?;
        if rows.capacity()!=n{return Err(CoreError::resource("receipt grid capacity differs"))}
        for (i,&(t,f)) in self.iter().enumerate(){rows.push((Self::grid_key(t,dwell,dt,now)?,i,t,f));}
        rows.sort_unstable_by_key(|r|(r.0,r.1));
        if rows.windows(2).all(|w|w[0].0!=w[1].0){return Ok(None)}
        let mut out=Self::new();
        for g in rows.chunk_by(|a,b|a.0==b.0){
            let(mut m,mut b)=(Expansion::default(),Expansion::default());
            let(mut lo,mut hi)=(f64::INFINITY,0.0f64);
            for &(_,_,t,f) in g{lo=lo.min(t);hi=hi.max(t);m.add(f).map_err(CoreError::value)?;b.add(t*f).map_err(CoreError::value)?;}
            let m=m.total();let b=b.total();
            if m<=0.||!m.is_finite()||!b.is_finite(){return Err(CoreError::arithmetic("receipt grid moment overflow"))}
            let t=if g.len()==1{g[0].2}else{(b/m).clamp(lo,hi)};
            if Self::grid_key(t,dwell,dt,now)?!=g[0].0||(t*m-b).abs()>1e-11*b.abs()+4.*f64::from_bits(1){return Err(CoreError::arithmetic("receipt grid centroid predicate/moment differs"))}
            if out.append_upper_bytes()>available{return Err(CoreError::resource("receipt grid output budget"))}
            out.push((t,m)).map_err(CoreError::value)?;
            if out.storage_bytes()>available{return Err(CoreError::resource("receipt grid output bytes"))}
        }
        let total=self.total();if (out.total()-total).abs()>1e-11*total+4.*f64::from_bits(1){return Err(CoreError::arithmetic("receipt grid total differs"))}
        Ok(Some(out))
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
#[cfg_attr(feature="python-extension", pyclass)]
pub struct NativeReceiptHistory {
    history: ReceiptHistory,
}

crate::optional_binding::optional_pymethods!(NativeReceiptHistory,
    [
    #[new]
    ] {
    fn new(rows: Vec<Receipt>) -> CoreResult<Self> {
        Ok(Self {
            history: ReceiptHistory::from_rows(rows).map_err(CoreError::value)?,
        })
    }
    }
    [

    ] {


    fn append(&mut self, time: f64, fraction: f64) -> CoreResult<()> {
        self.history
            .push((time, fraction))
            .map_err(CoreError::value)
    }
    }
    [

    ] {


    fn fork(&self) -> Self {
        Self {
            history: self.history.clone(),
        }
    }
    }
    [

    ] {


    fn snapshot(&self) -> Vec<Receipt> {
        self.history.to_vec()
    }
    }
    [

    ] {


    fn total(&self) -> f64 {
        self.history.total()
    }
    }
    [

    ] {


    fn eligible(&self, dwell: f64, now: f64) -> CoreResult<f64> {
        if !dwell.is_finite() || dwell < 0.0 || !now.is_finite() || now < 0.0 {
            return Err(CoreError::value("invalid native eligibility clock"));
        }
        Ok(self.history.eligible(dwell, now))
    }
    }
    [

    ] {


    fn valid_at(&self, now: f64) -> bool {
        self.history.valid_at(now)
    }
    }
    [

    ] {


    fn __len__(&self) -> usize {
        self.history.len()
    }
    }
    [

    ] {


    fn storage_shape(&self) -> (usize, usize, usize) {
        (
            std::mem::size_of::<ReceiptHistory>(),
            self.history.block_count(),
            BLOCK_ROWS,
        )
    }
    }
    [

    ] {


    fn shared_prefix_rows(&self, other: &Self) -> usize {
        self.history.shared_prefix_rows(&other.history)
    }
    }
    [

    ] {


    fn storage_bytes(&self) -> usize {
        self.history.storage_bytes()
    }
    }
    [

    ] {

    fn decoded_storage_upper_bytes(&self) -> usize {
        self.history.decoded_storage_upper_bytes()
    }
    }
    [

    ] {

    fn decoded_final_storage_upper_bytes(&self) -> usize {
        self.history.decoded_final_storage_upper_bytes()
    }
    }
    [

    ] {

    fn append_upper_bytes(&self) -> usize {
        self.history.append_upper_bytes()
    }
    }
);

#[cfg(test)]
mod mature_closure_tests {
 use super::*;
 #[test] fn mature_centroid_preserves_future_eligibility_and_immature_bits(){
   let mut h=ReceiptHistory::new();for row in [(2.,0.125),(15.,0.25),(4.,0.125),(18.,0.5)]{h.push(row).unwrap()}
   let c=h.compact_mature(20.,10.,1_000_000).unwrap().unwrap();
   assert_eq!(c.to_vec(),vec![(3.,0.25),(15.,0.25),(18.,0.5)]);
   for now in 20..40{for dwell in 0..=10{assert_eq!(h.eligible(dwell as f64,now as f64),c.eligible(dwell as f64,now as f64));}}
   assert_eq!(h.total(),c.total());
   assert_eq!(h.iter().map(|r|r.0*r.1).sum::<f64>(),c.iter().map(|r|r.0*r.1).sum::<f64>());
 }
 #[test] fn mature_closure_rejects_workspace_shortfall_and_noop(){
   let h=ReceiptHistory::from_rows(vec![(1.,0.25),(2.,0.25)]).unwrap();
   assert!(h.compact_mature(10.,0.,1).is_err());
   assert!(h.compact_mature(2.,10.,1_000_000).unwrap().is_none());
   assert_eq!(h.len(),2);
 }
}

#[cfg(test)]mod grid_closure_tests{use super::*;
#[test]fn future_grid_conserves_eligibility_even_for_immature_receipts(){let h=ReceiptHistory::from_rows(vec![(1.,0.125),(2.,0.125),(10.,0.25),(11.,0.25),(15.,0.25)]).unwrap();let c=h.compact_grid(20.,3600.,10.,1_000_000).unwrap().unwrap();assert_eq!(c.len(),2);for t in (20..=3650).step_by(10){assert_eq!(h.eligible(3600.,t as f64),c.eligible(3600.,t as f64));}assert_eq!(h.total(),c.total());assert_eq!(h.iter().map(|r|r.0*r.1).sum::<f64>(),c.iter().map(|r|r.0*r.1).sum::<f64>());assert!(h.compact_grid(21.,3600.,10.,1_000_000).is_err());assert!(h.compact_grid(20.,3600.,10.,1).is_err());}
}
