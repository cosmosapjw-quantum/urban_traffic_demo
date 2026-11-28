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

pub(crate) const WAVE_MPS:f64=5.;
pub(crate) const MODEL:&str="akm-native-sparse-proportional-v1";
#[derive(Default,Debug)]
pub(crate) struct StepStats{
    pub substeps:usize,pub peak_rows:usize,pub peak_storage_ratio:f64,
    pub offered:f64,pub entered:f64,pub transferred:f64,pub exited:f64,
}
fn scaled_split(x:Moment,f:f64,t:f64)->CoreResult<(Moment,Moment)>{
    if !f.is_finite()||!(0. ..=1.).contains(&f){return Err(bad("AKM fraction"))}
    let y=x.scaled(f);let r=x.scaled(1.-f);
    if (f>0.&&x.mass()>0.&&y.mass()==0.)||(f<1.&&x.mass()>0.&&r.mass()==0.)||!r.valid(t)||!y.valid(t){
        return Err(bad("AKM nonrepresentable positive split"))
    }
    Ok((r,y))
}
impl State{
    pub(crate) fn work_reserve(&self)->usize{
        // Explicit research allowance, not proof of allocator peak.
        // Six live sparse copies/work arrays + next frontier headroom.
        self.rows().saturating_mul(512).saturating_mul(6)
            .saturating_add(32*1024*1024)
    }
    pub(crate) fn advance(&self,road:&V1Road,dt:f64,offers:&[(usize,f64,f64)],event_limit:usize,available:usize)
        ->CoreResult<(Self,crate::v1_road::ChunkedEvents,StepStats)>{
        use metroflow_headless::active_kinetic::{Rates,react};
        use crate::v1_road::ChunkedEvents;
        self.check(road)?;
        let(groups,classes)=road.akm_geometry();let n=groups.len();let uref=road.akm_reference_speed();
        if !dt.is_finite()||dt<=0.||!uref.is_finite()||uref<=0.||groups.is_empty(){return Err(bad("AKM invalid step geometry"))}
        let min_l=groups.iter().map(|g|g[0]).fold(f64::INFINITY,f64::min);
        let sub=(dt*uref.max(WAVE_MPS)/min_l).ceil().max(1.) as usize;
        if sub>4096{return Err(CoreError::resource("AKM CFL subdivisions exceed research domain"))}
        let mut state=self.clone();let mut events=ChunkedEvents::new(false);
        let mut stats=StepStats{substeps:sub,peak_rows:self.rows(),..Default::default()};
        for &(tag,m,birth) in offers{
            let k=road.class_for_route(tag).ok_or_else(||bad("AKM offer tag absent"))?;
            let c=&classes[k];
            if !m.is_finite()||m<0.||!birth.is_finite()||birth<0.||birth>m*self.t+1e-8*(m*self.t).max(1.)||m==0.&&birth!=0.{return Err(bad("AKM invalid offer mass/birth"))}
            let mut x=Moment::point(m,c[7],c[11]/uref,0.);x.birth=birth;
            add(&mut state.pending,(tag,0),x,self.t)?;
            state.class[k][0]+=m;state.offered_birth+=birth;stats.offered+=m;
        }
        for s in 0..sub{
            let end=if s+1==sub{self.t+dt}else{self.t+dt*(s+1) as f64/sub as f64};
            let h=end-state.t;
            if !h.is_finite()||h<=0.{return Err(bad("AKM no clock progress"))}
            let f=road.akm_factors(state.t,end)?;
            if state.work_reserve().saturating_add(events.retained_storage_bytes())>available{return Err(CoreError::resource("AKM working reserve exceeds allowance"))}
            let mut occupancy=vec![0.;n];let mut send=vec![0.;n];let mut count=vec![0.;n];let mut metres=vec![0.;n];
            let mut donor=vec![1.;n];let mut receiver=vec![1.;n];
            for (&(tag,pos),x) in &state.road{
                let j=road.registered_path(tag).unwrap()[pos];let k=road.class_for_route(tag).unwrap();
                occupancy[j]+=x.mass()*classes[k][12];
            }
            let mut proposal=Vec::with_capacity(state.road.len());
            for (&(tag,pos),x) in &state.road{
                let path=road.registered_path(tag).unwrap();let j=path[pos];let k=road.class_for_route(tag).unwrap();let c=&classes[k];
                let phi=(occupancy[j]/groups[j][4]).clamp(0.,1.);
                let q=if f[j].0>0.{c[0].min(groups[j][1])/uref}else{0.};
                let beta=c[9]*(c[10]/c[6]).powi(2);
                let y=react(*x,Rates{alpha:c[8],nu:beta*phi*phi,tau:c[1],target:q},h).map_err(bad)?;
                if !y.valid(end)||y.mass()==0.{return Err(bad("AKM reaction cone or positive-mass underflow"))}
                let amount=(h*uref/groups[j][0]*y.momentum()).min(y.mass());
                send[j]+=amount;
                proposal.push(((tag,pos),j,k,path.get(pos+1).copied(),y,amount));
            }
            for j in 0..n{
                let cap=groups[j][3]*h*f[j].0*if f[j].1{1.}else{0.};
                if send[j]>cap{donor[j]=cap/send[j]}
            }
            for p in &mut proposal{
                p.5*=donor[p.1];
                if let Some(j)=p.3{count[j]+=p.5;metres[j]+=p.5*classes[p.2][12];}
            }
            for (&(tag,_),x) in &state.pending{
                let j=road.registered_path(tag).unwrap()[0];let k=road.class_for_route(tag).unwrap();
                count[j]+=x.mass();metres[j]+=x.mass()*classes[k][12];
            }
            for j in 0..n{
                let c=groups[j][2]*h*f[j].0;let m=(groups[j][4]-occupancy[j]).max(0.)*(h*WAVE_MPS/groups[j][0]).min(1.);
                receiver[j]=if count[j]>0.{(c/count[j]).min(1.)}else{1.};
                if metres[j]>0.{receiver[j]=receiver[j].min(m/metres[j]);}
            }
            donor.fill(1.);
            for p in &proposal{if p.5>0.{if let Some(j)=p.3{donor[p.1]=donor[p.1].min(receiver[j])}}}
            let mut next=Self::blank(end,classes.len());next.class=state.class.clone();
            next.initial_birth=state.initial_birth;next.offered_birth=state.offered_birth;next.outlet_birth=state.outlet_birth;
            for ((tag,pos),j,k,dst,x,q) in proposal{
                let (r,y)=scaled_split(x,(q*donor[j]/x.mass()).min(1.),end)?;
                add(&mut next.road,(tag,pos),r,end)?;
                if y.mass()>0.{
                    if dst.is_some(){add(&mut next.road,(tag,pos+1),y,end)?;stats.transferred+=y.mass();}
                    else{
                        if events.len()>=event_limit{return Err(CoreError::resource("AKM outlet history limit"))}
                        let row=(tag,j,None,y.mass(),end,end,y.birth);
                        if next.work_reserve().saturating_add(events.projected_append_storage_bytes(row)?)>available{return Err(CoreError::resource("AKM outlet working reserve"))}
                        events.push_checked(row)?;
                        next.class[k][1]+=y.mass();next.outlet_birth+=y.birth;stats.exited+=y.mass();
                    }
                }
            }
            for (&(tag,pos),x) in &state.pending{
                let j=road.registered_path(tag).unwrap()[0];
                let(r,y)=scaled_split(*x,receiver[j],end)?;
                add(&mut next.pending,(tag,pos),r,end)?;add(&mut next.road,(tag,0),y,end)?;stats.entered+=y.mass();
            }
            stats.peak_rows=stats.peak_rows.max(next.rows());stats.peak_storage_ratio=stats.peak_storage_ratio.max(next.check(road)?);
            state=next;
        }
        Ok((state,events,stats))
    }
}

