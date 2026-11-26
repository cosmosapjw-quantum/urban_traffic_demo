use metroflow_headless::receipt;
use serde_json::{json, Value};
use std::{fs, path::Path};
fn read(p: &str) -> Result<Value, Box<dyn std::error::Error>> {
    Ok(serde_json::from_reader(fs::File::open(p)?)?)
}
fn num(v: &Value) -> f64 {
    v.as_f64().expect("numeric field")
}
fn close(a: f64, b: f64, label: &str) {
    assert!(
        a.is_finite() && b.is_finite() && (a - b).abs() <= 1e-7 + 1e-12 * a.abs().max(b.abs()),
        "{label}: {a} != {b}"
    )
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() < 4 {
        return Err(
            "usage: metroflow-verify HISTORICAL_CAMPAIGN RUST_RECEIPT RUST_RECEIPT ...".into(),
        );
    }
    let h = read(&a[1])?;
    let runs = h["runs"].as_array().ok_or("historical runs")?;
    let mut results = vec![];
    let mut previous: Option<Value> = None;
    for path in &a[2..] {
        let r = read(path)?;
        assert_eq!(r["network_sha256"], h["input_sha256"]);
        assert_eq!(r["passages_sha256"], h["passages_sha256"]);
        let m = num(&r["config"]["mesh_s"]);
        let t = num(&r["config"]["horizon_s"]);
        let old = runs
            .iter()
            .find(|x| num(&x["mesh_s"]) == m && num(&x["horizon_s"]) == t)
            .ok_or("historical case missing")?;
        let s = r["result"]["snapshots"]
            .as_array()
            .ok_or("snapshots")?
            .last()
            .ok_or("no snapshot")?;
        assert_eq!(num(&s["time_s"]), t);
        let cls = s["classes"].as_array().ok_or("classes")?;
        assert_eq!(cls.len(), 3);
        for (a, b) in [
            ("expected", "expected_total"),
            ("released", "released"),
            ("admitted", "admitted"),
            ("exited", "exited"),
            ("completed", "completed"),
            ("active", "active"),
            ("road", "road_stock"),
            ("trip_seconds", "veh_trip_seconds"),
        ] {
            close(cls.iter().map(|c| num(&c[a])).sum(), num(&old[b]), b);
        }
        for k in ["max_storage_ratio", "max_receiving_ratio"] {
            close(num(&s[k]), num(&old[k]), k);
        }
        for k in ["storage_blocks", "rate_blocks"] {
            assert_eq!(s[k], old[k]);
        }
        assert_eq!(r["result"]["event_count"], old["event_count"]);
        close(
            num(&r["result"]["wait_veh_s"]),
            num(&old["waiting_veh_s"]),
            "waiting",
        );
        close(
            num(&r["result"]["blocked_veh_s"]),
            num(&old["blocked_veh_s"]),
            "blocked",
        );
        for (c, o) in cls
            .iter()
            .zip(old["per_class"].as_array().ok_or("old classes")?)
        {
            for k in ["expected", "completed", "active", "trip_seconds"] {
                close(num(&c[k]), num(&o[k]), k);
            }
        }
        if t == 86400. {
            for c in cls {
                close(num(&c["completed"]), num(&c["expected"]), "day completion");
                close(num(&c["active"]), 0., "day active");
            }
        }
        let mut exact_repeat = false;
        if let Some(p) = &previous {
            if p["config"] == r["config"] {
                assert_eq!(p["result"], r["result"]);
                exact_repeat = true;
            }
        }
        results.push(json!({"receipt":Path::new(path).file_name().unwrap().to_string_lossy(),"sha256":receipt::sha256(Path::new(path))?,"mesh_s":m,"horizon_s":t,"threads":r["threads"],"events":r["result"]["event_count"],"historical_tolerance_match":true,"identical_adjacent_repeat":exact_repeat}));
        previous = Some(r);
    }
    println!(
        "{}",
        serde_json::to_string_pretty(
            &json!({"status":"PASS","scope":"historical projected scenario parity only; not original V03 acceptance","historical_sha256":receipt::sha256(Path::new(&a[1]))?,"runs":results})
        )?
    );
    Ok(())
}
