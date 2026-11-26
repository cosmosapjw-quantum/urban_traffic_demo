use _metroflow_rust::atlas_generate;
use std::{fs::OpenOptions, io::BufWriter};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 10 {
        return Err("usage: metroflow-atlas-generate STYLE TERRAIN SIZE RESOLUTION SEED POPULATION THREADS CITY_JSON RECEIPT_JSON".into());
    }
    let n: usize = a[7].parse()?;
    if !(1..=256).contains(&n) {
        return Err("worker count".into());
    }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(n).build()?;
    let (value, mut report) = pool.install(|| {
        atlas_generate::generate(
            &a[1],
            &a[2],
            a[3].parse().unwrap_or(f64::NAN),
            a[4].parse().unwrap_or(0),
            a[5].parse().unwrap_or(u64::MAX),
            a[6].parse().unwrap_or(u64::MAX),
            true,
        )
    })?;
    report["threads"] = serde_json::json!(n);
    serde_json::to_writer(
        BufWriter::new(
            OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&a[8])?,
        ),
        &value,
    )?;
    serde_json::to_writer_pretty(
        BufWriter::new(
            OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&a[9])?,
        ),
        &report,
    )?;
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}
