use _metroflow_rust::frozen_city::{self, Matrix};
use std::{
    io::{BufRead, BufReader},
    path::Path,
    time::Instant,
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if ![4, 6].contains(&a.len()) {
        return Err("usage: metroflow-frozen-road-audit ROOT MATRIX THREADS [VALLEY_HISTORICAL_NETWORK VALLEY_LINK_IDS]".into());
    }
    let (m, hash) = Matrix::load(Path::new(&a[2]))?;
    let t: usize = a[3].parse()?;
    if !(1..=256).contains(&t) {
        return Err("invalid threads".into());
    }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(t).build()?;
    let mut rows = vec![];
    for case in &m.cases {
        let now = Instant::now();
        let mut r = pool.install(|| frozen_city::audit(Path::new(&a[1]), case, m.population))?;
        r["wall_s"] = serde_json::json!(now.elapsed().as_secs_f64());
        rows.push(r);
    }
    let mut comparison = serde_json::Value::Null;
    if a.len() == 6 {
        let old: Vec<String> = serde_json::from_reader(std::fs::File::open(&a[5])?)?;
        let row = rows
            .iter()
            .find(|r| r["case"] == "valley_weekday_s7")
            .ok_or("Valley absent")?;
        assert_eq!(row["link_ids"], serde_json::json!(old));
        let mut lines = BufReader::new(std::fs::File::open(&a[4])?).lines();
        let header = lines.next().ok_or("header absent")??;
        assert_eq!(
            header.split_whitespace().next().unwrap().parse::<usize>()?,
            old.len()
        );
        let mut max_rel = 0f64;
        for r in row["physical_road_rows"].as_array().unwrap() {
            let actual: Vec<f64> = r
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap())
                .collect();
            let prior: Vec<f64> = lines
                .next()
                .ok_or("missing road")??
                .split_whitespace()
                .map(str::parse)
                .collect::<Result<_, _>>()?;
            assert_eq!(prior.len(), 4);
            for (x, y) in [
                actual[0] / actual[1].min(10.),
                actual[2],
                actual[3],
                actual[4],
            ]
            .into_iter()
            .zip(prior)
            {
                let error = (x - y).abs() / x.abs().max(y.abs()).max(1.);
                assert!(error <= 1e-12, "historical road differs: {x} {y}");
                max_rel = max_rel.max(error);
            }
        }
        comparison = serde_json::json!({"rows":old.len(),"max_scaled_difference":max_rel,"link_id_order_exact":true});
    }
    println!(
        "{}",
        serde_json::to_string_pretty(
            &serde_json::json!({"matrix_sha256":hash,"threads":t,"rows":rows,"valley_historical_road_comparison":comparison})
        )?
    );
    Ok(())
}
