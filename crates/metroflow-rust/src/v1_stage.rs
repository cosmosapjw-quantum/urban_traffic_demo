//! Persistent exact access rows. Immutable blocks keep rollback clones cheap;
//! cached readiness skips only blocks whose every original predicate is false.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
use std::sync::Arc;

pub(crate) type Access = (usize, f64, f64, f64);
const BLOCK_ROWS: usize = 256;
const ALLOCATION_PADDING: usize = 128;

pub(crate) struct Block {
    pub(crate) rows: Vec<Access>,
    pub(crate) min_ready: f64,
    pub(crate) max_ready: f64,
    sorted_leg: bool,
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
            sorted_leg: self.sorted_leg,
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
        let sorted_leg=rows.windows(2).all(|p|p[0].0<=p[1].0);
        Self {
            rows,
            min_ready,
            max_ready,
            sorted_leg,
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
    /// Fresh row-wise checkpoint decoding can have different registry/tail
    /// capacities than a filtered queue. Include the largest append preflight,
    /// not merely its final allocation, without scanning logical rows.
    pub(crate) fn decoded_storage_upper_bytes(&self) -> usize {
        if self.len == 0 {
            return 0;
        }
        let blocks = self.len.div_ceil(BLOCK_ROWS);
        let tail = self.len % BLOCK_ROWS;
        let full = self.len / BLOCK_ROWS;
        let row_capacity = full
            .saturating_mul(BLOCK_ROWS)
            .saturating_add(if tail == 0 {
                0
            } else {
                tail.max(4).next_power_of_two()
            });
        let header =
            std::mem::size_of::<Block>() + 2 * std::mem::size_of::<usize>() + ALLOCATION_PADDING;
        let full_block = header + BLOCK_ROWS * std::mem::size_of::<Access>();
        blocks
            .saturating_mul(header)
            .saturating_add(row_capacity.saturating_mul(std::mem::size_of::<Access>()))
            .saturating_add(2 * full_block)
            .saturating_add(
                blocks
                    .saturating_add(2)
                    .saturating_mul(2)
                    .max(4)
                    .saturating_mul(std::mem::size_of::<Arc<Block>>()),
            )
            .saturating_add(ALLOCATION_PADDING)
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
    pub(crate) fn push(&mut self, row: Access) { self.push_partitioned(row,false); }
    pub(crate) fn push_partitioned(&mut self,row:Access,new_partition:bool){
        if new_partition || self
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
        block.sorted_leg &= block.rows.last().is_none_or(|a|a.0<=row.0);
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
    pub(crate) fn blocks(&self)->&[Arc<Block>]{&self.blocks}
    pub(crate) fn iter_from(&self,mut skip:usize)->impl Iterator<Item=&Access>{
        let mut idx=0;
        while idx<self.blocks.len()&&skip>=self.blocks[idx].rows.len(){skip-=self.blocks[idx].rows.len();idx+=1;}
        self.blocks[idx..].iter().enumerate().flat_map(move |(i,b)|b.rows[if i==0{skip}else{0}..].iter())
    }
    // Canonical partitions have homogeneous clock keys and nondecreasing
    // leg order. All non-tail blocks within one partition are full.
    pub(crate) fn canonical_clock_order(&self,key:impl Fn(f64)->Option<u32>)->bool{
        let mut prev:Option<(u32,usize,usize)>=None;
        for b in &self.blocks{
            if b.rows.is_empty()||!b.valid||!b.sorted_leg{return false}
            let Some(k)=key(b.min_ready)else{return false};
            if key(b.max_ready)!=Some(k){return false}
            let first=b.rows[0].0;let last=b.rows.last().unwrap().0;
            if let Some((pk,pl,pn))=prev{
                if pk>k||pk==k&&(pl>first||pn!=BLOCK_ROWS){return false}
            }
            prev=Some((k,last,b.rows.len()));
        }
        true
    }
    pub(crate) fn partitioned_block_bound(rows:usize,partitions:usize)->usize{
        rows.div_ceil(BLOCK_ROWS).saturating_add(partitions).saturating_add(1)
    }
    pub(crate) fn partitioned_storage_bound(rows:usize,partitions:usize)->usize{
        let b=Self::partitioned_block_bound(rows,partitions);
        let per=std::mem::size_of::<Block>()+2*std::mem::size_of::<usize>()+BLOCK_ROWS*std::mem::size_of::<Access>()+ALLOCATION_PADDING;
        b.saturating_mul(per.saturating_add(std::mem::size_of::<Arc<Block>>())).saturating_add(2*ALLOCATION_PADDING)
    }
    pub(crate) fn with_partition_capacity(rows:usize,partitions:usize)->CoreResult<Self>{
        let cap=Self::partitioned_block_bound(rows,partitions);
        let mut blocks=Vec::new();
        blocks.try_reserve_exact(cap).map_err(|_|CoreError::resource("delay calendar block registry allocation"))?;
        if blocks.capacity()!=cap{return Err(CoreError::resource("delay calendar block registry capacity differs"))}
        Ok(Self{blocks,..Self::default()})
    }
    pub(crate) fn append_shared_blocks(&mut self,blocks:&[Arc<Block>]){
        for b in blocks{
            self.len+=b.rows.len();self.payload_bytes+=b.storage_bytes();self.capacity_rows+=b.rows.capacity();
            self.blocks.push(b.clone());
        }
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
    pub(crate) fn retire_due(&mut self,deadline:f64,finish:impl FnMut(&Access))->usize{
        self.retire_due_mode(deadline,false,finish)
    }
    pub(crate) fn retire_due_mode(&mut self, deadline: f64, preserve_partitions:bool, mut finish: impl FnMut(&Access)) -> usize {
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
        // The original filtered blocks can retain most of a 256-row
        // allocation for only one live row. Stable, optional repacking changes
        // no logical row; it relieves a recurrent restore-vs-in-memory cost.
        if !preserve_partitions{self.repack_sparse_stable();}
        retired
    }
    /// Repartition only when actual fragmentation saves at least 256 KiB.
    /// Original immutable Arc blocks remain alive until replacement; this
    /// operation does not take credit for them during construction.
    fn repack_sparse_stable(&mut self) {
        if self.len == 0 || self.blocks.len() <= self.len.div_ceil(BLOCK_ROWS)+1 {
            return;
        }
        let count=self.len.div_ceil(BLOCK_ROWS);
        let full=self.len/BLOCK_ROWS;
        let tail=self.len%BLOCK_ROWS;
        let packed_slots=full.saturating_mul(BLOCK_ROWS)
            .saturating_add(if tail==0 {0}else{tail.max(4).next_power_of_two().min(BLOCK_ROWS)});
        let block_cost=std::mem::size_of::<Block>()
            + 2*std::mem::size_of::<usize>() + ALLOCATION_PADDING;
        let target=packed_slots.saturating_mul(std::mem::size_of::<Access>())
            .saturating_add(count.saturating_mul(block_cost))
            .saturating_add(count.saturating_mul(std::mem::size_of::<Arc<Block>>()));
        if self.storage_bytes().saturating_sub(target) < 256*1024 {
            return;
        }
        let mut new_blocks=Vec::new();
        if new_blocks.try_reserve_exact(count).is_err() {return;}
        // Allocate a new canonical sequence while the old remains immutable.
        // Each allocation is fallible; failed attempts leave self unchanged.
        let mut block=Vec::new();
        let mut block_index=0usize;
        for &row in self.iter() {
            if block.is_empty() {
                let final_tail=block_index==full && tail!=0;
                let capacity=if final_tail {tail.max(4).next_power_of_two().min(BLOCK_ROWS)}
                    else {BLOCK_ROWS};
                let mut next=Vec::new();
                if next.try_reserve_exact(capacity).is_err() {return;}
                block=next;
            }
            block.push(row);
            if block.len()==BLOCK_ROWS
                || (block_index==full && tail!=0 && block.len()==tail) {
                new_blocks.push(Arc::new(Block::new(std::mem::take(&mut block))));
                block_index+=1;
            }
        }
        if !block.is_empty() || new_blocks.len()!=count {return;}
        let mut bytes=0usize;
        let mut cap=0usize;
        for b in &new_blocks {
            bytes=bytes.saturating_add(b.storage_bytes());
            cap=cap.saturating_add(b.rows.capacity());
        }
        // Exactly one logical replacement; old blocks are released here unless
        // an externally held immutable snapshot still owns their Arc backing.
        self.blocks=new_blocks;
        self.payload_bytes=bytes;
        self.capacity_rows=cap;
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

#[cfg_attr(feature="python-extension", pyclass)]
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
crate::optional_binding::optional_pymethods!(NativeStageQueue,
    [
    #[new]
    ] {
    fn new(rows: Vec<Access>) -> CoreResult<Self> {
        if !rows.iter().all(valid) {
            return Err(CoreError::value("invalid native stage row"));
        }
        Ok(Self { queue: rows.into() })
    }
    }
    [

    ] {

    fn fork(&self) -> Self {
        Self {
            queue: self.queue.clone(),
        }
    }
    }
    [

    ] {

    fn append(&mut self, row: Access) -> CoreResult<()> {
        if !valid(&row) {
            return Err(CoreError::value("invalid native stage row"));
        }
        self.queue.push(row);
        Ok(())
    }
    }
    [

    ] {

    fn snapshot(&self) -> Vec<Access> {
        self.queue.to_vec()
    }
    }
    [

    ] {

    fn retire_due(&mut self, deadline: f64) -> CoreResult<Vec<Access>> {
        if !deadline.is_finite() || deadline < 0. {
            return Err(CoreError::value("invalid native stage deadline"));
        }
        let mut rows = Vec::new();
        self.queue.retire_due(deadline, |a| rows.push(*a));
        Ok(rows)
    }
    }
    [

    ] {

    fn due_count(&self, deadline: f64) -> CoreResult<usize> {
        if !deadline.is_finite() || deadline < 0. {
            return Err(CoreError::value("invalid native stage deadline"));
        }
        Ok(self.queue.due_count(deadline))
    }
    }
    [

    ] {

    fn append_upper_bytes(&self, additional: usize) -> usize {
        self.queue.append_upper_bytes(additional)
    }
    }
    [

    ] {

    fn decoded_storage_upper_bytes(&self) -> usize {
        self.queue.decoded_storage_upper_bytes()
    }
    }
    [

    ] {

    fn storage_shape(&self) -> (usize, usize, usize, usize) {
        (
            self.queue.len(),
            self.queue.block_count(),
            self.queue.capacity(),
            self.queue.storage_bytes(),
        )
    }
    }
    [

    ] {

    fn shared_rows(&self, other: &Self) -> usize {
        self.queue.shared_rows(&other.queue)
    }
    }
);


#[cfg(test)]
mod stable_capacity_normal_form_tests {
    use super::*;
    #[test]
    fn sparse_survivors_repack_without_changing_order_or_f64_fields() {
        let mut q=StageQueue::new();
        let mut expected=Vec::new();
        for i in 0..(192*256usize) {
            let mass=f64::from_bits(0x3ff0000000000000u64+(i%29) as u64);
            let row=(i,mass,0.0,if i%256==0 {10.0} else {0.0});
            if i%256==0 {expected.push(row);}
            q.push(row);
        }
        assert_eq!(q.block_count(),192);
        let mut expired=0;
        let removed=q.retire_due(1.0, |_|expired+=1);
        assert_eq!(removed,192*255);
        assert_eq!(removed,expired);
        assert_eq!(q.len(),192);
        assert_eq!(q.iter().copied().collect::<Vec<_>>(),expected);
        // Behavioral RED on the old filter: 192 huge sparse backings survive.
        assert!(q.block_count()<=q.len().div_ceil(256)+1,
            "must pack exact FIFO survivors into bounded source blocks");
        assert!(q.storage_bytes() < 192*64,
            "capacity-normalized source still retains dense filtered payload");
    }
}

#[cfg(test)]
mod delay_partition_block_tests{
    use super::*;
    #[test]
    fn immutable_clock_partitions_share_untouched_payload_and_survive_retire(){
        let key=|r:f64|Some((r/10.).ceil()as u32);
        let mut q=StageQueue::with_partition_capacity(520,3).unwrap();
        for i in 0..260{q.push_partitioned((i,1.,0.,10.),i==0);}
        for i in 0..260{q.push_partitioned((i,1.,0.,20.),i==0);}
        assert!(q.canonical_clock_order(key));assert_eq!(q.block_count(),4);
        assert_eq!(q.iter_from(259).count(),261);
        assert_eq!(q.iter_from(260).next().unwrap().0,0);
        let mut c=StageQueue::with_partition_capacity(520,3).unwrap();
        c.append_shared_blocks(q.blocks());
        assert_eq!(c.shared_rows(&q),520);
        let mut retired=0;c.retire_due_mode(10.,true,|_|retired+=1);
        assert_eq!(retired,260);assert_eq!(c.shared_rows(&q),260);
        assert!(c.canonical_clock_order(key));assert_eq!(q.len(),520);
        assert!(c.storage_bytes()<=StageQueue::partitioned_storage_bound(520,3));
        c.push((0,1.,0.,10.));assert!(!c.canonical_clock_order(key));
    }
}
