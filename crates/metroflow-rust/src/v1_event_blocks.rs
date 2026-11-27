//! Lossless random-access event payload pages. Source/time control stays
//! in ChunkedEvents. Store only integer deltas of exact IEEE bits, never
//! quantize, reorder, or reassociate. Raw fallback for high entropy.
use super::{budget,checkpoint_vec,push_checked,EventPayload,EVENT_PAGE_ROWS};
use crate::core_error::CoreResult;
const BLOCK:usize=128;
const N:usize=EVENT_PAGE_ROWS/BLOCK;
const RAW:usize=EVENT_PAGE_ROWS*3;
const HDR:usize=N+1;
const SUB_RAW:usize=BLOCK*3;
// One fixed raw tail and one bounded stack encoding buffer. Both included
// in append projection; the old and new page descriptor vectors also live.
pub(super) const EXTRA:usize=EVENT_PAGE_ROWS*24+32+ (RAW+HDR)*8+4096;
fn cols(p:EventPayload)->[u64;4]{[p.tag as u64,p.dest.wrapping_add(1)as u64,p.mass.to_bits(),p.birth.to_bits()]}
fn from_cols(x:[u64;4])->EventPayload{EventPayload{tag:x[0]as u32,dest:(x[1]as u32).wrapping_sub(1),mass:f64::from_bits(x[2]),birth:f64::from_bits(x[3])}}
fn width(x:u64)->usize{(64-x.leading_zeros())as usize}
fn put(a:&mut[u64],bit:usize,w:usize,v:u64){if w==0{return}let j=bit/64;let b=bit%64;a[j]|=v<<b;if b+w>64{a[j+1]|=v>>(64-b)}}
fn get(a:&[u64],bit:usize,w:usize)->u64{if w==0{return 0}let j=bit/64;let b=bit%64;let mut v=a[j]>>b;if b+w>64{v|=a[j+1]<<(64-b)}if w==64{v}else{v&((1u64<<w)-1)}}
fn raw_put(dst:&mut[u64],src:&[EventPayload]){for (x,p) in dst.chunks_exact_mut(3).zip(src){x[0]=(p.tag as u64)|((p.dest as u64)<<32);x[1]=p.mass.to_bits();x[2]=p.birth.to_bits();}}
fn raw_get(a:&[u64],i:usize)->EventPayload{let x=&a[i*3..i*3+3];EventPayload{tag:x[0]as u32,dest:(x[0]>>32)as u32,mass:f64::from_bits(x[1]),birth:f64::from_bits(x[2])}}
// Mode 0..64: frame of reference; 129..144: small dictionary.
// Avoid any heap temporary. Exact encoded length <= raw length.
fn encode_block(src:&[EventPayload],out:&mut[u64])->usize{
    let mut lo=[u64::MAX;4];let mut hi=[0;4];let mut dict=[[0u64;16];4];let mut d=[0usize;4];
    for p in src{for(k,v)in cols(*p).into_iter().enumerate(){lo[k]=lo[k].min(v);hi[k]=hi[k].max(v);if d[k]<=16&&!dict[k][..d[k]].contains(&v){if d[k]<16{dict[k][d[k]]=v;}d[k]+=1;}}}
    let mut mode=[0usize;4];let mut count=5;
    for k in 0..4{let w=width(hi[k]-lo[k]);let fw=2*w;let dw=if d[k]<=16{d[k]+2*width((d[k]-1)as u64)}else{usize::MAX};if dw<fw{mode[k]=128+d[k];count+=dw}else{mode[k]=w;count+=fw}}
    if count>=SUB_RAW{raw_put(&mut out[..SUB_RAW],src);return SUB_RAW}
    out[..count].fill(0);out[..4].copy_from_slice(&lo);
    out[4]=mode.iter().enumerate().fold(0,|a,(k,w)|a|((*w as u64)<<(8*k)));
    let mut at=5;
    for k in 0..4{
        let (w,n)=if mode[k]>64{let n=mode[k]-128;out[at..at+n].copy_from_slice(&dict[k][..n]);at+=n;(width((n-1)as u64),n)}else{(mode[k],0)};
        for (i,p) in src.iter().enumerate(){let v=cols(*p)[k];let x=if n>0{dict[k][..n].iter().position(|&a|a==v).unwrap()as u64}else{v-lo[k]};put(&mut out[at..at+2*w],i*w,w,x)}
        at+=2*w;
    }
    debug_assert_eq!(at,count);count
}
fn decode_block(a:&[u64],i:usize)->EventPayload{
    if a.len()==SUB_RAW{return raw_get(a,i)}
    let mut at=5;let mut x=[0;4];
    for k in 0..4{let m=((a[4]>>(8*k))&255)as usize;if m>64{let n=m-128;let w=width((n-1)as u64);let index=get(&a[at+n..at+n+2*w],i*w,w)as usize;x[k]=a[at+index];at+=n+2*w}else{x[k]=a[k]+get(&a[at..at+2*m],i*m,m);at+=2*m}}
    from_cols(x)
}
fn encode_page(src:&[EventPayload])->CoreResult<Vec<u64>>{
    debug_assert_eq!(src.len(),EVENT_PAGE_ROWS);
    let mut scratch=[0u64;RAW+HDR];let mut at=HDR;
    for (i,b) in src.chunks_exact(BLOCK).enumerate(){scratch[i]=at as u64;let n=encode_block(b,&mut scratch[at..at+SUB_RAW]);at+=n;}
    scratch[N]=at as u64;
    if at>=RAW{raw_put(&mut scratch[..RAW],src);at=RAW;}
    let mut page=checkpoint_vec(at)?;if page.capacity()!=at{return Err(budget("event block exact capacity differs"))}page.extend_from_slice(&scratch[..at]);Ok(page)
}
fn decode_page(a:&[u64],i:usize)->EventPayload{if a.len()==RAW{return raw_get(a,i)}let j=i/BLOCK;decode_block(&a[a[j]as usize..a[j+1]as usize],i%BLOCK)}
#[derive(Default)]
pub(super) struct PackedEvents{pages:Vec<Vec<u64>>,tail:Vec<EventPayload>,len:usize,saved:usize}
impl PackedEvents{
    pub(super) fn capacity(&self)->usize{self.len.div_ceil(EVENT_PAGE_ROWS)*EVENT_PAGE_ROWS}
    pub(super) fn pages(&self)->usize{self.pages.len()+usize::from(!self.tail.is_empty())}
    pub(super) fn descriptor_capacity(&self)->usize{self.pages.capacity()}
    pub(super) fn physical_bytes(&self)->usize{self.pages.len()*RAW*8-self.saved+self.tail.capacity()*24}
    pub(super) fn saved(&self)->usize{self.saved}
    pub(super) fn push(&mut self,p:EventPayload)->CoreResult<()>{
        if self.tail.capacity()==0{self.tail=checkpoint_vec(EVENT_PAGE_ROWS)?;if self.tail.capacity()!=EVENT_PAGE_ROWS{return Err(budget("event tail exact capacity differs"))}}
        self.tail.push(p);self.len+=1;
        if self.tail.len()==EVENT_PAGE_ROWS{let a=encode_page(&self.tail)?;let saved=RAW*8-a.capacity()*8;push_checked(&mut self.pages,a)?;self.saved+=saved;self.tail.clear();}
        Ok(())
    }
    pub(super) fn get(&self,i:usize)->Option<EventPayload>{if i>=self.len{return None}let j=i/EVENT_PAGE_ROWS;let k=i%EVENT_PAGE_ROWS;if j<self.pages.len(){Some(decode_page(&self.pages[j],k))}else{self.tail.get(k).copied()}}
}
#[cfg(test)]
mod tests{
 use super::*;
 fn bits(p:EventPayload)->[u64;4]{cols(p)}
 #[test] fn page_roundtrip_all_modes(){
  for mode in 0..4{
   let rows:Vec<_>=(0..EVENT_PAGE_ROWS).map(|i|{
    let x=(i as u64).wrapping_mul(0x9e3779b97f4a7c15);
    match mode{0=>EventPayload{tag:7,dest:u32::MAX,mass:-0.,birth:f64::from_bits(1)},1=>EventPayload{tag:i as u32,dest:i as u32%7,mass:f64::from_bits(x%13),birth:f64::from_bits(x%9)},2=>EventPayload{tag:i as u32,dest:(i as u32).wrapping_mul(0x9e3779b9),mass:f64::from_bits(x),birth:f64::from_bits(!x)},_=>EventPayload{tag:(x>>32)as u32,dest:x as u32,mass:f64::from_bits(x),birth:f64::from_bits(x^0x5555555555555555)}}
   }).collect();
   let a=encode_page(&rows).unwrap();assert!(a.len()<=RAW);
   for i in (0..EVENT_PAGE_ROWS).rev(){assert_eq!(bits(decode_page(&a,i)),bits(rows[i]));}
  }
 }
}
