use _metroflow_rust::{run_native_declaration_with_plan,recover_native_checkpoint,run_native_phase};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io::{BufReader, Read},
    path::Path,
    time::Instant,
};
fn digest(path: &Path) -> std::io::Result<String> {
    let mut file = File::open(path)?;
    let mut buf = vec![0; 1024 * 1024];
    let mut hash = Sha256::new();
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hash.update(&buf[..n])
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn rss() -> Option<u64> {
    std::fs::read_to_string("/proc/self/status")
        .ok()?
        .lines()
        .find_map(|s| s.strip_prefix("VmHWM:"))?
        .split_whitespace()
        .next()?
        .parse::<u64>()
        .ok()?
        .checked_mul(1024)
}
#[cfg(target_os = "linux")]
fn address_cap() -> std::io::Result<u64> {
    let mut lim = libc::rlimit {
        rlim_cur: 0,
        rlim_max: 0,
    };
    // SAFETY: valid pointer to an initialized libc rlimit structure.
    if unsafe { libc::getrlimit(libc::RLIMIT_AS, &mut lim) } != 0 {
        return Err(std::io::Error::last_os_error());
    }
    lim.rlim_cur = lim.rlim_cur.min(8 * 1024u64.pow(3)).min(lim.rlim_max);
    if unsafe { libc::setrlimit(libc::RLIMIT_AS, &lim) } != 0 {
        return Err(std::io::Error::last_os_error());
    }
    Ok(lim.rlim_cur)
}
#[cfg(not(target_os = "linux"))]
fn address_cap() -> std::io::Result<u64> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "Linux address cap required",
    ))
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.get(1).is_some_and(|x|x=="--phase"){
        if ![9,11].contains(&a.len()){return Err("usage: metroflow-native-run --phase MANIFEST CONFIG INPUTS END_S THREADS RECEIPT CHECKPOINT [PRIOR_RECEIPT PRIOR_CHECKPOINT]".into())}
        let started=Instant::now();let cap=address_cap()?;
        if Path::new(&a[7]).exists()||Path::new(&a[8]).exists(){return Err("output exists".into())}
        fn bounded_read<T:serde::de::DeserializeOwned>(p:&str)->Result<T,Box<dyn std::error::Error>>{
            if std::fs::metadata(p)?.len()>32*1024*1024{return Err("phase input/receipt byte bound".into())}
            Ok(serde_json::from_reader(BufReader::new(File::open(p)?))?)
        }
        let mh=digest(Path::new(&a[2]))?;let cfg_hash=digest(Path::new(&a[3]))?;let input_hash=digest(Path::new(&a[4]))?;
        let manifest=bounded_read(&a[2])?;let config=bounded_read(&a[3])?;let inputs=bounded_read(&a[4])?;
        let resume=if a.len()==11{let prior:Value=bounded_read(&a[9])?;
            if prior["schema"]!="metroflow_native_world_v1"||prior["status"]!="EXECUTED_FOR_REVIEW"||prior["manifest_sha256"]!=mh||prior["phase_config_sha256"]!=cfg_hash||prior["checkpoint_sha256"]!=digest(Path::new(&a[10]))?{return Err("phase resume binding differs".into())}
            let wire_hash=format!("{:x}",Sha256::digest(serde_json::to_vec(&prior["phase_wire"])?));
            if prior["phase_wire_sha256"]!=wire_hash{return Err("phase wire digest differs".into())}
            Some((a[10].as_str(),serde_json::from_value(prior["phase_wire"].clone())?))
        }else{None};
        let mut out=run_native_phase(manifest,a[6].parse()?,a[5].parse()?,config,inputs,resume,&a[8])?;
        if mh!=digest(Path::new(&a[2]))?||cfg_hash!=digest(Path::new(&a[3]))?||input_hash!=digest(Path::new(&a[4]))?{return Err("phase input changed".into())}
        out["manifest_sha256"]=json!(mh);out["phase_config_sha256"]=json!(cfg_hash);out["phase_inputs_sha256"]=json!(input_hash);out["checkpoint_sha256"]=json!(digest(Path::new(&a[8]))?);out["executable_sha256"]=json!(digest(&std::env::current_exe()?)?);
        out["checkpoint_bytes"]=json!(std::fs::metadata(&a[8])?.len());out["address_space_limit_bytes"]=json!(cap);out["peak_rss_bytes"]=json!(rss());out["wall_s"]=json!(started.elapsed().as_secs_f64());out["python_runtime_dependency"]=json!("none");
        serde_json::to_writer_pretty(OpenOptions::new().write(true).create_new(true).open(&a[7])?,&out)?;
        println!("{}",serde_json::to_string(&out)?);return Ok(())
    }
    if a.get(1).is_some_and(|x|x=="--recover"){
        if a.len()!=6{return Err("usage: metroflow-native-run --recover MANIFEST CHECKPOINT RECEIPT THREADS".into())}
        let started=Instant::now();let cap=address_cap()?;
        if Path::new(&a[4]).exists(){return Err("output exists".into())}
        let mh=digest(Path::new(&a[2]))?;let ch=digest(Path::new(&a[3]))?;
        let input=serde_json::from_reader(BufReader::new(File::open(&a[2])?))?;
        let mut out=recover_native_checkpoint(input,a[5].parse()?,&a[3])?;
        if mh!=digest(Path::new(&a[2]))?||ch!=digest(Path::new(&a[3]))?{return Err("recovery input changed".into())}
        out["manifest_sha256"]=json!(mh);out["checkpoint_sha256"]=json!(ch);out["executable_sha256"]=json!(digest(&std::env::current_exe()?)?);
        out["checkpoint_bytes"]=json!(std::fs::metadata(&a[3])?.len());out["address_space_limit_bytes"]=json!(cap);out["peak_rss_bytes"]=json!(rss());out["wall_s"]=json!(started.elapsed().as_secs_f64());out["python_runtime_dependency"]=json!("none");
        serde_json::to_writer_pretty(OpenOptions::new().write(true).create_new(true).open(&a[4])?,&out)?;
        println!("{}",serde_json::to_string(&out)?);return Ok(())
    }
    if ![6, 8].contains(&a.len()) {
        return Err("usage: metroflow-native-run MANIFEST END_S THREADS RECEIPT CHECKPOINT [PRIOR_RECEIPT PRIOR_CHECKPOINT]".into());
    }
    let start = Instant::now();
    let cap = address_cap()?;
    let manifest_hash = digest(Path::new(&a[1]))?;
    if Path::new(&a[4]).exists() || Path::new(&a[5]).exists() {
        return Err("output exists".into());
    }
    if a.len() == 8 {
        let previous: Value = serde_json::from_reader(BufReader::new(File::open(&a[6])?))?;
        if previous["manifest_sha256"] != manifest_hash
            || previous["checkpoint_sha256"] != digest(Path::new(&a[7]))?
        {
            return Err("resume source/byte identity differs".into());
        }
    }
    let input: Value = serde_json::from_reader(BufReader::new(File::open(&a[1])?))?;
    let segment = std::env::var("METROFLOW_NATIVE_SEGMENT_S").ok().map(|x|x.parse::<f64>()).transpose()?;
    let replay = std::env::var("METROFLOW_NATIVE_REPLAY_AT_S").ok().map(|x|x.parse::<f64>()).transpose()?;
    let mut out = run_native_declaration_with_plan(
        input,
        a[3].parse()?,
        a[2].parse()?,
        a.get(7).map(String::as_str),
        &a[5],
        segment,replay,
    )
    .map_err(|e| e.to_string())?;
    if digest(Path::new(&a[1]))? != manifest_hash {
        return Err("manifest changed".into());
    }
    out["manifest_sha256"] = json!(manifest_hash);
    out["checkpoint_sha256"] = json!(digest(Path::new(&a[5]))?);
    out["executable_sha256"] = json!(digest(&std::env::current_exe()?)?);
    out["checkpoint_bytes"] = json!(std::fs::metadata(&a[5])?.len());
    out["address_space_limit_bytes"] = json!(cap);
    out["peak_rss_bytes"] = json!(rss());
    out["wall_s"] = json!(start.elapsed().as_secs_f64());
    out["python_runtime_dependency"] = json!("none");
    serde_json::to_writer_pretty(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[4])?,
        &out,
    )?;
    println!("{}", serde_json::to_string(&out)?);
    if out["status"]=="BLOCKED"{std::process::exit(2)}
    Ok(())
}
