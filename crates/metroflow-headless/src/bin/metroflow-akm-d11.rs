#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Gate {
    Pass,
    Fail,
    Unknown,
}
fn eligible(gates: &[Gate]) -> bool {
    !gates.is_empty() && gates.iter().all(|g| *g == Gate::Pass)
}
fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 2 {
        return Err("usage: metroflow-akm-d11 REPO_ROOT".into());
    }
    let receipt = decision(Path::new(&args[1]))?;
    println!(
        "{}",
        serde_json::to_string_pretty(&receipt).map_err(|e| e.to_string())?
    );
    Ok(())
}
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

const BASE_MANIFEST: &str = "artifacts/akm_d11_decision_20261128/S01_baseline.txt";
const D09: &str = "artifacts/akm_d09_final_cohort_20261128/S09_audit.json";
const D09_OLD: &str = "artifacts/akm_d09_city_pilot_20261128/S09_audit.json";
const SUPPORT: &str = "artifacts/akm_d09_final_cohort_20261128/S08_support.json";
fn analyze_d(d: &Value, old: &Value, s: &Value) -> Result<Value, String> {
    if d["status"] != "D09_FINAL_ATTEMPT_NOT_ACCEPTED"
        || s["status"] != "UNCHANGED_ORIGINAL_SERVICE_SCOPE"
        || s["manifest_sha256"]
            .as_str()
            .filter(|v| v.len() == 64)
            .is_none()
        || d["manifest_sha256"] != s["manifest_sha256"]
        || d["support"] != *s
        || s["parent_profile_bound"] != old["support"]["day"]
    {
        return Err("D source/status or parent-bound mismatch".into());
    }
    let demand = number(s, "/bus_person_intent")?;
    let capacity = number(s, "/sum_single_run_seat_capacity")?;
    let deficit = (demand - capacity).max(0.0);
    let total = number(s, "/parent_profile_bound/requested/0")?;
    let ceiling = number(s, "/parent_profile_bound/optimistic_completion_ceiling/0")?;
    let lower = number(s, "/parent_profile_bound/uncompleted_lower_bound/0")?;
    if total <= 0.0
        || demand <= 0.0
        || (total - ceiling - lower).abs() > 1e-8
        || (deficit - number(s, "/optimistic_all_run_seat_deficit_person")?).abs() > 1e-8
        || lower + 1e-8 < deficit
    {
        return Err("inconsistent service bound".into());
    }
    let hs = arr(d, "/physical/actual_refinement_steps_s")?;
    let ds = arr(d, "/physical/synchronization_extra_s")?;
    if hs != [json!(1.0), json!(0.5), json!(0.25)]
        && hs.iter().map(Value::as_f64).collect::<Vec<_>>() != [Some(1.0), Some(0.5), Some(0.25)]
    {
        return Err("unexpected D refinement steps".into());
    }
    if ds.len() != hs.len() || ds.iter().any(|v| v.as_f64() != Some(7.0)) {
        return Err("unexpected D free-flow discriminator".into());
    }
    let old_rows = number(d, "/same_prefix/old_rows")?;
    let new_rows = number(d, "/same_prefix/new_rows")?;
    let old_completed = number(d, "/same_prefix/old_person_completed")?;
    let new_completed = number(d, "/same_prefix/new_person_completed")?;
    let mut residuals = serde_json::Map::new();
    for key in ["persons", "vehicles", "cargo_kg"] {
        let ledger = d["continuation"]["ledger"]
            .get(key)
            .ok_or("D missing ledger")?;
        let requested = number(ledger, "/requested")?;
        let released = number(ledger, "/released")?;
        let completed = number(ledger, "/completed")?;
        let active = number(ledger, "/active")?;
        let pending = number(ledger, "/pending")?;
        residuals.insert(
            key.into(),
            json!({"requested_minus_released_pending":requested-released-pending,
            "released_minus_completed_active":released-completed-active}),
        );
    }
    Ok(
        json!({"scope":"fixed original registry and actual sealed-cohort prefix; no full day",
        "manifest_sha256":s["manifest_sha256"],"bus_intent":demand,"seat_capacity":capacity,
        "bus_deficit_lower_bound":deficit,"bus_deficit_fraction":deficit/demand,
        "parent_profile_uncompleted_lower_bound":lower,"parent_profile_uncompleted_fraction":lower/total,
        "synchronization_steps_s":hs,"synchronization_extra_s":ds,
        "free_flow_consistency_pass":false,"old_rows":old_rows,"new_rows":new_rows,
        "row_reduction_fraction":1.0-new_rows/old_rows,
        "completed_person_relative_change":(new_completed-old_completed)/old_completed,
        "prefix_time_s":number(d,"/same_prefix/time_s")?,
        "last_actual_time_s":number(d,"/continuation/time_s")?,
        "requested_end_s":number(d,"/continuation/requested_end_s")?,
        "termination":d["continuation"]["failure"],
        "day_reached":number(d,"/continuation/time_s")?==number(d,"/continuation/requested_end_s")?,
        "checkpoint_recovery_byte_equal":d["physical"]["city_checkpoint_recovery_byte_equal"],
        "ledger_residuals":residuals}),
    )
}
#[cfg(test)]
mod archived_d {
    use super::*;
    #[test]
    fn d_evidence_and_identity() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let d = read_pinned(&root, D09, BASE_MANIFEST).unwrap();
        let old = read_pinned(&root, D09_OLD, BASE_MANIFEST).unwrap();
        let mut s = read_pinned(&root, SUPPORT, EXTRA_MANIFEST).unwrap();
        let r = analyze_d(&d, &old, &s).unwrap();
        assert!((r["bus_deficit_lower_bound"].as_f64().unwrap() - 29040.0).abs() < 1e-8);
        assert!(
            (r["parent_profile_uncompleted_fraction"].as_f64().unwrap() - 0.39903362574375).abs()
                < 1e-12
        );
        assert_eq!(r["day_reached"], false);
        assert_eq!(r["free_flow_consistency_pass"], false);
        assert!((r["row_reduction_fraction"].as_f64().unwrap() - 0.6100550091472113).abs() < 1e-12);
        s["manifest_sha256"] = json!("wrong");
        assert!(analyze_d(&d, &old, &s).is_err());
    }
}

