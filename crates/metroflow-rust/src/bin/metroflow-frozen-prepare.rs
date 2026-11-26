use _metroflow_rust::{frozen_city::Matrix, v1_prepare_city};
use serde_json::json;
use std::{
    fs::{File, OpenOptions},
    io::BufWriter,
    path::Path,
    time::Instant,
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 8 {
        return Err(
            "usage: metroflow-frozen-prepare ROOT MATRIX CASE THREADS STEP MANIFEST RECEIPT".into(),
        );
    }
    let (matrix, sha) = Matrix::load(Path::new(&a[2]))?;
    let case = matrix
        .cases
        .iter()
        .find(|c| c.id == a[3])
        .ok_or("unknown case")?;
    let n: usize = a[4].parse()?;
    if !(1..=256).contains(&n) {
        return Err("invalid thread count".into());
    }
    let step: f64 = a[5].parse()?;
    let pool = rayon::ThreadPoolBuilder::new().num_threads(n).build()?;
    let t = Instant::now();
    let (manifest, mut report) =
        pool.install(|| v1_prepare_city::prepare(Path::new(&a[1]), case, &matrix, step))?;
    report["prepare_wall_s"] = json!(t.elapsed().as_secs_f64());
    let t = Instant::now();
    report["calendar"] = v1_prepare_city::audit_calendar(&manifest)?;
    report["calendar_wall_s"] = json!(t.elapsed().as_secs_f64());
    report["matrix_sha256"] = json!(sha);
    report["threads"] = json!(n);
    report["peak_rss_bytes"] = json!(std::fs::read_to_string("/proc/self/status")?
        .lines()
        .find_map(|l| l.strip_prefix("VmHWM:"))
        .and_then(|s| s.split_whitespace().next())
        .and_then(|x| x.parse::<u64>().ok())
        .map(|x| 1024 * x));
    serde_json::to_writer(
        BufWriter::new(
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&a[6])?,
        ),
        &manifest,
    )?;
    serde_json::to_writer_pretty(File::create_new(&a[7])?, &report)?;
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}
