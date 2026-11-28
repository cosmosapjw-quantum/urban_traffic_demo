"""Independent D08 finite ledger, slow causality, actual backend/byte audit."""
from pathlib import Path
import hashlib,json,math,sys
A=Path("artifacts/akm_d08_rust_luti_20261128"); B=Path(sys.argv[1])
def load(p):return json.loads(p.read_bytes())
def get(n):return load(A/(n+".json"))
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def near(x,y,tol=1e-10):return abs(x-y)<=tol*max(1,abs(x),abs(y))
runs={}
metrics=[]
for b in [0,1]:
 for f in [0,1]:
    name=f"S05_b{b}_e{f}";r=get(name);w=load(B/(name+".bin"))
    assert r["status"]=="EXECUTED_FOR_REVIEW" and r["slow_updates"]==2 and r["completed_epochs"]==3 and r["time_s"]==9000
    assert r["config"]=={"bypass":bool(b),"endogenous":bool(f),"seed":7}
    assert w["schema"]=="AKMD08LUTI1" and w["model"]==r["model_identity"] and w["epochs"]==r["epochs"] and w["growth"]==r["growth"]
    assert sha(B/(name+".bin"))==r["checkpoint_sha256"] and sha(B/"metroflow-akm-d08")==r["executable_sha256"]
    assert r["wall_s"]<=600 and r["peak_rss_kib"]*1024<8*1024**3
    placed=150;pending=0;housing=150;constructed=0.;stats=[]
    for n,e in enumerate(r["epochs"]):
        assert e["index"]==n and e["start_s"]==3600*n
        a=e["activity"];tr=e["traffic"];g=e["growth_before"];access=e["access"]
        assert (a["residents_placed"],a["residents_pending"],a["housing"])==(placed,pending,housing)
        assert a["residents_requested"]==placed+pending==150+25*n
        assert g["allocations"]==[placed] and g["pending_increment"]==pending and g["epoch_s"]==n*3600 and g["construction_m"]==constructed
        work=placed if f else 150
        assert a["jobs"]==300 and a["work_trips"]==work and a["inactive_placed"]==placed-work
        assert tr["births"]==a["births"]==[600*i//work for i in range(work)]
        assert tr["completed"]==work and tr["pending"]==tr["road"]==0 and len(tr["done"])==work
        assert all(0<=x<=1800 and x>=birth for birth,x in zip(tr["births"],tr["done"]))
        ages=[x-y for x,y in zip(tr["done"],tr["births"])]
        assert tr["stock_veh_s"]==sum(ages) and near(tr["mean_s"],sum(ages)/work)
        assert tr["peak_storage"]<=1+1e-9 and sum(tr["final_branches"].values())==work
        assert access["stamp_s"]==n*3600+1800 and access["city_identity"]==e["city_identity"]
        assert access["costs"][0][0]=="home" and near(access["costs"][0][1],tr["mean_s"])
        for tick,released,done,active in tr["samples"]:
            assert released==sum(birth<tick for birth in tr["births"])
            assert done==sum(d<=tick for d in tr["done"])
            assert released==done+active
        stats.append({"epoch":n,"placed":placed,"pending":pending,"housing":housing,"scheduled":work,
            "inactive_placed":a["inactive_placed"],"mean_s":tr["mean_s"],"stock_veh_s":tr["stock_veh_s"],
            "peak_storage":tr["peak_storage"],"reroutes":tr["reroutes"],"final_branches":tr["final_branches"],
            "access_stamp_s":access["stamp_s"],"city_identity":e["city_identity"]})
        if n<2:
            pending+=25
            if tr["mean_s"]<=72:
                if housing==150 and pending>0:housing=200;constructed=25.
                x=min(pending,housing-placed);pending-=x;placed+=x
            after=e["growth_after"]
            assert after["allocations"]==[placed] and after["pending_increment"]==pending and after["added"]==[housing-150]
            assert after["epoch_s"]==(n+1)*3600>access["stamp_s"] and after["consumed_access_stamp_s"]==access["stamp_s"]
            assert after["construction_m"]==constructed and placed+pending==150+25*(n+1)
        else:assert e["growth_after"] is None
    assert r["growth"]==r["epochs"][-1]["growth_before"]
    runs[b,f]=r
    metrics.append({"arm":name,"epochs":stats,"wall_s":r["wall_s"],"peak_rss_kib":r["peak_rss_kib"],
                    "total_vehicle_seconds":sum(x["stock_veh_s"] for x in stats),"total_scheduled":sum(x["scheduled"] for x in stats)})
for b in [0,1]:
    assert runs[b,0]["epochs"][0]==runs[b,1]["epochs"][0]
for n in range(3):
    assert runs[0,0]["epochs"][n]==runs[0,1]["epochs"][n]
assert [e["activity"]["residents_placed"] for e in runs[1,1]["epochs"]]==[150,175,200]
assert [e["activity"]["work_trips"] for e in runs[1,0]["epochs"]]==[150,150,150]
assert [e["activity"]["work_trips"] for e in runs[1,1]["epochs"]]==[150,175,200]
# Same transport kernel as D07 with the previous initial 150-car schedule.
for b,n in [(0,"S06_4_baseline"),(1,"S06_4_reroute")]:
    old=load(Path("artifacts/akm_d07_causal_routing_20261128")/(n+".json"))
    tr=runs[b,1]["epochs"][0]["traffic"]
    assert tr["done"]==[o["done"] for o in old["owners"]] and tr["mean_s"]==old["mean_completed_s"]
    assert tr["final_branches"]==old["final_branches"]
    assert tr["stock_veh_s"]==old["physical"]["stock_integral"]
assert get("S07_d07_parity")["checkpoint_sha256"]==load(Path("artifacts/akm_d07_causal_routing_20261128/S06_4_reroute.json"))["checkpoint_sha256"]
assert sha(B/"S07_d07_parity.bin")==get("S07_d07_parity")["checkpoint_sha256"]
# Actual historical native generation and preparation are distinct from D08 lab.
p=get("S06_reuse_parity");hist=load(Path("artifacts/v03_rust_atlas_integration_20261127/C07_next_epoch.json"))
for key,rec,expected in [("generated_valley","S06_generated","before_calendar"),("historical_next_valley","S06_next","next_calendar")]:
    x=p[key];r=get(rec);assert x["city_bytes_identical"] and x["manifest_bytes_identical"] and x["city_semantic_identical"] and x["manifest_semantic_identical"]
    assert sha(B/key/"city.json")==r["city_sha256"] and sha(B/key/"manifest.json")==r["manifest_sha256"]
    assert x["calendar"]==r["calendar"]==hist[expected]
    assert sha(B/"metroflow-native-city")==r["executable_sha256"]
# Final corrected receipt identity and actual frontend city preparation.
for key,rec in [("next_reverified","S07_next_reverified"),("frontend_city","S08_front_city")]:
    r=get(rec);assert r["model_identity"]==r["prepare"]["static_identity"] and isinstance(r["model_identity"],str)
    assert sha(B/key/"manifest.json")==r["manifest_sha256"]==get("S06_next")["manifest_sha256"]
    assert sha(B/key/"city.json")==r["city_sha256"]==get("S06_next")["city_sha256"]
    assert sha(B/"metroflow-native-city-final")==r["executable_sha256"]
assert sha(B/"S07_cut1.bin")==sha(B/"S07_recover1.bin")==get("S07_cut1")["checkpoint_sha256"]
assert sha(B/"S07_resume3.bin")==sha(B/"S05_b1_e1.bin")==sha(B/"S08_front_d08.bin")
assert not any((B/f"S07_invalid_{k}.bin").exists() for k in ["future","stock","birth","model"])
for name,exe in [("S08_front_d08","metroflow-akm-d08"),("S08_front_exact","metroflow-native-run"),("S08_front_interface","metroflow-akm-native")]:
    r=get(name);assert r["status"]=="EXECUTED_FOR_REVIEW"
    assert sha(B/(name+".bin"))==r["checkpoint_sha256"] and sha(B/exe)==r["executable_sha256"]
assert get("S08_front_exact")["ledger"]["persons"]["completed"]==20
assert get("S08_front_interface")["checkpoint_sha256"]==load(Path("artifacts/akm_d05_final_20261128/S04_interface_one.json"))["checkpoint_sha256"]
assert "324 passed; 0 failed; 2 ignored" in (A/"S09_native_tests.log").read_text()
assert "19 passed; 0 failed" in (A/"S09_headless_tests.log").read_text()
assert "13 passed" in (A/"S09_frontend_tests.log").read_text()
assert "1 failed, 12 passed" in (A/"S09_frontend_before_oracle_fix.log").read_text()
assert "Historical Python scientific calculation is an opt-in" in (A/"S09_legacy_no_optin.log").read_text()
before=get("S01_census")["current"];after=get("S09_census")
print(json.dumps({"status":"D08_VERIFIED_SCOPED_LAGGED_LUTI_AND_NATIVE_ENTRY_NOT_RELEASE",
  "matrix":metrics,"native_city_reuse":p,
  "execution":{"native":"Rust scientific calculation: historical atlas, activity/demand/calendar, exact/AKM fixture, D07+D08; old oracle not loaded by native entry",
               "frontend":"Python lazy compatibility facade and subprocess/receipt only; actual -S direct CLI checks",
               "before_lines":before,"after_lines":after,"historical_functional_census":"13/15 prior scoped, not refreshed globally",
               "actual_frontend_native_receipts":["S08_front_city","S08_front_exact","S08_front_interface","S08_front_d08"]},
  "recovery":{"cut":sha(B/"S07_cut1.bin"),"direct":sha(B/"S05_b1_e1.bin"),"legacy_D07_wire_identical":True},
  "limits":["D08 synthetic single origin and one-way work activity, repeated drained windows; no original city growth feedback claim",
            "growth threshold 72s and externally requested increments authored; no estimated demand elasticity or empirical calibration",
            "higher N changes birth timing and routing feedback; nonmonotone mean is observed model-specific, not proof of extra capacity",
            "native city 100k/100010 preparation only; D09 pilot not run",
            "historical Python modules still present and callable in legacy/reference surfaces; not all applications migrated, no broad runtime coverage/LOC target claim",
            "full CI/GUI integration not run; native subagent unavailable"]},indent=2))
