use std::{fs,io::{Read,Write},path::Path};
use sha2::{Digest,Sha256};
use serde_json::json;
fn hash(path:&str)->Result<String,Box<dyn std::error::Error>>{
    let mut f=fs::File::open(path)?;let mut h=Sha256::new();let mut b=[0u8;65536];
    loop{let n=f.read(&mut b)?;if n==0{break}h.update(&b[..n]);}Ok(format!("{:x}",h.finalize()))
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();
    if a.len()!=9{return Err("usage: metroflow-akm-native MODE MANIFEST SOURCE_OR_- SOURCE_SHA_OR_- END_S THREADS OUT_CHECKPOINT OUT_RECEIPT".into())}
    let mode=&a[1];let manifest=&a[2];let source=&a[3];let expected=&a[4];let out=&a[7];let receipt=&a[8];
    if Path::new(out).exists()||Path::new(receipt).exists(){return Err("output exists".into())}
    let source_sha=if mode=="fresh"{if source!="-"||expected!="-"{return Err("fresh source must be -".into())}None}else{
        let got=hash(source)?;if &got!=expected{return Err("source checkpoint SHA mismatch".into())}Some(got)
    };
    let raw=fs::read(manifest)?;let manifest_sha=format!("{:x}",Sha256::digest(&raw));
    let mut r=_metroflow_rust::run_akm_native(serde_json::from_slice(&raw)?,&manifest_sha,mode,source,a[5].parse()?,a[6].parse()?,out)?;
    r["source_checkpoint_sha256"]=json!(source_sha);r["checkpoint_sha256"]=json!(hash(out)?);
    r["checkpoint_bytes"]=json!(fs::metadata(out)?.len());
    r["executable_sha256"]=json!(hash(std::env::current_exe()?.to_str().ok_or("exe path")?)?);
    let status=fs::read_to_string("/proc/self/status").unwrap_or_default();
    r["peak_rss_kib"]=json!(status.lines().find(|x|x.starts_with("VmHWM:")).and_then(|l|l.split_whitespace().nth(1)).and_then(|s|s.parse::<u64>().ok()));
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(receipt)?;
    serde_json::to_writer_pretty(&mut f,&r)?;f.write_all(b"\n")?;f.sync_all()?;
    println!("{}",serde_json::to_string(&r)?);
    if r["failure"]!=serde_json::Value::Null{std::process::exit(2)}Ok(())
}