fn gate_name(g: Gate) -> &'static str {
    match g {
        Gate::Pass => "PASS",
        Gate::Fail => "FAIL",
        Gate::Unknown => "UNKNOWN",
    }
}
fn candidate(name: &str, gates: [Gate; 5], positives: &[&str], negatives: &[&str]) -> Value {
    json!({"candidate":name,"gates":{
        "physical_refinement":gate_name(gates[0]),"original_service_support":gate_name(gates[1]),
        "original_full_day":gate_name(gates[2]),"original_full_day_replay":gate_name(gates[3]),
        "independent_holdout":gate_name(gates[4])},
        "eligible":eligible(&gates),"positive_scoped":positives,"negative_or_missing":negatives})
}
fn decision(root: &Path) -> Result<Value, String> {
    let a = analyze_a(&read_pinned(root, A_PATH, EXTRA_MANIFEST)?)?;
    let b = analyze_b(
        &read_pinned(root, B_COARSE, EXTRA_MANIFEST)?,
        &read_pinned(root, B_FINE, EXTRA_MANIFEST)?,
    )?;
    let d = analyze_d(
        &read_pinned(root, D09, BASE_MANIFEST)?,
        &read_pinned(root, D09_OLD, BASE_MANIFEST)?,
        &read_pinned(root, SUPPORT, EXTRA_MANIFEST)?,
    )?;
    if a["policies"]
        .as_array()
        .ok_or("A policies missing")?
        .iter()
        .any(|x| x["mean_refinement_pass"] != false)
        || b["receiving_diagnostic_pass"] != false
        || d["free_flow_consistency_pass"] != false
        || d["day_reached"] != false
        || number(&d, "/bus_deficit_lower_bound")? <= 0.0
    {
        return Err("archived decision assumptions changed; fresh review required".into());
    }
    let d07 = read_pinned(
        root,
        "artifacts/akm_d07_causal_routing_20261128/S09_audit.json",
        BASE_MANIFEST,
    )?;
    let d08 = read_pinned(
        root,
        "artifacts/akm_d08_rust_luti_20261128/S09_audit.json",
        BASE_MANIFEST,
    )?;
    if d07["status"] != "D07_VERIFIED_SCOPED_SYNTHETIC_NOT_RELEASE"
        || d08["status"] != "D08_VERIFIED_SCOPED_LAGGED_LUTI_AND_NATIVE_ENTRY_NOT_RELEASE"
    {
        return Err("D07/D08 scope changed".into());
    }
    use Gate::*;
    let candidates=vec![
        candidate("A",[Fail,Unknown,Unknown,Unknown,Unknown],
            &["positive local moments, conservative fixed support, synthetic zero-allocation runs"],
            &["joint refinement fails; two numerical stops; original service/full-day/holdout not established"]),
        candidate("B",[Fail,Unknown,Unknown,Unknown,Unknown],
            &["projected archive full-day vehicle run; matched AM mean stable"],
            &["receiving peak diagnostic fails; archive not original calendar or original replay"]),
        candidate("D",[Fail,Fail,Unknown,Unknown,Unknown],
            &["reserved bus fixture and owner/replay; smaller matched-prefix support; actual city checkpoint recovery",
              "D07/D08 synthetic causal/LUTI results retained in their own identities"],
            &["sealed-cohort free-flow bias; fixed original service shortage; session-sliced city, not resource failure",
              "no original full-day split/direct or independent holdout"])
    ];
    Ok(
        json!({"schema":"akm_d11_decision_v1","status":"NO_CANDIDATE_RESEARCH_DECISION",
       "model_identity":"akm-d11-archived-evidence-v1","scope":"D11 archived comparison, not a simulation or release",
       "candidate_selected":null,"candidate_matrix":candidates,"a":a,"b":b,"d":d,
       "cross_scope_pareto":"INCOMPARABLE: different calendars, physical closures and horizons; no scalar score",
       "retained_scoped":[d07["status"].clone(),d08["status"].clone()],
       "original_release":"UNCHANGED_BLOCKED","d10":"BLOCKED_TERMINAL_NOT_RUN",
       "d12":"NO_APPROVED_CANDIDATE_NOT_RUN","new_simulation_runs":0}),
    )
}
#[cfg(test)]
mod decision_tests {
    use super::*;
    #[test]
    fn archived_decision_has_no_candidate() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let r = decision(&root).unwrap();
        assert!(r["candidate_selected"].is_null());
        let rows = r["candidate_matrix"].as_array().unwrap();
        assert_eq!(rows.len(), 3);
        assert!(rows.iter().all(|r| r["eligible"] == false));
        assert_eq!(rows[2]["gates"]["original_full_day"], "UNKNOWN");
        assert_eq!(r["new_simulation_runs"], 0);
    }
    #[test]
    fn pin_missing_fails() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        assert!(read_pinned(&root, A_PATH, BASE_MANIFEST).is_err());
    }
}
