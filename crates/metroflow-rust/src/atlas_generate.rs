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
