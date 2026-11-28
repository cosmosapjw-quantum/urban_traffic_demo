"""Independent audit of finite D05 comparison, actual service and receipt bytes."""
from pathlib import Path
import hashlib,json,math,struct,sys
A=Path("artifacts/akm_d05_final_20261128"); B=Path(sys.argv[1])
def load(p):return json.loads(p.read_text())
def get(n):return load(A/(n+".json"))
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def near(x,y,tol=1e-9):return abs(x-y)<=tol*max(1,abs(x),abs(y))
# Preserve a failed horizon as a negative observation, not a day average.
a=get("S05_A_results")
assert len(a["results"])==24 and a["executable_sha256"]==sha(B/"metroflow-akm-d05-factorial")
rows=a["results"];failed=[];matrix={}
def compare(x,y):
    assert x["time_s"]==y["time_s"] and len(x["curves"])==len(y["curves"])
    assert all(i[0]==j[0] for i,j in zip(x["curves"],y["curves"]))
    den=max(1.,x["released"],y["released"])
    return {"mesh":[[x["scenario"]["cells"],x["scenario"]["dt"]],[y["scenario"]["cells"],y["scenario"]["dt"]]],
        "mean_gap_relative":abs(y["completed_conditional_mean_s"]/x["completed_conditional_mean_s"]-1),
        "completion_curve_gap_fraction":max(abs(i[2]-j[2]) for i,j in zip(x["curves"],y["curves"]))/den,
        "incomplete_curve_gap_fraction":max(abs(i[3]+i[4]-j[3]-j[4]) for i,j in zip(x["curves"],y["curves"]))/den,
        "stock_integral_gap_relative":abs(y["metrics"]["stock_veh_s"]/x["metrics"]["stock_veh_s"]-1)}
for idx,r in enumerate(rows):
    q=r["scenario"];assert r["slots"]==12*q["cells"]
    assert near(r["released"],r["completed"]+r["pending"]+r["active"])
    assert r["metrics"]["max_storage"]<=1+1e-9
    for t,rel,comp,pend,active,age in r["curves"]:assert near(rel,comp+pend+active)
    if r["status"]!="HORIZON_REACHED":
        assert r["status"]=="BLOCKED_NUMERICAL:road moment cone" and q["day_profile"] and q["cells"]==4
        failed.append({"policy":q["policy"],"time_s":r["time_s"],"reason":r["status"],"last_state_digest":r["checkpoint_sha256"],"full_checkpoint_retained":False})
        continue
    assert r["time_s"]==q["horizon"] and r["allocation_calls"]==r["reallocation_calls"]==0
    if q["day_profile"] and q["cells"]==4:
        assert sha(B/"A_lab"/f"lab-{idx}-final.bin")==r["checkpoint_sha256"]
assert sorted(x["policy"] for x in failed)==[0,2]
for k in range(4):
    day=[x for x in rows if x["scenario"]["policy"]==k and x["scenario"]["day_profile"]]
    control=[x for x in rows if x["scenario"]["policy"]==k and not x["scenario"]["day_profile"]]
    dy=[compare(x,y) for x,y in zip(day,day[1:]) if y["status"]=="HORIZON_REACHED"]
    matrix[str(k)]={"day_means_s":[r["completed_conditional_mean_s"] if r["status"]=="HORIZON_REACHED" else None for r in day],
        "day_comparisons":dy,"overload_comparisons":[compare(x,y) for x,y in zip(control,control[1:])],
        "finest_day_gate":len(dy)==2 and dy[-1]["mean_gap_relative"]<=.02 and dy[-1]["completion_curve_gap_fraction"]<=.02 and dy[-1]["incomplete_curve_gap_fraction"]<=.02}
assert not any(x["finest_day_gate"] for x in matrix.values())
for base,residual in [(0,2),(1,3)]:
    for x,y in zip([r for r in rows if r["scenario"]["policy"]==base],[r for r in rows if r["scenario"]["policy"]==residual]):
        if x["status"]==y["status"]=="HORIZON_REACHED":assert near(x["completed_conditional_mean_s"],y["completed_conditional_mean_s"],1e-10)
