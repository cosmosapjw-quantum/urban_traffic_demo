//! Lagged LUTI experiment: reuse D07 transport, M04 growth and completed
//! accessibility. Synthetic one-way work trips, not full native city calendar.
use crate::{akm_d07::{run_epoch,EpochTraffic},causal::{Observation,Key},
    core_error::{CoreError,CoreResult},frozen_city::hash,
    lagged_growth::{Growth,GrowthState,Block,Entry,Site,Accessibility,compile_accessibility}};
use serde::{Deserialize,Serialize};
fn bad(s:impl Into<String>)->CoreError{CoreError::value(s)}
const INITIAL:u64=150;
const ADD:u64=50;
const INFLOW:u64=25;
const JOBS:u64=300;
const SLOW:f64=3600.;
const FAST:f64=1800.;
const WINDOW:u32=600;
const CITY:&str="D08-one-origin-physical-fixture-v1";
const ACCESS_MAX:f64=72.;
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
pub struct Config{pub bypass:bool,pub endogenous:bool,pub seed:u64}
fn digest<T:Serialize>(x:&T)->CoreResult<String>{Ok(hash(&serde_json::to_vec(x).map_err(|e|bad(e.to_string()))?))}
fn model_id(c:&Config)->CoreResult<String>{
    digest(&("AKMD08LUTI1",c,INITIAL,ADD,INFLOW,JOBS,SLOW,FAST,WINDOW,CITY,ACCESS_MAX,25.0f64))
}
fn growth()->CoreResult<Growth>{
    Growth::new(CITY,vec![Block{id:"home".into(),residents:INITIAL,housing_capacity:INITIAL}],
        vec![Entry{id:"home-entry".into(),block:"home".into(),city_identity:CITY.into(),node:"s".into(),construction_length_m:25.,capacity_veh_s:1.}],
        vec![Site{block:"home".into(),entry_id:"home-entry".into(),added_capacity:ADD,priority:0}],25.,SLOW,ACCESS_MAX)
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Activity{
    residents_placed:u64, residents_pending:u64, residents_requested:u64,
    housing:u64, jobs:u64, work_trips:u64, inactive_placed:u64, births:Vec<u32>
}
fn activity(c:&Config,s:&GrowthState)->CoreResult<Activity>{
    let placed=s.allocations.iter().sum::<u64>();
    let pending=s.pending_increment;let requested=s.original_residents.checked_add(s.requested_increment).ok_or_else(||bad("population overflow"))?;
    let housing=INITIAL+s.added.iter().sum::<u64>();
    if placed+pending!=requested||placed>housing||placed<INITIAL{return Err(bad("D08 resident ledger"))}
    let work=if c.endogenous{placed.min(JOBS)}else{INITIAL.min(placed).min(JOBS)};
    if work==0||work>JOBS{return Err(bad("D08 activity support"))}
    let births=(0..work as u32).map(|i|WINDOW*i/work as u32).collect();
    Ok(Activity{residents_placed:placed,residents_pending:pending,residents_requested:requested,
        housing,jobs:JOBS,work_trips:work,inactive_placed:placed-work,births})
}
fn observed_access(city:&str,n:usize,tr:&EpochTraffic)->CoreResult<Accessibility>{
    if tr.births.len()!=tr.done.len()||tr.completed+tr.pending+tr.road!=tr.births.len(){return Err(bad("D08 transport activity ledger"))}
    let offset=n as f64*SLOW;let stamp=offset+FAST;
    let mut rows=Vec::with_capacity(tr.completed);
    for (id,(&birth,done)) in tr.births.iter().zip(&tr.done).enumerate(){
        if let Some(done)=done{
            if !done.is_finite()||*done<birth as f64||*done>FAST{return Err(bad("D08 completed event support"))}
            rows.push(("home".into(),Observation{key:Key{kind:"route".into(),id:"home-to-job".into(),class:"car".into()},
                seconds:*done-birth as f64,stamp_s:stamp,start_s:offset+birth as f64,end_s:offset+done,
                mass_veh:1.,sensor_xy:[0.,0.],source:"completed_D07_owner".into(),
                version:tr.world_sha256.clone(),population:format!("epoch-{n}-owner-{id}"),measure:"completed birth-to-sink mean seconds".into()}));
        }
    }
    if rows.len()!=tr.completed{return Err(bad("D08 completed census"))}
    compile_accessibility(city,&rows,stamp)
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Epoch{
    index:usize,start_s:f64,city_identity:String,activity:Activity,traffic:EpochTraffic,
    access:Accessibility,growth_before:GrowthState,growth_after:Option<GrowthState>
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct State{schema:String,model:String,config:Config,growth:GrowthState,epochs:Vec<Epoch>}
impl State{
    fn new(c:Config,g:&Growth)->CoreResult<Self>{
        Ok(Self{schema:"AKMD08LUTI1".into(),model:model_id(&c)?,config:c,growth:g.initial(),epochs:vec![]})
    }
    fn check(&self,g:&Growth,c:&Config)->CoreResult<()>{
        if self.schema!="AKMD08LUTI1"||self.model!=model_id(c)?||&self.config!=c||self.epochs.len()>3{return Err(bad("D08 state identity"))}
        let mut old=g.initial();
        for (n,e) in self.epochs.iter().enumerate(){
            let city=g.materialized_identity(&old)?;
            let act=activity(c,&old)?;
            if e.index!=n||e.start_s!=n as f64*SLOW||e.growth_before!=old||e.city_identity!=city||e.activity!=act||
                e.traffic.births!=act.births||e.traffic.completed!=act.work_trips as usize||e.traffic.pending!=0||e.traffic.road!=0{
                return Err(bad("D08 epoch binding or undrained traffic"))
            }
            let access=observed_access(&city,n,&e.traffic)?;
            if e.access!=access{return Err(bad("D08 observed access differs"))}
            let ages=e.traffic.births.iter().zip(&e.traffic.done).map(|(&b,d)|d.unwrap_or(FAST)-b as f64).sum::<f64>();
            if e.traffic.stock_veh_s!=ages||e.traffic.mean_s!=Some(ages/e.traffic.completed as f64){return Err(bad("D08 exposure ledger"))}
            let after=if n<2{Some(g.advance(&old,&access,(n+1)as f64*SLOW,INFLOW,&[])?)}else{None};
            if e.growth_after!=after{return Err(bad("D08 lagged transition differs"))}
            if let Some(next)=after{old=next;}
        }
        g.check(&self.growth)?;
        if self.growth!=old{return Err(bad("D08 growth stock differs"))}
        Ok(())
    }
    fn advance(&mut self,g:&Growth,target:usize)->CoreResult<()>{
        if !(1..=3).contains(&target)||target<self.epochs.len(){return Err(bad("D08 epoch horizon"))}
        while self.epochs.len()<target{
            let n=self.epochs.len();let before=self.growth.clone();
            let city=g.materialized_identity(&before)?;
            let act=activity(&self.config,&before)?;
            let traffic=run_epoch(self.config.bypass,self.config.seed,&act.births)?;
            // Do not reset occupied traffic into the following fast window.
            if traffic.completed!=act.work_trips as usize||traffic.pending>0||traffic.road>0{
                return Err(bad("D08 non-drained fast epoch; no next stock update"))
            }
            let access=observed_access(&city,n,&traffic)?;
            let after=if n<2{Some(g.advance(&before,&access,(n+1)as f64*SLOW,INFLOW,&[])?)}else{None};
            if let Some(next)=&after{self.growth=next.clone();}
            self.epochs.push(Epoch{index:n,start_s:n as f64*SLOW,city_identity:city,activity:act,traffic,
                access,growth_before:before,growth_after:after});
        }
        self.check(g,&self.config)
    }
}
/// No Python runtime. A slow boundary checkpoint contains only drained
/// fast-epoch summaries and the M04 stock owner, not a live road hot swap.
pub fn execute(c:Config,target:usize,source:Option<&[u8]>)->CoreResult<(Vec<u8>,serde_json::Value)>{
    let g=growth()?;
    let mut s=if let Some(raw)=source{serde_json::from_slice::<State>(raw).map_err(|e|bad(e.to_string()))?}else{State::new(c.clone(),&g)?};
    s.check(&g,&c)?;s.advance(&g,target)?;
    let r=serde_json::json!({"schema":"akm_d08_luti_v1","status":"EXECUTED_FOR_REVIEW","scope":"bounded D07 repeated synthetic one-way work windows with historical native M04 Growth; not original city or calibrated LUTI",
        "model_identity":s.model,"config":s.config,"epochs":s.epochs,"growth":s.growth,
        "time_s":s.epochs.last().map(|e|if let Some(a)=&e.growth_after{a.epoch_s}else{e.access.stamp_s}).unwrap_or(0.),
        "completed_epochs":s.epochs.len(),"slow_updates":s.epochs.iter().filter(|e|e.growth_after.is_some()).count()});
    Ok((serde_json::to_vec(&s).map_err(|e|bad(e.to_string()))?,r))
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]fn old_growth_rejects_same_stamp_stale_city_and_preserves_pending(){
        let g=growth().unwrap();let s=g.initial();let id=g.materialized_identity(&s).unwrap();
        let a=Accessibility{city_identity:id.clone(),stamp_s:1800.,costs:vec![("home".into(),73.)],source_version:"test".into()};
        let mut same=a.clone();same.stamp_s=3600.;assert!(g.advance(&s,&same,3600.,INFLOW,&[]).is_err());
        let n=g.advance(&s,&a,3600.,INFLOW,&[]).unwrap();
        assert_eq!(n.allocations,[150]);assert_eq!(n.pending_increment,25);
        assert!(g.advance(&n,&a,7200.,INFLOW,&[]).is_err());
        let b=Accessibility{city_identity:g.materialized_identity(&n).unwrap(),stamp_s:5400.,costs:vec![("home".into(),71.)],source_version:"test-next".into()};
        let e=g.advance(&n,&b,7200.,INFLOW,&[]).unwrap();
        assert_eq!(e.allocations,[200]);assert_eq!(e.pending_increment,0);
        assert_eq!(activity(&Config{bypass:true,endogenous:true,seed:7},&e).unwrap().work_trips,200);
        assert_eq!(activity(&Config{bypass:true,endogenous:false,seed:7},&e).unwrap().inactive_placed,50);
    }
    #[test]fn missing_completion_is_not_prior_access(){
        let t=EpochTraffic{births:vec![0],done:vec![None],completed:0,pending:1,road:0,mean_s:None,stock_veh_s:1800.,peak_storage:0.,reroutes:0,
            final_branches:Default::default(),world_sha256:"test".into(),samples:vec![]};
        assert!(observed_access(CITY,0,&t).unwrap().costs.is_empty());
    }
}
