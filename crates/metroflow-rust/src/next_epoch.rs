//! Actual original completed accessibility -> explicit site growth -> native
//! canonical city -> next-day factorized manifest. No current traffic hot swap.
use crate::{
    atlas_generate,
    core_error::{CoreError, CoreResult},
    frozen_city::{self, Case, Matrix},
    lagged_growth::{self, Accessibility, Block, Entry, Growth, Site},
    v1_prepare_city,
};
use serde_json::{json, Value};
use std::{collections::BTreeMap, path::Path};
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
pub fn audit(
    root: &Path,
    m: &Matrix,
    case: &Case,
    snapshot: Value,
    entry_receipt: Value,
    feedback: Value,
    archive_parity: &Value,
    step: f64,
) -> CoreResult<(Value, Value, Value, Value)> {
    let (snapshot, city) = frozen_city::bind_snapshot(snapshot)?;
    if entry_receipt["identity"] != city.identity
        || entry_receipt["seed"] != case.seed
        || entry_receipt["population"] != m.population
    {
        return Err(bad("entry receipt binding"));
    }
    let old = frozen_city::load(root, case, m.population)?;
    let row = archive_parity["rows"]
        .as_array()
        .and_then(|r| {
            r.iter()
                .find(|r| r["case"] == case.map_case && r["seed"] == case.seed)
        })
        .ok_or_else(|| bad("parity evidence missing"))?;
    if row["comparison"]["semantic_match"] != true
        || row["portal_comparison"] != true
        || row["generation"]["identity"] != city.identity
        || row["source_sha256"] != old.source_sha256
        || feedback["city_identity"] != old.identity
    {
        return Err(bad("frozen-to-generated identity bridge absent"));
    }
    if city.blocks.len() != old.blocks.len() || city.portals.len() != old.portals.len() {
        return Err(bad("source census differs"));
    }
    let ar = feedback["accessibility"].clone();
    let costs: Vec<(String, f64)> =
        serde_json::from_value(ar["costs"].clone()).map_err(|e| bad(e.to_string()))?;
    let stamp = ar["stamp_s"]
        .as_f64()
        .ok_or_else(|| bad("accessibility stamp"))?;
    let map: BTreeMap<_, _> = costs.iter().map(|(b, c)| (b.as_str(), *c)).collect();
    // Explicit scoped test policy: one physical registered site, 20 units new
    // housing, 10 incoming residents, 100 m construction cap, original 1800s
    // accessibility threshold. Select geometrically, not by a block label.
    let mut candidates = vec![];
    for e in entry_receipt["entry_evidence"]
        .as_array()
        .ok_or_else(|| bad("entry rows"))?
    {
        let block = e["block_id"].as_str().ok_or_else(|| bad("entry block"))?;
        let node = e["node_id"].as_str().ok_or_else(|| bad("entry node"))?;
        let b = city
            .blocks
            .iter()
            .find(|b| b.id == block)
            .ok_or_else(|| bad("block absent"))?;
        if b.housing_capacity == 0
            || map.get(block).is_none_or(|x| *x > 1800. || !x.is_finite())
            || e["construction_length_m"]
                .as_f64()
                .is_none_or(|x| x > 100. || x <= 0.)
        {
            continue;
        }
        if !city
            .portals
            .iter()
            .any(|p| p.block_id == block && p.node_id == node && e["id"] == p.id)
        {
            return Err(bad("entry registry differs"));
        }
        candidates.push((city.nodes[node].xyz, e));
    }
    candidates.sort_by(|(a, _), (b, _)| {
        a.iter()
            .zip(b)
            .map(|(x, y)| x.total_cmp(y))
            .find(|o| *o != std::cmp::Ordering::Equal)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let e = candidates
        .first()
        .ok_or_else(|| bad("no eligible declared growth site"))?
        .1;
    let block = e["block_id"].as_str().unwrap().to_owned();
    let id = e["id"].as_str().unwrap().to_owned();
    let node = e["node_id"].as_str().unwrap().to_owned();
    // Recompile physical entry evidence from source snapshot, not trust receipt
    // numbers. The atlas generation and full archive parity bind its geometry.
    let land: crate::terrain_validation::Landscape =
        serde_json::from_value(snapshot["landscape"].clone()).map_err(|x| bad(x.to_string()))?;
    let corridor: [[f64; 2]; 2] =
        serde_json::from_value(e["corridor"].clone()).map_err(|x| bad(x.to_string()))?;
    let b = city.blocks.iter().find(|b| b.id == block).unwrap();
    let poly = crate::v1_area::canonical(
        b.boundary
            .iter()
            .map(|n| {
                let p = city.nodes[n].xyz;
                [p[0], p[1]]
            })
            .collect(),
    )?;
    let door = city.nodes[&node].xyz;
    if corridor[1] != [door[0], door[1]]
        || !crate::v1_area::segment_inside(corridor[0], corridor[1], &poly)
        || !crate::terrain_validation::segment_clear(corridor[0], corridor[1], &land.water, 2.)
        || !crate::terrain_validation::segment_clear(corridor[0], corridor[1], &land.protected, 2.)
    {
        return Err(bad("entry corridor invalid"));
    }
    let (_, length, grade) = crate::atlas_roads::ground(&land.terrain, corridor[0], corridor[1])?;
    if length <= 0.
        || length > 100.
        || grade > 0.12
        || (length - e["construction_length_m"].as_f64().unwrap()).abs() > 1e-8
    {
        return Err(bad("entry physical declaration differs"));
    }
    let blocks = city
        .blocks
        .iter()
        .map(|b| Block {
            id: b.id.clone(),
            residents: b.residents,
            housing_capacity: b.housing_capacity,
        })
        .collect();
    let model = Growth::new(
        &city.identity,
        blocks,
        vec![Entry {
            id: id.clone(),
            block: block.clone(),
            city_identity: city.identity.clone(),
            node,
            construction_length_m: length,
            capacity_veh_s: 1.,
        }],
        vec![Site {
            block: block.clone(),
            entry_id: id,
            added_capacity: 20,
            priority: 0,
        }],
        100.,
        3600.,
        1800.,
    )?;
    let initial = model.initial();
    let access = Accessibility {
        city_identity: city.identity.clone(),
        stamp_s: stamp,
        costs,
        source_version: ar["source_version"]
            .as_str()
            .ok_or_else(|| bad("source version"))?
            .to_owned(),
    };
    // Advance old completed epochs with no requested growth; their input has
    // empty support and is explicit. The actual completed sample is consumed
    // at the first following slow boundary, 25200 < 25320 < 28800.
    let target = (stamp / 3600.).floor() * 3600. + 3600.;
    let mut s = initial.clone();
    while s.epoch_s + 3600. < target {
        let next = s.epoch_s + 3600.;
        let empty = lagged_growth::compile_accessibility(
            &model.materialized_identity(&s)?,
            &[],
            s.epoch_s,
        )?;
        s = model.advance(&s, &empty, next, 0, &[])?;
    }
    let same = Accessibility {
        stamp_s: target,
        ..access.clone()
    };
    if model.advance(&s, &same, target, 10, &[]).is_ok() {
        return Err(bad("same tick growth leaked"));
    }
    let next = model.advance(&s, &access, target, 10, &[])?;
    if next.pending_increment != 0 || next.allocations.iter().sum::<u64>() != city.population + 10 {
        return Err(bad("growth fixture not applied"));
    }
    let next_city = lagged_growth::materialize_snapshot(&model, &next, snapshot.clone())?;
    let (before_manifest, before_report) =
        v1_prepare_city::prepare_snapshot(snapshot, case, m, step)?;
    let (next_manifest, next_report) =
        v1_prepare_city::prepare_snapshot(next_city.clone(), case, m, step)?;
    let before_cal = v1_prepare_city::audit_calendar(&before_manifest)?;
    let next_cal = v1_prepare_city::audit_calendar(&next_manifest)?;
    if next_report["city_identity"] == before_report["city_identity"]
        || next_report["schedule_identity"] == before_report["schedule_identity"]
        || next_report["population"] != json!(100010.)
    {
        return Err(bad("next epoch identity/stock"));
    }
    let report = json!({"schema":"metroflow_native_next_epoch_v1","scope":"explicit growth fixture using real completed route-derived block accessibility; archive semantic identity bridge; no occupied traffic hot swap","source_frozen_city":old.identity,"source_generated_city":city.identity,"source_archive_sha256":old.source_sha256,"input_stamp_s":stamp,"next_slow_boundary_s":target,"same_tick_rejected":true,"site_block":block,"construction_length_m":length,"maximum_grade":grade,"requested_increment":10,"added_capacity":20,"previous_population":city.population,"next_population":next_city["requested_population"],"next_city_identity":next_city["identity"],"before_schedule_identity":before_manifest["calendar"]["schedule_identity"],"next_schedule_identity":next_manifest["calendar"]["schedule_identity"],"before_calendar":before_cal,"next_calendar":next_cal,"growth_state":next,"next_prepare":next_report});
    Ok((before_manifest, next_city, next_manifest, report))
}