#[cfg(test)]
mod sparse_flux_tests{
    use super::*;
    fn road()->V1Road{
        V1Road::new("akm-fixture".into(),1.,vec![vec![100.,10.,2.,2.,200.,1.];2],vec![None,None],
            vec![(vec![0,1],0)],vec![vec![10.,2.,2.,4.,2.,1.,5.,1.,0.2,0.3,10.,0.,5.]],vec![vec![1],vec![0]],vec![],1000,Some(1000),true).unwrap()
    }
    #[test]
    fn sparse_transport_conserves_two_link_birth_and_mass(){
        let road=road();let mut s=State::blank(0.,1);let mut out=0.;
        for i in 0..100{
            let offer=if i==0{vec![(0,1.,0.)]}else{vec![]};
            let (next,e,stats)=s.advance(&road,1.,&offer,1000,256*1024*1024).unwrap();
            out+=e.iter().map(|x|x.3).sum::<f64>();assert!(stats.peak_rows<=3);s=next;
        }
        assert!(out>0.9);assert!((out+s.active_mass()-1.).abs()<1e-12);
        assert_eq!(s.total_birth(),0.);
        let old=s.clone();assert!(s.advance(&road,1.,&[(3,1.,0.)],1000,256*1024*1024).is_err());assert_eq!(old,s);
    }
}
