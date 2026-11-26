"""Opt-in comparison only. Never an input generator or scientific runner."""
import json
import math
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get("METROFLOW_ENABLE_PYTHON_ORACLE") != "1"
                                or not os.environ.get("METROFLOW_RUST_MANIFEST_DIR"),
                                reason="explicit Python oracle and Rust input directory required")

@pytest.mark.parametrize("case_id", ["valley_weekday_s7", "coastal_weekend_s41", "river_weekday_s17"])
def test_frozen_rust_manifest_semantics(case_id):
    from tools.run_v1_acceptance import load_release_city
    from metroflow.v1.activity import compile_activity, intrazonal_law
    from metroflow.v1.factorized_demand import compile_factorized_demand
    from metroflow.v1.release_inventory import build_inventory, InventoryPolicy
    from metroflow.v1.native_static import prepare_native_static
    from metroflow.v1.demand import calendar_profiles
    matrix=json.loads((ROOT/"scenarios/v1/release_matrix.json").read_text())
    case=next(c for c in matrix["cases"] if c["id"]==case_id)
    city,_=load_release_city(case,ROOT)
    homes=tuple(compile_activity(city,b.id) for b in city.face_graph.blocks if b.residents)
    jobs=tuple(compile_activity(city,b.id,"job") for b in city.face_graph.blocks if b.jobs)
    services=tuple(compile_activity(city,b.id,"service",service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
    schedule=compile_factorized_demand(homes,jobs,services,day=case["day"],freight_kg=1000,
                                      worker_shortfall=matrix["worker_shortfall"])
    inventory=build_inventory(city,InventoryPolicy(**matrix["inventory_policy"]))
    old=prepare_native_static(city,schedule,inventory,step_s=10.,record_budget=20000,event_budget=20000)
    m=json.loads((Path(os.environ["METROFLOW_RUST_MANIFEST_DIR"])/f"{case_id}.manifest.json").read_text())
    s=m["static"]; cal=m["calendar"]; labels=[json.loads(l) for l in cal["labels"]]
    def lists(x):
        return json.loads(json.dumps(x))
    def cmp(a,b):
        if isinstance(a,(list,tuple)):
            assert len(a)==len(b)
            for x,y in zip(a,b): cmp(x,y)
        elif isinstance(a,(int,float)) and not isinstance(a,bool):
            assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10),(a,b)
        else: assert a==b,(a,b)
    for key in ("city_identity","groups","signals","classes","class_names","incoming","windows",
                "link_ids","route_arcs","route_costs","allowed_turns","corridors","corridor_routes",
                "depot_block_id","depot_node_or_None"):
        cmp(lists(old[key]),s[key])
    def actkey(row):
        x=json.loads(row[0]);return x["block_id"],x["kind"]
    aa={actkey(r):r[1:] for r in old["activities"]}
    bb={actkey(r):r[1:] for r in s["activities"]}
    assert aa.keys()==bb.keys()
    for k in aa: cmp(aa[k],bb[k])
    hmap={h.block_id:h for h in homes}; jmap={d.block_id:d for d in jobs}; smap={d.block_id:d for d in services}
    new_laws=dict(s["intrazonal_laws"])
    # All law rows and pair bindings, including school/service sharing.
    for h,d,p,l in cal["laws"]:
        origin,destination,purpose=labels[h],labels[d],labels[p]
        assert origin["block_id"]==destination["block_id"]
        src=hmap[origin["block_id"]]
        target=(jmap if purpose=="work" else smap)[destination["block_id"]]
        expected=intrazonal_law(src,target,depth=0).atoms
        cmp(expected,new_laws[cal["labels"][l]])
    assert [labels[h]["block_id"] for h,_,_ in cal["homes"]]==[h.block_id for h in schedule.homes]
    for p,profile,back,mass,support,ext,ds in cal["targets"]:
        purpose=labels[p]; assert not ext
        src=schedule.jobs if purpose=="work" else schedule.services
        cmp([labels[d]["block_id"] for d,_ in ds],[d.block_id for d in src])
        a,b=calendar_profiles(case["day"],purpose)
        cmp(cal["profiles"][profile],[(w.start_s,w.end_s,w.probability) for w in a.windows])
        cmp(cal["profiles"][back],[(w.start_s,w.end_s,w.probability) for w in b.windows])
        cmp(support,math.fsum(d.mass for d in src))
    print(f"{case_id}: {len(aa)} activity rows, {len(cal['laws'])} intrazonal pair bindings, {len(s['corridor_routes'])} fixed routes, complete road registry")
