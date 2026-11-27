use std::{fs::File, io::BufReader};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 6 {
        return Err("usage: metroflow-marked-diverge MANIFEST DT END SCALE RECEIPT".into());
    }
    let m = serde_json::from_reader(BufReader::new(File::open(&a[1])?))?;
    let r = _metroflow_rust::marked_fifo::project_manifest(
        m,
        a[2].parse()?,
        a[3].parse()?,
        a[4].parse()?,
    )?;
    serde_json::to_writer_pretty(
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&a[5])?,
        &r,
    )?;
    println!("{}", serde_json::to_string(&r)?);
    Ok(())
}