# B: verify observational read-only invariance at old common stamps.
br=[get(f"S06_B_mesh{k}") for k in [300,150]]
times=[25200,25720,26400,27000,27600,28200,28800]
for k,r in zip([300,150],br):
    assert r["config"]["mesh_s"]==k and r["observation_times_s"]==times
    assert [s["time_s"] for s in r["result"]["snapshots"]]==times
    assert r["network_sha256"]=="af8a0c16e2bd31d4a42282e83d076ea10075e6cbe0bb3982dfb5978cfa9f72a5"
    assert r["passages_sha256"]=="a310ee706ae3eb64ba35eef2c9275da38141dbd32eb89f86bcb6a90c89bd73c1"
    assert r["executable_sha256"]==sha(B/"metroflow-active-city-observed")
    for s in r["result"]["snapshots"]:
        assert s["max_storage_ratio"]<=1+1e-9 and s["max_receiving_ratio"]<=1+1e-9
        for c in s["classes"]:assert near(c["released"],c["completed"]+c["active"])
old=load(Path("artifacts/akm_d05_transport_20261128/S05_B_mesh300.json"))["result"]
current=br[0]["result"]
assert [s for s in current["snapshots"] if s["time_s"] in [25720,28800]]==old["snapshots"]
assert {k:v for k,v in current.items() if k!="snapshots"}=={k:v for k,v in old.items() if k!="snapshots"}
s0,s1=[r["result"]["snapshots"] for r in br]
bc={k:max(abs(i["classes"][0][k]-j["classes"][0][k])/max(1,i["classes"][0]["released"],j["classes"][0]["released"]) for i,j in zip(s0,s1)) for k in ["released","completed","active","road"]}
bc.update({k:max(abs(i[k]-j[k]) for i,j in zip(s0,s1)) for k in ["max_storage_ratio","max_receiving_ratio"]})
cs=[s[-1]["classes"][0] for s in [s0,s1]]
means=[x["trip_seconds"]/x["completed"] for x in cs]
bc["mean_gap_relative"]=abs(means[1]/means[0]-1)
assert bc["completed"]<.02 and bc["released"]<.02 and bc["max_storage_ratio"]<.02 and bc["max_receiving_ratio"]>.02
# D: decode logical and physical interface from actual little-endian wire.
def wire(n):
    data=(B/(n+".bin")).read_bytes();assert data[:8]==b"AKMFULL3";off=8
    def read(fmt):
        nonlocal off
        v=struct.unpack_from("<"+fmt,data,off);off+=struct.calcsize("<"+fmt);return v
    def u():return read("Q")[0]
    n=u();identity=data[off:off+n].decode();off+=n
    t,ib,ob,ex=read("4d");classes=[read("2d") for _ in range(u())];maps=[]
    for _ in range(2):
        maps.append([read("QQ7d") for _ in range(u())])
    bus=u();tracks=[read("QQ2d") for _ in range(u())];cross=[read("QQd") for _ in range(u())]
    assert bus==2 and all(0<x[2]<1 for x in cross)
    runs=[read("QQ3d") for _ in range(u())];people=[read("5d") for _ in range(u())]
    return dict(time=t,identity=identity,tracks=tracks,cross=cross,runs=runs,people=people,road=maps[0],pending=maps[1],class_road_ledger=classes)
