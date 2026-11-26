//! Original V1 atlas construction without reading a frozen map. The output is
//! a new native canonical snapshot with explicit (different) byte identity.
use crate::{
    atlas_portals, atlas_roads, atlas_zoning,
    core_error::{CoreError, CoreResult},
    frozen_city,
    terrain_validation::Landscape,
};
use serde_json::{json, Value};
use std::time::Instant;
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
pub fn generate(
    style: &str,
    kind: &str,
    l: f64,
    n: usize,
    seed: u64,
    population: u64,
    portals: bool,
) -> CoreResult<(Value, Value)> {
    let started = Instant::now();
    let roads = atlas_roads::generate(style, kind, l, n, seed)?;
    let road_s = started.elapsed().as_secs_f64();
    let start = Instant::now();
    let mut blocks = atlas_zoning::zoning(&roads, kind, l, population)?;
    let zoning_s = start.elapsed().as_secs_f64();
    let residents = blocks.iter().map(|b| b.residents).sum::<u64>();
    let jobs = blocks.iter().map(|b| b.jobs).sum::<u64>();
    blocks.sort_by(|a, b| a.id.cmp(&b.id));
    let mut landscape = serde_json::to_value(&roads.land).map_err(|e| bad(e.to_string()))?;
    landscape["kind"] = json!(kind);
    landscape["seed"] = json!(seed);
    let name = match kind {
        "river" => "river",
        "valley" => "valley_river",
        "coast" => "sea",
        "lake" => "lake",
        _ => "",
    };
    for p in landscape["water"].as_array_mut().unwrap() {
        p["name"] = json!(name)
    }
    for p in landscape["protected"].as_array_mut().unwrap() {
        p["name"] = json!("reserve")
    }
    let mut value = json!({"schema":"metroflow_city_v1","identity_scheme":"metroflow_native_city_v1","identity":"","roadmap":{"style":style,"terrain":roads.land.terrain,"nodes":roads.nodes,"sections":roads.sections,"rejected":roads.rejected.iter().collect::<Vec<_>>()},"landscape":landscape,"blocks":blocks,"portals":[],"requested_population":population,"unplaced_residents":population-residents});
    let start = Instant::now();
    let (bound, city) = frozen_city::bind_snapshot(value.clone())?;
    value = bound;
    let mut entry_count = 0usize;
    let mut backbone = 0usize;
    let mut evidence = vec![];
    if portals {
        let (entries, n) = atlas_portals::generate(&city, &roads.land)?;
        entry_count = entries.len();
        backbone = n;
        value["portals"] = json!(entries
            .iter()
            .map(|e| json!({"id":e.id,"block_id":e.block_id,"node_id":e.node_id}))
            .collect::<Vec<_>>());
        evidence = entries;
        value["identity"] = json!("");
        value = frozen_city::bind_snapshot(value)?.0;
    }
    let validation_s = start.elapsed().as_secs_f64();
    let served = blocks
        .iter()
        .filter(|b| evidence.iter().any(|e| e.block_id == b.id))
        .map(|b| b.residents)
        .sum::<u64>();
    let report = json!({"schema":"metroflow_native_atlas_receipt_v1","identity":value["identity"],"style":style,"terrain":kind,"size_m":l,"resolution":n,"seed":seed,"population":population,"residents":residents,"unplaced_residents":population-residents,"jobs":jobs,"nodes":roads.nodes.len(),"sections":roads.sections.len(),"blocks":blocks.len(),"bridges":roads.sections.iter().filter(|s|s.facility=="bridge").count(),"bridge_candidates":roads.bridge_candidates,"centers":roads.centers,"gateways":roads.gateways,"unserved_centers":roads.unserved_centers,"orbital_unreachable":roads.orbital_unreachable,"orbital_connectors":roads.orbital_connectors,"removed":roads.removed,"phases":roads.phases,"registered_portals":entry_count,"registered_served_residents":served,"registered_unserved_residents":population-served,"backbone_links":backbone,"entry_evidence":evidence,"road_s":road_s,"zoning_s":zoning_s,"validation_and_portal_s":validation_s,"wall_s":started.elapsed().as_secs_f64(),"scope":"original terrain-city generator, depth-zero entry selection; distinct Rust identity; no historical byte identity or separate restored interchange grammar claim"});
    Ok((value, report))
}

