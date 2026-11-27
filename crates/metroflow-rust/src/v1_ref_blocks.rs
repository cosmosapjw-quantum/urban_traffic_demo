//! Exact random-access, 128-rank integer blocks for receiving postings.
//! Three independent frame-of-reference columns, constant columns cost zero.
//! Raw 96-bit fallback when packing would grow. Original f64 payload lives
//! in the event owner; no arithmetic, sorting or quantization is performed.
use crate::core_error::{CoreError,CoreResult};
const B:usize=128;
const RAW_WORDS:usize=B*3/2;
fn bad(s:&str)->CoreError{CoreError::resource(s)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
#[repr(C)]
pub(super) struct ReceivingRef {pub(super) event:u32,pub(super) offset:u32,pub(super) control:u32}
const _: [();12]=[();std::mem::size_of::<ReceivingRef>()];
impl ReceivingRef{fn columns(self)->[u32;3]{[self.event,self.offset,self.control]}fn from_columns(c:[u32;3])->Self{Self{event:c[0],offset:c[1],control:c[2]}}}
fn width(x:u32)->usize{(u32::BITS-x.leading_zeros())as usize}
fn block_words(widths:[usize;3])->usize{2+2*widths.iter().sum::<usize>()}
fn write_bits(dst:&mut [u64],bit:usize,n:usize,x:u32){
    if n==0{return}
    let i=bit/64;let b=bit%64;dst[i]|=(x as u64)<<b;
    if b+n>64{dst[i+1]|=(x as u64)>>(64-b)}
}
fn read_bits(src:&[u64],bit:usize,n:usize)->u32{
    if n==0{return 0}
    let i=bit/64;let b=bit%64;
    let mut x=src[i]>>b;if b+n>64{x|=src[i+1]<<(64-b)}
    (x&((1u64<<n)-1))as u32
}
fn encode(rows:&[ReceivingRef])->CoreResult<Vec<u64>>{
    assert_eq!(rows.len(),B);
    let mut lo=[u32::MAX;3];let mut hi=[0u32;3];
    for r in rows{for (k,v) in r.columns().into_iter().enumerate(){lo[k]=lo[k].min(v);hi[k]=hi[k].max(v)}}
    let mut w=std::array::from_fn(|i|width(hi[i]-lo[i]));
    let packed=block_words(w)<RAW_WORDS;
    let n=if packed{block_words(w)}else{lo=[0;3];w=[32;3];RAW_WORDS};
    let mut out=Vec::new();out.try_reserve_exact(n).map_err(|_|bad("receiving block allocation"))?;
    if out.capacity()!=n{return Err(bad("receiving block exact capacity differs"))}
    out.resize(n,0);
    let header=if packed{
        out[0]=lo[0]as u64|((lo[1]as u64)<<32);
        out[1]=lo[2]as u64|((w[0]as u64)<<32)|((w[1]as u64)<<38)|((w[2]as u64)<<44);2
    }else{0};
    let mut at=header;
    for (k,&bits) in w.iter().enumerate(){
        for (i,r) in rows.iter().enumerate(){write_bits(&mut out[at..at+2*bits],i*bits,bits,r.columns()[k]-lo[k]);}
        at+=2*bits;
    }
    Ok(out)
}
fn decode(block:&[u64],i:usize)->ReceivingRef{
    debug_assert!(i<B);
    let (lo,w,h)=if block.len()==RAW_WORDS{([0;3],[32;3],0)}else{
        ([block[0]as u32,(block[0]>>32)as u32,block[1]as u32],
        [((block[1]>>32)&63)as usize,((block[1]>>38)&63)as usize,((block[1]>>44)&63)as usize],2)
    };
    let mut at=h;let mut c=[0;3];
    for k in 0..3{c[k]=lo[k]+read_bits(&block[at..at+2*w[k]],i*w[k],w[k]);at+=2*w[k]}
    ReceivingRef::from_columns(c)
}
#[derive(Default)]
pub(super) struct PackedRefs{
    blocks:Vec<Vec<u64>>,
    tail:Vec<ReceivingRef>,
    len:usize,
    saved:usize,
}
impl PackedRefs{
    pub(super) fn len(&self)->usize{self.len}
    pub(super) fn logical_capacity(&self)->usize{self.len.div_ceil(B)*B}
    pub(super) fn descriptor_capacity(&self)->usize{self.blocks.capacity()}
    pub(super) fn saved_bytes(&self)->usize{self.saved}
    pub(super) fn physical_capacity_bytes(&self)->usize{
        self.blocks.len()*RAW_WORDS*8-self.saved+self.tail.capacity()*12
    }
    pub(super) fn allocated_bytes(&self)->usize{self.physical_capacity_bytes()+self.blocks.capacity()*std::mem::size_of::<Vec<u64>>()}
    // Seal only complete ranks. Extra reusable tail allocation is charged by
    // caller; the entire raw next block and descriptor growth are reserved
    // before append. No credited savings until encoding and installation finish.
    pub(super) fn push(&mut self,r:ReceivingRef)->CoreResult<usize>{
        if self.tail.capacity()==0{
            self.tail.try_reserve_exact(B).map_err(|_|bad("receiving staging allocation"))?;
            if self.tail.capacity()!=B{return Err(bad("receiving staging capacity differs"))}
        }
        self.tail.push(r);self.len=self.len.checked_add(1).ok_or_else(||bad("receiving rank overflow"))?;
        if self.tail.len()!=B{return Ok(0)}
        let block=encode(&self.tail)?;
        if self.blocks.len()==self.blocks.capacity(){
            let target=self.blocks.capacity().checked_mul(2).ok_or_else(||bad("receiving descriptor overflow"))?.max(4);
            let mut next=Vec::new();next.try_reserve_exact(target).map_err(|_|bad("receiving block descriptor allocation"))?;
            if next.capacity()!=target{return Err(bad("receiving block descriptor capacity differs"))}
            next.append(&mut self.blocks);self.blocks=next;
        }
        let credit=RAW_WORDS*8-block.capacity()*8;
        self.blocks.push(block);self.tail.clear();self.saved+=credit;Ok(credit)
    }
    pub(super) fn get(&self,i:usize)->Option<ReceivingRef>{
        if i>=self.len{return None}
        if i/B<self.blocks.len(){Some(decode(&self.blocks[i/B],i%B))}else{self.tail.get(i%B).copied()}
    }
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]fn widths_and_random_access_bits(){
        for bits in 0..=32{
            let max=if bits==32{u32::MAX}else{(1u32<<bits)-1};
            let rows=(0..B).map(|i|ReceivingRef{event:(i as u32).wrapping_mul(2654435761)&max,offset:u32::MAX-max+(i as u32&max),control:if i==0{max}else{0}}).collect::<Vec<_>>();
            let b=encode(&rows).unwrap();assert!(b.capacity()<=RAW_WORDS);
            for i in (0..B).rev(){assert_eq!(decode(&b,i),rows[i])}
        }
        let rows=vec![ReceivingRef{event:123,offset:u32::MAX,control:0};B];
        let b=encode(&rows).unwrap();assert_eq!(b.len(),2);assert_eq!(decode(&b,127),rows[0]);
    }
    #[test]fn exact_order_and_fallback_after_multiple_block_growths(){
        let mut p=PackedRefs::default();let mut total=0;
        let raw=(0..8223usize).map(|i|{
            let u=i as u32;
            if (i/B)%2==0{ReceivingRef{event:u*11,offset:u%12,control:u/31}}else{ReceivingRef{event:u.wrapping_mul(2654435761),offset:u.wrapping_mul(214013),control:u.wrapping_mul(1103515245)}}
        }).collect::<Vec<_>>();
        for (i,&r) in raw.iter().enumerate(){total+=p.push(r).unwrap();assert_eq!(p.get(i),Some(r));assert_eq!(p.saved_bytes(),total);}
        for i in (0..raw.len()).rev(){assert_eq!(p.get(i),Some(raw[i]))}
        assert!(total>0);assert_eq!(p.get(raw.len()),None);
        assert_eq!(p.physical_capacity_bytes(),(raw.len()/B)*B*12-total+B*12);
    }
}
