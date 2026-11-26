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
    let size: f64 = a[3].parse()?;
    let resolution: u32 = a[4].parse()?;
    let seed: u64 = a[5].parse()?;
    let population: u64 = a[6].parse()?;
    if !size.is_finite() || population > (1u64 << 53) { return Err("invalid atlas size or population".into()); }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(n).build()?;
    let (value, mut report) = pool.install(|| {
        atlas_generate::generate(
            &a[1],
            &a[2],
            size,
            resolution as usize,
            seed,
            population,
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
