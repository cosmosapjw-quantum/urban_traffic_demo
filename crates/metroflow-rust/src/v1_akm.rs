//! Research-only sparse fixed-support AKM-A road. Exact journey and service
//! owners are reused. No claim of exact ordered FIFO or V03 equivalence.
use crate::{core_error::{CoreError,CoreResult},v1_road::V1Road};
use metroflow_headless::active_kinetic::Moment;
use std::collections::BTreeMap;
pub(crate) type Key=(usize,usize);
pub(crate) const ROAD_ROW_LIMIT:usize=1_000_000;
#[derive(Clone,Debug,PartialEq)]
pub(crate) struct State{
    pub t:f64,pub road:BTreeMap<Key,Moment>,pub pending:BTreeMap<Key,Moment>,
    pub class:Vec<[f64;2]>,pub initial_birth:f64,pub offered_birth:f64,pub outlet_birth:f64,
}
fn bad(s:impl Into<String>)->CoreError{CoreError::value(s)}
pub(crate) fn add(rows:&mut BTreeMap<Key,Moment>,key:Key,x:Moment,t:f64)->CoreResult<()>{
    if !x.valid(t){return Err(bad("invalid research moment"))}
    if x.mass()==0.{return Ok(())}
    if !rows.contains_key(&key)&&rows.len()>=ROAD_ROW_LIMIT{return Err(CoreError::resource("AKM sparse support guard"))}
    let y=rows.get(&key).copied().unwrap_or_default().add(x);
    if !y.valid(t){return Err(bad("invalid aggregated research moment"))}
    rows.insert(key,y);Ok(())
}
impl State{
    pub(crate) fn blank(t:f64,classes:usize)->Self{Self{t,road:BTreeMap::new(),pending:BTreeMap::new(),class:vec![[0.;2];classes],initial_birth:0.,offered_birth:0.,outlet_birth:0.}}
    pub(crate) fn rows(&self)->usize{self.road.len()+self.pending.len()}
    pub(crate) fn total_birth(&self)->f64{crate::v1_journey::fsum(self.road.values().chain(self.pending.values()).map(|x|x.birth))}
    pub(crate) fn active_mass(&self)->f64{crate::v1_journey::fsum(self.road.values().chain(self.pending.values()).map(|x|x.mass()))}
    pub(crate) fn active_by_tag(&self)->BTreeMap<usize,f64>{
        let mut out=BTreeMap::new();for (&(tag,_),x) in self.road.iter().chain(self.pending.iter()){*out.entry(tag).or_insert(0.)+=x.mass();}
        out
    }
    pub(crate) fn check(&self,road:&V1Road)->CoreResult<f64>{
        let (groups,classes)=road.akm_geometry();
        if !self.t.is_finite()||self.t<0.||self.class.len()!=classes.len()||self.rows()>ROAD_ROW_LIMIT{return Err(bad("AKM state shape/record budget"))}
        let mut occupancy=vec![0.;groups.len()];let mut class=vec![0.;classes.len()];
        for (is_pending,rows) in [(false,&self.road),(true,&self.pending)]{
            for (&(tag,offset),x) in rows{
                let k=road.class_for_route(tag).ok_or_else(||bad("AKM tag"))?;
                let j=*road.registered_path(tag).and_then(|p|p.get(offset)).ok_or_else(||bad("AKM route-position"))?;
                if is_pending&&offset!=0||!x.valid(self.t)||x.mass()<=0.{return Err(bad("AKM positive moment or pending offset"))}
                class[k]+=x.mass();if !is_pending{occupancy[j]+=classes[k][12]*x.mass();}
            }
        }
        let mut peak=0f64;
        for (j,v) in occupancy.iter().enumerate(){let r=v/groups[j][4];if !r.is_finite()||r>1.+1e-9{return Err(bad("AKM lane storage"))}peak=peak.max(r);}
        for (k,c) in self.class.iter().enumerate(){
            if c.iter().any(|x|!x.is_finite()||*x<0.)||(c[0]-c[1]-class[k]).abs()>1e-9*c[0].max(1.){return Err(bad(format!("AKM class mass ledger {k}: {:?} active {}",c,class[k])))}
        }
        if [self.initial_birth,self.offered_birth,self.outlet_birth].iter().any(|x|!x.is_finite()||*x<0.){return Err(bad("AKM birth nonnegative"))}
        let err=self.initial_birth+self.offered_birth-self.outlet_birth-self.total_birth();
        if err.abs()>1e-8*(self.initial_birth+self.offered_birth).max(1.){return Err(bad("AKM birth ledger"))}
        Ok(peak)
    }
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn two_old_cohorts_collapse_to_one_slot_without_losing_birth(){
        let mut x=BTreeMap::new();
        let a=Moment::point(0.5,0.25,0.3,1.);
        let b=Moment::point(0.5,0.75,0.4,2.);
        add(&mut x,(3,1),a,3.).unwrap();add(&mut x,(3,1),b,3.).unwrap();
        assert_eq!(x.len(),1);assert_eq!(x[&(3,1)],a.add(b));assert_eq!(x[&(3,1)].birth,1.5);
        let before=x.clone();assert!(add(&mut x,(3,1),Moment::point(1.,1.,1.,4.),3.).is_err());assert_eq!(x,before);
    }
}
