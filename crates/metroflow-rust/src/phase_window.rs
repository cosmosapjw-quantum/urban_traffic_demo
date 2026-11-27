//! Restartable outlet moments, one append per committed physical tick.
use crate::{core_error::{CoreError,CoreResult},v1_journey::fsum,v1_road::EventRow};
use serde::{Serialize,Deserialize};
use sha2::{Sha256,Digest};
use std::collections::BTreeMap;
const MAX_GROUPS:usize=10000;
const MAX_PARTIALS:usize=64;
fn bad(s:&str)->CoreError{CoreError::value(s)}
#[derive(Clone,Debug,Serialize,Deserialize,Default,PartialEq)]
struct Expansion { #[serde(with="inline_partials")] partials:smallvec::SmallVec<[f64;4]> }
mod inline_partials {
 use serde::{Serialize,Serializer,Deserializer,de::{Visitor,SeqAccess,Error}};
 type Parts=smallvec::SmallVec<[f64;4]>;
 pub fn serialize<S:Serializer>(p:&Parts,s:S)->Result<S::Ok,S::Error>{p.as_slice().serialize(s)}
 pub fn deserialize<'de,D:Deserializer<'de>>(d:D)->Result<Parts,D::Error>{
  struct V;
  impl<'de> Visitor<'de> for V{
   type Value=Parts;
   fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result{write!(f,"at most {} finite expansion components",super::MAX_PARTIALS)}
   fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->Result<Parts,A::Error>{
    let mut p=Parts::new();while let Some(x)=a.next_element::<f64>()?{if p.len()==super::MAX_PARTIALS||!x.is_finite(){return Err(A::Error::custom("phase expansion bound or nonfinite value"))}p.push(x)}Ok(p)
   }
  }d.deserialize_seq(V)
 }
}
impl Expansion {
    fn add(&mut self,mut x:f64)->CoreResult<()>{
        if !x.is_finite(){return Err(bad("nonfinite outlet moment"))}
        let mut i=0;
        for j in 0..self.partials.len(){
            let mut y=self.partials[j];
            if x.abs()<y.abs(){std::mem::swap(&mut x,&mut y)}
            let hi=x+y;
            if !hi.is_finite(){return Err(bad("outlet moment overflow"))}
            let lo=y-(hi-x);
            if lo!=0.{self.partials[i]=lo;i+=1}
            x=hi;
        }
        self.partials.truncate(i);
        if x!=0.{
            if self.partials.len()==MAX_PARTIALS{return Err(CoreError::resource("phase outlet expansion bound"))}
            self.partials.push(x);
        }
        Ok(())
    }
    fn value(&self)->f64{fsum(self.partials.iter().copied())}
    fn valid(&self)->bool{self.partials.len()<=MAX_PARTIALS&&self.partials.iter().all(|v|v.is_finite())&&self.value().is_finite()}
}
#[derive(Clone,Debug,Serialize,Deserialize,PartialEq)]
struct Group { mass:Expansion,elapsed:Expansion,start:f64,end:f64,count:u64,hash:[u8;32] }
#[derive(Clone,Debug,Serialize,Deserialize,PartialEq)]
pub struct PhaseWindow { since:f64,last:f64,groups:BTreeMap<usize,Group> }
pub(crate) struct Moment { pub tag:usize,pub mass:f64,pub elapsed:f64,pub start:f64,pub end:f64,pub count:u64,pub hash:[u8;32] }
impl PhaseWindow {
    pub(crate) fn new(t:f64)->Self{Self{since:t,last:t,groups:BTreeMap::new()}}
    pub(crate) fn validate(&self,since:f64,now:f64,tags:usize)->CoreResult<()>{
        if !since.is_finite()||!now.is_finite()||since<0.||since>now||self.since!=since||self.last!=now||self.groups.len()>MAX_GROUPS
            || self.groups.iter().any(|(&tag,g)|tag>=tags||g.count==0||!g.mass.valid()||g.mass.value()<=0.||!g.elapsed.valid()||!g.start.is_finite()||!g.end.is_finite()||g.start<0.||g.start>g.end||g.end<=since||g.end>now){
            return Err(bad("phase outlet window identity/clock/bound differs"));
        }
        Ok(())
    }
    pub(crate) fn append_tick(&mut self,previous:f64,now:f64,tags:usize,events:impl IntoIterator<Item=EventRow>)->CoreResult<()>{
        if previous!=self.last||!now.is_finite()||now<=previous{return Err(bad("phase outlet tick repeated or out of order"))}
        for e in events{
            if e.2.is_some(){continue}
            if !e.4.is_finite()||!e.5.is_finite()||e.4<0.||e.4>e.5||e.5>now||e.0>=tags||!e.3.is_finite()||e.3<=0.{return Err(bad("invalid outlet row"))}
            if e.5<=self.since{continue}
            let elapsed=e.3*(e.4+e.5)/2.-e.6;
            if !self.groups.contains_key(&e.0)&&self.groups.len()==MAX_GROUPS{return Err(CoreError::resource("phase outlet group bound"))}
            let g=self.groups.entry(e.0).or_insert_with(||Group{mass:Expansion::default(),elapsed:Expansion::default(),start:e.4,end:e.5,count:0,hash:[0;32]});
            g.mass.add(e.3)?;g.elapsed.add(elapsed)?;g.start=g.start.min(e.4);g.end=g.end.max(e.5);g.count=g.count.checked_add(1).ok_or_else(||bad("outlet count overflow"))?;
            let mut h=Sha256::new();h.update(g.hash);
            for v in [e.0 as u64,e.1 as u64,e.3.to_bits(),e.4.to_bits(),e.5.to_bits(),e.6.to_bits()]{h.update(v.to_le_bytes())}
            g.hash=h.finalize().into();
        }
        self.last=now;
        Ok(())
    }
    pub(crate) fn publish(&mut self,now:f64)->CoreResult<Vec<Moment>>{
        if now!=self.last||now<=self.since{return Err(bad("outlet publication clock differs"))}
        let mut out=Vec::with_capacity(self.groups.len());
        for (tag,g) in std::mem::take(&mut self.groups){
            let mass=g.mass.value();let elapsed=g.elapsed.value();
            if !mass.is_finite()||mass<=0.||!elapsed.is_finite()||elapsed<0.{return Err(bad("invalid aggregate outlet moment"))}
            out.push(Moment{tag,mass,elapsed,start:g.start,end:g.end,count:g.count,hash:g.hash});
        }
        self.since=now;Ok(out)
    }
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn earlier_tick_survives_restart_and_no_double_count(){
        let mut w=PhaseWindow::new(0.);
        let a=(0,1,None,2.,0.,1.,0.);
        let b=(0,1,None,3.,1.,2.,0.);
        w.append_tick(0.,1.,1,[a]).unwrap();
        let mut restored:PhaseWindow=serde_json::from_slice(&serde_json::to_vec(&w).unwrap()).unwrap();
        restored.validate(0.,1.,1).unwrap();
        w.append_tick(1.,2.,1,[b]).unwrap();
        restored.append_tick(1.,2.,1,[b]).unwrap();
        assert_eq!(w,restored);
        assert!(w.append_tick(1.,2.,1,[b]).is_err());
        let m=w.publish(2.).unwrap();
        assert_eq!(m.len(),1);assert_eq!(m[0].count,2);assert_eq!(m[0].mass,5.);assert_eq!(m[0].elapsed,5.5);
        w.validate(2.,2.,1).unwrap();
    }
    #[test]
    fn wire_decoder_refuses_oversized_expansion_before_use(){
        let v=serde_json::json!({"partials":vec![1.;MAX_PARTIALS+1]});
        assert!(serde_json::from_value::<Expansion>(v).is_err());
    }
    #[test]
    fn partitions_preserve_exact_moments(){
        let rows=[(0,0,None,1e16,0.,1.,0.),(0,0,None,1.,0.,1.,0.),(0,0,None,1.,1.,2.,0.)];
        let mut w=PhaseWindow::new(0.);
        w.append_tick(0.,1.,1,rows[..2].iter().copied()).unwrap();
        w.append_tick(1.,2.,1,rows[2..].iter().copied()).unwrap();
        let m=w.publish(2.).unwrap();
        assert_eq!(m[0].mass.to_bits(),fsum(rows.iter().map(|r|r.3)).to_bits());
        assert_eq!(m[0].elapsed.to_bits(),fsum(rows.iter().map(|r|r.3*(r.4+r.5)/2.-r.6)).to_bits());
    }
}
