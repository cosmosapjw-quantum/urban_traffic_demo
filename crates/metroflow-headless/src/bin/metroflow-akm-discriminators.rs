use metroflow_headless::{active_kinetic::{Moment,split_velocity_selected},active_network::{Class,Link,Route,Declaration,Model},receipt};
use serde_json::{json,Value};
use std::{fs::OpenOptions,time::Instant};
fn cls(footprint:f64,beta:f64)->Class{Class{speed_ref:10.,footprint,alpha:0.2,nu0:0.,beta,tau:2.}}
fn link(length:f64,storage:f64)->Link{Link{length,speed_limit:10.,entry:1000.,exit:1000.,storage,wave_speed:10.}}
fn pulse(k:usize,a:f64,beta:f64,mass:f64,storage:f64)->Result<Value,String>{
    let dt=10.*a/k as f64;
    let m=Model::new(Declaration{dt,links:vec![link(100./k as f64,storage);k],classes:vec![cls(5.,beta)],routes:vec![Route{class:0,links:(0..k).collect()}]})?;
    let mut s=m.initial();let mut w=m.workspace();s.road[0]=Moment::point(mass,1.,1.,0.);s.released[0]=mass;
    let gate=vec![1.;k];let(mut mean,mut second,mut half,mut before_ballistic,mut prev,mut peak)=(0.,0.,0.,0.,0.,0f64);
    let mut maxerr=0f64;
    // Discrete time, no admission offset; retain tail (no pruning).
    let mut n=0;
    while n<4096 && s.completed[0]<mass*(1.-1e-12){
        let z=m.step(&mut s,&mut w,&[0.],&gate)?;n+=1;peak=peak.max(z.max_storage_ratio);maxerr=maxerr.max(z.max_mass_residual);
        let delta=s.completed[0]-prev;mean+=delta*s.time/mass;second+=delta*s.time*s.time/mass;prev=s.completed[0];
        if s.time<=5.+1e-10{half=prev/mass}
        if s.time<10.-1e-10{before_ballistic=prev/mass}
    }
    let tail=1.-prev/mass;
    if tail>1e-10{return Err("pulse tail not resolved in declared domain".into())}
    let var=second-mean*mean;
    if beta==0.{
        let exp=100.*(1.-a)/k as f64;
        if (mean-10.).abs()>1e-7||(var-exp).abs()>1e-5{return Err(format!("analytic pulse mismatch k={k} a={a} mean={mean} var={var}"))}
    }
    Ok(json!({"cells":k,"cfl":a,"dt_s":dt,"mass_veh":mass,"beta_s_inv":beta,"mean_s":mean,"variance_s2":var,"early_fraction_at_5s":half,"fraction_strictly_before_ballistic":before_ballistic,"tail_fraction":tail,"steps":n,"max_mass_error":maxerr,"max_storage_ratio":peak,"scope":"preloaded pulse, actual A transport, no pending source"}))
}
fn diverge()->Result<Value,String>{
    let model=Model::new(Declaration{dt:10.,links:vec![link(100.,100.),link(100.,5.),link(100.,100.)],classes:vec![cls(5.,0.)],routes:vec![Route{class:0,links:vec![0,1]},Route{class:0,links:vec![0,2]}]})?;
    let mut s=model.initial();let mut w=model.workspace();
    s.road[0]=Moment::point(1.,1.,1.,0.);s.road[1]=Moment::point(1.,1.,1.,0.);s.road[2]=Moment::point(1.,1.,1.,0.);
    s.released=[2.,1.].to_vec();
    let x=model.step(&mut s,&mut w,&[0.,0.],&[1.,0.,1.])?;
    assert_eq!(x.transferred,0.);assert_eq!(s.road[3].mass(),0.);
    // Independent ordered FIFO oracle: stop at first head whose destination
    // has no supply. One unit cap, equal mass heads and readiness.
    let fifo=|order:[usize;2]|{let mut r=[0.,1.];let mut out=0.;for j in order{if r[j]<1.{break}r[j]-=1.;out+=1.;}out};
    assert_eq!(fifo([0,1]),0.);assert_eq!(fifo([1,0]),1.);
    Ok(json!({"mixed_A_open_branch":s.road[3].mass(),"strict_AB_open_branch":fifo([0,1]),"strict_BA_open_branch":fifo([1,0]),"same_aggregate_initial":true,"blocked_branch_pre_step_full":true,"scope":"order ambiguity under strict FIFO; separate lanes could permit different physics"}))
}
fn merge()->Result<Value,String>{
    let m=Model::new(Declaration{dt:10.,links:vec![link(100.,100.),link(100.,100.),link(100.,15.)],classes:vec![cls(5.,0.),cls(10.,0.)],routes:vec![Route{class:0,links:vec![0,2]},Route{class:1,links:vec![1,2]}]})?;
    let mut s=m.initial();let mut w=m.workspace();
    s.road[0]=Moment::point(3.,1.,1.,0.);s.road[2]=Moment::point(3.,1.,1.,0.);s.released=[3.,3.].to_vec();
    let x=m.step(&mut s,&mut w,&[0.,0.],&[1.,1.,1.])?;
    assert!((x.transferred-2.).abs()<1e-12);assert!((s.road[1].mass()-1.).abs()<1e-12);assert!((s.road[3].mass()-1.).abs()<1e-12);
    Ok(json!({"car_in_veh":s.road[1].mass(),"bus_in_veh":s.road[3].mass(),"used_m":5.*s.road[1].mass()+10.*s.road[3].mass(),"receiver_storage_m":15.,"max_storage_ratio":x.max_storage_ratio}))
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();if a.len()!=2{return Err("usage: metroflow-akm-discriminators OUTPUT_JSON".into())}
    let t=Instant::now();let mut pulses=vec![];
    for k in [1,2,4,8]{for c in [1.,0.5,0.25,0.125]{pulses.push(pulse(k,c,0.,1.,1e6)?);}}
    let active=pulse(1,0.25,0.6,10.,50.)?;let off=pulse(1,0.25,0.,10.,50.)?;
    assert!(active["mean_s"].as_f64().unwrap()>off["mean_s"].as_f64().unwrap());
    let x=Moment::point(0.5,1.,0.,0.).add(Moment::point(0.5,1.,1.,0.));
    let (remain,out)=split_velocity_selected(x,1.,0.)?;
    let response=json!({"schema":"akm_d04_discriminators_v1","status":"EXECUTED_FOR_REVIEW","scope":"actual A kernel low-density ballistic limit, spatial/temporal dispersion, active pulse, blocked turn and multi-class merge; not network equivalence","pulses":pulses,"active_pulse":active,"inactive_pulse":off,"diverge":diverge()?,"merge":merge()?,"selective":{"out_mass":out.mass(),"out_momentum":out.momentum(),"mixed_momentum":x.scaled(0.5).momentum(),"remaining_momentum":remain.momentum()},"wall_s":t.elapsed().as_secs_f64(),"rss_bytes":receipt::peak_rss_bytes(),"executable_sha256":receipt::sha256(&std::env::current_exe()?)?});
    serde_json::to_writer_pretty(OpenOptions::new().create_new(true).write(true).open(&a[1])?,&response)?;println!("{}",serde_json::to_string(&response)?);Ok(())
}
