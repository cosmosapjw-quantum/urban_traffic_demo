use metroflow_headless::{input::Input,queue::{self,Config,ActivePolicy},receipt};
use serde_json::json;
use std::{path::Path,time::Instant,fs::OpenOptions};
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<String>=std::env::args().collect();
    if a.len()!=12{return Err("usage: metroflow-active-city NETWORK PASSAGES MESH HORIZON SEED THREADS OUT_JSON ALPHA BETA TAU COMMA_SEPARATED_OBSERVATION_TIMES".into())}
    let t=Instant::now();
    let(n,p)=(Path::new(&a[1]),Path::new(&a[2]));
    let (nh,ph)=(receipt::sha256(n)?,receipt::sha256(p)?);
    let input=Input::load(n,p)?;
    let cfg=Config{mesh_s:a[3].parse()?,horizon_s:a[4].parse()?,seed:a[5].parse()?,shock_link:None,shock_factor:1.};
    let threads:usize=a[6].parse()?;if !(1..=64).contains(&threads){return Err("invalid workers".into())}
    let policy=ActivePolicy{alpha:a[8].parse()?,beta:a[9].parse()?,tau:a[10].parse()?};
    let times:Vec<f64>=a[11].split(',').map(str::parse).collect::<Result<_,_>>()?;
    let pool=rayon::ThreadPoolBuilder::new().num_threads(threads).build()?;
    let prep_s=t.elapsed().as_secs_f64();let s=Instant::now();
    let run=pool.install(||queue::run_active_observed(&input,cfg,policy,&times))?;
    let run_s=s.elapsed().as_secs_f64();
    if nh!=receipt::sha256(n)?||ph!=receipt::sha256(p)?{return Err("input changed".into())}
    let o=json!({"schema":"akm_b_active_city_observed_v1","observation_times_s":times,"scope":"archived projected city fixed-route common-rank access and whole-batch queue; mean-field frozen passage time dilation, not original V03 acceptance","config":cfg,"policy":policy,"threads":threads,"roads":input.roads.len(),"paths":input.paths.len(),"groups":input.groups.len(),"network_sha256":nh,"passages_sha256":ph,"executable_sha256":receipt::sha256(&std::env::current_exe()?)?,"prep_s":prep_s,"run_s":run_s,"wall_s":t.elapsed().as_secs_f64(),"peak_rss_bytes":receipt::peak_rss_bytes(),"result":run});
    serde_json::to_writer_pretty(OpenOptions::new().write(true).create_new(true).open(&a[7])?,&o)?;
    println!("{}",serde_json::to_string(&o)?);Ok(())
}