/// Compare the actual independently generated geometry to immutable archives.
/// Ignore representation-only identity and float serialization differences;
/// every discrete field is exact and each physical numeric field bounded.
pub fn compare_snapshots(new: &Value, old: &Value) -> CoreResult<Value> {
    use std::collections::BTreeMap;
    let mut mismatch = vec![];
    let mut numeric = 0usize;
    let mut max_scaled = 0f64;
    let mut max_abs = 0f64;
    fn compare(
        a: &Value,
        b: &Value,
        path: &str,
        numeric: &mut usize,
        max_scaled: &mut f64,
        max_abs: &mut f64,
        mismatch: &mut Vec<String>,
    ) {
        match (a, b) {
            (Value::Number(x), Value::Number(y)) => {
                if x.is_i64() && y.is_i64() || x.is_u64() && y.is_u64() {
                    if a != b && mismatch.len() < 40 {
                        mismatch.push(format!("{path}: discrete {a} != {b}"));
                    }
                    return;
                }
                let x = x.as_f64().unwrap();
                let y = y.as_f64().unwrap();
                let diff = (x - y).abs();
                let err = diff / x.abs().max(y.abs()).max(1.);
                *numeric += 1;
                *max_scaled = max_scaled.max(err);
                *max_abs = max_abs.max(diff);
                if diff > 1e-8 + 1e-10 * x.abs().max(y.abs()) && mismatch.len() < 40 {
                    mismatch.push(format!("{path}: {x} != {y}"))
                }
            }
            (Value::Array(a), Value::Array(b)) => {
                if a.len() != b.len() && mismatch.len() < 40 {
                    mismatch.push(format!("{path}: len {} != {}", a.len(), b.len()))
                }
                for (i, (x, y)) in a.iter().zip(b).enumerate() {
                    compare(
                        x,
                        y,
                        &format!("{path}[{i}]"),
                        numeric,
                        max_scaled,
                        max_abs,
                        mismatch,
                    )
                }
            }
            (Value::Object(a), Value::Object(b)) => {
                for (k, x) in a {
                    if let Some(y) = b.get(k) {
                        compare(
                            x,
                            y,
                            &format!("{path}.{k}"),
                            numeric,
                            max_scaled,
                            max_abs,
                            mismatch,
                        )
                    } else if mismatch.len() < 40 {
                        mismatch.push(format!("{path}.{k}: absent in archive"))
                    }
                }
                for k in b.keys() {
                    if !a.contains_key(k) && mismatch.len() < 40 {
                        mismatch.push(format!("{path}.{k}: absent in native"))
                    }
                }
            }
            _ => {
                if a != b && mismatch.len() < 40 {
                    mismatch.push(format!("{path}: {a} != {b}"))
                }
            }
        }
    }
    for k in [
        "requested_population",
        "unplaced_residents",
        "landscape",
        "roadmap",
        "blocks",
        "portals",
    ] {
        compare(
            &new[k],
            &old[k],
            k,
            &mut numeric,
            &mut max_scaled,
            &mut max_abs,
            &mut mismatch,
        );
    }
    Ok(
        json!({"semantic_match":mismatch.is_empty(),"mismatch_samples":mismatch,"numeric_fields":numeric,"max_scaled_difference":max_scaled,"max_absolute_difference":max_abs,"tolerance":"abs 1e-8 + rel 1e-10; integer, strings, topology, sequence exact"}),
    )
}
pub fn compare_archive(
    root: &std::path::Path,
    row: &Value,
    threads: usize,
    portals: bool,
) -> CoreResult<Value> {
    let source = row["source"].as_str().ok_or_else(|| bad("source absent"))?;
    if std::path::Path::new(source)
        .file_name()
        .and_then(|p| p.to_str())
        != Some(source)
    {
        return Err(bad("archive source leaf"));
    }
    let path = root.join("artifacts/v1/map_audit").join(source);
    let raw = frozen_city::load_bytes(&path)?;
    if frozen_city::hash(&raw) != row["source_sha256"].as_str().unwrap_or("") {
        return Err(bad("archive byte hash"));
    }
    let mut old: Value = frozen_city::from_xz(&raw)?;
    if portals {
        // Bind the original portal patch for the three release cases.
        let idx = match (row["case"].as_str(), row["seed"].as_u64()) {
            (Some("polycentric_river"), Some(17)) => 4,
            (Some("coastal_port"), Some(41)) => 11,
            (Some("valley_city"), Some(7)) => 12,
            _ => return Err(bad("no selected release patch")),
        };
        let base = root.join("artifacts/v1_portal_resolution_20261027");
        let audit: Value = serde_json::from_slice(&frozen_city::load_bytes(
            &base.join(format!("{idx:02}.audit.json")),
        )?)
        .map_err(|e| bad(e.to_string()))?;
        let bytes = frozen_city::load_bytes(
            &base.join(audit["patch"].as_str().ok_or_else(|| bad("patch"))?),
        )?;
        if frozen_city::hash(&bytes) != audit["patch_sha256"].as_str().unwrap_or("") {
            return Err(bad("patch hash"));
        }
        let patch: Value = frozen_city::from_xz(&bytes)?;
        if patch["base_source"] != row["source"] || patch["base_sha256"] != row["source_sha256"] {
            return Err(bad("patch source binding"));
        }
        old["portals"] = patch["portals"].clone();
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .map_err(|e| bad(e.to_string()))?;
    let result = pool.install(|| {
        generate(
            row["style"].as_str().unwrap_or(""),
            row["terrain"].as_str().unwrap_or(""),
            8000.,
            row["resolution"].as_u64().unwrap_or(0) as usize,
            row["seed"].as_u64().unwrap_or(0),
            row["requested_population"].as_u64().unwrap_or(100000),
            portals,
        )
    });
    let mut res = json!({"case":row["case"],"family":row["family"],"seed":row["seed"],"source":row["source"],"source_sha256":row["source_sha256"],"threads":threads,"portal_comparison":portals});
    match result {
        Ok((new, report)) => {
            res["status"] = json!("EXECUTED");
            res["comparison"] = compare_snapshots(&new, &old)?;
            res["generation"] = json!({"identity":new["identity"],"wall_s":report["wall_s"],"nodes":report["nodes"],"sections":report["sections"],"blocks":report["blocks"],"residents":report["residents"],"jobs":report["jobs"],"registered_portals":report["registered_portals"]});
        }
        Err(e) => {
            res["status"] = json!("BLOCKED");
            res["error"] = json!(e.to_string());
        }
    }
    Ok(res)
}