d={}
for name in ["S04_interface_half","S04_interface_one","S04_interface_two","S07_entry31","S07_entry31_recover","S07_entry_resume360","S07_exit_full360","S07_exit_partial","S07_exit_partial_recover","S07_exit_resume360","S09_final_fixture"]:
    r=get(name);assert r["status"]=="EXECUTED_FOR_REVIEW" and r["failure"] is None
    assert sha(B/(name+".bin"))==r["checkpoint_sha256"]
    exe="metroflow-akm-native-final" if name=="S09_final_fixture" else "metroflow-akm-native"
    assert r["executable_sha256"]==sha(B/exe)
    assert r["peak_storage_ratio"]<=1+1e-9 and r["peak_rss_kib"]*1024<8*1024**3
    for v in r["ledger"].values():assert near(v["requested"],v["released"]+v["pending"]) and near(v["released"],v["completed"]+v["active"])
    assert near(math.fsum(c[0]-c[1] for c in r["class_road_ledger"]),r["active_road_mass"])
    assert near(r["initial_road_birth"]+r["new_offered_birth"],r["outlet_birth"]+r["active_road_birth"],1e-8)
    w=wire(name);assert w["identity"]==r["model_identity"] and w["time"]==r["time_s"]
    if r["time_s"]==360:
        assert all(near(r["ledger"][k]["completed"],m) for k,m in [("persons",20.),("vehicles",13.06),("cargo_kg",100.)])
        assert len(w["cross"])==0 and all(x[1]==2 for x in w["runs"])
    d[name]={"receipt_sha256":sha(A/(name+".json")),"checkpoint_sha256":r["checkpoint_sha256"],"wire":w,"interface":r["interface"]}
for pair in [("S07_entry31","S07_entry31_recover"),("S04_interface_one","S07_entry_resume360","S09_final_fixture"),("S07_exit_partial","S07_exit_partial_recover"),("S07_exit_full360","S07_exit_resume360")]:
    assert len({d[n]["checkpoint_sha256"] for n in pair})==1
arr=[[x[2] for x in d[n]["wire"]["runs"]] for n in ["S04_interface_half","S04_interface_one","S04_interface_two"]]
assert arr==[[44.,74.5],[45.,75.],[46.,76.]]
assert all(max(abs(i-j) for i,j in zip(x,y))<=2 for x,y in zip(arr,arr[1:]))
assert all(x[0]<60 for x in arr)
e=d["S07_entry31"]["wire"];x=d["S07_exit_partial"]["wire"]
assert e["cross"][0][:2] in [r[:2] for r in e["pending"]]
assert x["cross"][0][:2] in [r[:2] for r in x["road"]] and x["people"][0][1]==2 and x["people"][0][2]==0
assert not (B/"S07_invalid_output.bin").exists()
old=load(Path("artifacts/akm_d05_transport_20261128/S07_mixed360.json"))
assert get("S07_old_mixed360")["checkpoint_sha256"]==old["checkpoint_sha256"]
old=load(Path("artifacts/akm_d05_transport_20261128/S08_hybrid_two.json"))
assert get("S07_old_hybrid_two")["checkpoint_sha256"]==old["checkpoint_sha256"]
assert "314 passed; 0 failed; 2 ignored" in (A/"S09_native_tests.log").read_text()
assert "19 passed; 0 failed" in (A/"S09_headless_tests.log").read_text()
assert "3 passed" in (A/"S09_frontend_tests.log").read_text()
assert "competing_merge_reservation_consumes_current_receiver_supply ... ok" in (A/"S07_transport_controls.log").read_text()
assert "exact_slack_remains_partial_without_fictitious_completion ... ok" in (A/"S07_transport_controls.log").read_text()
print(json.dumps({"status":"D05_FINAL_SELECTION_VERIFIED_SCOPED_NOT_RELEASE","A":{"cases":24,"reached":22,"failed":failed,"factorial":matrix,"decision":"reject all tested A policies as validated day-resolution solution; local kernels retained; do not infer numerical root cause"},
 "B":{"mesh_s":[300,150],"means_s":means,"comparison":bc,"old_mesh300_observation_invariance":True,"decision":"projected comparator only; receiving peak diagnostic fails"},
 "D":{"arrivals_s":arr,"wire_checks":d,"decision":"select reserved-interface service subclosure for next research; scoped same fixture and controls only; no full-city validated transport"},
 "architecture":{"backend":"Rust native and headless, no Python dependency in native research build","frontend":"Python read-only typed receipt adapter, 3 tests"},
 "remaining":"A mixed fluid cone/time refinement; B current full-calendar bridge and receiving peak; D exact-slack liveness, bus priority/fairness, whole-city positive service and mixed fluid coupling, journey history. D05 no further attempts; D07 research only."},indent=2))
