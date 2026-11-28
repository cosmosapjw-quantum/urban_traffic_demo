#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Gate {
    Pass,
    Fail,
    Unknown,
}
fn eligible(gates: &[Gate]) -> bool {
    !gates.is_empty() && gates.iter().all(|g| *g == Gate::Pass)
}
fn main() {}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn noncompensatory() {
        assert!(!eligible(&[Gate::Pass, Gate::Fail]));
        assert!(!eligible(&[Gate::Pass, Gate::Unknown]));
        assert!(!eligible(&[]));
        assert!(eligible(&[Gate::Pass, Gate::Pass]));
    }
}

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

const A_PATH: &str = "artifacts/akm_d05_final_20261128/S05_A_results.json";
const B_COARSE: &str = "artifacts/akm_d05_final_20261128/S06_B_mesh300.json";
const B_FINE: &str = "artifacts/akm_d05_final_20261128/S06_B_mesh150.json";
const EXTRA_MANIFEST: &str = "artifacts/akm_d11_decision_20261128/S02_extra_sources.sha256";

fn read_pinned(root: &Path, rel: &str, manifest: &str) -> Result<Value, String> {
    let raw = fs::read(root.join(rel)).map_err(|e| format!("{rel}: {e}"))?;
    let expected = fs::read_to_string(root.join(manifest)).map_err(|e| e.to_string())?;
    let digest = format!("{:x}", Sha256::digest(&raw));
    let matches: Vec<_> = expected
        .lines()
        .filter_map(|l| l.split_once("  "))
        .filter(|(_, path)| *path == rel)
        .map(|(hash, _)| hash)
        .collect();
    if matches.as_slice() != [digest.as_str()] {
        return Err(format!("missing or mismatched input digest: {rel}"));
    }
    serde_json::from_slice(&raw).map_err(|e| format!("{rel}: {e}"))
}
fn number(v: &Value, ptr: &str) -> Result<f64, String> {
    v.pointer(ptr)
        .and_then(Value::as_f64)
        .filter(|x| x.is_finite() && *x >= 0.0)
        .ok_or_else(|| format!("missing/nonfinite/negative metric {ptr}"))
}
fn arr<'a>(v: &'a Value, ptr: &str) -> Result<&'a [Value], String> {
    v.pointer(ptr)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| format!("missing array {ptr}"))
}
fn relative(coarse: f64, fine: f64) -> Result<f64, String> {
    if coarse <= 0.0 {
        return Err("nonpositive comparison denominator".into());
    }
    Ok((fine - coarse).abs() / coarse)
}
fn analyze_a(a: &Value) -> Result<Value, String> {
    let rows = arr(a, "/results")?;
    if rows.len() != 24 {
        return Err("unexpected A case count".into());
    }
    let mut policies = Vec::new();
    let mut failed = Vec::new();
    for row in rows {
        if row["status"] != "HORIZON_REACHED" {
            failed.push(json!({"status":row["status"],"scenario":row["scenario"],"time_s":number(row,"/time_s")?}));
        } else if number(row, "/time_s")? != number(row, "/scenario/horizon")? {
            return Err("A horizon mismatch".into());
        }
    }
    for policy in 0..4 {
        let mut day = Vec::new();
        for (cells, dt) in [(1, 5.0), (2, 2.5), (4, 1.25)] {
            let matches: Vec<_> = rows
                .iter()
                .filter(|r| {
                    r["scenario"]["policy"] == policy
                        && r["scenario"]["cells"] == cells
                        && r["scenario"]["day_profile"] == true
                })
                .collect();
            if matches.len() != 1 {
                return Err("ambiguous A day cell".into());
            }
            let r = matches[0];
            if number(r, "/scenario/dt")? != dt || number(r, "/scenario/horizon")? != 86400.0 {
                return Err("A day scope mismatch".into());
            }
            day.push(if r["status"] == "HORIZON_REACHED" {
                Some(number(r, "/completed_conditional_mean_s")?)
            } else {
                None
            });
        }
        let gap = match (day[1], day[2]) {
            (Some(c), Some(f)) => Some(relative(c, f)?),
            _ => None,
        };
        policies.push(
            json!({"policy":policy,"mean_s":day,"finest_adjacent_relative_gap":gap,
          "mean_refinement_pass":gap.is_some_and(|g|g<=0.02)}),
        );
    }
    Ok(
        json!({"cases":rows.len(),"reached":rows.len()-failed.len(),"failed":failed,"policies":policies,
        "scope":"synthetic joint space/time ladder; incomplete day means excluded"}),
    )
}
fn analyze_b(c: &Value, f: &Value) -> Result<Value, String> {
    for k in [
        "network_sha256",
        "passages_sha256",
        "policy",
        "observation_times_s",
        "executable_sha256",
    ] {
        if c.get(k).is_none() || c[k] != f[k] {
            return Err(format!("B incomparable {k}"));
        }
    }
    for k in ["horizon_s", "seed", "shock_factor", "shock_link"] {
        if c["config"].get(k).is_none() || c["config"][k] != f["config"][k] {
            return Err(format!("B incomparable config {k}"));
        }
    }
    if number(c, "/config/mesh_s")? != 300.0
        || number(f, "/config/mesh_s")? != 150.0
        || number(c, "/config/horizon_s")? != 28800.0
    {
        return Err("unexpected B scope".into());
    }
    let cs = arr(c, "/result/snapshots")?;
    let fs = arr(f, "/result/snapshots")?;
    if cs.is_empty() || cs.len() != fs.len() {
        return Err("B observation count mismatch".into());
    }
    let mut peak_recv: f64 = 0.0;
    let mut peak_store: f64 = 0.0;
    for (x, y) in cs.iter().zip(fs) {
        if number(x, "/time_s")? != number(y, "/time_s")? {
            return Err("B observation clock mismatch".into());
        }
        peak_recv = peak_recv
            .max((number(x, "/max_receiving_ratio")? - number(y, "/max_receiving_ratio")?).abs());
        peak_store = peak_store
            .max((number(x, "/max_storage_ratio")? - number(y, "/max_storage_ratio")?).abs());
    }
    let mean = |v: &Value| -> Result<f64, String> {
        if number(v, "/time_s")? != 28800.0 {
            return Err("B final observation not AM target".into());
        }
        let n = number(v, "/classes/0/completed")?;
        if n <= 0.0 {
            return Err("B no car completions".into());
        }
        Ok(number(v, "/classes/0/trip_seconds")? / n)
    };
    let cm = mean(cs.last().unwrap())?;
    let fm = mean(fs.last().unwrap())?;
    Ok(
        json!({"mesh_s":[300,150],"mean_s":[cm,fm],"mean_relative_gap":relative(cm,fm)?,
        "max_receiving_ratio_abs_gap":peak_recv,"max_storage_ratio_abs_gap":peak_store,
        "receiving_diagnostic_pass":peak_recv<=0.02,"scope":"matched projected archive AM, not original calendar",
        "wall_s":[number(c,"/wall_s")?,number(f,"/wall_s")?],
        "peak_rss_bytes":[number(c,"/peak_rss_bytes")?,number(f,"/peak_rss_bytes")?]}),
    )
}
#[cfg(test)]
mod archived_ab {
    use super::*;
    fn root() -> std::path::PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
    }
    #[test]
    fn a_raw_matrix() {
        let r = analyze_a(&read_pinned(&root(), A_PATH, EXTRA_MANIFEST).unwrap()).unwrap();
        assert_eq!(r["reached"], 22);
        assert_eq!(r["failed"].as_array().unwrap().len(), 2);
        assert!(r["policies"]
            .as_array()
            .unwrap()
            .iter()
            .all(|p| p["mean_refinement_pass"] == false));
        assert!(
            (r["policies"][1]["finest_adjacent_relative_gap"]
                .as_f64()
                .unwrap()
                - 0.4328322203465471)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn b_raw_matched() {
        let c = read_pinned(&root(), B_COARSE, EXTRA_MANIFEST).unwrap();
        let mut f = read_pinned(&root(), B_FINE, EXTRA_MANIFEST).unwrap();
        let r = analyze_b(&c, &f).unwrap();
        assert!(
            (r["max_receiving_ratio_abs_gap"].as_f64().unwrap() - 0.028614155879121805).abs()
                < 1e-12
        );
        assert_eq!(r["receiving_diagnostic_pass"], false);
        f["network_sha256"] = json!("other");
        assert!(analyze_b(&c, &f).is_err());
    }
}
