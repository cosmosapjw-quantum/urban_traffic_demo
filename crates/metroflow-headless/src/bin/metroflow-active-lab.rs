use metroflow_headless::{active_network::{self,Model,State,Workspace},receipt};
use serde::{Serialize,Deserialize};
use serde_json::json;
use sha2::{Digest,Sha256};
use std::{alloc::{GlobalAlloc,Layout,System},sync::atomic::{AtomicU64,Ordering},path::{Path,PathBuf},time::Instant,io::Write};
struct Counter;
static ALLOC:AtomicU64=AtomicU64::new(0);static REALLOC:AtomicU64=AtomicU64::new(0);
unsafe impl GlobalAlloc for Counter{
    unsafe fn alloc(&self,l:Layout)->*mut u8{ALLOC.fetch_add(1,Ordering::Relaxed);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{ALLOC.fetch_add(1,Ordering::Relaxed);unsafe{System.alloc_zeroed(l)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{REALLOC.fetch_add(1,Ordering::Relaxed);unsafe{System.realloc(p,l,n)}}
}
#[global_allocator]static G:Counter=Counter;
#[derive(Clone,Copy,Debug,Serialize,Deserialize,PartialEq)]
struct Scenario{dt:f64,horizon:f64,beta:f64,incident:bool,weekday:bool,amplitude:f64,day_profile:bool}
#[derive(Clone,Copy,Debug,PartialEq)]
struct Policy{share:[f64;2],seen:[f64;4],seen_feasible:[bool;2],applied_feasible:[bool;2],ready:bool}
impl Default for Policy{fn default()->Self{Self{share:[0.5;2],seen:[0.;4],seen_feasible:[true;2],applied_feasible:[true;2],ready:false}}}
#[derive(Clone,Copy,Debug,Default,Serialize)]
struct Metrics{max_storage:f64,max_mass_error:f64,max_birth_error:f64,max_pending:f64,stock_veh_s:f64,served_upper:f64,served_lower:f64,max_share_jump:f64,updates:u64}
#[derive(Serialize)]
struct Output{scenario:Scenario,status:String,time_s:f64,slots:usize,checkpoint_sha256:String,released:f64,completed:f64,active:f64,pending:f64,completed_age_veh_s:f64,completed_conditional_mean_s:Option<f64>,metrics:Metrics,wall_s:f64,allocation_calls:u64,reallocation_calls:u64}
fn hash(b:&[u8])->String{format!("{:x}",Sha256::digest(b))}
fn scenario_id(q:Scenario)->String{hash(&serde_json::to_vec(&q).unwrap())}
fn gates(q:Scenario,t:f64)->[f64;4]{
    let closed=q.incident&&if q.day_profile{(27000. ..28800.).contains(&t)}else{(120. ..300.).contains(&t)};
    [1.,if closed{0.}else{1.},1.,1.]
}
fn rates(q:Scenario,t:f64)->[f64;2]{
    let (car,other)=if q.day_profile{
        if (25200. ..32400.).contains(&t)||(57600. ..64800.).contains(&t){
            if q.weekday{(0.70,0.08)}else{(0.31,0.06)}
        }else{(0.012,0.004)}
    }else if t<360.{(0.9,0.1)}else{(0.012,0.004)};
    [car*q.amplitude,other*q.amplitude]
}
fn advance(m:&Model,s:&mut State,w:&mut Workspace,p:&mut Policy,q:Scenario,target:f64,metrics:&mut Metrics)->Result<(),String>{
    let mut occ=[0.;4];let mut costs=[0.;4];
    while s.time<target{
        let t=s.time;let gate=gates(q,t);let mut pn=*p;let mut next_metrics=*metrics;
        // At medium boundary first consume previous report, then publish current
        // observation. No same-tick information feed-through.
        if t%60.==0.{
            if pn.ready{
                for c in 0..2{
                    let before=pn.share[c];
                    if pn.seen_feasible[0]&&pn.seen_feasible[1]{
                        pn.share[c]=active_network::relaxed_pair(before,[pn.seen[2*c],pn.seen[2*c+1]],10.,60.,60.)?;
                    }
                    next_metrics.max_share_jump=next_metrics.max_share_jump.max((before-pn.share[c]).abs());
                }
                pn.applied_feasible=pn.seen_feasible;next_metrics.updates+=1;
            }
            // Source offers use the previous report's feasibility, not newly
            // computed feasibility. Store the new report after forming shares.
        }
        let available=pn.applied_feasible;let r=rates(q,t);
        let mut offer=[0.;4];
        for c in 0..2{
            let f=match available{[true,true]=>pn.share[c],[true,false]=>1.,[false,true]=>0.,_=>return Err("fixture both source paths closed; no unassigned ledger defined".into())};
            offer[2*c]=q.dt*r[c]*f;offer[2*c+1]=q.dt*r[c]*(1.-f);
        }
        if t%60.==0.{m.route_costs(s,&mut occ,&mut costs)?;pn.seen=costs;pn.seen_feasible=[gate[1]>0.,gate[2]>0.];pn.ready=true;}
        let x=m.step(s,w,&offer,&gate)?;*p=pn;*metrics=next_metrics;
        metrics.max_storage=metrics.max_storage.max(x.max_storage_ratio);metrics.max_mass_error=metrics.max_mass_error.max(x.max_mass_residual);metrics.max_birth_error=metrics.max_birth_error.max(x.max_birth_residual);
        let pending=s.pending.iter().map(|v|v.mass()).sum::<f64>();
        metrics.max_pending=metrics.max_pending.max(pending);metrics.stock_veh_s+=q.dt*(pending+s.road.iter().map(|v|v.mass()).sum::<f64>());
        metrics.served_upper=s.completed[0]+s.completed[2];metrics.served_lower=s.completed[1]+s.completed[3];
    }
    Ok(())
}
fn encode(m:&Model,s:&State,p:Policy,q:Scenario)->Result<Vec<u8>,String>{
    let mut b=m.encode(s)?;b.extend(b"AKMPOL2");b.extend(scenario_id(q).as_bytes());
    for x in p.share.into_iter().chain(p.seen){b.extend(x.to_bits().to_le_bytes());}
    b.extend([u8::from(p.seen_feasible[0]),u8::from(p.seen_feasible[1]),u8::from(p.applied_feasible[0]),u8::from(p.applied_feasible[1]),u8::from(p.ready)]);Ok(b)
}
fn decode(m:&Model,b:&[u8],q:Scenario)->Result<(State,Policy),String>{
    let n=7+64+48+5;if b.len()<n{return Err("truncated policy checkpoint".into())}
    let p=&b[b.len()-n..];if &p[..7]!=b"AKMPOL2"||&p[7..71]!=scenario_id(q).as_bytes(){return Err("policy scenario identity".into())}
    let mut x=p[71..119].chunks_exact(8).map(|b|f64::from_bits(u64::from_le_bytes(b.try_into().unwrap())));
    let share=[x.next().unwrap(),x.next().unwrap()];let seen=std::array::from_fn(|_|x.next().unwrap());
    if share.iter().any(|x|!x.is_finite()||!(0. ..=1.).contains(x))||seen.iter().any(|x|!x.is_finite()||*x<0.)||p[119..].iter().any(|&x|x>1){return Err("invalid policy state".into())}
    Ok((m.decode(&b[..b.len()-n])?,Policy{share,seen,seen_feasible:[p[119]!=0,p[120]!=0],applied_feasible:[p[121]!=0,p[122]!=0],ready:p[123]!=0}))
}
fn write_new(path:&Path,b:&[u8])->std::io::Result<()>{let mut f=std::fs::OpenOptions::new().create_new(true).write(true).open(path)?;f.write_all(b)?;f.sync_all()}
fn run(q:Scenario,dir:&Path,idx:usize,replay:bool)->Result<Output,Box<dyn std::error::Error>>{
    let m=active_network::diamond(q.dt,q.beta)?;let mut s=m.initial();let mut w=m.workspace();let mut p=Policy::default();let mut metrics=Metrics::default();
    let t=Instant::now();let a=ALLOC.load(Ordering::Relaxed);let r=REALLOC.load(Ordering::Relaxed);
    let result=advance(&m,&mut s,&mut w,&mut p,q,q.horizon,&mut metrics);
    let allocations=ALLOC.load(Ordering::Relaxed)-a;let reallocations=REALLOC.load(Ordering::Relaxed)-r;
    let wall=t.elapsed().as_secs_f64();
    let status=match result{Ok(())=>"HORIZON_REACHED".into(),Err(e)=>format!("BLOCKED_NUMERICAL:{e}")};
    if status=="HORIZON_REACHED"{assert_eq!((allocations,reallocations),(0,0));}
    let checkpoint=encode(&m,&s,p,q)?;
    let digest=hash(&checkpoint);
    if replay&&status=="HORIZON_REACHED"{
        let mut t=m.initial();let mut w=m.workspace();let mut p=Policy::default();let mut mtr=Metrics::default();let cut=q.horizon/2.;
        advance(&m,&mut t,&mut w,&mut p,q,cut,&mut mtr)?;
        let path=dir.join(format!("lab-{idx}-mid.bin"));let bytes=encode(&m,&t,p,q)?;write_new(&path,&bytes)?;
        let (mut t,mut p)=decode(&m,&std::fs::read(&path)?,q)?;
        advance(&m,&mut t,&mut w,&mut p,q,q.horizon,&mut mtr)?;
        assert_eq!(checkpoint,encode(&m,&t,p,q)?);
        write_new(&dir.join(format!("lab-{idx}-final.bin")),&checkpoint)?;
    }
    let (released,completed,age)=(s.released.iter().sum(),s.completed.iter().sum::<f64>(),s.completed_age.iter().sum::<f64>());
    let active=s.road.iter().map(|v|v.mass()).sum();let pending=s.pending.iter().map(|v|v.mass()).sum();
    Ok(Output{scenario:q,status,time_s:s.time,slots:m.slot_count(),checkpoint_sha256:digest,released,completed,active,pending,completed_age_veh_s:age,completed_conditional_mean_s:if completed>0.{Some(age/completed)}else{None},metrics,wall_s:wall,allocation_calls:allocations,reallocation_calls:reallocations})
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();if a.len()!=2{return Err("usage: metroflow-active-lab EMPTY_OUTPUT_DIR".into())}
    let dir=PathBuf::from(&a[1]);std::fs::create_dir(&dir)?;
    let base=Scenario{dt:5.,horizon:1200.,beta:0.6,incident:true,weekday:true,amplitude:1.,day_profile:false};
    let mut cases=vec![base,Scenario{dt:2.5,..base},Scenario{dt:1.25,..base},Scenario{incident:false,..base},Scenario{beta:0.,..base},
        Scenario{horizon:3600.,..base},Scenario{horizon:86400.,day_profile:true,..base},Scenario{horizon:86400.,day_profile:true,incident:false,..base},Scenario{horizon:86400.,day_profile:true,weekday:false,..base},Scenario{amplitude:10.,..base},Scenario{amplitude:100.,..base}];
    // Add an active-day finer comparison, not a full V03 refinement claim.
    cases.push(Scenario{dt:2.5,horizon:86400.,day_profile:true,..base});
    let mut results=vec![];
    for (i,q) in cases.into_iter().enumerate(){let x=run(q,&dir,i,i==1||i==6)?;println!("case {i}: {} t={} completed={}",x.status,x.time_s,x.completed);results.push(x);}
    let out=json!({"schema":"akm_a_lab_v1","scope":"synthetic multiclass fixed-route-position mixing model; source-only delayed preference and capacity intervention; not V03","executable_sha256":receipt::sha256(&std::env::current_exe()?)?,"peak_rss_bytes":receipt::peak_rss_bytes(),"replayed_case_indices":[1,6],"results":results});
    write_new(&dir.join("RESULTS.json"),&serde_json::to_vec_pretty(&out)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn delayed_closure_does_not_change_new_route_choice_before_delivery(){
        let q=Scenario{dt:5.,horizon:1200.,beta:0.6,incident:true,weekday:true,amplitude:1.,day_profile:false};
        let m=active_network::diamond(q.dt,q.beta).unwrap();let mut s=m.initial();let mut w=m.workspace();let mut p=Policy::default();let mut z=Metrics::default();
        advance(&m,&mut s,&mut w,&mut p,q,125.,&mut z).unwrap();
        assert_eq!(p.seen_feasible,[false,true]);assert_eq!(p.applied_feasible,[true,true]);
        advance(&m,&mut s,&mut w,&mut p,q,180.,&mut z).unwrap();
        let b=s.released[0];advance(&m,&mut s,&mut w,&mut p,q,185.,&mut z).unwrap();
        assert_eq!(p.applied_feasible,[false,true]);assert_eq!(s.released[0],b);
        let bytes=encode(&m,&s,p,q).unwrap();let (restored,policy)=decode(&m,&bytes,q).unwrap();assert_eq!(s,restored);assert_eq!(p,policy);
        assert!(decode(&m,&bytes,Scenario{incident:false,..q}).is_err());
    }
}
