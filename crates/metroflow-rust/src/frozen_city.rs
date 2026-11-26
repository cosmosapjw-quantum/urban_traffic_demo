//! Original frozen release-map activation. Byte-pinned base and portal patch
//! are authoritative input, not a replacement city generator. The entire
//! directional transport registry is recompiled in Rust.
use crate::{
    core_error::{CoreError, CoreResult},
    v1_area::{cross, dist, Point},
    v1_journey::fsum,
};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::{Component, Path},
};

#[derive(Clone, Debug, Deserialize)]
pub struct Case {
    pub id: String,
    pub map_index: usize,
    pub map_case: String,
    pub seed: u64,
    pub day: String,
    pub max_cohorts: usize,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Limits {
    pub wall_s: u64,
    pub peak_rss_bytes: u64,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Policy {
    pub max_stops: usize,
    pub departures_s: Vec<f64>,
    pub capacity_persons: f64,
    pub dwell_s: f64,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Matrix {
    pub schema_version: u32,
    pub population: u64,
    pub horizon_s: f64,
    pub repeat: usize,
    pub limits: Limits,
    pub cases: Vec<Case>,
    pub demand_representation: String,
    pub worker_shortfall: String,
    pub inventory_policy: Policy,
    pub route_materialization_budget: usize,
}
#[derive(Clone, Debug, Deserialize)]
pub(crate) struct Node {
    pub id: String,
    pub layer: u32,
    pub xyz: [f64; 3],
}
#[derive(Clone, Debug, Deserialize)]
struct Section {
    id: String,
    start: String,
    end: String,
    facility: String,
    hierarchy: String,
    points: Vec<[f64; 3]>,
    length_m: f64,
    max_grade: f64,
    forward_lanes: u32,
    backward_lanes: u32,
    ramp_purpose: Option<String>,
    failure_group: Option<String>,
}
#[derive(Clone, Debug, Deserialize)]
pub(crate) struct Block {
    pub id: String,
    pub boundary: Vec<String>,
    pub area_m2: f64,
    pub perimeter_m: f64,
    pub residents: u64,
    pub jobs: u64,
    pub housing_capacity: u64,
    pub job_capacity: u64,
}
#[derive(Clone, Debug, Deserialize)]
pub(crate) struct Portal {
    pub id: String,
    pub block_id: String,
    pub node_id: String,
}
#[derive(Deserialize)]
struct RoadMap {
    terrain: crate::terrain_validation::Terrain,
    nodes: Vec<Node>,
    sections: Vec<Section>,
}
#[derive(Deserialize)]
struct RawCity {
    schema: String,
    identity: String,
    roadmap: RoadMap,
    landscape: crate::terrain_validation::Landscape,
    blocks: Vec<Block>,
    portals: Vec<Portal>,
    requested_population: u64,
    unplaced_residents: u64,
}
#[derive(Deserialize)]
struct Patch {
    base_source: String,
    base_sha256: String,
    parent_identity: String,
    identity: String,
    portals: Vec<Portal>,
}
#[derive(Deserialize)]
struct Audit {
    case: String,
    seed: u64,
    identity: String,
    patch: String,
    patch_sha256: String,
    source_sha256: String,
    registered_portal_count: usize,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Link {
    pub id: String,
    pub tail: String,
    pub head: String,
    pub length: f64,
    pub speed: f64,
    pub capacity: f64,
    pub storage: f64,
    pub priority: f64,
    facility: String,
    ramp_purpose: Option<String>,
}
pub(crate) struct City {
    pub identity: String,
    pub source_sha256: String,
    pub patch_sha256: String,
    pub population: u64,
    pub unplaced_residents: u64,
    pub geometry_audit: crate::terrain_validation::Report,
    pub nodes: BTreeMap<String, Node>,
    pub blocks: Vec<Block>,
    pub portals: Vec<Portal>,
    pub links: Vec<Link>,
    pub turns: Vec<(String, String)>,
    pub incoming: Vec<Vec<usize>>,
}
pub(crate) fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
pub(crate) fn load_bytes(p: &Path) -> CoreResult<Vec<u8>> {
    fs::read(p).map_err(|e| CoreError::io(format!("{}: {e}", p.display())))
}
fn from_json<T: serde::de::DeserializeOwned>(b: &[u8]) -> CoreResult<T> {
    serde_json::from_slice(b).map_err(|e| bad(format!("JSON: {e}")))
}
fn from_xz<T: serde::de::DeserializeOwned>(b: &[u8]) -> CoreResult<T> {
    let reader = lzma_rust2::XzReader::new(b, false);
    let mut out = Vec::new();
    const CAP: u64 = 256 * 1024 * 1024;
    reader
        .take(CAP + 1)
        .read_to_end(&mut out)
        .map_err(|e| CoreError::io(format!("XZ: {e}")))?;
    if out.len() as u64 > CAP {
        return Err(CoreError::resource("map decode bound"));
    }
    from_json(&out)
}
fn leaf(s: &str) -> CoreResult<&str> {
    let mut c = Path::new(s).components();
    if matches!(c.next(), Some(Component::Normal(_))) && c.next().is_none() {
        Ok(s)
    } else {
        Err(bad("invalid frozen source leaf"))
    }
}
impl Matrix {
    pub fn load(path: &Path) -> CoreResult<(Self, String)> {
        let b = load_bytes(path)?;
        let m: Self = from_json(&b)?;
        if m.schema_version != 1
            || m.population != 100000
            || m.horizon_s != 86400.
            || m.repeat != 3
            || m.limits.wall_s != 7200
            || m.limits.peak_rss_bytes != 8 * 1024u64.pow(3)
            || m.cases.len() != 3
            || m.worker_shortfall != "unassigned_home"
            || m.demand_representation != "exact_factorized_independent_OD"
            || m.route_materialization_budget != 20000
        {
            return Err(bad("original matrix contract differs"));
        }
        if m.cases
            .iter()
            .map(|c| c.id.as_str())
            .collect::<BTreeSet<_>>()
            .len()
            != 3
        {
            return Err(bad("duplicate case"));
        }
        Ok((m, hash(&b)))
    }
}
fn xy(p: [f64; 3]) -> Point {
    [p[0], p[1]]
}
fn positive(x: f64) -> bool {
    x.is_finite() && x > 0.
}
fn close(a: f64, b: f64) -> bool {
    (a - b).abs() <= 1e-5 + 1e-8 * a.abs().max(b.abs())
}
fn curvature(points: &[[f64; 3]]) -> CoreResult<f64> {
    let mut xy_points = Vec::new();
    for &p in points {
        let p = xy(p);
        if xy_points.last().is_none_or(|&q| dist(p, q) > 1e-7) {
            xy_points.push(p)
        }
    }
    let mut result = 0f64;
    for w in xy_points.windows(3) {
        let (a, b, c) = (w[0], w[1], w[2]);
        let den = dist(a, b) * dist(b, c) * dist(a, c);
        if den <= 1e-12 {
            return Err(bad("degenerate centreline"));
        }
        result = result.max(2. * cross(a, b, c).abs() / den);
    }
    Ok(result)
}
fn compile_section(s: &Section, nodes: &BTreeMap<String, Node>) -> CoreResult<Vec<Link>> {
    let a = nodes
        .get(&s.start)
        .ok_or_else(|| bad("missing section start"))?;
    let b = nodes
        .get(&s.end)
        .ok_or_else(|| bad("missing section end"))?;
    if a.id == b.id
        || s.id.is_empty()
        || s.points.len() < 2
        || s.points.iter().flatten().any(|x| !x.is_finite())
        || !positive(s.length_m)
        || !s.max_grade.is_finite()
        || s.max_grade < 0.
        || s.max_grade > 0.12 + 1e-10
        || s.forward_lanes + s.backward_lanes == 0
        || s.points.first() != Some(&a.xyz)
        || s.points.last() != Some(&b.xyz)
    {
        return Err(bad(format!("invalid section geometry {}", s.id)));
    }
    let (mut speed, mut cap, mut priority) = match s.hierarchy.as_str() {
        "local" => (8.33, 0.45, 1.),
        "collector" => (13.89, 0.50, 2.),
        "arterial" => (16.67, 0.55, 3.),
        "expressway" => (25., 0.60, 4.),
        _ => return Err(bad("unsupported hierarchy")),
    };
    match s.facility.as_str() {
        "ramp" => {
            let layer = match s.ramp_purpose.as_deref() {
                Some("on_ramp") => (0, 1),
                Some("off_ramp") => (1, 0),
                _ => return Err(bad("invalid ramp purpose")),
            };
            if (a.layer, b.layer) != layer || s.forward_lanes != 1 || s.backward_lanes != 0 {
                return Err(bad("ramp layer/direction"));
            }
            (speed, cap, priority) = (11.11, 0.45, 1.);
        }
        "mainline" => {
            if (a.layer, b.layer) != (1, 1) || s.forward_lanes == 0 || s.backward_lanes != 0 {
                return Err(bad("mainline direction/layer"));
            }
        }
        "surface" | "bridge" => {
            if (a.layer, b.layer) != (0, 0) {
                return Err(bad("ground layer"));
            }
        }
        _ => return Err(bad("unsupported facility")),
    }
    speed /= 1. + 3. * s.max_grade;
    let k = curvature(&s.points)?;
    if k > 1e-12 {
        speed = speed.min((2. / k).sqrt())
    }
    let mut links = vec![];
    for (d, l, u, v) in [
        (0, s.forward_lanes, &s.start, &s.end),
        (1, s.backward_lanes, &s.end, &s.start),
    ] {
        if l > 0 {
            links.push(Link {
                id: format!("{}|{d}", s.id),
                tail: u.clone(),
                head: v.clone(),
                length: s.length_m,
                speed,
                capacity: cap * l as f64,
                storage: s.length_m * l as f64,
                priority,
                facility: s.facility.clone(),
                ramp_purpose: s.ramp_purpose.clone(),
            })
        }
    }
    Ok(links)
}
fn compile_links(
    sections: &[Section],
    nodes: &BTreeMap<String, Node>,
) -> CoreResult<(Vec<Link>, Vec<(String, String)>, Vec<Vec<usize>>)> {
    let ids = sections
        .iter()
        .map(|s| s.id.as_str())
        .collect::<BTreeSet<_>>();
    if ids.len() != sections.len() {
        return Err(bad("duplicate sections"));
    }
    let rows: Vec<CoreResult<Vec<Link>>> = sections
        .par_iter()
        .map(|s| compile_section(s, nodes))
        .collect();
    let mut links = Vec::with_capacity(sections.len() * 2);
    for r in rows {
        links.extend(r?)
    }
    links.sort_by(|a, b| a.id.cmp(&b.id));
    if links.is_empty() || links.len() > 10000 {
        return Err(CoreError::resource("road group bound"));
    }
    let (mut incoming, mut outgoing): (BTreeMap<&str, Vec<usize>>, BTreeMap<&str, Vec<usize>>) =
        (BTreeMap::new(), BTreeMap::new());
    for (i, r) in links.iter().enumerate() {
        incoming.entry(&r.head).or_default().push(i);
        outgoing.entry(&r.tail).or_default().push(i);
    }
    let ground = |l: &Link| matches!(l.facility.as_str(), "surface" | "bridge");
    let mut turns = vec![];
    for (&node, inc) in &incoming {
        for &i in inc {
            for &j in outgoing.get(node).into_iter().flatten() {
                let (a, b) = (&links[i], &links[j]);
                if a.tail == b.head {
                    continue;
                }
                let legal = if nodes[node].layer == 1 {
                    (a.facility == "mainline" && b.facility == "mainline")
                        || (a.ramp_purpose.as_deref() == Some("on_ramp")
                            && b.facility == "mainline")
                        || (a.facility == "mainline"
                            && b.ramp_purpose.as_deref() == Some("off_ramp"))
                } else {
                    (ground(a) && ground(b))
                        || (a.ramp_purpose.as_deref() == Some("off_ramp") && ground(b))
                        || (ground(a) && b.ramp_purpose.as_deref() == Some("on_ramp"))
                };
                if legal {
                    turns.push((a.id.clone(), b.id.clone()))
                }
            }
        }
    }
    turns.sort();
    let incoming = incoming.into_values().collect();
    Ok((links, turns, incoming))
}
pub(crate) fn load(root: &Path, case: &Case, population: u64) -> CoreResult<City> {
    let evidence = root.join("artifacts/v1_portal_resolution_20261027");
    let audit: Audit = from_json(&load_bytes(
        &evidence.join(format!("{:02}.audit.json", case.map_index)),
    )?)?;
    if audit.case != case.map_case || audit.seed != case.seed {
        return Err(bad("map case/seed differs"));
    }
    let patch_bytes = load_bytes(&evidence.join(leaf(&audit.patch)?))?;
    if hash(&patch_bytes) != audit.patch_sha256 {
        return Err(bad("portal patch SHA differs"));
    }
    let patch: Patch = from_xz(&patch_bytes)?;
    let bytes = load_bytes(
        &root
            .join("artifacts/v1/map_audit")
            .join(leaf(&patch.base_source)?),
    )?;
    let source_sha = hash(&bytes);
    if source_sha != patch.base_sha256 || source_sha != audit.source_sha256 {
        return Err(bad("source map SHA differs"));
    }
    let mut raw: RawCity = from_xz(&bytes)?;
    if raw.schema != "metroflow_city_v1"
        || raw.identity != patch.parent_identity
        || patch.identity != audit.identity
        || !raw.portals.is_empty()
        || patch.portals.len() != audit.registered_portal_count
        || raw.requested_population != population
    {
        return Err(bad("frozen city binding differs"));
    }
    raw.portals = patch.portals;
    raw.identity = audit.identity;
    compile_raw(raw, source_sha, audit.patch_sha256)
}

/// New native identity is a SHA of the exact typed snapshot payload with the
/// identity slot blank. Never pretend to be the Python JSON/repr digest.
pub(crate) fn bind_snapshot(mut value: Value) -> CoreResult<(Value, City)> {
    if value["schema"] != "metroflow_city_v1"
        || value["identity_scheme"] != "metroflow_native_city_v1"
    {
        return Err(bad("native snapshot schema"));
    }
    let old = value["identity"].as_str().unwrap_or("").to_owned();
    value["identity"] = json!("");
    let bytes = serde_json::to_vec(&value).map_err(|e| bad(e.to_string()))?;
    let id = hash(&bytes);
    if !old.is_empty() && old != id {
        return Err(bad("native snapshot digest differs"));
    }
    value["identity"] = json!(id);
    let raw: RawCity = serde_json::from_value(value.clone()).map_err(|e| bad(e.to_string()))?;
    let city = compile_raw(raw, id.clone(), id)?;
    Ok((value, city))
}

fn compile_raw(raw: RawCity, source_sha: String, patch_sha: String) -> CoreResult<City> {
    let population = raw.requested_population;
    let count = raw.roadmap.nodes.len();
    let nodes: BTreeMap<_, _> = raw
        .roadmap
        .nodes
        .into_iter()
        .map(|n| (n.id.clone(), n))
        .collect();
    if count != nodes.len()
        || nodes.is_empty()
        || nodes
            .values()
            .any(|n| n.id.is_empty() || n.layer > 1 || n.xyz.iter().any(|v| !v.is_finite()))
    {
        return Err(bad("node registry"));
    }
    let (mut blocks, mut portals) = (raw.blocks, raw.portals);
    blocks.sort_by(|a, b| a.id.cmp(&b.id));
    portals.sort_by(|a, b| a.id.cmp(&b.id));
    let block_lookup: BTreeMap<_, _> = blocks.iter().map(|b| (b.id.as_str(), b)).collect();
    if block_lookup.len() != blocks.len() {
        return Err(bad("duplicate block"));
    }
    let mut ground_pairs = BTreeSet::new();
    for s in &raw.roadmap.sections {
        if matches!(s.facility.as_str(), "surface" | "bridge") {
            ground_pairs.insert((s.start.as_str(), s.end.as_str()));
            ground_pairs.insert((s.end.as_str(), s.start.as_str()));
        }
    }
    let checks: Vec<CoreResult<()>> = blocks
        .par_iter()
        .map(|b| {
            if b.id.is_empty()
                || b.boundary.len() < 3
                || b.residents > b.housing_capacity
                || b.jobs > b.job_capacity
                || !positive(b.area_m2)
                || !positive(b.perimeter_m)
            {
                return Err(bad("invalid block stock/geometry"));
            }
            let p: Vec<Point> = b
                .boundary
                .iter()
                .map(|k| {
                    nodes
                        .get(k)
                        .filter(|n| n.layer == 0)
                        .map(|n| xy(n.xyz))
                        .ok_or_else(|| bad("ground boundary missing"))
                })
                .collect::<CoreResult<_>>()?;
            for (a, c) in b.boundary.iter().zip(b.boundary.iter().cycle().skip(1)) {
                if !ground_pairs.contains(&(a.as_str(), c.as_str())) {
                    return Err(bad("ground face lacks registered section"));
                }
            }
            let area = 0.5
                * fsum(
                    p.iter()
                        .zip(p.iter().cycle().skip(1))
                        .map(|(a, c)| a[0] * c[1] - c[0] * a[1]),
                );
            let perimeter = fsum(
                p.iter()
                    .zip(p.iter().cycle().skip(1))
                    .map(|(&a, &c)| dist(a, c)),
            );
            if !close(area, b.area_m2) || !close(perimeter, b.perimeter_m) {
                return Err(bad(format!("block geometry differs {}", b.id)));
            }
            Ok(())
        })
        .collect();
    for c in checks {
        c?
    }
    if blocks
        .iter()
        .try_fold(raw.unplaced_residents, |n, b| n.checked_add(b.residents))
        .ok_or_else(|| bad("population overflow"))?
        != population
    {
        return Err(bad("population ledger"));
    }
    let mut pids = BTreeSet::new();
    for p in &portals {
        if p.id.is_empty()
            || !pids.insert(&p.id)
            || !block_lookup
                .get(p.block_id.as_str())
                .is_some_and(|b| b.boundary.contains(&p.node_id))
            || !nodes.get(&p.node_id).is_some_and(|n| n.layer == 0)
        {
            return Err(bad("invalid registered portal"));
        }
    }
    let (links, turns, incoming) = compile_links(&raw.roadmap.sections, &nodes)?;
    let developed: Vec<_> = blocks
        .iter()
        .filter(|b| b.housing_capacity > 0 || b.job_capacity > 0)
        .collect();
    let face_checks: Vec<_> = developed
        .par_iter()
        .map(|b| {
            let ps: Vec<_> = b.boundary.iter().map(|n| xy(nodes[n].xyz)).collect();
            raw.landscape
                .developed_face(&ps)
                .map_err(|e| bad(format!("block {}: {e}", b.id)))
        })
        .collect();
    for c in face_checks {
        c?;
    }
    let views: Vec<_> = raw
        .roadmap
        .sections
        .iter()
        .map(|s| crate::terrain_validation::SectionView {
            id: &s.id,
            start: &s.start,
            end: &s.end,
            facility: &s.facility,
            failure_group: s.failure_group.as_deref(),
            points: &s.points,
            length: s.length_m,
            grade: s.max_grade,
            lanes: s.forward_lanes + s.backward_lanes,
        })
        .collect();
    let geometry_audit = crate::terrain_validation::audit(
        &raw.roadmap.terrain,
        &raw.landscape,
        &views,
        developed.len(),
    )?;
    Ok(City {
        identity: raw.identity,
        source_sha256: source_sha,
        patch_sha256: patch_sha,
        population,
        unplaced_residents: raw.unplaced_residents,
        geometry_audit,
        nodes,
        blocks,
        portals,
        links,
        turns,
        incoming,
    })
}
pub fn audit(root: &Path, case: &Case, population: u64) -> CoreResult<Value> {
    let c = load(root, case, population)?;
    Ok(
        json!({"case":case.id,"city_identity":c.identity,"source_sha256":c.source_sha256,"patch_sha256":c.patch_sha256,"population":c.population,"nodes":c.nodes.len(),"blocks":c.blocks.len(),"portals":c.portals.len(),"links":c.links.len(),"legal_turns":c.turns.len(),"incoming_groups":c.incoming.len(),"link_ids":c.links.iter().map(|x|&x.id).collect::<Vec<_>>(),"physical_road_rows":c.links.iter().map(|x|[x.length,x.speed,x.capacity,x.capacity,x.storage,x.priority]).collect::<Vec<_>>(),"geometry_audit":c.geometry_audit,"scope":"byte-pinned frozen maps; original terrain, road centreline, masks, crossings and developed faces; no generative atlas or pavement envelope claim"}),
    )
}
