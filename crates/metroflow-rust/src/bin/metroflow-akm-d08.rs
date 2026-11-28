use _metroflow_rust::akm_d08::{Config,execute};
use serde_json::json;
use sha2::{Digest,Sha256};
use std::{fs,io::Write,time::Instant,path::Path};
fn sha(b:&[u8])->String{format!("{:x}",Sha256::digest(b))}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();
    if a.len()!=10{return Err("usage: metroflow-akm-d08 BYPASS_0_1 ENDOGENOUS_0_1 SEED EPOCHS THREADS SOURCE_OR_- SOURCE_SHA_OR_- OUT_CHECKPOINT OUT_RECEIPT".into())}
    let flag=|x:&str|match x{"0"=>Ok(false),"1"=>Ok(true),_=>Err("expected 0/1")};
    let config=Config{bypass:flag(&a[1])?,endogenous:flag(&a[2])?,seed:a[3].parse()?};
    let target:usize=a[4].parse()?;let threads:usize=a[5].parse()?;
    if !(1..=8).contains(&threads){return Err("workers outside bounded domain".into())}
    if Path::new(&a[8]).exists()||Path::new(&a[9]).exists()||a[8]==a[9]{return Err("output exists or aliases".into())}
    let source=if a[6]=="-"{if a[7]!="-"{return Err("source hash must be -".into())}None}else{
        if fs::metadata(&a[6])?.len()>16*1024*1024{return Err("D08 input byte bound".into())}
        let b=fs::read(&a[6])?;if sha(&b)!=a[7]{return Err("source digest mismatch".into())}Some(b)
    };
    let t=Instant::now();let pool=rayon::ThreadPoolBuilder::new().num_threads(threads).build()?;
    let (bytes,mut r)=pool.install(||execute(config,target,source.as_deref()))?;
    r["checkpoint_sha256"]=json!(sha(&bytes));r["source_sha256"]=json!(source.as_ref().map(|x|sha(x)));
    r["executable_sha256"]=json!(sha(&fs::read(std::env::current_exe()?)?));
    r["wall_s"]=json!(t.elapsed().as_secs_f64());r["threads"]=json!(threads);
    let status=fs::read_to_string("/proc/self/status").unwrap_or_default();
    r["peak_rss_kib"]=json!(status.lines().find(|x|x.starts_with("VmHWM:")).and_then(|x|x.split_whitespace().nth(1)).and_then(|x|x.parse::<u64>().ok()));
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(&a[8])?;f.write_all(&bytes)?;f.sync_all()?;
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(&a[9])?;serde_json::to_writer_pretty(&mut f,&r)?;f.sync_all()?;
    for e in r["epochs"].as_array().unwrap(){println!("{}",json!({"index":e["index"],"activity":e["activity"],"mean":e["traffic"]["mean_s"],"growth_after":e["growth_after"]}));}
    Ok(())
}
