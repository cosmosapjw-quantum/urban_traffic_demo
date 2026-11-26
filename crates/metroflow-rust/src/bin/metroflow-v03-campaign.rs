//! Pure Rust process-isolated V03 runner. Full mode preserves original matrix,
//! three repeats, one resumed repeat, and matched 8-hour refinement. Prefix
//! mode is intentionally never counted toward release acceptance.
use _metroflow_rust::frozen_city::Matrix;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{BufReader, Read},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn read(p: &Path) -> Result<Value> {
    Ok(serde_json::from_reader(BufReader::new(File::open(p)?))?)
}
fn digest(p: &Path) -> Result<String> {
    let mut f = File::open(p)?;
    let mut h = Sha256::new();
    let mut b = vec![0; 1024 * 1024];
    loop {
        let n = f.read(&mut b)?;
        if n == 0 {
            break;
        }
        h.update(&b[..n]);
    }
    Ok(format!("{:x}", h.finalize()))
}
fn atomic(p: &Path, v: &Value) -> Result<()> {
    let tmp = p.with_extension("stage");
    let f = OpenOptions::new().create_new(true).write(true).open(&tmp)?;
    serde_json::to_writer_pretty(&f, v)?;
    f.sync_all()?;
    fs::rename(tmp, p)?;
    Ok(())
}
fn launch(mut c: Command, stem: &Path, limit: Duration) -> Result<(bool, bool, f64)> {
    c.stdout(Stdio::from(File::create(stem.with_extension("stdout"))?))
        .stderr(Stdio::from(File::create(stem.with_extension("stderr"))?));
    let t = Instant::now();
    let mut child = c.spawn()?;
    loop {
        if let Some(s) = child.try_wait()? {
            return Ok((s.success(), false, t.elapsed().as_secs_f64()));
        }
        if t.elapsed() >= limit {
            child.kill()?;
            child.wait()?;
            return Ok((false, true, t.elapsed().as_secs_f64()));
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}
fn validate(r: &Value, end: f64, step: f64, prep: &Value, hash: &str, replay: bool) -> Result<()> {
    if r["status"] != "EXECUTED_FOR_REVIEW"
        || r["time_s"].as_f64() != Some(end)
        || r["manifest_sha256"] != hash
        || r["resume_verified"].as_bool() != Some(replay)
        || r["calendar_legs"] != prep["calendar"]["calendar_legs"]
        || r["city_identity"] != prep["city_identity"]
        || r["schedule_identity"] != prep["schedule_identity"]
        || r["python_runtime_dependency"] != "none"
    {
        return Err("execution binding or status differs".into());
    }
    if r["peak_rss_bytes"]
        .as_u64()
        .is_none_or(|x| x > 8 * 1024u64.pow(3))
        || r["native_route_latency"]["status"] != "MEASURED_INTERVAL"
        || r["native_route_latency"]["observed_calls"]
            .as_u64()
            .unwrap_or(0)
            == 0
    {
        return Err("RSS/route census absent or exceeded".into());
    }
    let ts = r["tick_times_s"].as_array().ok_or("tick times absent")?;
    if ts.len() != (end / step).round() as usize
        || ts
            .iter()
            .any(|x| x.as_f64().is_none_or(|f| !f.is_finite() || f < 0.))
    {
        return Err("tick census differs".into());
    }
    for (i, u) in ["persons", "vehicles", "cargo_kg"].iter().enumerate() {
        let l = &r["ledger"][u];
        let v = ["requested", "released", "completed", "pending", "active"]
            .map(|k| l[k].as_f64().unwrap_or(f64::NAN));
        if v.iter().any(|x| !x.is_finite()) {
            return Err("nonfinite ledger".into());
        }
        let t = 1e-9 * v[0].abs().max(v[1].abs()).max(v[2].abs()).max(1.);
        if v.iter().any(|x| *x < -t)
            || (v[0] - v[1] - v[3]).abs() > t
            || (v[1] - v[2] - v[4]).abs() > t
        {
            return Err("ledger conservation differs".into());
        }
        let total = prep["calendar"][u]
            .as_f64()
            .ok_or("calendar total missing")?;
        if r["calendar_totals"][i].as_f64() != Some(total)
            || (end == 86400. && (v[0] - total).abs() > 1e-9 * total.max(1.))
        {
            return Err("calendar/day requested total differs".into());
        }
    }
    Ok(())
}
fn main() -> Result<()> {
    let a: Vec<_> = std::env::args().collect();
    if ![8, 9].contains(&a.len()) {
        return Err("usage: metroflow-v03-campaign ROOT MATRIX OUTPUT PREPARE_BIN RUN_BIN THREADS (full|PREFIX_S) [CASE]".into());
    }
    let root = Path::new(&a[1]);
    let matrix_path = Path::new(&a[2]);
    let (m, msha) = Matrix::load(matrix_path)?;
    let out = PathBuf::from(&a[3]);
    fs::create_dir(&out)?;
    let threads: usize = a[6].parse()?;
    if !(1..=256).contains(&threads) {
        return Err("threads invalid".into());
    }
    let full = a[7] == "full";
    let end = if full {
        m.horizon_s
    } else {
        a[7].parse::<f64>()?
    };
    if !end.is_finite() || end <= 0. || end > m.horizon_s || end % 10. != 0. {
        return Err("prefix must be positive aligned seconds".into());
    }
    let selected: Vec<_> = m
        .cases
        .iter()
        .filter(|c| a.get(8).is_none_or(|s| s == &c.id))
        .collect();
    if selected.is_empty() {
        return Err("case absent".into());
    }
    let prep_sha = digest(Path::new(&a[4]))?;
    let run_sha = digest(Path::new(&a[5]))?;
    let mut report = json!({"schema":"metroflow_v03_rust_campaign_v1","mode":if full{"FULL"}else{"PREFIX_ONLY"},"matrix_sha256":msha,"prepare_binary_sha256":prep_sha,"run_binary_sha256":run_sha,"threads":threads,"required_full_runs":m.cases.len()*m.repeat,"completed_full_runs":0,"status":"RUNNING","cases":[]});
    atomic(&out.join("RECEIPT.json"), &report)?;
    let mut completed = 0;
    let mut all_ok = true;
    for case in selected {
        let mut case_report = json!({"case":case.id,"runs":[],"status":"RUNNING"});
        let dir = out.join(&case.id);
        fs::create_dir(&dir)?;
        let mut coarse_hashes = vec![];
        let mut coarse_prefix = None;
        let mut fine_prefix = None;
        let mut resumed = 0;
        'steps: for step in if full { vec![10., 5.] } else { vec![10.] } {
            let manifest = dir.join(format!("step{step}.manifest.json"));
            let prepfile = dir.join(format!("step{step}.prepare.json"));
            let mut c = Command::new(&a[4]);
            c.arg(root)
                .arg(matrix_path)
                .arg(&case.id)
                .arg(threads.to_string())
                .arg(step.to_string())
                .arg(&manifest)
                .arg(&prepfile);
            let (ok, timeout, prep_wall) = launch(
                c,
                &dir.join(format!("prep{step}")),
                Duration::from_secs(m.limits.wall_s),
            )?;
            if !ok {
                case_report["failure"] = json!({"stage":"prepare","timeout":timeout});
                all_ok = false;
                break;
            }
            let prep = read(&prepfile)?;
            if prep["matrix_sha256"] != msha
                || prep["population"].as_f64() != Some(m.population as f64)
                || prep["peak_rss_bytes"]
                    .as_u64()
                    .is_none_or(|x| x > m.limits.peak_rss_bytes)
            {
                return Err("preparation binding differs".into());
            }
            let hash = digest(&manifest)?;
            let repeat = if full && step == 10. { m.repeat } else { 1 };
            for rep in 0..repeat {
                let horizon = if step == 5. { 28800. } else { end };
                let replay = if full { step == 10. && rep == 2 } else { true };
                let replay_at = if full {
                    43200.
                } else {
                    (end / 20.).floor() * 10.
                };
                let replay = replay && replay_at > 0.;
                let stem = dir.join(format!("dt{step}-r{rep}"));
                let result = stem.with_extension("json");
                let ck = stem.with_extension("bin");
                let mut c = Command::new(&a[5]);
                c.arg(&manifest)
                    .arg(horizon.to_string())
                    .arg(threads.to_string())
                    .arg(&result)
                    .arg(&ck)
                    .env(
                        "METROFLOW_NATIVE_SEGMENT_S",
                        if full { "3600" } else { "30" },
                    )
                    .env_remove("METROFLOW_NATIVE_REPLAY_AT_S");
                if replay {
                    c.env("METROFLOW_NATIVE_REPLAY_AT_S", replay_at.to_string());
                }
                let remain = (m.limits.wall_s as f64 - prep_wall).max(0.);
                let (ok, timeout, wall) = launch(c, &stem, Duration::from_secs_f64(remain))?;
                let mut row = if result.exists() {
                    read(&result)?
                } else {
                    json!({"status":if timeout{"BLOCKED_RESOURCE"}else{"BLOCKED"},"last_valid_checkpoint_exists":ck.exists()})
                };
                row["step_s"] = json!(step);
                row["total_wall_s"] = json!(wall + prep_wall);
                row["replay_requested"] = json!(replay);
                row["timeout"] = json!(timeout);
                let valid = ok
                    && wall + prep_wall <= m.limits.wall_s as f64
                    && validate(&row, horizon, step, &prep, &hash, replay).is_ok()
                    && row["checkpoint_sha256"] == digest(&ck)?
                    && row["executable_sha256"] == run_sha;
                row["validated"] = json!(valid);
                if let Some(t) = row["tick_times_s"].as_array() {
                    let mut ts: Vec<_> = t.iter().filter_map(Value::as_f64).collect();
                    ts.sort_by(f64::total_cmp);
                    if !ts.is_empty() {
                        row["tick_p50_s"] = json!(ts[(ts.len() - 1) / 2]);
                        row["tick_p95_s"] = json!(ts[(ts.len() - 1) * 95 / 100]);
                    }
                }
                case_report["runs"]
                    .as_array_mut()
                    .unwrap()
                    .push(row.clone());
                atomic(&dir.join("case.json"), &case_report)?;
                if !valid {
                    all_ok = false;
                    case_report["failure"] =
                        json!({"stage":"execute_or_validate","step_s":step,"repeat":rep});
                    break 'steps;
                }
                if full && step == 10. {
                    completed += 1;
                    coarse_hashes.push(row["checkpoint_sha256"].clone());
                    resumed += usize::from(replay);
                    if coarse_prefix.is_none() {
                        coarse_prefix = Some(row["refinement_prefix"].clone())
                    }
                }
                if full && step == 5. {
                    fine_prefix = Some(row["refinement_prefix"].clone())
                }
            }
        }
        let replay_ok = full
            && coarse_hashes.len() == m.repeat
            && coarse_hashes.windows(2).all(|w| w[0] == w[1])
            && resumed == 1;
        let refinement = coarse_prefix
            .as_ref()
            .zip(fine_prefix.as_ref())
            .filter(|(a, b)| a["time_s"] == 28800. && b["time_s"] == 28800.);
        let has_refinement = refinement.is_some();
        if let Some((a, b)) = refinement {
            let mut delta = serde_json::Map::new();
            for u in ["persons", "vehicles", "cargo_kg"] {
                let mut d = serde_json::Map::new();
                for k in ["requested", "released", "completed", "pending", "active"] {
                    if let (Some(x), Some(y)) =
                        (a["ledger"][u][k].as_f64(), b["ledger"][u][k].as_f64())
                    {
                        d.insert(k.into(), json!(y - x));
                    }
                }
                delta.insert(u.into(), json!(d));
            }
            case_report["refinement_deltas"] = json!(delta);
        }
        case_report["checkpoint_replay"] = json!(replay_ok);
        case_report["refinement_status"] = json!(if has_refinement {
            "REQUIRES_SEPARATE_REVIEW"
        } else {
            "NOT_RUN_OR_INCOMPLETE"
        });
        case_report["status"] = json!(if case_report.get("failure").is_some() {
            "BLOCKED"
        } else if full && replay_ok && has_refinement {
            "MEASURED_REQUIRES_REVIEW"
        } else if !full {
            "PREFIX_EXECUTED"
        } else {
            "BLOCKED"
        });
        if full && (!replay_ok || !has_refinement) {
            all_ok = false
        }
        atomic(&dir.join("case.json"), &case_report)?;
        report["cases"].as_array_mut().unwrap().push(case_report);
        report["completed_full_runs"] = json!(completed);
        atomic(&out.join("RECEIPT.json"), &report)?;
    }
    if digest(Path::new(&a[4]))? != prep_sha
        || digest(Path::new(&a[5]))? != run_sha
        || digest(matrix_path)? != msha
    {
        return Err("binary or matrix changed during campaign".into());
    }
    report["status"] = json!(if !all_ok {
        "BLOCKED"
    } else if !full {
        "PREFIX_ONLY_NOT_ACCEPTANCE"
    } else if completed == m.cases.len() * m.repeat {
        "MEASURED_REQUIRES_REVIEW"
    } else {
        "BLOCKED_INCOMPLETE_MATRIX"
    });
    atomic(&out.join("RECEIPT.json"), &report)?;
    println!(
        "{}",
        json!({"status":report["status"],"completed_full_runs":completed,"receipt":out.join("RECEIPT.json")})
    );
    if !all_ok {
        std::process::exit(2)
    }
    Ok(())
}
