//! The frozen V03 production marginal-input path, without Python or per-leg JSON.
use crate::{
    core_error::{CoreError, CoreResult},
    frozen_city::{self, Case, City, Matrix},
    v1_area::{Area, Law},
    v1_calendar::FactorizedDeclaration,
    v1_journey::fsum,
    v1_routing::V1RoutingGraph,
};
use rayon::prelude::*;
use serde_json::{json, Value};
use std::{cmp::Ordering, collections::BTreeMap, path::Path};

type Profile = Vec<(f64, f64, f64)>;
type ActivityRow = (
    String,
    String,
    Option<String>,
    Option<String>,
    Law,
    Law,
    f64,
);
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
fn bytes(v: &Value) -> CoreResult<Vec<u8>> {
    serde_json::to_vec(v).map_err(|e| bad(e.to_string()))
}
#[derive(Default)]
struct Registry {
    labels: Vec<String>,
    index: BTreeMap<String, u32>,
    profiles: Vec<Profile>,
}
impl Registry {
    fn label(&mut self, s: String) -> u32 {
        if let Some(&i) = self.index.get(&s) {
            return i;
        }
        let i = self.labels.len() as u32;
        self.labels.push(s.clone());
        self.index.insert(s, i);
        i
    }
    fn word(&mut self, s: &str) -> u32 {
        self.label(json!(s).to_string())
    }
    fn profile(&mut self, p: Profile) -> u32 {
        if let Some(i) = self.profiles.iter().position(|v| v == &p) {
            return i as u32;
        }
        let i = self.profiles.len() as u32;
        self.profiles.push(p);
        i
    }
}
fn coord(a: &[f64; 3], b: &[f64; 3]) -> Ordering {
    a.iter()
        .zip(b)
        .map(|(x, y)| x.partial_cmp(y).unwrap())
        .find(|o| *o != Ordering::Equal)
        .unwrap_or(Ordering::Equal)
}
fn geo_key(a: &([f64; 3], Vec<[f64; 3]>), b: &([f64; 3], Vec<[f64; 3]>)) -> Ordering {
    coord(&a.0, &b.0).then_with(|| {
        a.1.iter()
            .zip(&b.1)
            .map(|(x, y)| coord(x, y))
            .find(|o| *o != Ordering::Equal)
            .unwrap_or_else(|| a.1.len().cmp(&b.1.len()))
    })
}
fn activity_label(block: &str, kind: &str) -> String {
    json!({"block_id":block,"kind":kind,"geometry":"frozen_uniform_depth0_v1"}).to_string()
}
fn law_label(block: &str, kind: &str) -> String {
    json!({"block_id":block,"internal_destination":kind,"geometry":"frozen_uniform_depth0_v1"})
        .to_string()
}
struct Geometry {
    block: String,
    home: Option<ActivityRow>,
    job: Option<ActivityRow>,
    service: Option<ActivityRow>,
    internal: Option<Law>,
}
fn geometries(city: &City) -> CoreResult<Vec<Geometry>> {
    let mut portals: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for p in &city.portals {
        portals.entry(&p.block_id).or_default().push(&p.node_id)
    }
    let rows: Vec<CoreResult<Geometry>> = city
        .blocks
        .par_iter()
        .filter(|b| b.residents > 0 || b.jobs > 0)
        .map(|b| {
            let points = b
                .boundary
                .iter()
                .map(|n| {
                    let p = city.nodes[n].xyz;
                    [p[0], p[1]]
                })
                .collect();
            let area = Area::new(points).map_err(|e| bad(format!("block {}: {e}", b.id)))?;
            let options = portals.get(b.id.as_str());
            let door = options
                .and_then(|v| {
                    v.iter()
                        .min_by(|a, b| coord(&city.nodes[**a].xyz, &city.nodes[**b].xyz))
                })
                .map(|s| s.to_string());
            let car = if options.is_some_and(|v| v.len() == 1) {
                door.clone()
            } else {
                None
            };
            let row = |kind: &str, stock: u64| -> CoreResult<Option<ActivityRow>> {
                if stock == 0 {
                    return Ok(None);
                }
                let (service, maximum) = if let Some(ref id) = door {
                    let p = city.nodes[id].xyz;
                    area.access([p[0], p[1]], stock as f64)?
                } else {
                    (vec![], 0.)
                };
                let car_law = if car.is_some() {
                    let z = fsum(service.iter().map(|a| a.1));
                    if z <= 0. {
                        return Err(bad("zero conditional law"));
                    }
                    service.iter().map(|&(d, w)| (d, w / z)).collect()
                } else {
                    vec![]
                };
                Ok(Some((
                    activity_label(&b.id, kind),
                    b.id.clone(),
                    car.clone(),
                    door.clone(),
                    car_law,
                    service,
                    maximum,
                )))
            };
            let home = row("residential", b.residents)?;
            let job = row("job", b.jobs)?;
            let service = job.as_ref().map(|j| {
                let mut s = j.clone();
                s.0 = activity_label(&b.id, "service");
                s
            });
            let internal = if b.residents > 0 && b.jobs > 0 {
                Some(area.internal(b.residents as f64, b.jobs as f64)?)
            } else {
                None
            };
            Ok(Geometry {
                block: b.id.clone(),
                home,
                job,
                service,
                internal,
            })
        })
        .collect();
    rows.into_iter().collect()
}
fn fleet(city: &City, m: &Matrix) -> CoreResult<Value> {
    let p = &m.inventory_policy;
    if !(2..=32).contains(&p.max_stops)
        || p.departures_s.is_empty()
        || p.departures_s
            .iter()
            .any(|x| !x.is_finite() || *x < 0. || *x >= 86400.)
        || p.departures_s.windows(2).any(|x| x[0] >= x[1])
        || !p.capacity_persons.is_finite()
        || p.capacity_persons <= 0.
        || !p.dwell_s.is_finite()
        || p.dwell_s < 0.
    {
        return Err(bad("inventory policy invalid"));
    }
    let mut doors: BTreeMap<&str, &str> = BTreeMap::new();
    for x in &city.portals {
        let entry = doors.entry(&x.block_id).or_insert(&x.node_id);
        if coord(&city.nodes[&x.node_id].xyz, &city.nodes[*entry].xyz) == Ordering::Less {
            *entry = &x.node_id
        }
    }
    let mut candidates = vec![];
    for b in &city.blocks {
        if let Some(&node) = doors.get(b.id.as_str()) {
            let mut boundary = b
                .boundary
                .iter()
                .map(|k| city.nodes[k].xyz)
                .collect::<Vec<_>>();
            boundary.sort_by(coord);
            candidates.push((
                (city.nodes[node].xyz, boundary),
                b.id.clone(),
                node.to_owned(),
            ));
        }
    }
    candidates.sort_by(|a, b| geo_key(&a.0, &b.0));
    if candidates
        .windows(2)
        .any(|w| geo_key(&w[0].0, &w[1].0) == Ordering::Equal)
    {
        return Err(bad("ambiguous physical stop geometry"));
    }
    let mut seen = std::collections::BTreeSet::new();
    candidates.retain(|c| seen.insert(c.2.clone()));
    let count = p.max_stops.min(candidates.len());
    if count < 2 || count * p.departures_s.len() > 20000 {
        return Err(bad("fixed fleet count invalid"));
    }
    let stops: Vec<_> = (0..count)
        .map(|i| {
            let c = &candidates[i * (candidates.len() - 1) / (count - 1)];
            (c.1.clone(), c.2.clone())
        })
        .collect();
    let arcs = city
        .links
        .iter()
        .map(|x| (x.id.clone(), x.tail.clone(), x.head.clone()))
        .collect();
    let costs = city.links.iter().map(|x| x.length / x.speed).collect();
    let mut graph = V1RoutingGraph::new(arcs, costs, Some(city.turns.clone()), 8)?;
    let mut corridors = vec![];
    let mut routes = vec![];
    for i in 0..count {
        let a = &stops[i];
        let b = &stops[(i + 1) % count];
        let (found, _, _) = graph.search_inner(&a.1, &b.1, 1, 2000).map_err(bad)?;
        let path = found
            .first()
            .filter(|x| !x.is_empty())
            .ok_or_else(|| bad("fixed corridor lacks legal route"))?;
        for (j, &t) in p.departures_s.iter().enumerate() {
            let id = format!("fixed-ring:{i}:{j}");
            corridors.push(json!([id, a.0, b.0, t, p.capacity_persons, p.dwell_s]));
            routes.push(json!([id, path]));
        }
    }
    Ok(
        json!({"stops":stops,"corridors":corridors,"corridor_routes":routes,"depot_block_id":stops[0].0,"depot_node_or_None":stops[0].1}),
    )
}
fn window(a: f64, b: f64) -> Profile {
    vec![(a * 3600., b * 3600., 1.)]
}
fn day_profiles(day: &str, purpose: &str) -> CoreResult<(Profile, Profile)> {
    let (a, b, c, d) = match (day, purpose) {
        ("weekday", "work") => (7., 9., 17., 19.),
        ("weekday", "school") => (8., 9., 15., 16.),
        ("weekday", "service") => (10., 11., 13., 14.),
        ("weekend", "work") => (9., 10., 14., 15.),
        ("weekend", "school") => (10., 11., 14., 15.),
        ("weekend", "service") => (10., 12., 16., 18.),
        _ => return Err(bad("day/purpose invalid")),
    };
    Ok((window(a, b), window(c, d)))
}
pub fn prepare(root: &Path, case: &Case, m: &Matrix, step: f64) -> CoreResult<(Value, Value)> {
    if !step.is_finite() || step <= 0. {
        return Err(bad("step invalid"));
    }
    let city = frozen_city::load(root, case, m.population)?;
    let (wf, sf, ss) = match case.day.as_str() {
        "weekday" => (0.5, 0.2, 0.25),
        "weekend" => (0.1, 0.4, 0.),
        _ => return Err(bad("day invalid")),
    };
    let population = fsum(city.blocks.iter().map(|b| b.residents as f64));
    if population != m.population as f64 {
        return Err(bad("population ledger differs"));
    }
    let support = fsum(city.blocks.iter().map(|b| b.jobs as f64));
    if support <= 0. {
        return Err(bad("job and service support empty"));
    }
    let requested = population * wf;
    let allocated = requested.min(support);
    let unmet = requested - allocated;
    let service_requested = population * sf;
    let service_assigned = service_requested.min(support);
    let service_unmet = service_requested - service_assigned;
    let geometry = geometries(&city)?;
    let inventory = fleet(&city, m)?;
    let mut r = Registry::default();
    let null = r.label("null".to_owned());
    let mut homes = vec![];
    let mut jobs = vec![];
    let mut services = vec![];
    let mut activities = vec![];
    let mut laws = vec![];
    let mut static_laws = vec![];
    let mut freight = vec![];
    let mut lookup = BTreeMap::new();
    for b in &city.blocks {
        lookup.insert(b.id.as_str(), b);
    }
    for g in geometry {
        let b = lookup[g.block.as_str()];
        let mut home_id = None;
        let mut job_id = None;
        let mut service_id = None;
        if let Some(row) = g.home {
            let id = r.label(row.0.clone());
            let mass = b.residents as f64;
            let ratio = mass / population;
            let stationary = [mass * (1. - wf - sf), service_unmet * ratio, unmet * ratio]
                .iter()
                .filter(|x| **x > 0.)
                .count() as u32;
            homes.push((id, mass, stationary));
            home_id = Some(id);
            activities.push(row);
        }
        if let Some(row) = g.job {
            let id = r.label(row.0.clone());
            jobs.push((id, b.jobs as f64));
            job_id = Some(id);
            activities.push(row)
        }
        if let Some(row) = g.service {
            let id = r.label(row.0.clone());
            services.push((id, b.jobs as f64));
            service_id = Some(id);
            activities.push(row);
            freight.push((
                format!("freight:{}", b.id),
                id,
                1000. * b.jobs as f64 / support,
            ));
        }
        if let Some(law) = g.internal {
            let h = home_id.ok_or_else(|| bad("internal home absent"))?;
            for (dest, kind, purposes) in [
                (job_id, "job", vec![("work", allocated)]),
                (
                    service_id,
                    "service",
                    vec![
                        ("school", service_assigned * ss),
                        ("service", service_assigned * (1. - ss)),
                    ],
                ),
            ] {
                let dest = dest.ok_or_else(|| bad("internal target absent"))?;
                if purposes.iter().all(|(_, m)| *m == 0.) {
                    continue;
                }
                let label = law_label(&b.id, kind);
                let law_id = r.label(label.clone());
                static_laws.push((label, law.clone()));
                for (purpose, mass) in purposes {
                    if mass > 0. {
                        laws.push((h, dest, r.word(purpose), law_id))
                    }
                }
            }
        }
    }
    let mut targets = vec![];
    for (purpose, mass, dests) in [
        ("work", allocated, &jobs),
        ("school", service_assigned * ss, &services),
        ("service", service_assigned * (1. - ss), &services),
    ] {
        if mass == 0. {
            continue;
        }
        let (p, q) = day_profiles(&case.day, purpose)?;
        targets.push((
            r.word(purpose),
            r.profile(p),
            r.profile(q),
            mass,
            support,
            false,
            dests,
        ));
    }
    let modes = vec![
        (r.word("car"), r.word("car"), 0.6, 1.25, false),
        (r.word("bus"), r.word("scheduled_bus"), 0.25, 25., false),
        (r.word("noncar"), null, 0.15, 1., true),
    ];
    let constants = vec![
        null,
        r.word("return_home"),
        r.word("interzonal"),
        r.word("intrazonal"),
        r.word("external"),
        r.word("delivery"),
        r.word("freight"),
        r.word("freight"),
    ];
    let fp = r.profile(vec![(32400., 36000., 0.6), (54000., 57600., 0.4)]);
    let mut cal = json!({"city_identity":city.identity,"schedule_identity":"","labels":r.labels,"profiles":r.profiles,"homes":homes,"targets":targets,"modes":modes,"laws":laws,"freight":freight,"config":[population,sf,0.,3600.,1000.],"constants":constants,"freight_profile":fp});
    let sid = frozen_city::hash(&bytes(&cal)?);
    cal["schedule_identity"] = json!(sid);
    let groups: Vec<_> = city
        .links
        .iter()
        .map(|g| {
            [
                g.length, g.speed, g.capacity, g.capacity, g.storage, g.priority,
            ]
        })
        .collect();
    let classes: Vec<_> = [5., 10., 12.]
        .into_iter()
        .map(|l| [10., 2., 2., 4., 2., 1., l, 1., 0.2, 0.3, 10., 0., l])
        .collect();
    let mut st = json!({"schema":"native_calendar_static_v1","identity":"","city_identity":city.identity,"schedule_identity":sid,"step_s":step,"record_budget":20000,"event_budget":20000,"max_service_runs":20000,"preserve_entry_intervals":true,"activities":activities,"intrazonal_laws":static_laws,"groups":groups,"signals":vec![Value::Null;city.links.len()],"classes":classes,"class_names":["car","freight","scheduled_bus"],"incoming":city.incoming,"windows":[],"link_ids":city.links.iter().map(|g|&g.id).collect::<Vec<_>>(),"route_arcs":city.links.iter().map(|g|(&g.id,&g.tail,&g.head)).collect::<Vec<_>>(),"route_costs":city.links.iter().map(|g|(&g.id,g.length/g.speed)).collect::<Vec<_>>(),"allowed_turns":city.turns,"corridors":inventory["corridors"],"corridor_routes":inventory["corridor_routes"],"depot_block_id":inventory["depot_block_id"],"depot_node_or_None":inventory["depot_node_or_None"]});
    let static_id = frozen_city::hash(&bytes(&st)?);
    st["identity"] = json!(static_id);
    let manifest = json!({"schema":"metroflow_native_declaration_v1","byte_budget":6*1024u64.pow(3),"calendar":cal,"static":st});
    let report = json!({"case":case.id,"city_identity":city.identity,"source_sha256":city.source_sha256,"patch_sha256":city.patch_sha256,"schedule_identity":sid,"static_identity":static_id,"identity_scope":"new Rust declaration identity; frozen source city identity preserved; old checkpoint compatibility not claimed","population":population,"requested_workers":requested,"allocated_workers":allocated,"unassigned_workers":unmet,"service_assigned":service_assigned,"unassigned_service":service_unmet,"home_factors":homes.len(),"job_factors":jobs.len(),"service_factors":services.len(),"fixed_runs":inventory["corridors"].as_array().unwrap().len(),"stops":inventory["stops"],"activities":activities.len(),"internal_laws":static_laws.len(),"links":city.links.len(),"legal_turns":city.turns.len()});
    Ok((manifest, report))
}
/// Actual enumeration by the native engine, without running the transport.
pub fn audit_calendar(manifest: &Value) -> CoreResult<Value> {
    let cal: FactorizedDeclaration =
        serde_json::from_value(manifest["calendar"].clone()).map_err(|e| bad(e.to_string()))?;
    let calendar = cal.compile(6 * 1024usize.pow(3))?;
    let rows = calendar.owned_legs();
    let totals = calendar.totals();
    Ok(
        json!({"calendar_legs":rows.len(),"persons":totals.0,"vehicles":totals.1,"cargo_kg":totals.2}),
    )
}
