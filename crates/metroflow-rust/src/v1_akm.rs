//! Research-only sparse fixed-support AKM-A road. Exact journey and service
//! owners are reused. No claim of exact ordered FIFO or V03 equivalence.
use crate::{core_error::{CoreError,CoreResult},v1_road::V1Road};
use metroflow_headless::active_kinetic::Moment;
use std::collections::BTreeMap;
pub(crate) type Key=(usize,usize);
pub(crate) const ROAD_ROW_LIMIT:usize=1_000_000;
pub(crate) const INTERFACE_MODEL:&str="akm-native-reserved-bus-interface-v1";
pub(crate) const HYBRID_MODEL:&str="akm-native-whole-bus-characteristic-v1";
#[derive(Clone,Copy,Debug,PartialEq)]
pub(crate) struct BusTrack{pub distance:f64,pub entry_s:f64}
#[derive(Clone,Debug,PartialEq)]
pub(crate) struct State{
    pub t:f64,pub road:BTreeMap<Key,Moment>,pub pending:BTreeMap<Key,Moment>,
    pub class:Vec<[f64;2]>,pub initial_birth:f64,pub offered_birth:f64,pub outlet_birth:f64,
    pub whole_bus_class:Option<usize>,pub bus_tracks:BTreeMap<Key,BusTrack>,
    pub interface:bool,pub crossings:BTreeMap<Key,f64>,
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
    pub(crate) fn enable_whole_bus(&mut self,class:usize,road:&V1Road)->CoreResult<()>{
        if class>=road.akm_geometry().1.len()||self.whole_bus_class.is_some()||
            self.road.keys().chain(self.pending.keys()).any(|&(tag,_)|road.class_for_route(tag)==Some(class)){
            return Err(bad("whole-service hybrid migration requires no active or pending mixed bus"))
        }
        self.whole_bus_class=Some(class);Ok(())
    }
    pub(crate) fn blank(t:f64,classes:usize)->Self{Self{t,road:BTreeMap::new(),pending:BTreeMap::new(),class:vec![[0.;2];classes],initial_birth:0.,offered_birth:0.,outlet_birth:0.,whole_bus_class:None,bus_tracks:BTreeMap::new(),interface:false,crossings:BTreeMap::new()}}
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
        if self.whole_bus_class.is_some_and(|k|k>=classes.len())||self.whole_bus_class.is_none()&&!self.bus_tracks.is_empty(){return Err(bad("AKM whole bus class/track shape"))}
        if self.interface&&self.whole_bus_class.is_none()||!self.interface&&!self.crossings.is_empty(){return Err(bad("AKM interface policy"))}
        let mut seen=std::collections::BTreeSet::new();let mut tracked=0usize;let mut crossing_seen=0;
        let mut occupancy=vec![0.;groups.len()];let mut class=vec![0.;classes.len()];
        for (is_pending,rows) in [(false,&self.road),(true,&self.pending)]{
            for (&(tag,offset),x) in rows{
                let k=road.class_for_route(tag).ok_or_else(||bad("AKM tag"))?;
                let j=*road.registered_path(tag).and_then(|p|p.get(offset)).ok_or_else(||bad("AKM route-position"))?;
                if is_pending&&offset!=0||!x.valid(self.t)||x.mass()<=0.{return Err(bad("AKM positive moment or pending offset"))}
                if self.whole_bus_class==Some(k){
                    if (x.mass()-1.).abs()>1e-12||!seen.insert(tag){return Err(bad("AKM whole bus is fractional or duplicated"))}
                    if !is_pending{
                        let q=self.bus_tracks.get(&(tag,offset)).ok_or_else(||bad("AKM bus track absent"))?;
                        if !q.distance.is_finite()||q.distance<0.||q.distance>groups[j][0]||!q.entry_s.is_finite()||q.entry_s<0.||q.entry_s>self.t{return Err(bad("AKM bus progress support"))}
                        tracked+=1;
                    }
                }
                class[k]+=x.mass();
                let weight=classes[k][12]*x.mass();
                if let Some(&a)=self.crossings.get(&(tag,offset)){
                    if !self.interface||self.whole_bus_class!=Some(k)||!a.is_finite()||!(0.<a&&a<1.){return Err(bad("AKM invalid crossing fraction"))}
                    crossing_seen+=1;
                    if is_pending{occupancy[j]+=weight*a;}
                    else{
                        if self.bus_tracks[&(tag,offset)].distance<groups[j][0]{return Err(bad("AKM crossing before boundary readiness"))}
                        occupancy[j]+=weight*(1.-a);
                        if let Some(&dst)=road.registered_path(tag).unwrap().get(offset+1){occupancy[dst]+=weight*a;}
                    }
                }else if !is_pending{occupancy[j]+=weight;}

            }
        }
        if crossing_seen!=self.crossings.len(){return Err(bad("AKM orphan crossing"))}
        if tracked!=self.bus_tracks.len(){return Err(bad("AKM orphan bus track"))}
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
    pub bus_exited:f64,pub bus_moves:usize,pub bus_quota_blocks:usize,
    pub bus_boundary_in:f64,pub bus_boundary_internal:f64,pub bus_boundary_sink:f64,
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
        use metroflow_headless::active_kinetic::{Rates,react,react_with_distance};
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
        if state.whole_bus_class.is_some(){state.check(road)?;}
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
                let weight=x.mass()*classes[k][12];
                if let Some(&a)=state.crossings.get(&(tag,pos)){
                    occupancy[j]+=weight*(1.-a);
                    if let Some(&dst)=road.registered_path(tag).unwrap().get(pos+1){occupancy[dst]+=weight*a;}
                }else{occupancy[j]+=weight;}
            }
            for (&(tag,pos),x) in &state.pending{if let Some(&a)=state.crossings.get(&(tag,pos)){
                let j=road.registered_path(tag).unwrap()[0];let k=road.class_for_route(tag).unwrap();
                occupancy[j]+=a*x.mass()*classes[k][12];
            }}
            let mut send_cap:Vec<f64>=(0..n).map(|j|groups[j][3]*h*f[j].0*if f[j].1{1.}else{0.}).collect();
            let mut receive_count:Vec<f64>=(0..n).map(|j|groups[j][2]*h*f[j].0).collect();
            let mut receive_metres:Vec<f64>=(0..n).map(|j|(groups[j][4]-occupancy[j]).max(0.)*(h*WAVE_MPS/groups[j][0]).min(1.)).collect();
            let mut next=Self::blank(end,classes.len());next.class=state.class.clone();
            next.initial_birth=state.initial_birth;next.offered_birth=state.offered_birth;next.outlet_birth=state.outlet_birth;
            next.whole_bus_class=state.whole_bus_class;next.interface=state.interface;
            if let Some(bus)=state.whole_bus_class{
                let mut ready=Vec::with_capacity(state.bus_tracks.len());
                for (&key,track) in &state.bus_tracks{
                    let (tag,pos)=key;let path=road.registered_path(tag).unwrap();let j=path[pos];
                    let c=&classes[bus];let phi=(occupancy[j]/groups[j][4]).clamp(0.,1.);
                    let q=if f[j].0>0.{c[0].min(groups[j][1])/uref}else{0.};
                    let beta=c[9]*(c[10]/c[6]).powi(2);let x=state.road[&key];
                    let(y,dx)=react_with_distance(x,Rates{alpha:c[8],nu:beta*phi*phi,tau:c[1],target:q},h).map_err(bad)?;
                    let track=BusTrack{distance:(track.distance+uref*dx).min(groups[j][0]),entry_s:track.entry_s};
                    ready.push((j,track.entry_s,key,path.get(pos+1).copied(),y,track));
                }
                ready.sort_by(|a,b|a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)).then(a.2.cmp(&b.2)));
                let mut bus_blocked=vec![false;n];
                for (j,_,key,dst,y,track) in ready{
                    let m=y.mass();let metres=m*classes[bus][12];let arrived=track.distance>=groups[j][0];
                    let old=state.crossings.get(&key).copied().unwrap_or(0.);
                    let (amount,progress,done)=if bus_blocked[j]||!arrived{(0.,old,false)}
                        else if state.interface{
                            let r=crate::v1_akm_interface::increment(m,old,send_cap[j],dst.map_or(f64::INFINITY,|k|receive_count[k]),dst.map_or(f64::INFINITY,|k|receive_metres[k]),classes[bus][12])?;
                            (r.amount,r.progress,r.done)
                        }else if send_cap[j]>=m&&dst.is_none_or(|k|receive_count[k]>=m&&receive_metres[k]>=metres){(m,1.,true)}
                        else{(0.,0.,false)};
                    if amount>0.{
                        send_cap[j]=(send_cap[j]-amount).max(0.);
                        if let Some(k)=dst{
                            receive_count[k]=(receive_count[k]-amount).max(0.);
                            receive_metres[k]=(receive_metres[k]-amount*classes[bus][12]).max(0.);
                            stats.bus_boundary_internal+=amount;stats.transferred+=amount;
                        }else{stats.bus_boundary_sink+=amount;}
                    }
                    if done{
                        stats.bus_moves+=1;
                        if dst.is_some(){
                            let new_key=(key.0,key.1+1);add(&mut next.road,new_key,y,end)?;
                            next.bus_tracks.insert(new_key,BusTrack{distance:0.,entry_s:end});
                        }else{
                            if events.len()>=event_limit{return Err(CoreError::resource("AKM outlet history limit"))}
                            let row=(key.0,j,None,m,end,end,y.birth);
                            if next.work_reserve().saturating_add(events.projected_append_storage_bytes(row)?)>available{return Err(CoreError::resource("AKM outlet working reserve"))}
                            events.push_checked(row)?;next.class[bus][1]+=m;next.outlet_birth+=y.birth;
                            stats.exited+=m;stats.bus_exited+=m;
                        }
                    }else{
                        if arrived&&amount==0.{stats.bus_quota_blocks+=1;}
                        bus_blocked[j]=true;add(&mut next.road,key,y,end)?;next.bus_tracks.insert(key,track);
                        if progress>0.{next.crossings.insert(key,progress);}
                    }
                }
                // Source priority is deterministic: intent birth then tag.
                // No fractional scheduled vehicles or unbounded quota carry.
                let mut sources=Vec::new();
                for (&key,x) in &state.pending{if road.class_for_route(key.0)==Some(bus){
                    if (x.mass()-1.).abs()>1e-12{return Err(bad("AKM scheduled source must be a whole unit"))}
                    sources.push((x.birth/x.mass(),key,*x));
                }}
                sources.sort_by(|a,b|a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
                for (_,key,x) in sources{
                    let j=road.registered_path(key.0).unwrap()[0];let m=x.mass();let metres=m*classes[bus][12];
                    let old=state.crossings.get(&key).copied().unwrap_or(0.);
                    let (amount,progress,done)=if state.interface{
                        let r=crate::v1_akm_interface::increment(m,old,f64::INFINITY,receive_count[j],receive_metres[j],classes[bus][12])?;
                        (r.amount,r.progress,r.done)
                    }else if receive_count[j]>=m&&receive_metres[j]>=metres{(m,1.,true)}
                    else{(0.,0.,false)};
                    receive_count[j]=(receive_count[j]-amount).max(0.);
                    receive_metres[j]=(receive_metres[j]-amount*classes[bus][12]).max(0.);
                    stats.entered+=amount;stats.bus_boundary_in+=amount;
                    if done{
                        add(&mut next.road,key,x,end)?;next.bus_tracks.insert(key,BusTrack{distance:0.,entry_s:end});
                    }else{
                        if amount==0.{stats.bus_quota_blocks+=1;}
                        add(&mut next.pending,key,x,end)?;
                        if progress>0.{next.crossings.insert(key,progress);}
                    }
                }
            }
            let mut proposal=Vec::with_capacity(state.road.len());
            for (&(tag,pos),x) in &state.road{
                let path=road.registered_path(tag).unwrap();let j=path[pos];let k=road.class_for_route(tag).unwrap();let c=&classes[k];
                if state.whole_bus_class==Some(k){continue}
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
                let cap=send_cap[j];
                if send[j]>cap{donor[j]=cap/send[j]}
            }
            for p in &mut proposal{
                p.5*=donor[p.1];
                if let Some(j)=p.3{count[j]+=p.5;metres[j]+=p.5*classes[p.2][12];}
            }
            for (&(tag,_),x) in &state.pending{
                let j=road.registered_path(tag).unwrap()[0];let k=road.class_for_route(tag).unwrap();
                if state.whole_bus_class==Some(k){continue}
                count[j]+=x.mass();metres[j]+=x.mass()*classes[k][12];
            }
            for j in 0..n{
                let c=receive_count[j];let m=receive_metres[j];
                receiver[j]=if count[j]>0.{(c/count[j]).min(1.)}else{1.};
                if metres[j]>0.{receiver[j]=receiver[j].min(m/metres[j]);}
            }
            donor.fill(1.);
            for p in &proposal{if p.5>0.{if let Some(j)=p.3{donor[p.1]=donor[p.1].min(receiver[j])}}}

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
                if state.whole_bus_class==road.class_for_route(tag){continue}
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
    fn whole_service_vehicle_is_indivisible_and_causal(){
        let road=road();let mut s=State::blank(0.,1);s.enable_whole_bus(0,&road).unwrap();
        let mut done=None;
        for i in 0..100{
            let offer=if i==0{vec![(0,1.,0.)]}else{vec![]};
            let (next,e,_)=s.advance(&road,1.,&offer,1000,256*1024*1024).unwrap();
            assert!(next.road.values().chain(next.pending.values()).all(|m|(m.mass()-1.).abs()<1e-12),"fractional scheduled vehicle");
            for row in e.iter(){assert!(row.3>1.-1e-12&&row.5>=21.,"premature or fractional outlet");assert!(done.replace(row.5).is_none());}
            s=next;
        }
        assert!(done.is_some());assert!(done.unwrap()<100.);assert_eq!(s.rows(),0);
        assert!((s.class[0][0]-s.class[0][1]).abs()<1e-12);
    }
    #[test]
    fn whole_service_cannot_bypass_subunit_supply(){
        let road=V1Road::new("akm-small-cap".into(),1.,vec![vec![100.,10.,0.1,2.,200.,1.]],vec![None],
            vec![(vec![0],0)],vec![vec![10.,2.,2.,4.,2.,1.,5.,1.,0.2,0.3,10.,0.,5.]],vec![vec![0]],vec![],1000,Some(1000),true).unwrap();
        let mut s=State::blank(0.,1);s.enable_whole_bus(0,&road).unwrap();
        for i in 0..20{
            let offer=if i==0{vec![(0,1.,0.)]}else{vec![]};
            let(next,events,st)=s.advance(&road,1.,&offer,1000,256*1024*1024).unwrap();
            assert_eq!(events.len(),0);assert_eq!(next.pending[&(0,0)].mass(),1.);assert_eq!(next.road.len(),0);assert_eq!(st.bus_quota_blocks,1);s=next;
        }
    }
    #[test]
    fn reserved_crossing_preserves_whole_service_and_current_quota(){
        let road=V1Road::new("akm-reservation".into(),1.,vec![vec![100.,10.,0.5,0.5,200.,1.];2],vec![None,None],
            vec![(vec![0,1],0)],vec![vec![10.,2.,2.,4.,2.,1.,5.,1.,0.2,0.3,10.,0.,12.]],vec![vec![1],vec![0]],vec![],1000,Some(1000),true).unwrap();
        let mut s=State::blank(0.,1);s.enable_whole_bus(0,&road).unwrap();s.interface=true;
        let mut sums=[0.;3];let mut completed=0.;let mut partial=[false;3];
        for i in 0..100{
            let offer=if i==1{vec![(0,1.,1.)]}else{vec![]};
            let (next,events,st)=s.advance(&road,1.,&offer,1000,256*1024*1024).unwrap();
            for v in [st.bus_boundary_in,st.bus_boundary_internal,st.bus_boundary_sink]{assert!(v<=0.5+1e-12);}
            sums[0]+=st.bus_boundary_in;sums[1]+=st.bus_boundary_internal;sums[2]+=st.bus_boundary_sink;
            for (&(tag,pos),&a) in &next.crossings{
                assert!(a>0.&&a<1.);
                partial[if next.pending.contains_key(&(tag,pos)){0}else if pos==0{1}else{2}]=true;
            }
            for row in events.iter(){assert!((row.3-1.).abs()<1e-12&&row.5>=21.);completed+=row.3;}
            assert!((next.active_mass()+completed-next.class[0][0]).abs()<1e-12);
            s=next;
        }
        assert!(partial.into_iter().all(|x|x));
        assert!((completed-1.).abs()<1e-12);
        assert!(sums.into_iter().all(|x|(x-1.).abs()<1e-12));
        assert_eq!(s.rows(),0);
        assert!((s.outlet_birth-1.).abs()<1e-12);
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

impl State{
    pub(crate) fn write<W:std::io::Write>(&self,w:&mut W)->CoreResult<()>{
        use crate::v1_road::{write_f64,write_len};
        write_f64(w,self.t)?;
        for x in [self.initial_birth,self.offered_birth,self.outlet_birth]{write_f64(w,x)?}
        write_len(w,self.class.len())?;
        for c in &self.class{for x in c{write_f64(w,*x)?}}
        for rows in [&self.road,&self.pending]{
            write_len(w,rows.len())?;
            for (&(tag,pos),x) in rows{
                write_len(w,tag)?;write_len(w,pos)?;
                for v in x.m.into_iter().chain(x.j).chain(x.z).chain([x.birth]){write_f64(w,v)?}
            }
        }
        if let Some(k)=self.whole_bus_class{
            write_len(w,k)?;write_len(w,self.bus_tracks.len())?;
            for (&(tag,pos),v) in &self.bus_tracks{write_len(w,tag)?;write_len(w,pos)?;write_f64(w,v.distance)?;write_f64(w,v.entry_s)?;}
        }
        if self.interface{
            write_len(w,self.crossings.len())?;
            for (&(tag,pos),&a) in &self.crossings{write_len(w,tag)?;write_len(w,pos)?;write_f64(w,a)?;}
        }
        Ok(())
    }
    pub(crate) fn read<R:std::io::Read>(r:&mut R,road:&V1Road,whole_bus_class:Option<usize>,interface:bool)->CoreResult<Self>{
        use crate::v1_road::{read_f64,read_len,read_exact_len};
        let t=read_f64(r)?;let n=road.akm_geometry().1.len();
        let mut s=Self::blank(t,n);s.initial_birth=read_f64(r)?;s.offered_birth=read_f64(r)?;s.outlet_birth=read_f64(r)?;
        read_exact_len(r,n)?;
        for c in &mut s.class{for x in c{*x=read_f64(r)?}}
        let max_tag=road.akm_support().0.saturating_sub(1);
        for rows in [&mut s.road,&mut s.pending]{
            let count=read_len(r,ROAD_ROW_LIMIT)?;
            for _ in 0..count{
                let tag=read_len(r,max_tag)?;
                let pos=read_len(r,road.registered_path(tag).ok_or_else(||bad("AKM wire route absent"))?.len().saturating_sub(1))?;
                let x=Moment{m:[read_f64(r)?,read_f64(r)?],j:[read_f64(r)?,read_f64(r)?],z:[read_f64(r)?,read_f64(r)?],birth:read_f64(r)?};
                if rows.insert((tag,pos),x).is_some(){return Err(bad("duplicate AKM checkpoint slot"))}
            }
        }
        if let Some(k)=whole_bus_class{
            read_exact_len(r,k)?;s.whole_bus_class=Some(k);
            let count=read_len(r,ROAD_ROW_LIMIT)?;
            for _ in 0..count{
                let tag=read_len(r,max_tag)?;let pos=read_len(r,road.registered_path(tag).ok_or_else(||bad("AKM track route"))?.len().saturating_sub(1))?;
                if s.bus_tracks.insert((tag,pos),BusTrack{distance:read_f64(r)?,entry_s:read_f64(r)?}).is_some(){return Err(bad("duplicate AKM bus track"))}
            }
        }
        s.interface=interface;
        if interface{
            let count=read_len(r,ROAD_ROW_LIMIT)?;
            for _ in 0..count{
                let tag=read_len(r,max_tag)?;let pos=read_len(r,road.registered_path(tag).ok_or_else(||bad("AKM crossing route"))?.len().saturating_sub(1))?;
                if s.crossings.insert((tag,pos),read_f64(r)?).is_some(){return Err(bad("duplicate AKM crossing"))}
            }
        }
        s.check(road)?;Ok(s)
    }
}
