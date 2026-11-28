//! Bounded D07 research lab, not the original city or a production candidate.
use crate::{causal::{Key,Prior,Channel,Information,Observation,Report,DecisionObservation},causal_routing::{Link,Routing,Commitment,Boundary,Preference,Decision},core_error::{CoreError,CoreResult},frozen_city::hash};
use serde::{Serialize,Deserialize};
use metroflow_headless::active_kinetic::{Moment,Rates,react_with_distance};
use std::collections::BTreeSet;
fn bad(s:&str)->CoreError{CoreError::value(s)}
const E:usize=7;const BYPASS:usize=5;
const IDS:[&str;E]=["approach","bridge","upper_exit","long","lower_exit","bypass","exit"];
const TAIL:[&str;E]=["s","x","u","x","v","x","z"];
const HEAD:[&str;E]=["x","u","z","v","z","z","d"];
const L:[f64;E]=[150.,60.,60.,130.,130.,100.,80.];
const CAP:[f64;E]=[1.,0.35,0.35,0.6,0.6,0.65,1.];
const TURNS:[(usize,usize);8]=[(0,1),(1,2),(2,6),(0,3),(3,4),(4,6),(0,5),(5,6)];
const MAX:usize=300;
fn idx(s:&str)->CoreResult<usize>{IDS.iter().position(|x|*x==s).ok_or_else(||bad("unknown lab link"))}
fn pref()->Preference{Preference{class:"car".into(),purpose:"work".into(),time_weight:1.,distance_s_per_m:0.,money_s_per_unit:0.,logit_scale_s:12.,path_size_beta:1.}}
fn route_model(installed:[bool;E],version:u32)->CoreResult<Routing>{
    let links=(0..E).filter(|&i|installed[i]).map(|i|Link{id:IDS[i].into(),tail:TAIL[i].into(),head:HEAD[i].into(),length_m:L[i],toll_units:0.}).collect();
    let turns=TURNS.iter().filter(|&&(i,j)|installed[i]&&installed[j]).map(|&(i,j)|(IDS[i].into(),IDS[j].into())).collect();
    Routing::new(links,turns,&format!("akm-d07-graph-{version}"),3,256,256,64,2)
}
fn legal(path:&[String],installed:[bool;E])->bool{
    let Ok(p)=path.iter().map(|x|idx(x)).collect::<CoreResult<Vec<_>>>() else{return false};
    if p.is_empty()||p[0]!=0||*p.last().unwrap()!=6||p.iter().any(|&i|!installed[i])||p.windows(2).any(|w|!TURNS.contains(&(w[0],w[1]))){return false}
    let mut nodes=BTreeSet::new();nodes.insert(TAIL[p[0]]);
    p.iter().all(|&i|nodes.insert(HEAD[i]))
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Owner{
    id:usize,birth:f64,moment:Moment,route:Option<Commitment>,initial_branch:Option<String>,
    phase:u8, // 0 source pending,1 physical road,2 logical complete
    distance:f64,entry:f64,cross:f64,done:Option<f64>,last_reroute:Option<f64>
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct GraphEvent{time:f64,action:String,accepted:bool,reason:String,before:String,after:String}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Graph{installed:[bool;E],version:u32,id:String}
impl Graph{
    fn new()->CoreResult<Self>{let mut installed=[true;E];installed[BYPASS]=false;
        Ok(Self{installed,version:0,id:route_model(installed,0)?.graph_id})}
    fn edit(&mut self,owners:&mut[Owner],t:f64,link:usize,add:bool)->CoreResult<GraphEvent>{
        if link>=E||!t.is_finite()||t<0.||self.installed[link]==add{return Err(bad("invalid graph edit"))}
        let action=format!("{}:{}",if add{"add"}else{"remove"},IDS[link]);
        let before=self.id.clone();
        let mut installed=self.installed;installed[link]=add;
        if owners.iter().filter(|o|o.phase!=2).any(|o|o.route.as_ref().is_some_and(|r|!legal(&r.links,installed))){
            return Ok(GraphEvent{time:t,action,accepted:false,reason:"live commitment prevents removal".into(),before:before.clone(),after:before})
        }
        let version=self.version.checked_add(1).ok_or_else(||bad("graph version overflow"))?;
        let id=route_model(installed,version)?.graph_id;
        for o in owners.iter_mut().filter(|o|o.phase!=2){
            if let Some(r)=&mut o.route{r.graph_id=id.clone();}
        }
        *self=Self{installed,version,id:id.clone()};
        Ok(GraphEvent{time:t,action,accepted:true,reason:"installed legal graph".into(),before,after:id})
    }
}
fn initial_owner(id:usize,t:f64)->Owner{Owner{id,birth:t,moment:Moment::point(1.,1.,0.,t),route:None,initial_branch:None,phase:0,distance:0.,entry:t,cross:0.,done:None,last_reroute:None}}
fn route(graph:&Graph,p:&[usize])->Commitment{Commitment{graph_id:graph.id.clone(),links:p.iter().map(|&i|IDS[i].into()).collect(),position:0}}
#[cfg(test)]
mod graph_tests{
    use super::*;
    #[test] fn graph_add_rebind_and_refuse_live_removal(){
        let mut g=Graph::new().unwrap();let mut owners=vec![initial_owner(0,0.)];
        owners[0].route=Some(route(&g,&[0,1,2,6]));let before=owners[0].clone();
        let a=g.edit(&mut owners,300.,BYPASS,true).unwrap();assert!(a.accepted);assert_ne!(a.before,a.after);
        assert_eq!(owners[0].route.as_ref().unwrap().links,before.route.unwrap().links);
        assert_eq!(owners[0].moment,before.moment);assert_eq!(owners[0].route.as_ref().unwrap().graph_id,g.id);
        owners[0].route=Some(route(&g,&[0,5,6]));let saved=owners.clone();let old=g.clone();
        let a=g.edit(&mut owners,540.,BYPASS,false).unwrap();assert!(!a.accepted);assert_eq!(owners,saved);assert_eq!(g,old);
        owners[0].phase=2;owners[0].done=Some(600.);
        let a=g.edit(&mut owners,600.,BYPASS,false).unwrap();assert!(a.accepted);assert!(!g.installed[BYPASS]);
    }
}

const ELL:f64=5.;
const U:f64=10.;
fn storage(i:usize)->f64{1.5*L[i]}
fn no_entry(i:usize,t:f64)->bool{i==1&&(360. ..480.).contains(&t)}
#[derive(Clone,Debug,Default,PartialEq,Serialize,Deserialize)]
struct Passage{owner:usize,link:usize,entered:f64,exited:f64}
#[derive(Clone,Debug,Default,PartialEq,Serialize,Deserialize)]
struct Physical{
    peak_storage:f64,peak_send:f64,peak_receive:f64,peak_metre:f64,
    boundary_mass:f64,partial_steps:usize,peak_ready:usize,stock_integral:f64,
    blocked_steps:usize,passages:Vec<Passage>
}
fn stock(owners:&[Owner])->CoreResult<[f64;E]>{
    let mut s=[0.;E];
    for o in owners{
        if o.phase==2{continue}
        if let Some(r)=&o.route{
            let i=idx(r.links.get(r.position).ok_or_else(||bad("bad owner position"))?)?;
            if o.phase==0{s[i]+=ELL*o.cross;}
            else if o.phase==1{
                s[i]+=ELL*(1.-o.cross);
                if let Some(j)=r.links.get(r.position+1){s[idx(j)?]+=ELL*o.cross;}
            }else{return Err(bad("bad phase"))}
        }
    }
    Ok(s)
}
fn check(g:&Graph,owners:&[Owner],t:f64)->CoreResult<()>{
    if owners.len()>MAX{return Err(CoreError::resource("D07 owner domain"))}
    let mut seen=BTreeSet::new();
    for o in owners{
        if !seen.insert(o.id)||o.id>=MAX||!o.birth.is_finite()||o.birth<0.||o.birth>t||
            !o.moment.valid(t)|| (o.moment.mass()-1.).abs()>1e-10||
            (o.moment.birth-o.birth).abs()>1e-10*o.birth.max(1.)||
            !o.cross.is_finite()||!(0. ..1.).contains(&o.cross)||
            !o.distance.is_finite()||o.distance<0.||o.phase>2||
            !o.entry.is_finite()||o.entry<o.birth||o.entry>t{
            return Err(bad("owner mass/birth/phase invariant"))
        }
        if o.phase==2{if o.done.is_none_or(|x|!x.is_finite()||x<o.birth||x>t)||o.cross!=0.{return Err(bad("bad completed owner"))}continue}
        if o.done.is_some(){return Err(bad("active owner marked complete"))}
        if let Some(r)=&o.route{
            if r.graph_id!=g.id||!legal(&r.links,g.installed)||r.position>=r.links.len(){return Err(bad("illegal active commitment"))}
            let i=idx(&r.links[r.position])?;
            if o.phase==0&&(r.position!=0||o.distance!=0.)||
                o.phase==1&&(o.distance>L[i]||o.cross>0.&&o.distance<L[i]){return Err(bad("bad position or premature crossing"))}
        }else if o.phase!=0||o.cross!=0.{return Err(bad("unassigned physical owner"))}
    }
    for (i,x) in stock(owners)?.iter().enumerate(){if !x.is_finite()||*x<0.||*x>storage(i)+1e-8||!g.installed[i]&&*x!=0.{return Err(bad("storage support"))}}
    Ok(())
}
fn physical_step(g:&Graph,owners:&mut Vec<Owner>,p:&mut Physical,t:f64)->CoreResult<()>{
    check(g,owners,t)?;
    let before=stock(owners)?;
    let mut send=[0.;E];let mut recv=[0.;E];let mut metres=[0.;E];
    for i in 0..E{
        if g.installed[i]{
            send[i]=CAP[i];if !no_entry(i,t){recv[i]=CAP[i];metres[i]=(storage(i)-before[i]).max(0.)*5./L[i];}
        }
    }
    let s0=send;let r0=recv;let m0=metres;
    let mut next=owners.clone();let mut staged=p.clone();
    staged.stock_integral+=owners.iter().filter(|o|o.phase!=2).count() as f64;
    let mut ready=vec![];
    for (k,o) in next.iter_mut().enumerate(){
        if o.phase!=1{continue}
        let r=o.route.as_ref().unwrap();let i=idx(&r.links[r.position])?;
        let (m,dx)=react_with_distance(o.moment,Rates{alpha:0.2,nu:0.3*(before[i]/storage(i)).powi(2),tau:2.,target:1.},1.).map_err(CoreError::value)?;
        o.moment=m;o.distance=(o.distance+U*dx).min(L[i]);
        ready.push((i,o.entry,o.id,k));
    }
    ready.sort_by(|a,b|a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)).then(a.2.cmp(&b.2)));
    let mut blocked=[false;E];let mut nready=0;
    for (i,_,_,k) in ready{
        let o=&mut next[k];if o.distance<L[i]{blocked[i]=true;continue}
        nready+=1;
        if blocked[i]{staged.blocked_steps+=1;continue}
        let r=o.route.as_mut().unwrap();let dst=r.links.get(r.position+1).map(|x|idx(x)).transpose()?;
        let z=crate::v1_akm_interface::increment(1.,o.cross,send[i],dst.map_or(f64::INFINITY,|j|recv[j]),dst.map_or(f64::INFINITY,|j|metres[j]),ELL)?;
        send[i]=(send[i]-z.amount).max(0.);
        if let Some(j)=dst{recv[j]=(recv[j]-z.amount).max(0.);metres[j]=(metres[j]-ELL*z.amount).max(0.);}
        staged.boundary_mass+=z.amount;
        if z.done{
            staged.passages.push(Passage{owner:o.id,link:i,entered:o.entry,exited:t+1.});
            o.cross=0.;o.distance=0.;
            if dst.is_some(){r.position+=1;o.entry=t+1.;}
            else{o.phase=2;o.done=Some(t+1.);}
        }else{
            o.cross=z.progress;blocked[i]=true;staged.blocked_steps+=1;
            if z.amount>0.{staged.partial_steps+=1;}
        }
    }
    staged.peak_ready=staged.peak_ready.max(nready);
    // Source queue by stable owner id; no route means explicitly pending.
    for o in next.iter_mut().filter(|o|o.phase==0){
        let Some(r)=&o.route else{continue};let i=idx(&r.links[0])?;
        let z=crate::v1_akm_interface::increment(1.,o.cross,f64::INFINITY,recv[i],metres[i],ELL)?;
        recv[i]=(recv[i]-z.amount).max(0.);metres[i]=(metres[i]-ELL*z.amount).max(0.);
        staged.boundary_mass+=z.amount;
        if z.done{o.phase=1;o.cross=0.;o.entry=t+1.;}
        else{o.cross=z.progress;if z.amount>0.{staged.partial_steps+=1;}break}
    }
    for i in 0..E{
        for (old,new,peak) in [(s0[i],send[i],&mut staged.peak_send),(r0[i],recv[i],&mut staged.peak_receive),(m0[i],metres[i],&mut staged.peak_metre)]{
            if new<0.||new>old+1e-12{return Err(bad("step quota"))}
            if old>0.{*peak=peak.max((old-new)/old);}
        }
    }
    check(g,&next,t+1.)?;
    for (a,b) in owners.iter().zip(&next){
        if a.id!=b.id||a.birth!=b.birth||a.route.as_ref().map(|r|&r.links)!=b.route.as_ref().map(|r|&r.links){return Err(bad("physical owner rewrite"))}
    }
    for (i,x) in stock(&next)?.iter().enumerate(){staged.peak_storage=staged.peak_storage.max(x/storage(i));}
    *owners=next;*p=staged;Ok(())
}
#[cfg(test)]
mod physical_tests{
    use super::*;
    #[test]fn reserved_carrier_finite_travel_and_one_owner(){
        let g=Graph::new().unwrap();let mut o=vec![initial_owner(0,0.)];o[0].route=Some(route(&g,&[0,1,2,6]));
        let mut p=Physical::default();
        for t in 0..200{physical_step(&g,&mut o,&mut p,t as f64).unwrap();}
        assert_eq!(o[0].phase,2);assert_eq!(p.passages.len(),4);
        for x in &p.passages{assert!(x.exited-x.entered>=L[x.link]/U);}
        assert!(p.partial_steps>0);assert!(p.peak_storage<=1.+1e-10);
        assert_eq!(o[0].moment.birth,0.);assert_eq!(o[0].id,0);
    }
    #[test]fn closed_receiver_does_not_delete_committed_owner(){
        let g=Graph::new().unwrap();let mut o=vec![initial_owner(0,0.)];o[0].route=Some(route(&g,&[0,1,2,6]));
        o[0].phase=1;o[0].entry=350.;o[0].distance=L[0];let mut p=Physical::default();
        physical_step(&g,&mut o,&mut p,360.).unwrap();
        assert_eq!(o[0].phase,1);assert_eq!(o[0].cross,0.);assert_eq!(o[0].route.as_ref().unwrap().position,0);
        assert_eq!(p.passages.len(),0);assert_eq!(stock(&o).unwrap()[0],ELL);
    }
}

