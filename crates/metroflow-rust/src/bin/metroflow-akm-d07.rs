use _metroflow_rust::akm_d07::{Config,execute};
use serde_json::json;
use sha2::{Digest,Sha256};
use std::{fs,io::Write,time::Instant,path::Path};
fn sha(b:&[u8])->String{format!("{:x}",Sha256::digest(b))}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();
    if a.len()!=12{return Err("usage: metroflow-akm-d07 INTERARRIVAL BYPASS_0_1 REROUTE_0_1 SEED TARGET_S THREADS SOURCE_OR_- SOURCE_SHA_OR_- OUT_CHECKPOINT OUT_RECEIPT D07".into())}
    // executable + ten arguments = 11; explicit final label binds invocation.
    if a[11]!="D07"{return Err("missing research label D07".into())}
    let flag=|x:&str|match x{"0"=>Ok(false),"1"=>Ok(true),_=>Err("expected 0/1")};
    let config=Config{interarrival_s:a[1].parse()?,bypass:flag(&a[2])?,reroute:flag(&a[3])?,seed:a[4].parse()?};
    let target:u32=a[5].parse()?;let threads:usize=a[6].parse()?;if !(1..=8).contains(&threads){return Err("workers outside bounded domain".into())}
    if Path::new(&a[9]).exists()||Path::new(&a[10]).exists(){return Err("output exists".into())}
    let source=if a[7]=="-"{if a[8]!="-"{return Err("source hash must be -".into())}None}else{
        let b=fs::read(&a[7])?;if sha(&b)!=a[8]{return Err("source digest mismatch".into())}Some(b)
    };
    let t=Instant::now();let pool=rayon::ThreadPoolBuilder::new().num_threads(threads).build()?;
    let (bytes,mut r)=pool.install(||execute(config,target,source.as_deref()))?;
    r["checkpoint_sha256"]=json!(sha(&bytes));r["source_sha256"]=json!(source.as_ref().map(|x|sha(x)));
    r["executable_sha256"]=json!(sha(&fs::read(std::env::current_exe()?)?));
    r["wall_s"]=json!(t.elapsed().as_secs_f64());r["threads"]=json!(threads);
    let status=fs::read_to_string("/proc/self/status").unwrap_or_default();
    r["peak_rss_kib"]=json!(status.lines().find(|x|x.starts_with("VmHWM:")).and_then(|x|x.split_whitespace().nth(1)).and_then(|x|x.parse::<u64>().ok()));
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(&a[9])?;f.write_all(&bytes)?;f.sync_all()?;
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(&a[10])?;serde_json::to_writer_pretty(&mut f,&r)?;f.sync_all()?;
    println!("{}",json!({"time":target,"last":r["last_sample"],"mean":r["mean_completed_s"],"reroutes":r["reroutes"].as_array().unwrap().len(),"graph":r["graph_events"],"wall_s":r["wall_s"]}));Ok(())
}
