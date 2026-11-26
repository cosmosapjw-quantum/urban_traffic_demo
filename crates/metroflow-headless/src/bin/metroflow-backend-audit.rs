//! Explicit functional census, not an inference from code volume or evidence file existence.
use metroflow_headless::receipt;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 3 {
        return Err("usage: metroflow-backend-audit ARTIFACT_DIR PLAN_JSON".into());
    }
    let d = Path::new(&a[1]);
    let p: Value = serde_json::from_reader(fs::File::open(&a[2])?)?;
    let base = fs::read_to_string(d.join("backend_scope.tsv"))?;
    let result = fs::read_to_string(d.join("backend_result.tsv"))?;
    let mut by = BTreeMap::new();
    for l in base.lines().skip(1) {
        let v: Vec<_> = l.split('\t').collect();
        assert_eq!(v.len(), 3);
        assert!(by.insert(v[0], (v[1], v[2])).is_none());
    }
    assert_eq!(by.len(), 15);
    let mut seen = BTreeSet::new();
    let (mut baseline, mut host, mut pure, mut partial) = (0, 0, 0, 0);
    let mut rows = vec![];
    for l in result.lines().skip(1) {
        let v: Vec<_> = l.split('\t').collect();
        assert_eq!(v.len(), 3);
        assert!(seen.insert(v[0]));
        let (name, old) = by[v[0]];
        if old == "RUST_PYO3" {
            baseline += 1;
        }
        let evidence = match v[1] {
            "RUST_HOST_SCOPED" => {
                host += 1;
                Some(receipt::sha256(&d.join(v[2]))?)
            }
            "PURE_RUST_SCOPED" => {
                pure += 1;
                Some(receipt::sha256(&d.join(v[2]))?)
            }
            "PARTIAL" => {
                partial += 1;
                Some(receipt::sha256(&d.join(v[2]))?)
            }
            "REMAINING" => {
                assert_eq!(v[2], "-");
                None
            }
            _ => panic!("unrecognized status"),
        };
        rows.push(json!({"id":v[0],"component":name,"baseline":old,"status":v[1],"evidence":v[2],"evidence_sha256":evidence}));
    }
    assert_eq!(seen.len(), by.len());
    let nodes = p["nodes"].as_array().ok_or("plan nodes")?;
    let ids: BTreeSet<_> = nodes.iter().map(|x| x["id"].as_str().unwrap()).collect();
    assert_eq!(ids.len(), nodes.len());
    for n in nodes {
        for dep in n["depends_on"].as_array().unwrap() {
            assert!(ids.contains(dep.as_str().unwrap()));
        }
    }
    let scoped = nodes
        .iter()
        .filter(|n| matches!(n["status"].as_str(), Some("ACCEPTED" | "VERIFIED_SCOPED")))
        .count();
    let accepted = nodes.iter().filter(|n| n["status"] == "ACCEPTED").count();
    let v = nodes
        .iter()
        .find(|n| n["id"] == "V03")
        .ok_or("missing V03")?;
    assert_eq!(v["status"], "BLOCKED");
    let deps = v["depends_on"].as_array().unwrap();
    let ready = deps
        .iter()
        .filter(|d| {
            nodes.iter().any(|n| {
                n["id"] == **d
                    && matches!(n["status"].as_str(), Some("ACCEPTED" | "VERIFIED_SCOPED"))
            })
        })
        .count();
    let total = by.len();
    let mut original = 0;
    for case in [
        "valley_weekday_s7",
        "coastal_weekend_s41",
        "river_weekday_s17",
    ] {
        let pp = d.join(format!("{case}.prepare.json"));
        let ep = d.join(format!("{case}.engine10.json"));
        if pp.exists() && ep.exists() {
            let p: Value = serde_json::from_reader(fs::File::open(pp)?)?;
            let e: Value = serde_json::from_reader(fs::File::open(ep)?)?;
            assert_eq!(p["case"], case);
            assert_eq!(p["population"].as_f64(), Some(100000.));
            assert_eq!(p["calendar"]["calendar_legs"], e["calendar_legs"]);
            assert_eq!(p["city_identity"], e["city_identity"]);
            assert_eq!(p["schedule_identity"], e["schedule_identity"]);
            assert_eq!(e["time_s"].as_f64(), Some(10.));
            assert_eq!(e["python_runtime_dependency"], "none");
            original += 1;
        }
    }
    println!(
        "{}",
        serde_json::to_string_pretty(
            &json!({"schema":"metroflow_backend_functional_census_v1","denominator":total,"method":"unweighted, fixed C01 functional inventory; scoped evidence reviewed; not LOC, full-city completeness or release acceptance","baseline_rust_core":baseline,"rust_implemented_scoped":host+pure,"rust_implemented_percent":100.*(host+pure) as f64/total as f64,"pure_rust_verified_scoped":pure,"pure_rust_percent":100.*pure as f64/total as f64,"native_host_linked_python_scoped":host,"remaining_functions":total-host-pure,"partial_functions":partial,"unimplemented_functions":total-host-pure-partial,"original_v03_full_days":0,"original_v03_total":9,"original_dag_scoped_or_accepted":scoped,"original_dag_accepted":accepted,"original_dag_total":nodes.len(),"original_v03_direct_dependencies_ready":ready,"original_v03_direct_dependencies_total":deps.len(),"original_v03_rust_only_city_preparations_verified":original,"rows":rows})
        )?
    );
    Ok(())
}
