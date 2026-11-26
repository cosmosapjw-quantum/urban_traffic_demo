use _metroflow_rust::atlas_generate;
use serde_json::{json, Value};
use std::{fs::File, io::BufReader, path::Path};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 4 {
        return Err("usage: metroflow-atlas-parity ROOT THREADS all|release".into());
    }
    let root = Path::new(&a[1]);
    let n: usize = a[2].parse()?;
    if !(1..=256).contains(&n) {
        return Err("workers".into());
    }
    let m: Value = serde_json::from_reader(BufReader::new(File::open(
        root.join("artifacts/v1/map_audit/MATRIX.json"),
    )?))?;
    let cases = m["cases"].as_array().ok_or("cases")?;
    let release = a[3] == "release";
    if !release && a[3] != "all" {
        return Err("mode".into());
    }
    let mut rows = vec![];
    for (i, r) in cases.iter().enumerate() {
        if release && ![4, 11, 12].contains(&i) {
            continue;
        }
        let x = atlas_generate::compare_archive(root, r, n, release)?;
        eprintln!(
            "{} {} {}",
            r["case"], r["seed"], x["comparison"]["semantic_match"]
        );
        rows.push(x);
    }
    println!(
        "{}",
        serde_json::to_string_pretty(
            &json!({"rows":rows,"threads":n,"mode":a[3],"passed":rows.iter().filter(|r|r["comparison"]["semantic_match"]==true).count(),"total":rows.len()})
        )?
    );
    Ok(())
}
