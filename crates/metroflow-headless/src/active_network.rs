//! AKM-A: fixed-support, conservative moment transport.
//! Mixing closure, not exact arrival-order FIFO. SI units.
use crate::{active_kinetic::{Moment,Rates,react,split_velocity_selected},input::Result};
use serde::{Deserialize,Serialize};
use sha2::{Digest,Sha256};
#[derive(Clone,Copy,Debug,Serialize,Deserialize)]
pub struct Class {pub speed_ref:f64,pub footprint:f64,pub alpha:f64,pub nu0:f64,pub beta:f64,pub tau:f64}
#[derive(Clone,Copy,Debug,Serialize,Deserialize)]
pub struct Link {pub length:f64,pub speed_limit:f64,pub entry:f64,pub exit:f64,pub storage:f64,pub wave_speed:f64}
#[derive(Clone,Debug,Serialize,Deserialize)]
pub struct Route {pub class:usize,pub links:Vec<usize>}
#[derive(Clone,Debug,Serialize,Deserialize)]
pub struct Declaration {pub dt:f64,pub links:Vec<Link>,pub classes:Vec<Class>,pub routes:Vec<Route>}
#[derive(Clone,Copy,Debug)]
struct Slot{link:usize,route:usize,next:Option<usize>}
#[derive(Clone,Debug,PartialEq)]
pub struct State{
    pub time:f64, pub road:Vec<Moment>,pub pending:Vec<Moment>,
    pub released:Vec<f64>,pub released_birth:Vec<f64>,pub completed:Vec<f64>,pub completed_birth:Vec<f64>,
    pub completed_age:Vec<f64>,
}
#[derive(Clone,Copy,Debug,Default,Serialize)]
pub struct Stats{
    pub max_storage_ratio:f64,pub max_mass_residual:f64,pub max_birth_residual:f64,
    pub admitted:f64,pub transferred:f64,pub exited:f64,pub unused_receive_veh:f64,
}
#[derive(Clone,Copy,Debug,PartialEq,Eq,Serialize)]
pub enum FluxPolicy{Proportional,SelectiveResidual}
pub struct Model{decl:Declaration,slots:Vec<Slot>,roots:Vec<usize>,identity:String,policy:FluxPolicy}
pub struct Workspace{
    candidate:State,kinetic:Vec<Moment>,proposal:Vec<f64>,source:Vec<f64>,
    occupancy:Vec<f64>,send:Vec<f64>,receive:Vec<f64>,metres:Vec<f64>,
    ratio:Vec<f64>,scale:Vec<f64>,incoming:Vec<f64>,incoming_m:Vec<f64>,
    mass_check:Vec<f64>,birth_check:Vec<f64>,
    left_count:Vec<f64>,left_metres:Vec<f64>,extra:Vec<f64>,extra_source:Vec<f64>,
}
fn positive(x:f64)->bool{x.is_finite()&&x>0.}
fn nonnegative(x:f64)->bool{x.is_finite()&&x>=0.}
impl Model{
    pub fn new(decl:Declaration)->Result<Self>{Self::new_with_policy(decl,FluxPolicy::Proportional)}
    pub fn new_with_policy(decl:Declaration,policy:FluxPolicy)->Result<Self>{
        if !positive(decl.dt)||decl.links.is_empty()||decl.classes.is_empty()||decl.routes.is_empty(){return Err("invalid AKM declaration".into())}
        for c in &decl.classes{
            if ![c.speed_ref,c.footprint,c.alpha,c.tau].iter().all(|&x|positive(x))||![c.nu0,c.beta].iter().all(|&x|nonnegative(x))||!(c.nu0+c.beta+c.alpha).is_finite(){return Err("invalid AKM class".into())}
        }
        for l in &decl.links{
            if ![l.length,l.speed_limit,l.entry,l.exit,l.storage,l.wave_speed].iter().all(|&x|positive(x))||
                decl.classes.iter().any(|c|decl.dt*c.speed_ref.max(l.wave_speed)>l.length*(1.+1e-14)){return Err("AKM CFL or link geometry".into())}
        }
        let mut slots=vec![];let mut roots=vec![];
        for (r,p) in decl.routes.iter().enumerate(){
            if p.class>=decl.classes.len()||p.links.is_empty()||p.links.iter().any(|&e|e>=decl.links.len())||p.links.windows(2).any(|q|q[0]==q[1]){return Err("invalid AKM path".into())}
            roots.push(slots.len());
            for (i,&link) in p.links.iter().enumerate(){
                let idx=slots.len();slots.push(Slot{link,route:r,next:(i+1<p.links.len()).then_some(idx+1)});
            }
        }
        let identity=format!("akm-a-v1:{:x}",Sha256::digest(serde_json::to_vec(&decl).map_err(|e|e.to_string())?));
        let identity=if policy==FluxPolicy::Proportional{identity}else{format!("{identity}:selective-residual-v1")};
        Ok(Self{decl,slots,roots,identity,policy})
    }
    pub fn identity(&self)->&str{&self.identity}
    pub fn declaration(&self)->&Declaration{&self.decl}
    pub fn slot_count(&self)->usize{self.slots.len()}
    pub fn initial(&self)->State{
        let r=self.roots.len();
        State{time:0.,road:vec![Moment::default();self.slots.len()],pending:vec![Moment::default();r],
            released:vec![0.;r],released_birth:vec![0.;r],completed:vec![0.;r],completed_birth:vec![0.;r],completed_age:vec![0.;r]}
    }
    pub fn workspace(&self)->Workspace{
        let(e,r,p)=(self.decl.links.len(),self.roots.len(),self.slots.len());
        Workspace{candidate:self.initial(),kinetic:vec![Moment::default();p],proposal:vec![0.;p],source:vec![0.;r],
            occupancy:vec![0.;e],send:vec![0.;e],receive:vec![0.;e],metres:vec![0.;e],ratio:vec![0.;e],scale:vec![0.;e],
            incoming:vec![0.;e],incoming_m:vec![0.;e],mass_check:vec![0.;r],birth_check:vec![0.;r],
            left_count:vec![0.;e],left_metres:vec![0.;e],extra:vec![0.;e],extra_source:vec![0.;e]}
    }
    fn shape(&self,s:&State)->bool{
        let r=self.roots.len();
        s.road.len()==self.slots.len()&&s.pending.len()==r&&[s.released.len(),s.released_birth.len(),s.completed.len(),s.completed_birth.len(),s.completed_age.len()].iter().all(|&n|n==r)&&nonnegative(s.time)
    }
    fn validate(&self,s:&State,occ:&mut[f64],m:&mut[f64],b:&mut[f64])->Result<Stats>{
        if !self.shape(s){return Err("invalid AKM state shape".into())}
        occ.fill(0.);m.fill(0.);b.fill(0.);
        for (i,x) in s.road.iter().enumerate(){
            let sl=self.slots[i];let c=self.decl.classes[self.decl.routes[sl.route].class];
            if !x.valid(s.time){return Err("road moment cone".into())}
            occ[sl.link]+=c.footprint*x.mass();m[sl.route]+=x.mass();b[sl.route]+=x.birth;
        }
        let mut q=Stats::default();
        for i in 0..occ.len(){
            let z=occ[i]/self.decl.links[i].storage;
            if !nonnegative(z)||z>1.+1e-9{return Err("storage invariant".into())}
            q.max_storage_ratio=q.max_storage_ratio.max(z);
        }
        for i in 0..m.len(){
            if !s.pending[i].valid(s.time)||![s.released[i],s.released_birth[i],s.completed[i],s.completed_birth[i],s.completed_age[i]].iter().all(|&x|nonnegative(x)){return Err("invalid AKM ledger".into())}
            let dm=(s.released[i]-s.pending[i].mass()-m[i]-s.completed[i]).abs();
            let db=(s.released_birth[i]-s.pending[i].birth-b[i]-s.completed_birth[i]).abs();
            q.max_mass_residual=q.max_mass_residual.max(dm);
            q.max_birth_residual=q.max_birth_residual.max(db);
            if dm>1e-9*s.released[i].max(1.)||db>1e-8*s.released_birth[i].max(1.){return Err("AKM route mass/birth ledger".into())}
        }
        Ok(q)
    }
    pub fn validate_state(&self,s:&State)->Result<Stats>{
        let mut w=self.workspace();self.validate(s,&mut w.occupancy,&mut w.mass_check,&mut w.birth_check)
    }
    /// All allocations occur at model/state/workspace construction. Failed
    /// step leaves s unchanged; this is a simultaneous old-state transaction.
    pub fn step(&self,s:&mut State,w:&mut Workspace,offer:&[f64],gate:&[f64])->Result<Stats>{
        self.validate(s,&mut w.occupancy,&mut w.mass_check,&mut w.birth_check)?;
        let(e,r)=(self.decl.links.len(),self.roots.len());let h=self.decl.dt;
        if offer.len()!=r||gate.len()!=e||offer.iter().any(|&x|!nonnegative(x))||gate.iter().any(|&x|!x.is_finite()||!(0. ..=1.).contains(&x)){return Err("invalid AKM offers/gates".into())}
        let end=s.time+h;
        if !end.is_finite()||end<=s.time{return Err("AKM nonprogress clock".into())}
        let next=&mut w.candidate;
        next.time=end;next.road.fill(Moment::default());next.pending.copy_from_slice(&s.pending);
        next.released.copy_from_slice(&s.released);next.released_birth.copy_from_slice(&s.released_birth);
        next.completed.copy_from_slice(&s.completed);next.completed_birth.copy_from_slice(&s.completed_birth);
        next.completed_age.copy_from_slice(&s.completed_age);
        w.send.fill(0.);w.receive.fill(0.);w.metres.fill(0.);w.incoming.fill(0.);w.incoming_m.fill(0.);w.scale.fill(1.);
        for (i,sl) in self.slots.iter().enumerate(){
            let c=self.decl.classes[self.decl.routes[sl.route].class];let l=self.decl.links[sl.link];
            let phi=(w.occupancy[sl.link]/l.storage).min(1.);
            let rates=Rates{alpha:c.alpha,nu:c.nu0+c.beta*phi*phi,tau:c.tau,target:(l.speed_limit/c.speed_ref).min(1.)};
            let x=react(s.road[i],rates,h)?;
            w.kinetic[i]=x;
            let q=(h*c.speed_ref/l.length*x.momentum()).min(x.mass());
            w.proposal[i]=q;w.send[sl.link]+=q;
        }
        for j in 0..e{
            let cap=self.decl.links[j].exit*h*gate[j];
            if w.send[j]>cap{w.scale[j]=cap/w.send[j];}
        }
        for (i,sl) in self.slots.iter().enumerate(){
            w.proposal[i]*=w.scale[sl.link];
            if let Some(dst)=sl.next{
                let j=self.slots[dst].link;let q=w.proposal[i];let c=self.decl.classes[self.decl.routes[sl.route].class];
                w.receive[j]+=q;w.metres[j]+=q*c.footprint;
            }
        }
        for i in 0..r{
            let q=offer[i];let source=Moment::point(q,1.,0.,s.time);
            next.pending[i]=next.pending[i].add(source);
            next.released[i]+=q;next.released_birth[i]+=source.birth;
            w.source[i]=next.pending[i].mass();
            let j=self.slots[self.roots[i]].link;let c=self.decl.classes[self.decl.routes[i].class];
            w.receive[j]+=w.source[i];w.metres[j]+=w.source[i]*c.footprint;
        }
        // All destinations see the same pre-step free storage. Internal and
        // source proposals compete without inventing an ID-dependent priority.
        for j in 0..e{
            let l=self.decl.links[j];
            let metres=(l.storage-w.occupancy[j]).max(0.)*(h*l.wave_speed/l.length).min(1.);
            let count=h*l.entry;
            let qc=if w.receive[j]>0.{(count/w.receive[j]).min(1.)}else{1.};
            let mc=if w.metres[j]>0.{(metres/w.metres[j]).min(1.)}else{1.};
            w.ratio[j]=qc.min(mc);
        }
        w.scale.fill(1.);
        for (i,sl) in self.slots.iter().enumerate(){
            if w.proposal[i]>0.{if let Some(j)=sl.next{w.scale[sl.link]=w.scale[sl.link].min(w.ratio[self.slots[j].link]);}}
        }
        // One bounded residual allocation pass. A donor whose positive
        // remaining movement needs exhausted supply cannot increase its
        // common fraction and is excluded from residual competition.
        if self.policy==FluxPolicy::SelectiveResidual{
            for (i,sl) in self.slots.iter().enumerate(){
                if let Some(dst)=sl.next{let j=self.slots[dst].link;let q=w.proposal[i]*w.scale[sl.link];
                    w.incoming[j]+=q;w.incoming_m[j]+=q*self.decl.classes[self.decl.routes[sl.route].class].footprint;}
            }
            for i in 0..r{let j=self.slots[self.roots[i]].link;let q=w.source[i]*w.ratio[j];w.incoming[j]+=q;w.incoming_m[j]+=q*self.decl.classes[self.decl.routes[i].class].footprint;}
            for j in 0..e{let l=self.decl.links[j];w.left_count[j]=(h*l.entry-w.incoming[j]).max(0.);
                w.left_metres[j]=((l.storage-w.occupancy[j]).max(0.)*(h*l.wave_speed/l.length).min(1.)-w.incoming_m[j]).max(0.);}
            w.extra.fill(1.);w.receive.fill(0.);w.metres.fill(0.);
            for (i,sl) in self.slots.iter().enumerate(){if w.proposal[i]*(1.-w.scale[sl.link])>0.{if let Some(dst)=sl.next{
                let j=self.slots[dst].link;if w.left_count[j]==0.||w.left_metres[j]==0.{w.extra[sl.link]=0.;}
            }}}
            for (i,sl) in self.slots.iter().enumerate(){if w.extra[sl.link]>0.{if let Some(dst)=sl.next{
                let j=self.slots[dst].link;let q=w.proposal[i]*(1.-w.scale[sl.link]);w.receive[j]+=q;w.metres[j]+=q*self.decl.classes[self.decl.routes[sl.route].class].footprint;
            }}}
            for i in 0..r{let j=self.slots[self.roots[i]].link;let q=w.source[i]*(1.-w.ratio[j]);w.receive[j]+=q;w.metres[j]+=q*self.decl.classes[self.decl.routes[i].class].footprint;}
            for j in 0..e{let c=if w.receive[j]>0.{(w.left_count[j]/w.receive[j]).min(1.)}else{1.};
                let b=if w.metres[j]>0.{(w.left_metres[j]/w.metres[j]).min(1.)}else{1.};w.extra_source[j]=c.min(b);}
            for (i,sl) in self.slots.iter().enumerate(){if w.proposal[i]*(1.-w.scale[sl.link])>0.{if let Some(dst)=sl.next{
                w.extra[sl.link]=w.extra[sl.link].min(w.extra_source[self.slots[dst].link]);
            }}}
            for j in 0..e{w.scale[j]=(w.scale[j]+(1.-w.scale[j])*w.extra[j]).min(1.);
                w.ratio[j]=(w.ratio[j]+(1.-w.ratio[j])*w.extra_source[j]).min(1.);}
            w.incoming.fill(0.);w.incoming_m.fill(0.);
        }
        let mut stats=Stats::default();
        for (i,sl) in self.slots.iter().enumerate(){
            let x=w.kinetic[i];let m=x.mass();
            let f=if m>0.{(w.proposal[i]*w.scale[sl.link]/m).min(1.)}else{0.};
            let (remain,y)=if self.policy==FluxPolicy::SelectiveResidual{
                let c=if x.momentum()>0.{(w.proposal[i]*w.scale[sl.link]/x.momentum()).min(1.)}else{0.};
                split_velocity_selected(x,c,end)?
            }else{(x.scaled(1.-f),x.scaled(f))};
            if f>0.&&m>0.&&y.mass()==0.{return Err("positive transfer underflow".into())}
            if f<1.&&m>0.&&remain.mass()==0.{return Err("positive remainder underflow".into())}
            next.road[i]=next.road[i].add(remain);
            if let Some(j)=sl.next{
                next.road[j]=next.road[j].add(y);
                let dst=self.slots[j].link;let c=self.decl.classes[self.decl.routes[sl.route].class];
                w.incoming[dst]+=y.mass();w.incoming_m[dst]+=y.mass()*c.footprint;
                stats.transferred+=y.mass();
            }else{
                next.completed[sl.route]+=y.mass();next.completed_birth[sl.route]+=y.birth;
                next.completed_age[sl.route]+=(end*y.mass()-y.birth).max(0.);
                stats.exited+=y.mass();
            }
        }
        for i in 0..r{
            let x=next.pending[i];let j=self.slots[self.roots[i]].link;let f=w.ratio[j];
            let y=x.scaled(f);let remain=x.scaled(1.-f);
            if f>0.&&x.mass()>0.&&y.mass()==0.||f<1.&&x.mass()>0.&&remain.mass()==0.{return Err("positive source transfer underflow".into())}
            next.pending[i]=remain;next.road[self.roots[i]]=next.road[self.roots[i]].add(y);
            w.incoming[j]+=y.mass();w.incoming_m[j]+=y.mass()*self.decl.classes[self.decl.routes[i].class].footprint;
            stats.admitted+=y.mass();
        }
        for j in 0..e{
            let l=self.decl.links[j];let c=h*l.entry;let b=(l.storage-w.occupancy[j]).max(0.)*(h*l.wave_speed/l.length).min(1.);
            if w.incoming[j]>c+1e-9*c.max(1.)||w.incoming_m[j]>b+1e-9*b.max(1.){return Err("AKM receive quota".into())}
            stats.unused_receive_veh+=(c-w.incoming[j]).max(0.);
        }
        let q=self.validate(next,&mut w.occupancy,&mut w.mass_check,&mut w.birth_check)?;
        stats.max_storage_ratio=q.max_storage_ratio;stats.max_mass_residual=q.max_mass_residual;stats.max_birth_residual=q.max_birth_residual;
        std::mem::swap(s,next);Ok(stats)
    }
    /// Causal equilibrium-mobility forecast, not realized travel time.
    /// Only old state at observation boundary is used.
    pub fn route_costs(&self,s:&State,occ:&mut[f64],out:&mut[f64])->Result<()>{
        if occ.len()!=self.decl.links.len()||out.len()!=self.roots.len()||!self.shape(s){return Err("AKM forecast shape".into())}
        occ.fill(0.);
        for (i,sl) in self.slots.iter().enumerate(){occ[sl.link]+=s.road[i].mass()*self.decl.classes[self.decl.routes[sl.route].class].footprint;}
        for (i,r) in self.decl.routes.iter().enumerate(){
            let c=self.decl.classes[r.class];let mut cost=0.;
            for &j in &r.links{let l=self.decl.links[j];let phi=(occ[j]/l.storage).min(1.);let p=c.alpha/(c.alpha+c.nu0+c.beta*phi*phi);
                cost+=l.length/(c.speed_ref.min(l.speed_limit)*p);
            }
            out[i]=cost;
        }
        Ok(())
    }
    /// Fixed shape bit-exact checkpoint (no float JSON conversion).
    pub fn encode(&self,s:&State)->Result<Vec<u8>>{
        self.validate_state(s)?;
        let mut v=vec![];v.extend(b"AKMSTATE1");v.extend(self.identity.as_bytes());v.push(0);
        let mut emit=|x:f64|v.extend(x.to_bits().to_le_bytes());
        emit(s.time);for x in s.road.iter().chain(s.pending.iter()){for y in x.m.into_iter().chain(x.j).chain(x.z).chain([x.birth]){emit(y);}}
        for row in [&s.released,&s.released_birth,&s.completed,&s.completed_birth,&s.completed_age]{for &x in row{emit(x);}}
        Ok(v)
    }
    pub fn decode(&self,b:&[u8])->Result<State>{
        let id=self.identity.as_bytes();let off=9+id.len()+1;
        if b.len()<off||&b[..9]!=b"AKMSTATE1"||&b[9..off-1]!=id||b[off-1]!=0{return Err("AKM checkpoint identity".into())}
        let expected=1+7*(self.slots.len()+self.roots.len())+5*self.roots.len();
        if b.len()-off!=8*expected{return Err("AKM checkpoint length".into())}
        let mut iter=b[off..].chunks_exact(8).map(|z|f64::from_bits(u64::from_le_bytes(z.try_into().unwrap())));
        let mut s=self.initial();s.time=iter.next().unwrap();
        for x in s.road.iter_mut().chain(s.pending.iter_mut()){
            for y in x.m.iter_mut().chain(x.j.iter_mut()).chain(x.z.iter_mut()).chain(std::iter::once(&mut x.birth)){*y=iter.next().unwrap();}
        }
        for row in [&mut s.released,&mut s.released_birth,&mut s.completed,&mut s.completed_birth,&mut s.completed_age]{for x in row{*x=iter.next().unwrap();}}
        self.validate_state(&s)?;Ok(s)
    }
}
pub fn relaxed_pair(old:f64,costs:[f64;2],temperature:f64,relax:f64,dt:f64)->Result<f64>{
    if ![old,costs[0],costs[1],temperature,relax,dt].iter().all(|x|x.is_finite())||!(0. ..=1.).contains(&old)||temperature<=0.||relax<=0.||dt<0.{return Err("invalid route preference".into())}
    let target=if costs[0]<=costs[1]{1./(1.+((costs[0]-costs[1])/temperature).exp())}else{
        let q=((costs[1]-costs[0])/temperature).exp();q/(1.+q)};
    Ok(old+(target-old)*(-(-dt/relax).exp_m1()))
}
pub fn diamond(dt:f64,beta:f64)->Result<Model>{diamond_with_policy(dt,beta,FluxPolicy::Proportional)}
pub fn diamond_with_policy(dt:f64,beta:f64,policy:FluxPolicy)->Result<Model>{
    let l=|length,exit,storage|Link{length,speed_limit:10.,entry:1.4,exit,storage,wave_speed:5.};
    Model::new_with_policy(Declaration{dt,links:vec![l(100.,1.2,150.),l(100.,0.6,150.),l(160.,0.9,240.),l(100.,1.2,150.)],
    classes:vec![Class{speed_ref:10.,footprint:5.,alpha:0.2,nu0:0.,beta,tau:2.},Class{speed_ref:8.,footprint:10.,alpha:0.15,nu0:0.,beta,tau:3.}],
    routes:vec![Route{class:0,links:vec![0,1,3]},Route{class:0,links:vec![0,2,3]},Route{class:1,links:vec![0,1,3]},Route{class:1,links:vec![0,2,3]}]},policy)
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test] fn residual_donor_recovers_stranded_receiving_capacity(){
        let l=Link{length:100.,speed_limit:10.,entry:0.1,exit:10.,storage:100.,wave_speed:10.};
        let c=Class{speed_ref:10.,footprint:5.,alpha:0.2,nu0:0.,beta:0.,tau:2.};
        let decl=Declaration{dt:10.,links:vec![l;4],classes:vec![c],
            routes:vec![Route{class:0,links:vec![0,2]},Route{class:0,links:vec![0,3]},Route{class:0,links:vec![1,3]},Route{class:0,links:vec![2]}]};
        for policy in [FluxPolicy::Proportional,FluxPolicy::SelectiveResidual]{
            let m=Model::new_with_policy(decl.clone(),policy).unwrap();let mut s=m.initial();let mut w=m.workspace();
            for (i,mass) in [(0,1.),(2,1.),(4,1.),(6,20.)]{s.road[i]=Moment::point(mass,1.,1.,0.);}
            s.released.copy_from_slice(&[1.,1.,1.,20.]);
            let x=m.step(&mut s,&mut w,&[0.;4],&[1.,1.,0.,1.]).unwrap();
            let expected=if policy==FluxPolicy::Proportional{0.5}else{1.};
            assert!((s.road[5].mass()-expected).abs()<1e-12,"policy {:?} expected {}, actual {}",policy,expected,s.road[5].mass());
            assert_eq!(s.road[1].mass(),0.);assert_eq!(s.road[3].mass(),0.);
            assert!((x.transferred-expected).abs()<1e-12);
        }
    }
    #[test] fn conservation_storage_clock_and_restart(){
        let m=diamond(2.,0.6).unwrap();let mut s=m.initial();let mut w=m.workspace();
        let mut backup=vec![];
        for i in 0..600{
            let q=if i<120{[0.8,0.4,0.1,0.05]}else{[0.;4]};
            let gate=if (30..100).contains(&i){[1.,0.,1.,1.]}else{[1.;4]};
            m.step(&mut s,&mut w,&q,&gate).unwrap();
            if i==199{backup=m.encode(&s).unwrap();}
        }
        assert!(s.completed.iter().sum::<f64>()>140.);
        assert_eq!(m.slot_count(),12);
        let mut t=m.decode(&backup).unwrap();let mut w=m.workspace();
        for _ in 200..600{m.step(&mut t,&mut w,&[0.;4],&[1.;4]).unwrap();}
        assert_eq!(m.encode(&s).unwrap(),m.encode(&t).unwrap());
        assert!(diamond(20.,0.6).is_err());
        assert!(diamond(2.,0.).unwrap().decode(&backup).is_err());
        let before=m.encode(&s).unwrap();assert!(m.step(&mut s,&mut w,&[-1.,0.,0.,0.],&[1.;4]).is_err());assert_eq!(before,m.encode(&s).unwrap());
    }
    #[test] fn physical_source_spillback_and_mixture(){
        let m=diamond(2.,0.6).unwrap();let mut s=m.initial();let mut w=m.workspace();
        for _ in 0..100{m.step(&mut s,&mut w,&[20.,20.,10.,10.],&[0.,1.,1.,1.]).unwrap();}
        assert!(s.pending.iter().map(|x|x.mass()).sum::<f64>()>5000.);
        assert_eq!(s.completed.iter().sum::<f64>(),0.);
        assert!(m.validate_state(&s).unwrap().max_storage_ratio<=1.+1e-9);
    }
}
