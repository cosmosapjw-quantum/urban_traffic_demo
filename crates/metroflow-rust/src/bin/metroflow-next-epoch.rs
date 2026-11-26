use _metroflow_rust::{frozen_city::Matrix, next_epoch};
use serde_json::Value;
use std::{
    fs::{File, OpenOptions},
    io::{BufReader, BufWriter},
    path::Path,
};
fn read(p: &str) -> Result<Value, Box<dyn std::error::Error>> {
    Ok(serde_json::from_reader(BufReader::new(File::open(p)?))?)
}
fn write(p: &str, v: &Value) -> Result<(), Box<dyn std::error::Error>> {
    serde_json::to_writer(
        BufWriter::new(OpenOptions::new().create_new(true).write(true).open(p)?),
        v,
    )?;
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 13 {
        return Err("usage: metroflow-next-epoch ROOT MATRIX CASE CITY ENTRY_RECEIPT FEEDBACK PARITY THREADS BEFORE_MANIFEST NEXT_CITY NEXT_MANIFEST RECEIPT".into());
    }
    let (m, _) = Matrix::load(Path::new(&a[2]))?;
    let case = m.cases.iter().find(|c| c.id == a[3]).ok_or("case")?;
    let n: usize = a[8].parse()?;
    if !(1..=256).contains(&n) {
        return Err("worker count".into());
    }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(n).build()?;
    let (before, city, next, mut report) = pool.install(|| {
        next_epoch::audit(
            Path::new(&a[1]),
            &m,
            case,
            read(&a[4])
                .map_err(|e| _metroflow_rust::core_error::CoreError::value(e.to_string()))?,
            read(&a[5])
                .map_err(|e| _metroflow_rust::core_error::CoreError::value(e.to_string()))?,
            read(&a[6])
                .map_err(|e| _metroflow_rust::core_error::CoreError::value(e.to_string()))?,
            &read(&a[7])
                .map_err(|e| _metroflow_rust::core_error::CoreError::value(e.to_string()))?,
            10.,
        )
    })?;
    report["threads"] = serde_json::json!(n);
    write(&a[9], &before)?;
    write(&a[10], &city)?;
    write(&a[11], &next)?;
    write(&a[12], &report)?;
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}
