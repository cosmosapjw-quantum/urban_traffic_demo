use std::{fs,io::Write,time::Instant};
use sha2::{Digest,Sha256};
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();
    if a.len()!=4{return Err("usage: metroflow-akm-support MANIFEST THREADS RECEIPT".into())}
    let start=Instant::now();let bytes=fs::read(&a[1])?;
    let mut r=_metroflow_rust::akm_support_audit(serde_json::from_slice(&bytes)?,a[2].parse()?)?;
    r["manifest_sha256"]=serde_json::json!(format!("{:x}",Sha256::digest(&bytes)));
    r["executable_sha256"]=serde_json::json!(format!("{:x}",Sha256::digest(fs::read(std::env::current_exe()?)?)));
    r["wall_s"]=serde_json::json!(start.elapsed().as_secs_f64());
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(&a[3])?;
    serde_json::to_writer_pretty(&mut f,&r)?;f.flush()?;f.sync_all()?;
    println!("{}",r);Ok(())
}
