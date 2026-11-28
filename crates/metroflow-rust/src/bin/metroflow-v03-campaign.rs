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
    File::open(p.parent().unwrap_or_else(|| Path::new(".")))?.sync_all()?;
    Ok(())
}
fn launch(mut c: Command, stem: &Path, limit: Duration) -> Result<(bool, bool, f64)> {
    c.stdout(Stdio::from(File::create(stem.with_extension("stdout"))?))
        .stderr(Stdio::from(File::create(stem.with_extension("stderr"))?));
    // Both preparation and native simulation are subject to the same 8 GiB
    // address-space ceiling. No child can silently bypass the production cap.
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::process::CommandExt;
        // SAFETY: only async-signal-safe getrlimit/setrlimit in the child.
        unsafe {
            c.pre_exec(|| {
                let mut lim = libc::rlimit {
                    rlim_cur: 0,
                    rlim_max: 0,
                };
                if libc::getrlimit(libc::RLIMIT_AS, &mut lim) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                lim.rlim_cur = lim.rlim_cur.min(lim.rlim_max).min(8 * 1024u64.pow(3));
                if libc::setrlimit(libc::RLIMIT_AS, &lim) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }
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
        || r["start_s"].as_f64() != Some(0.)
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
    if r["address_space_limit_bytes"]
        .as_u64()
        .is_none_or(|x| x > 8 * 1024u64.pow(3))
        || r["byte_budget"].as_u64() != Some(6 * 1024u64.pow(3))
        || r["peak_rss_bytes"]
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
/// Successful run must also survive an independent native load.
fn recovered_matches(run:&Value,recovered:&Value,hash:&str,ck_hash:&str,bin_hash:&str)->bool{
    recovered["status"]=="RECOVERED_CHECKPOINT_ONLY"
        && recovered["manifest_sha256"]==hash
        && recovered["checkpoint_sha256"]==ck_hash
        && recovered["executable_sha256"]==bin_hash
        && recovered["python_runtime_dependency"]=="none"
        && recovered["address_space_limit_bytes"].as_u64().is_some_and(|x|x<=8*1024u64.pow(3))
        && recovered["peak_rss_bytes"].as_u64().is_some_and(|x|x<=8*1024u64.pow(3))
        && ["time_s","native_identity","city_identity","schedule_identity","ledger","road_totals","road_class_ledgers","calendar_totals","byte_budget"].iter().all(|k|!run[*k].is_null()&&run[*k]==recovered[*k])
        && (if run.get("canonical_logical_sha256").is_some()||recovered.get("canonical_logical_sha256").is_some(){
            run["canonical_logical_sha256"].as_str().is_some_and(|h|h.len()==64&&h.bytes().all(|b|b.is_ascii_hexdigit()))
                &&run["canonical_logical_sha256"]==recovered["canonical_logical_sha256"]
                &&run["canonical_logical_bytes"].as_u64().is_some_and(|n|n>0)
                &&run["canonical_logical_bytes"]==recovered["canonical_logical_bytes"]
        }else{true})
}
fn valid_refinement(r: &Value) -> bool {
    if r["time_s"].as_f64() != Some(28800.) {
        return false;
    }
    for u in ["persons", "vehicles", "cargo_kg"] {
        let v = ["requested", "released", "completed", "pending", "active"]
            .map(|k| r["ledger"][u][k].as_f64().unwrap_or(f64::NAN));
        if v.iter().any(|x| !x.is_finite()) {
            return false;
        }
        let t = 1e-9 * v[0].abs().max(v[1].abs()).max(v[2].abs()).max(1.);
        if v.iter().any(|x| *x < -t)
            || (v[0] - v[1] - v[3]).abs() > t
            || (v[1] - v[2] - v[4]).abs() > t
        {
            return false;
        }
    }
    true
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn independent_recovery_rejects_wrong_clock_and_ledger(){
        let run=json!({"time_s":60.,"native_identity":"native","city_identity":"city","schedule_identity":"schedule","ledger":{"persons":{"active":1.}},"road_totals":[1.],"road_class_ledgers":[[1.]],"calendar_totals":[1.],"byte_budget":6442450944u64});
        let mut rec=run.clone();
        for (k,v) in [("status",json!("RECOVERED_CHECKPOINT_ONLY")),("manifest_sha256",json!("m")),("checkpoint_sha256",json!("c")),("executable_sha256",json!("b")),("python_runtime_dependency",json!("none")),("address_space_limit_bytes",json!(8589934592u64)),("peak_rss_bytes",json!(1000u64))]{rec[k]=v;}
        assert!(recovered_matches(&run,&rec,"m","c","b"));
        rec["time_s"]=json!(50.);assert!(!recovered_matches(&run,&rec,"m","c","b"));
        rec["time_s"]=json!(60.);rec["ledger"]["persons"]["active"]=json!(2.);assert!(!recovered_matches(&run,&rec,"m","c","b"));
        rec["ledger"]=run["ledger"].clone();let mut run=run;
        run["canonical_logical_sha256"]=json!("a".repeat(64));run["canonical_logical_bytes"]=json!(1000u64);
        assert!(!recovered_matches(&run,&rec,"m","c","b"));
        rec["canonical_logical_sha256"]=run["canonical_logical_sha256"].clone();rec["canonical_logical_bytes"]=json!(1000u64);
        assert!(recovered_matches(&run,&rec,"m","c","b"));
        rec["canonical_logical_sha256"]=json!("b".repeat(64));assert!(!recovered_matches(&run,&rec,"m","c","b"));
    }
    #[test]
    fn missing_refinement_rows_cannot_be_counted() {
        let l = json!({"requested":10.,"released":7.,"completed":3.,"pending":3.,"active":4.});
        let mut x = json!({"time_s":28800.,"ledger":{"persons":l,"vehicles":l,"cargo_kg":l}});
        assert!(valid_refinement(&x));
        x["ledger"]["persons"]["active"] = Value::Null;
        assert!(!valid_refinement(&x));
    }
}
fn main() -> Result<()> {
    let a: Vec<_> = std::env::args().collect();
    if ![8, 9].contains(&a.len()) {
        return Err("usage: metroflow-v03-campaign ROOT MATRIX OUTPUT PREPARE_BIN RUN_BIN THREADS (full|PREFIX_S|prefix-pair:PREFIX_S) [CASE]".into());
    }
    let root = Path::new(&a[1]);
    let matrix_path = Path::new(&a[2]);
    let (m, msha) = Matrix::load(matrix_path)?;
    if msha != "1eb90b60d260feff915b785ed4d425dde0bcc1601ad3ad8200640c73d765655a" {
        return Err("original release matrix byte binding differs".into());
    }
    let out = PathBuf::from(&a[3]);
    fs::create_dir(&out)?;
    let threads: usize = a[6].parse()?;
    if !(1..=256).contains(&threads) {
        return Err("threads invalid".into());
    }
    let full = a[7] == "full";
    let prefix_pair=a[7].strip_prefix("prefix-pair:");
    let diagnostic_timeout = std::env::var("METROFLOW_CAMPAIGN_PREFIX_TIMEOUT_S")
        .ok()
        .map(|x| x.parse::<f64>())
        .transpose()?;
    if diagnostic_timeout
        .is_some_and(|x| full || !x.is_finite() || x <= 0. || x > m.limits.wall_s as f64)
    {
        return Err("diagnostic timeout permitted only for bounded prefix".into());
    }
    let end = if full {
        m.horizon_s
    } else {
        prefix_pair.unwrap_or(&a[7]).parse::<f64>()?
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
    let mut report = json!({"schema":"metroflow_v03_rust_campaign_v1","mode":if full{"FULL"}else if prefix_pair.is_some(){"PREFIX_PAIR_ONLY"}else{"PREFIX_ONLY"},"matrix_sha256":msha,"prepare_binary_sha256":prep_sha,"run_binary_sha256":run_sha,"threads":threads,"required_full_runs":m.cases.len()*m.repeat,"completed_full_runs":0,"status":"RUNNING","cases":[]});
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
        let mut diagnostic_pair:Vec<Value>=vec![];
        let mut resumed = 0;
        'steps: for step in if full || prefix_pair.is_some() { vec![10., 5.] } else { vec![10.] } {
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
                let horizon = if full && step == 5. { 28800. } else { end };
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
                let remain = (m.limits.wall_s as f64 - prep_wall)
                    .max(0.)
                    .min(diagnostic_timeout.unwrap_or(f64::INFINITY));
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
                let validation: Result<()> = (|| {
                    if !ok {
                        return Err(if timeout {
                            "external wall timeout"
                        } else {
                            "child returned nonzero"
                        }
                        .into());
                    }
                    if wall + prep_wall > m.limits.wall_s as f64 {
                        return Err("wall limit exceeded".into());
                    }
                    validate(&row, horizon, step, &prep, &hash, replay)?;
                    if row["checkpoint_sha256"] != digest(&ck)?
                        || row["executable_sha256"] != run_sha
                    {
                        return Err("checkpoint or binary digest differs".into());
                    }
                    Ok(())
                })();
                let mut valid = validation.is_ok();
                row["validation_error"] = json!(validation.err().map(|e| e.to_string()));
                row["validated"] = json!(valid);
                if ck.is_file() {
                    // Recovery is an explicitly separate diagnostic, never
                    // credited to the measured run or its original horizon.
                    let recover_file = stem.with_extension("recovery.json");
                    let mut c = Command::new(&a[5]);
                    c.arg("--recover")
                        .arg(&manifest)
                        .arg(&ck)
                        .arg(&recover_file)
                        .arg(threads.to_string());
                    let (rok, rtimed, rwall) = launch(
                        c,
                        &stem.with_extension("recovery"),
                        Duration::from_secs(120),
                    )?;
                    let recovery = if rok && recover_file.is_file() {
                        let r = read(&recover_file)?;
                        if r["status"] == "RECOVERED_CHECKPOINT_ONLY"
                            && r["manifest_sha256"] == hash
                            && r["checkpoint_sha256"] == digest(&ck)?
                            && r["executable_sha256"] == run_sha
                            && r["city_identity"] == prep["city_identity"]
                            && r["schedule_identity"] == prep["schedule_identity"]
                            && r["time_s"].as_f64().is_some_and(|t| {
                                t.is_finite()
                                    && t >= 0.
                                    && t <= horizon
                                    && (t / step - (t / step).round()).abs() < 1e-8
                            })
                        {
                            let matched=valid&&recovered_matches(&row,&r,&hash,&digest(&ck)?,&run_sha);
                            json!({"status":"RECOVERED_CHECKPOINT_ONLY","time_s":r["time_s"],"checkpoint_sha256":r["checkpoint_sha256"],"receipt":recover_file,"diagnostic_wall_s":rwall,"matches_successful_run":matched})
                        } else {
                            json!({"status":"RECOVERY_BINDING_REJECTED","diagnostic_wall_s":rwall})
                        }
                    } else {
                        json!({"status":"RECOVERY_NOT_VERIFIED","timeout":rtimed,"diagnostic_wall_s":rwall})
                    };
                    if valid && recovery["matches_successful_run"]!=true {
                        valid=false;row["validated"]=json!(false);row["validation_error"]=json!("independent checkpoint recovery differs");
                    }
                    row["recovery"] = recovery;
                }
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
                    case_report["failure"] = json!({"stage":"execute_or_validate","step_s":step,"repeat":rep,"reason":row["validation_error"],"native_failure":row["failure"]});
                    break 'steps;
                }
                if prefix_pair.is_some(){
                    diagnostic_pair.push(json!({"step_s":step,"time_s":row["time_s"],"ledger":row["ledger"],"road_totals":row["road_totals"],"checkpoint_sha256":row["checkpoint_sha256"],"validated":row["validated"]}));
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
        if prefix_pair.is_some(){
            case_report["prefix_pair"]=json!({"scope":"matched short prefixes only; no original 8-hour refinement credit","rows":diagnostic_pair,"both_verified":diagnostic_pair.len()==2});
        }
        let replay_ok = full
            && coarse_hashes.len() == m.repeat
            && coarse_hashes.windows(2).all(|w| w[0] == w[1])
            && resumed == 1;
        let refinement = coarse_prefix
            .as_ref()
            .zip(fine_prefix.as_ref())
            .filter(|(a, b)| valid_refinement(a) && valid_refinement(b));
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
        case_report["checkpoint_replay"] = if full {
            json!(replay_ok)
        } else {
            json!("NOT_FULL_DAY_TEST")
        };
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
    if !all_ok || report["status"] == "BLOCKED_INCOMPLETE_MATRIX" {
        std::process::exit(2)
    }
    Ok(())
}
