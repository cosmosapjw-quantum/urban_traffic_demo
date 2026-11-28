"""Independent receipt/hash and small fixture service-wire review."""
import hashlib,json,struct,sys,math
from pathlib import Path
A=Path("artifacts/akm_observables_owners_20261128")
B=Path(sys.argv[1])
def load(p):return json.loads(p.read_text())
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def receipt(name):return load(A/(name+".json"))
def verify_run(name):
    r=receipt(name);p=B/(name+".bin")
    assert r["status"]=="EXECUTED_FOR_REVIEW" and r["failure"] is None and r["time_s"]==r["requested_end_s"], name
    assert sha(p)==r["checkpoint_sha256"] and p.stat().st_size==r["checkpoint_bytes"], name
    assert sha(B/"metroflow-akm-native")==r["executable_sha256"]
    assert r["peak_rss_kib"]*1024<8*1024**3
    assert r["peak_storage_ratio"]<=1+1e-9
    assert r["peak_road_rows"]<=r["road_rows_guard"]
    for l in r["ledger"].values():
        assert min(l["requested"],l["released"],l["active"],l["completed"],l["pending"])>=-1e-7
        assert math.isclose(l["requested"],l["pending"]+l["released"],abs_tol=1e-8)
        assert math.isclose(l["released"],l["active"]+l["completed"],abs_tol=1e-8)
    m=math.fsum(c[0]-c[1] for c in r["class_road_ledger"])
    bm=math.fsum([r["initial_road_birth"],r["new_offered_birth"],-r["outlet_birth"],-r["active_road_birth"]])
    assert abs(m-r["active_road_mass"])<1e-7*max(1,m)
    assert abs(bm)<1e-8*max(1,r["initial_road_birth"]+r["new_offered_birth"])
    return r,{"name":name,"time_s":r["time_s"],"rows":r["road_rows"],"peak_rows":r["peak_road_rows"],"wall_s":r["wall_s"],"advance_s":r["advance_s"],"peak_rss_bytes":r["peak_rss_kib"]*1024,"checkpoint_bytes":r["checkpoint_bytes"],"road_mass_residual_veh":m-r["active_road_mass"],"road_birth_residual_veh_s":bm}
names=["S08_fixture120","S08_fixture360","S08_valley25380","S08_valley25560","S08_valley26160","S09_fixture360_direct","S09_fixture360_recover","S09_valley25380_recover","S09_valley26160_recover"]
runs={};metrics=[]
for name in names:r,q=verify_run(name);runs[name]=r;metrics.append(q)
for names in [["S08_fixture360","S09_fixture360_direct","S09_fixture360_recover"],["S08_valley25380","S09_valley25380_recover"],["S08_valley26160","S09_valley26160_recover"]]:
    assert len({runs[x]["checkpoint_sha256"] for x in names})==1
    assert all(runs[x]["ledger"]==runs[names[0]]["ledger"] for x in names)
src=load(B/"valley25320_original_receipt.json")
first=runs["S08_valley25380"]
assert src["checkpoint_sha256"]==sha(B/"valley25320_source.bin")==first["source_checkpoint_sha256"]
assert src["manifest_sha256"]==sha(B/"valley-original.manifest.json")==first["manifest_sha256"]
assert first["migration"]["source_owner_ledger"]==first["initial_ledger"]==src["ledger"]
assert first["migration"]["source_native_identity"]==src["native_identity"]==first["original_identity"]
assert first["model_identity"]!=first["original_identity"]
city=[runs[x] for x in ["S08_valley25380","S08_valley25560","S08_valley26160"]]
for r in city:
    assert r["calendar_legs"]==src["calendar_legs"]==918450
    assert r["calendar_totals"]==src["calendar_totals"]==[120000.0,58801.0,1000.0]
    assert r["unsupported_legs"]==src["unsupported_legs"]==610820
    assert r["manifest_sha256"]==src["manifest_sha256"]
for a,b in zip(city,city[1:]):
    assert a["checkpoint_sha256"]==b["source_checkpoint_sha256"]
    assert a["ledger"]==b["initial_ledger"] and a["time_s"]==b["start_s"]
