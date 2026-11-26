use _metroflow_rust::feedback_audit;
use std::{fs::File, io::BufReader};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 4 {
        return Err("usage: metroflow-feedback-audit MANIFEST NATIVE_RECEIPT THREADS".into());
    }
    let v = feedback_audit::audit(
        serde_json::from_reader(BufReader::new(File::open(&a[1])?))?,
        serde_json::from_reader(BufReader::new(File::open(&a[2])?))?,
        a[3].parse()?,
    )?;
    println!("{}", serde_json::to_string_pretty(&v)?);
    Ok(())
}
