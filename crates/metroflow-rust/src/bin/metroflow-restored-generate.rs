fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 5 {
        return Err("usage: metroflow-restored-generate STYLE N SEED INTERCHANGES_BOOL".into());
    }
    let x = _metroflow_rust::restored_atlas::generate(
        &a[1],
        a[2].parse()?,
        a[3].parse()?,
        a[4].parse()?,
    )?;
    println!("{}", serde_json::to_string(&x)?);
    Ok(())
}
