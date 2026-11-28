//! Independent microscopic PDMP sample: event-time generation and exact
//! deterministic drift; no use of the mesoscopic flux algorithm.
use metroflow_headless::{active_kinetic::{self,Moment,Mobility,Rates},receipt};
use serde_json::json;
use std::{fs::OpenOptions,time::Instant};
fn uniform(x:&mut u64)->f64{
    *x=x.wrapping_add(0x9e3779b97f4a7c15);
    let mut z=*x;z=(z^(z>>30)).wrapping_mul(0xbf58476d1ce4e5b9);
    z=(z^(z>>27)).wrapping_mul(0x94d049bb133111eb);z^=z>>31;
    ((z>>12)as f64+0.5)/4503599627370496.
}
fn sample(n:usize,seed:u64,r:Rates,end:f64)->[f64;3]{
    let mut rng=seed;let mut sums=[0.;3];
    for _ in 0..n{
        let mut t=0.;let mut u=0.1;let mut s=uniform(&mut rng)<0.8;
        while t<end{
            let lambda=if s{r.nu}else{r.alpha};
            let wait=if lambda>0.{-uniform(&mut rng).ln()/lambda}else{f64::INFINITY};
            let h=wait.min(end-t);let target=if s{r.target}else{0.};
            u=target+(u-target)*(-h/r.tau).exp();
            t+=h;if t>=end{break}s=!s;
        }
        sums[0]+=u8::from(s)as f64;sums[1]+=u;sums[2]+=u*u;
    }
    sums.map(|x|x/n as f64)
}
fn projected(r:Rates,t:f64,h:f64)->Result<[f64;3],String>{
    let mut x=Moment::point(1.,0.8,0.1,0.);
    let n=(t/h).round()as usize;
    for _ in 0..n{x=active_kinetic::react(x,r,h)?;}
    Ok([x.m[1],x.momentum(),x.z[0]+x.z[1]])
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();if a.len()!=2{return Err("usage: metroflow-active-micro OUT_JSON".into())}
    let n=100000usize;let seed=20261128u64;let r=Rates{alpha:0.2,nu:0.3,tau:2.,target:1.};
    let start=Instant::now();
    let p=r.alpha/(r.alpha+r.nu);let variance=p*(1.-p)/(1.+(r.alpha+r.nu)*r.tau);
    // Union over 2 times * 3 bounded observables: probability <=0.01 under IID model.
    let eps=(f64::ln(12./0.01)/(2.*n as f64)).sqrt();
    let mut rows=vec![];
    for (i,t) in [10.,200.].into_iter().enumerate(){
        let mc=sample(n,seed+i as u64,r,t);let a=projected(r,t,0.01)?;let b=projected(r,t,0.005)?;
        let means=Mobility{p:0.8,u:0.1}.advance(r,t)?;
        assert!((b[0]-means.p).abs()<1e-10&&(b[1]-means.u).abs()<2e-6);
        let diff=(0..3).map(|j|(a[j]-b[j]).abs()).fold(0.,f64::max);
        assert!(diff<2e-5);
        assert!((0..3).all(|j|(mc[j]-b[j]).abs()<=eps+2e-5));
        if t==200.{assert!((b[1]-p).abs()<1e-10&&(b[2]-p*p-variance).abs()<2e-6);}
        rows.push(json!({"time_s":t,"micro_means_sigma_u_u2":mc,"meso_dt_0_01":a,"meso_dt_0_005":b,"mean_exact":[means.p,means.u],"refinement_max_diff":diff,"sample_variance":mc[2]-mc[1]*mc[1],"within_joint_hoeffding_plus_numerical_tolerance":true}));
    }
    let out=json!({"schema":"akm_micro_pdmp_v1","scope":"frozen homogeneous independent driver PDMP; synthetic parameters, not real calibration","seed":seed,"samples_per_time":n,"rates":r,"stationary_mean":p,"stationary_variance":variance,"joint_hoeffding_epsilon":eps,"family_failure_bound_under_iid":0.01,"results":rows,"wall_s":start.elapsed().as_secs_f64(),"executable_sha256":receipt::sha256(&std::env::current_exe()?)?});
    serde_json::to_writer_pretty(OpenOptions::new().write(true).create_new(true).open(&a[1])?,&out)?;
    println!("{}",serde_json::to_string_pretty(&out)?);Ok(())
}