fixture_old=load(Path("artifacts/v03_pure_rust_core_20261127/c02_120_8.json"))
fixture_new=runs["S08_fixture120"];last=runs["S08_fixture360"]
assert fixture_old["manifest_sha256"]==fixture_new["manifest_sha256"]==sha(B/"fixture.manifest.json")
assert fixture_old["ledger"]["persons"]["completed"]==20
assert math.isclose(last["ledger"]["persons"]["pending"],2.,abs_tol=1e-9)
assert math.isclose(last["ledger"]["cargo_kg"]["completed"],100.,abs_tol=1e-9)
# Independent small-wire service parser, little-endian, exact fixed widths.
def fixture_service(name):
    data=(B/(name+".bin")).read_bytes();assert data[:8]==b"AKMFULL1";off=8
    def read(fmt):
        nonlocal off
        val=struct.unpack_from("<"+fmt,data,off);off+=struct.calcsize("<"+fmt);return val
    def u():return read("Q")[0]
    n=u();off+=n
    t,_,_,_=read("4d")
    for _ in range(u()):read("2d")
    for _ in range(2):
        n=u();off+=72*n
    bus=[read("QQ3d") for _ in range(u())]
    people=[read("5d") for _ in range(u())]
    return {"time_s":t,"bus_runs":bus,"people_rows":people,"run_fields":["stop_index","phase","ready_s","partial_sink","delay_s"],"people_fields":["waiting","onboard","completed","wait_person_s","arrival_person_s"]}
f120=fixture_service("S08_fixture120")
f360=fixture_service("S08_fixture360")
assert f120["people_rows"][0][1]==2. and f120["people_rows"][1][0]==2.
assert f360["bus_runs"][0][2]==230. and f360["bus_runs"][1][2]==260.
assert f360["people_rows"][0][2]==2. and f360["people_rows"][1][0]==2. and f360["people_rows"][1][2]==0.
d=receipt("S04_discriminators")
assert sha(B/"metroflow-akm-discriminators")==d["executable_sha256"]
assert len(d["pulses"])==16 and d["diverge"]["strict_AB_open_branch"]==0 and d["diverge"]["strict_BA_open_branch"]==1 and d["diverge"]["mixed_A_open_branch"]==0
err_m=max(abs(r["mean_s"]-10.) for r in d["pulses"])
err_v=max(abs(r["variance_s2"]-100*(1-r["cfl"])/r["cells"]) for r in d["pulses"])
assert err_m<1e-7 and err_v<1e-5 and d["merge"]["used_m"]==15
resp=load(Path("artifacts/active_kinetic_meso_20261128/R07_response_oracle.json"))
assert max(x["relative_error"] for x in resp["results"])<1e-4
assert receipt("S09_moment_envelope")["status"]=="PASS"
assert receipt("S02_oracle")["status"]=="PASS"
assert "306 passed; 0 failed; 2 ignored" in (A/"S09_native_tests.log").read_text()
assert "16 passed; 0 failed" in (A/"S09_headless_tests.log").read_text()
assert not (B/"S09_wrong_identity.bin").exists() and not (B/"S09_wrong_tail.bin").exists()
out={"status":"VERIFIED_SCOPED","D04":{"mean_error_s":err_m,"variance_error_s2":err_v,"pulse_matrix":16,"response_reference_max_relative_error":max(x["relative_error"] for x in resp["results"]),"scope":"aligned free-flow ballistic limit, spatial/temporal pulse dispersion, dense active pulse, node order counterexample, metre supply and prior frozen local response; no network jam-wave convergence claim"},
     "D06":{"scope":"original input/calendar and existing service/journey owners, positive original city prefix and actual independent recovery; not transport equivalence or all modes implemented",
            "migration_source_rows":first["migration"]["source_rows"],"projected_rows":first["migration"]["projected_rows"],"last_time_s":city[-1]["time_s"],"city_ticks":sum(r["committed_steps"] for r in city),"metrics":metrics,
            "fixture_service_independent_decode":[f120,f360],"fixture_original_120_ledger":fixture_old["ledger"],"fixture_akm_120_ledger":fixture_new["ledger"],"fixture_akm_360_ledger":last["ledger"],
            "calendar_legs":src["calendar_legs"],"calendar_totals":src["calendar_totals"],"unsupported_legs_inherited":src["unsupported_legs"],"model_identity":city[-1]["model_identity"],
            "remaining":"2-person missed return stays waiting; original unsupported mode/path ownership retained; dense egress and receipt history grow; no claim full day or global speedup",
            "last_city_ledger":city[-1]["ledger"],"journey_records_last":city[-1]["journey_records"],"recovery_sha256":city[-1]["checkpoint_sha256"]},
     "scope":"independent arithmetic and bytes of actual receipts and fixture service prefix; native cross-owner invariants checked during each committed tick"}
print(json.dumps(out,indent=2))
