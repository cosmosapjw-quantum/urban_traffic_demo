//! Restore the old native atlas -> prepared demand -> calendar path as one
//! Rust entry point, rather than rebuilding any of it in the Python frontend.
use _metroflow_rust::{atlas_generate,frozen_city::Matrix,v1_prepare_city};
use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::{fs,io::Write,path::Path,time::Instant};
fn sha(b:&[u8])->String{format!("{:x}",Sha256::digest(b))}
fn write(p:&Path,v:&Value)->Result<String,Box<dyn std::error::Error>>{
    let bytes=serde_json::to_vec(v)?;
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(p)?;
    f.write_all(&bytes)?;f.sync_all()?;Ok(sha(&bytes))
}
fn main()->Result<(),Box<dyn std::error::Error>>{
    let a:Vec<_>=std::env::args().collect();
    if !matches!(a.get(1).map(String::as_str),Some("generate"|"prepare")){
        return Err("usage: metroflow-native-city generate MATRIX CASE THREADS STEP OUT_DIR STYLE TERRAIN SIZE RESOLUTION | prepare MATRIX CASE THREADS STEP OUT_DIR CITY_JSON".into())
    }
    let fresh=a[1]=="generate";
    if (fresh&&a.len()!=11)||(!fresh&&a.len()!=8){return Err("invalid native city arguments".into())}
    let (matrix,matrix_sha)=Matrix::load(Path::new(&a[2]))?;
    let case=matrix.cases.iter().find(|c|c.id==a[3]).ok_or("unknown matrix case")?;
    let threads:usize=a[4].parse()?;if !(1..=8).contains(&threads){return Err("bounded workers".into())}
    let step:f64=a[5].parse()?;if !step.is_finite()||step<=0.{return Err("invalid step".into())}
    let out=Path::new(&a[6]);if out.exists(){return Err("output directory exists".into())}
    let t=Instant::now();let pool=rayon::ThreadPoolBuilder::new().num_threads(threads).build()?;
    let (city,atlas,source_sha)=if fresh{
        let (city,atlas)=pool.install(||atlas_generate::generate(&a[7],&a[8],a[9].parse::<f64>().unwrap_or(f64::NAN),a[10].parse::<usize>().unwrap_or(0),case.seed,matrix.population,true))?;
        (city,Some(atlas),None)
    }else{
        if fs::metadata(&a[7])?.len()>64*1024*1024{return Err("city input byte bound".into())}
        let raw=fs::read(&a[7])?;
        (serde_json::from_slice::<Value>(&raw)?,None,Some(sha(&raw)))
    };
    let (manifest,prepare)=pool.install(||v1_prepare_city::prepare_snapshot(city.clone(),case,&matrix,step))?;
    let calendar=pool.install(||v1_prepare_city::audit_calendar(&manifest))?;
    fs::create_dir(out)?;
    let city_sha=write(&out.join("city.json"),&city)?;
    let manifest_sha=write(&out.join("manifest.json"),&manifest)?;
    let status=fs::read_to_string("/proc/self/status").unwrap_or_default();
    let report=json!({"schema":"metroflow_native_city_pipeline_v1","scope":"Rust atlas/physical portal validation and factorized activity/calendar preparation; no traffic advancement or V03 acceptance",
        "status":"EXECUTED_FOR_REVIEW","mode":a[1],"case":case.id,"matrix_sha256":matrix_sha,"source_city_sha256":source_sha,
        "city_identity":city["identity"],"schedule_identity":manifest["calendar"]["schedule_identity"],"city_sha256":city_sha,
        "manifest_sha256":manifest_sha,"model_identity":prepare["native_identity"],"atlas":atlas,"prepare":prepare,"calendar":calendar,
        "threads":threads,"step_s":step,"wall_s":t.elapsed().as_secs_f64(),"python_runtime_dependency":"none",
        "peak_rss_kib":status.lines().find(|x|x.starts_with("VmHWM:")).and_then(|x|x.split_whitespace().nth(1)).and_then(|x|x.parse::<u64>().ok()),
        "executable_sha256":sha(&fs::read(std::env::current_exe()?)?)});
    write(&out.join("receipt.json"),&report)?;
    println!("{}",json!({"case":case.id,"city_identity":report["city_identity"],"schedule_identity":report["schedule_identity"],"calendar":report["calendar"],"wall_s":report["wall_s"],"peak_rss_kib":report["peak_rss_kib"]}));Ok(())
}
