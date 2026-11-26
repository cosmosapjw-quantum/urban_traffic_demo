use metroflow_headless::{
    prepare::{self, Manifest},
    receipt,
};
use serde_json::json;
use std::{
    fs::{File, OpenOptions},
    io::{BufReader, BufWriter, Write},
    path::Path,
    time::Instant,
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    if a.len() != 6 {
        return Err("usage: metroflow-prepare MANIFEST NETWORK PASSAGES THREADS RECEIPT".into());
    }
    let t: usize = a[4].parse()?;
    if !(1..=256).contains(&t) {
        return Err("invalid threads".into());
    }
    let start = Instant::now();
    let input_hash = receipt::sha256(Path::new(&a[1]))?;
    let m: Manifest = serde_json::from_reader(BufReader::new(File::open(&a[1])?))?;
    let pool = rayon::ThreadPoolBuilder::new().num_threads(t).build()?;
    let (input, report) = pool.install(|| prepare::prepare(m))?;
    let mut n = BufWriter::new(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[2])?,
    );
    let mut p = BufWriter::new(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[3])?,
    );
    prepare::write_input(&input, &mut n, &mut p)?;
    n.flush()?;
    p.flush()?;
    if receipt::sha256(Path::new(&a[1]))? != input_hash {
        return Err("input changed".into());
    }
    let r = json!({"schema":"metroflow_access_preparation_receipt_v1","input_sha256":input_hash,"network_sha256":receipt::sha256(Path::new(&a[2]))?,"passages_sha256":receipt::sha256(Path::new(&a[3]))?,"threads":t,"wall_s":start.elapsed().as_secs_f64(),"peak_rss_bytes":receipt::peak_rss_bytes(),"report":report});
    serde_json::to_writer_pretty(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[5])?,
        &r,
    )?;
    println!("{r}");
    Ok(())
}
