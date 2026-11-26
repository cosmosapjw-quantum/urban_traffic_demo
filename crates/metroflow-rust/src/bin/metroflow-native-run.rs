use _metroflow_rust::run_native_declaration;
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
    if ![6, 8].contains(&a.len()) {
        return Err("usage: metroflow-native-run MANIFEST END_S THREADS RECEIPT CHECKPOINT [PRIOR_RECEIPT PRIOR_CHECKPOINT]".into());
    }
    let start = Instant::now();
    let cap = address_cap()?;
    let manifest_hash = digest(Path::new(&a[1]))?;
    let py_initialized_before = unsafe { pyo3::ffi::Py_IsInitialized() != 0 };
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
    let mut out = run_native_declaration(
        input,
        a[3].parse()?,
        a[2].parse()?,
        a.get(7).map(String::as_str),
        &a[5],
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
    out["python_interpreter_initialized_before"] = json!(py_initialized_before);
    out["python_interpreter_initialized_after"] =
        json!(unsafe { pyo3::ffi::Py_IsInitialized() != 0 });
    serde_json::to_writer_pretty(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[4])?,
        &out,
    )?;
    println!("{}", serde_json::to_string(&out)?);
    Ok(())
}
