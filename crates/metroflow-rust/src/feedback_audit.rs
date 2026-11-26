//! Read-only R01/M04 bridge for actual completed native route observations.
//! The R02 link-cost surface is deliberately not fed route-total observations.
use crate::{
    causal::{Channel, Information, Observation, Prior, Report},
    core_error::{CoreError, CoreResult},
    frozen_city::hash,
    lagged_growth::compile_accessibility,
    v1_calendar::FactorizedDeclaration,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    time::Instant,
};
fn bad(x: impl Into<String>) -> CoreError {
    CoreError::value(x)
}
pub fn audit(manifest: Value, receipt: Value, threads: usize) -> CoreResult<Value> {
    if threads == 0 || threads > 256 {
        return Err(bad("worker count"));
    }
    if receipt["city_identity"] != manifest["calendar"]["city_identity"]
        || receipt["schedule_identity"] != manifest["calendar"]["schedule_identity"]
        || receipt["status"] != "EXECUTED_FOR_REVIEW"
    {
        return Err(bad("native observation/manifest binding"));
    }
    let now = receipt["time_s"]
        .as_f64()
        .ok_or_else(|| bad("native clock"))?;
    let obs: Vec<Observation> =
        serde_json::from_value(receipt["completed_observations"]["observations"].clone())
            .map_err(|e| bad(e.to_string()))?;
    if obs.is_empty()
        || obs.len() > 20000
        || obs.iter().any(|o| {
            o.stamp_s != now
                || o.key.kind != "route"
                || o.source != "T04_completed_outlet"
                || o.version != receipt["native_identity"].as_str().unwrap_or("")
        })
    {
        return Err(bad("invalid native completed observations"));
    }
    // Re-enumerate exact native calendar independently for semantic tag->block
    // binding; do not guess a block from coordinates or route costs.
    let t = Instant::now();
    let c: FactorizedDeclaration =
        serde_json::from_value(manifest["calendar"].clone()).map_err(|e| bad(e.to_string()))?;
    let cal = c.compile(6 * 1024usize.pow(3))?;
    let wanted: BTreeSet<_> = obs
        .iter()
        .filter(|o| o.key.class == "car")
        .map(|o| o.key.id.as_str())
        .collect();
    let mut mapping = BTreeMap::new();
    // Route IDs are lossless native calendar text. Only requested car tags are retained.
    for leg in cal.owned_legs() {
        let labels = cal.owned_labels();
        if labels[leg.metadata[3] as usize] != "\"car\"" {
            continue;
        }
        let id = cal.text(leg.id).ok_or_else(|| bad("calendar leg tag"))?;
        if !wanted.contains(id.as_str()) {
            continue;
        }
        let label: Value = serde_json::from_str(&labels[leg.metadata[1] as usize])
            .map_err(|e| bad(e.to_string()))?;
        let b = label["block_id"]
            .as_str()
            .ok_or_else(|| bad("completed car destination block"))?;
        if mapping.insert(id, b.to_owned()).is_some() {
            return Err(bad("ambiguous route tag"));
        }
    }
    if mapping.len() != wanted.len() {
        return Err(bad("completed car tag absent from calendar"));
    }
    drop(cal);
    let binding_s = t.elapsed().as_secs_f64();
    let city = receipt["city_identity"].as_str().unwrap();
    let rows: Vec<_> = obs
        .iter()
        .filter(|o| o.key.class == "car")
        .map(|o| (mapping[&o.key.id].clone(), o.clone()))
        .collect();
    // Explicit diagnostic prior, never an inferred live cost or input to production OD.
    let priors: Vec<_> = obs
        .iter()
        .map(|o| Prior {
            key: o.key.clone(),
            seconds: 100.,
            version: "diagnostic-prior".into(),
            measure: o.measure.clone(),
        })
        .collect();
    let channel = Channel {
        id: "completed".into(),
        kind: "server".into(),
        coverage: priors.iter().map(|p| p.key.clone()).collect(),
        radius_m: f64::INFINITY,
        latency_s: 5.,
        propagation_mps: 100.,
        max_age_s: 100.,
    };
    let im = Information::new(priors, vec![channel], 20000)?;
    let reports: Vec<_> = obs
        .iter()
        .cloned()
        .map(|observation| Report {
            channel: "completed".into(),
            observation,
        })
        .collect();
    let state = im.advance(&im.initial(), now, &reports)?;
    let one = rayon::ThreadPoolBuilder::new()
        .num_threads(1)
        .build()
        .map_err(|e| bad(e.to_string()))?;
    let many = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .map_err(|e| bad(e.to_string()))?;
    let a = one.install(|| im.observe(&state, [0., 0.], "origin"))?;
    if a.coverage_fraction != 0. {
        return Err(bad("same-tick delivery leaked"));
    }
    let next = im.advance(&state, now + 5., &[])?;
    let b = one.install(|| im.observe(&next, [0., 0.], "origin"))?;
    let other = many.install(|| im.observe(&next, [0., 0.], "origin"))?;
    if b != other
        || b.coverage_fraction != 1.
        || b.costs
            .iter()
            .zip(&obs)
            .any(|(d, o)| d.seconds.to_bits() != o.seconds.to_bits())
    {
        return Err(bad("causal delivery parity"));
    }
    let access = one.install(|| compile_accessibility(city, &rows, now))?;
    if access != many.install(|| compile_accessibility(city, &rows, now))? {
        return Err(bad("accessibility worker parity"));
    }
    if compile_accessibility(city, &rows, now - 0.001).is_ok() {
        return Err(bad("future accessibility admitted"));
    }
    let mut serial = Vec::new();
    let mut parallel = Vec::new();
    for i in 0..9 {
        for parallel_run in if i % 2 == 0 {
            [false, true]
        } else {
            [true, false]
        } {
            let pool = if parallel_run { &many } else { &one };
            let t = Instant::now();
            let result = pool.install(|| im.observe(&next, [0., 0.], "origin"))?;
            let elapsed = t.elapsed().as_secs_f64();
            if result != b {
                return Err(bad("observation replay differs"));
            }
            if parallel_run {
                parallel.push(elapsed)
            } else {
                serial.push(elapsed)
            }
        }
    }
    serial.sort_by(f64::total_cmp);
    parallel.sort_by(f64::total_cmp);
    let semantic = serde_json::to_vec(&(&b, &access)).map_err(|e| bad(e.to_string()))?;
    Ok(
        json!({"schema":"metroflow_native_feedback_audit_v1","scope":"actual car route observations -> destination block conditional accessibility; explicit diagnostic prior/latency; no physical suffix mutation or next-day city/demand rebuild","city_identity":city,"time_s":now,"observed_routes":obs.len(),"car_route_bindings":mapping.len(),"accessibility_blocks":access.costs.len(),"calendar_binding_s":binding_s,"coverage_at_stamp":a.coverage_fraction,"coverage_after_latency":b.coverage_fraction,"future_accessibility_rejected":true,"one_many_exact":true,"threads":threads,"serial_s":serial,"parallel_s":parallel,"serial_median_s":serial[4],"parallel_median_s":parallel[4],"semantic_sha256":hash(&semantic),"accessibility":access}),
    )
}