const MEASURE:&str="availability-conditioned completed link passage";
fn key(i:usize)->Key{Key{kind:"link".into(),id:IDS[i].into(),class:"car".into()}}
fn information()->CoreResult<Information>{
    let priors=(0..E).map(|i|Prior{key:key(i),seconds:L[i]/U+4.,version:"D07-prior-v1".into(),measure:MEASURE.into()}).collect();
    let channels=vec![Channel{id:"server".into(),kind:"server".into(),coverage:(0..E).map(key).collect(),
        radius_m:f64::INFINITY,latency_s:40.,propagation_mps:1e6,max_age_s:80.}];
    Information::new(priors,channels,128)
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
pub struct Config{pub interarrival_s:u32,pub bypass:bool,pub reroute:bool,pub seed:u64}
impl Config{fn valid(&self)->bool{[2,4,8].contains(&self.interarrival_s)&&(!self.reroute||self.bypass)}}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct ObservationEpoch{time:f64,graph_id:String,source:Decision,delivered:DecisionObservation,published:Vec<Report>}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Reroute{time:f64,owner:usize,birth:f64,position:usize,old:Vec<String>,new:Vec<String>,gain_s:Option<f64>,hard:bool,graph_id:String,epoch:String}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct Sample{time_s:f64,released:usize,completed:usize,pending:usize,on_road:usize,stock_m:[f64;E],ready:usize,partial:usize,completed_age_s:f64}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
struct World{
    config:Config,time:u32,graph:Graph,owners:Vec<Owner>,physical:Physical,
    reports:Vec<Report>,cursor:usize,epochs:Vec<ObservationEpoch>,reroutes:Vec<Reroute>,
    graph_events:Vec<GraphEvent>,samples:Vec<Sample>,source:Option<Decision>
}
fn rank(id:usize,seed:u64)->f64{
    let mut x=(id as u64).wrapping_add(seed).wrapping_add(0x9e3779b97f4a7c15);
    x=(x^(x>>30)).wrapping_mul(0xbf58476d1ce4e5b9);x=(x^(x>>27)).wrapping_mul(0x94d049bb133111eb);
    ((x^(x>>31))>>11)as f64/9007199254740992.
}
fn choose(g:&Graph,o:&mut Owner,d:&Decision,seed:u64)->CoreResult<()>{
    if o.route.is_some()||o.phase!=0||o.cross!=0.{return Err(bad("source selection must be uncommitted"))}
    if d.alternatives.is_empty(){return Ok(())}
    let u=rank(o.id,seed);let mut c=0.;let mut selected=d.alternatives.last().unwrap();
    for a in &d.alternatives{c+=a.probability;if u<c{selected=a;break}}
    if selected.commitment.graph_id!=g.id||!legal(&selected.commitment.links,g.installed){return Err(bad("stale or illegal source route"))}
    o.initial_branch=Some(selected.commitment.links[1].clone());o.route=Some(selected.commitment.clone());Ok(())
}
fn try_reroute(g:&Graph,model:&Routing,o:&mut Owner,obs:&DecisionObservation,t:f64)->CoreResult<Option<Reroute>>{
    if o.phase!=1||o.cross!=0.||o.last_reroute.is_some_and(|x|t-x<40.){return Ok(None)}
    let old=o.route.as_ref().unwrap();
    let i=idx(&old.links[old.position])?;
    if o.distance<L[i]||old.position+1==old.links.len(){return Ok(None)}
    let mut obs=obs.clone();obs.decision="en_route".into();
    let (_,d)=model.decide(&model.initial(),&obs,&Boundary{time_s:t,node:HEAD[i].into(),incoming:Some(IDS[i].into())},&pref(),"d",Some(old),&[])?;
    let hard=d.fallback.is_none();let gain=d.regret_s;
    if !hard&&gain.is_none_or(|x|x<=5.){return Ok(None)}
    let Some(best)=d.alternatives.iter().min_by(|a,b|a.generalized_cost_s.total_cmp(&b.generalized_cost_s).then(a.commitment.links.cmp(&b.commitment.links))) else{return Ok(None)};
    let new=&best.commitment;
    if new.links==old.links{return Ok(None)}
    if new.position!=old.position||new.links[..=new.position]!=old.links[..=old.position]||new.graph_id!=g.id||!legal(&new.links,g.installed){return Err(bad("reroute would change occupied prefix"))}
    let rec=Reroute{time:t,owner:o.id,birth:o.birth,position:old.position,old:old.links.clone(),new:new.links.clone(),gain_s:gain,hard,graph_id:g.id.clone(),epoch:d.cost_epoch};
    o.route=Some(new.clone());o.last_reroute=Some(t);Ok(Some(rec))
}
impl World{
    fn new(config:Config)->CoreResult<Self>{
        if !config.valid(){return Err(bad("D07 scenario domain"))}
        Ok(Self{config,time:0,graph:Graph::new()?,owners:vec![],physical:Physical::default(),reports:vec![],cursor:0,epochs:vec![],reroutes:vec![],graph_events:vec![],samples:vec![],source:None})
    }
    fn check(&self)->CoreResult<()>{
        if !self.config.valid()||self.time>1800||self.cursor>self.physical.passages.len()||
            self.graph.id!=route_model(self.graph.installed,self.graph.version)?.graph_id{return Err(bad("D07 checkpoint identity"))}
        check(&self.graph,&self.owners,self.time as f64)?;
        for (i,o) in self.owners.iter().enumerate(){if o.id!=i||o.birth!=i as f64*self.config.interarrival_s as f64||o.birth>=600.{return Err(bad("birth registry changed"))}}
        Ok(())
    }
    fn medium(&mut self,info:&Information)->CoreResult<()>{
        let t=self.time as f64;let model=route_model(self.graph.installed,self.graph.version)?;
        let mut count=[0usize;E];let mut sum=[0.;E];let mut start=[t;E];
        for p in &self.physical.passages[self.cursor..]{
            if p.exited>t||p.exited<p.entered{return Err(bad("future passage"))}
            count[p.link]+=1;sum[p.link]+=p.exited-p.entered;start[p.link]=start[p.link].min(p.entered);
        }
        let mut published=vec![];
        if !(420. ..540.).contains(&t){
            for i in 0..E{
                if !self.graph.installed[i]{continue}
                // A closure report is an availability observation with actual
                // affected ready owner population, NOT a completed passage.
                let affected=if no_entry(i,t){self.owners.iter().filter(|o|o.phase==1&&o.route.as_ref().is_some_and(|r|r.links.get(r.position+1).is_some_and(|x|x==IDS[i])&&o.distance>=L[idx(&r.links[r.position]).unwrap()])).count()}else{0};
                let (seconds,mass,source,from)=if affected>0{(f64::INFINITY,affected,"observed_no_entry",t)}
                    else if count[i]>0{(sum[i]/count[i] as f64,count[i],"completed_link_passage",start[i])}else{continue};
                published.push(Report{channel:"server".into(),observation:Observation{key:key(i),seconds,stamp_s:t,start_s:from,end_s:t,mass_veh:mass as f64,
                    sensor_xy:[0.,0.],source:source.into(),version:self.graph.id.clone(),population:format!("D07:{i}:{}:{mass}",self.time),measure:MEASURE.into()}});
            }
        }
        self.cursor=self.physical.passages.len();
        // Reconstruct retained info state from authoritative reports; no hidden cache state.
        let old=info.advance(&info.initial(),t,&self.reports)?;
        let st=info.advance(&old,t,&published)?;
        self.reports=st.reports().to_vec();
        let mut o=info.observe(&st,[0.,0.],"origin")?;
        o.costs.retain(|c|self.graph.installed[idx(&c.key.id).unwrap()]);
        o.coverage_fraction=o.costs.iter().filter(|c|c.is_delivered()).count()as f64/o.costs.len()as f64;
        let (_,d)=model.decide(&model.initial(),&o,&Boundary{time_s:t,node:"s".into(),incoming:None},&pref(),"d",None,&["approach".into(),"bridge".into(),"upper_exit".into(),"exit".into()])?;
        if self.config.reroute{
            for owner in &mut self.owners{if let Some(r)=try_reroute(&self.graph,&model,owner,&o,t)?{self.reroutes.push(r);}}
        }
        for owner in self.owners.iter_mut().filter(|x|x.route.is_none()){choose(&self.graph,owner,&d,self.config.seed)?;}
        self.source=Some(d.clone());self.epochs.push(ObservationEpoch{time:t,graph_id:self.graph.id.clone(),source:d,delivered:o,published});
        Ok(())
    }
    fn sample(&self)->CoreResult<Sample>{
        let t=self.time as f64;
        Ok(Sample{time_s:t,released:self.owners.len(),completed:self.owners.iter().filter(|o|o.phase==2).count(),
            pending:self.owners.iter().filter(|o|o.phase==0).count(),on_road:self.owners.iter().filter(|o|o.phase==1).count(),
            stock_m:stock(&self.owners)?,ready:self.owners.iter().filter(|o|o.phase==1&&o.route.as_ref().is_some_and(|r|o.distance>=L[idx(&r.links[r.position]).unwrap()])).count(),
            partial:self.owners.iter().filter(|o|o.cross>0.).count(),completed_age_s:self.owners.iter().filter_map(|o|o.done.map(|d|d-o.birth)).sum()})
    }
    fn advance(&mut self,target:u32)->CoreResult<()>{
        self.check()?;
        if target<self.time||target>1800{return Err(bad("D07 horizon"))}
        let info=information()?;
        while self.time<target{
            let t=self.time;
            if self.config.bypass&&t==300{self.graph_events.push(self.graph.edit(&mut self.owners,t as f64,BYPASS,true)?);}
            if self.config.bypass&&t==540&&self.graph.installed[BYPASS]{self.graph_events.push(self.graph.edit(&mut self.owners,t as f64,BYPASS,false)?);}
            if t%20==0{self.medium(&info)?;}
            if t<600&&t%self.config.interarrival_s==0{
                let mut o=initial_owner(self.owners.len(),t as f64);
                choose(&self.graph,&mut o,self.source.as_ref().ok_or_else(||bad("source epoch absent"))?,self.config.seed)?;
                self.owners.push(o);
            }
            physical_step(&self.graph,&mut self.owners,&mut self.physical,t as f64)?;
            self.time+=1;
            if self.time%60==0{self.samples.push(self.sample()?);}
        }
        if target==1800&&self.config.bypass&&self.graph.installed[BYPASS]{
            self.graph_events.push(self.graph.edit(&mut self.owners,1800.,BYPASS,false)?);
        }
        self.check()
    }
}
#[cfg(test)]
mod causal_tests{
    use super::*;
    #[test]fn delivered_report_and_expiry_use_existing_channel(){
        let info=information().unwrap();
        let r=Report{channel:"server".into(),observation:Observation{key:key(1),seconds:f64::INFINITY,stamp_s:360.,start_s:360.,end_s:360.,mass_veh:1.,sensor_xy:[0.,0.],source:"test".into(),version:"test".into(),population:"test".into(),measure:MEASURE.into()}};
        let st=info.advance(&info.initial(),360.,&[r.clone()]).unwrap();
        assert!(!info.observe(&st,[0.,0.],"origin").unwrap().costs[1].is_delivered());
        let st=info.advance(&st,400.,&[]).unwrap();
        assert!(info.observe(&st,[0.,0.],"origin").unwrap().costs[1].seconds.is_infinite());
        let st=info.advance(&st,441.,&[]).unwrap();
        assert!(!info.observe(&st,[0.,0.],"origin").unwrap().costs[1].is_delivered());
        assert!(info.advance(&info.initial(),359.,&[r]).is_err());
    }
    #[test]fn ready_suffix_changes_only_unreserved_boundary(){
        let mut g=Graph::new().unwrap();let mut o=vec![initial_owner(0,0.)];
        g.edit(&mut o,300.,BYPASS,true).unwrap();let mut x=initial_owner(0,0.);
        x.route=Some(route(&g,&[0,1,2,6]));x.phase=1;x.distance=L[0];
        let info=information().unwrap();
        let r=Report{channel:"server".into(),observation:Observation{key:key(1),seconds:f64::INFINITY,stamp_s:360.,start_s:360.,end_s:360.,mass_veh:1.,sensor_xy:[0.,0.],source:"test".into(),version:"test".into(),population:"test".into(),measure:MEASURE.into()}};
        let st=info.advance(&info.initial(),400.,&[r]).unwrap();let obs=info.observe(&st,[0.,0.],"origin").unwrap();
        let model=route_model(g.installed,g.version).unwrap();let before=x.clone();
        let mut partial=x.clone();partial.cross=0.5;assert!(try_reroute(&g,&model,&mut partial,&obs,400.).unwrap().is_none());assert_eq!(partial.route,before.route);
        let rr=try_reroute(&g,&model,&mut x,&obs,400.).unwrap().unwrap();
        assert!(rr.hard);assert_eq!(x.moment,before.moment);assert_eq!(x.id,before.id);assert_eq!(x.distance,before.distance);assert_eq!(x.route.unwrap().links[0],"approach");
    }
    #[test]fn existing_router_k4_and_k8_turn_legality(){
        use crate::v1_routing::V1RoutingGraph;
        let mut arcs=vec![];let mut costs=vec![];let mut turns=vec![];
        for i in 0..9{let a=format!("a{i}");let b=format!("b{i}");let n=format!("n{i}");arcs.push((a.clone(),"s".into(),n.clone()));arcs.push((b.clone(),n,"d".into()));costs.extend([i as f64+1.,1.]);if i!=0{turns.push((a,b));}}
        let mut model=V1RoutingGraph::new(arcs,costs,Some(turns),2).unwrap();
        for k in [4,8]{let (p,_,truncated)=model.search_inner("s","d",k,100).unwrap();assert!(!truncated);assert_eq!(p.len(),k);assert_eq!(p[0],["a1","b1"]);assert!(p.iter().all(|x|x[0]!="a0"));}
    }
}
