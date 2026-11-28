"""Independent finite D09 audit: actual checkpoint, support bound and owner ledgers."""
from pathlib import Path
import hashlib,json,math,struct,sys
A=Path("artifacts/akm_d09_city_pilot_20261128")
B=Path(sys.argv[1])
def load(p):return json.loads(p.read_bytes())
def get(n):return load(A/(n+".json"))
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def near(x,y,tol=1e-9):return abs(x-y)<=tol*max(1,abs(x),abs(y))
def wire(n):
    # Independently decode the actual fixed-width road prefix. Service and
    # journey payloads are verified by native recovery, not decoded here.
    with (B/(n+".bin")).open("rb") as f:
        assert f.read(8)==b"AKMFULL3"
        def read(fmt):return struct.unpack("<"+fmt,f.read(struct.calcsize("<"+fmt)))
        def u():return read("Q")[0]
        identity=f.read(u()).decode()
        t,initial,offered,outlet=read("4d")
        classes=[read("2d") for _ in range(u())]
        maps=[]
        for name in ["road","pending"]:
            rows=u();tagset=set();masses=[];births=[];thresholds=[1e-15,1e-12,1e-9,1e-6,1e-3]
            counts=[0]*5;ms=[[] for _ in thresholds];bs=[[] for _ in thresholds]
            last=None
            for _ in range(rows):
                tag,pos,m0,m1,j0,j1,z0,z1,b=read("QQ7d")
                assert last is None or (tag,pos)>last;last=(tag,pos)
                tagset.add(tag);m=m0+m1;assert m>0 and math.isfinite(m) and 0<=b<=m*t+1e-8*max(1,m*t)
                assert all(math.isfinite(x) and x>=-1e-12 for x in [m0,m1,j0,j1,z0,z1])
                masses.append(m);births.append(b)
                for i,thr in enumerate(thresholds):
                    if m<=thr:counts[i]+=1;ms[i].append(m);bs[i].append(b)
            maps.append(dict(storage=name,rows=rows,distinct_tags=len(tagset),mass_veh=math.fsum(masses),birth=math.fsum(births),
                bins=[dict(threshold_veh=thr,rows=c,mass_veh=math.fsum(m),birth_veh_s=math.fsum(b)) for thr,c,m,b in zip(thresholds,counts,ms,bs)]))
        bus_class=u();tracks=[read("QQ2d") for _ in range(u())];cross=[read("QQd") for _ in range(u())]
        assert bus_class==2 and all(0<x[2]<1 for x in cross)
        return dict(identity=identity,time_s=t,initial_birth=initial,offered_birth=offered,outlet_birth=outlet,classes=classes,maps=maps,tracks=tracks,cross=cross)
manifest=sha(B/"valley-original.manifest.json")
assert manifest=="2088b2df7a0bb0503adea24bfcdec196758171d5d52f64f42b03269dcb008bd3"
assert sha(B/"valley25320_source.bin")=="e7bbb23f52e271e0d520110cf7fb6c1c4c8c89ba9b01776924d4613d0d745ad0"
s=get("S03_support")
assert s["manifest_sha256"]==manifest and s["executable_sha256"]==sha(B/"metroflow-akm-support")
assert s["calendar_legs"]==918450 and s["unsupported_legs"]==610820 and s["calendar_totals"]==[120000.,58801.,1000.]
assert sum(x["legs"] for x in s["groups"])==918450
assert sum(x["zero_direct_support_legs"] for x in s["groups"])==610820
for k in range(3):
    assert near(math.fsum(x["amounts"][k] for x in s["groups"]),s["calendar_totals"][k])
for w in s["windows"]:
    for r,c,l in zip(w["requested"],w["optimistic_completion_ceiling"],w["uncompleted_lower_bound"]):
        assert 0<=c<=r and near(r,c+l)
day=s["windows"][-1]
direct=[math.fsum(x["direct_uncompleted_lower_bound"][k] for x in s["groups"]) for k in range(3)]
assert all(a<=b+1e-7 for a,b in zip(direct,day["uncompleted_lower_bound"]))
assert near(day["optimistic_completion_ceiling"][0],72115.96491075)
names=["S05_interface360","S05_pilot31","S05_pilot360","S05_recover31","S05_resume360",
       "S06_fresh_day","S07_migrate25380","S07_recover25380","S07_resume_day","S07_recover_fresh","S07_recover_migrated","S08_blocker"]
rs={n:get(n) for n in names}
for n,r in rs.items():
    assert sha(B/(n+".bin"))==r["checkpoint_sha256"]
    assert r["executable_sha256"]==sha(B/("metroflow-akm-native-final" if n=="S08_blocker" else "metroflow-akm-native"))
    assert r["road_rows"]<=r["road_rows_guard"]==1000000 and r["peak_rss_kib"]*1024<=8*1024**3
    assert r["peak_storage_ratio"]<=1+1e-9
    for x in r["ledger"].values():
        assert near(x["requested"],x["released"]+x["pending"])
        assert near(x["released"],x["completed"]+x["active"])
    assert near(math.fsum(x[0]-x[1] for x in r["class_road_ledger"]),r["active_road_mass"])
    assert near(r["initial_road_birth"]+r["new_offered_birth"],r["outlet_birth"]+r["active_road_birth"],1e-8)
    if n.startswith(("S06","S07","S08")):
        assert r["manifest_sha256"]==manifest and r["calendar_legs"]==918450 and r["calendar_totals"]==[120000.,58801.,1000.]
        times=[x["time_s"] for x in r["pilot"]["samples"]]
        assert times[-1]==r["time_s"] and all(a<b for a,b in zip(times,times[1:]))
for a,b in [("S05_pilot31","S05_recover31"),("S05_pilot360","S05_resume360"),("S07_migrate25380","S07_recover25380"),("S06_fresh_day","S07_recover_fresh"),("S07_resume_day","S07_recover_migrated"),("S06_fresh_day","S08_blocker")]:
    assert rs[a]["checkpoint_sha256"]==rs[b]["checkpoint_sha256"]
    assert rs[a]["ledger"]==rs[b]["ledger"]
old=load(Path("artifacts/akm_d05_final_20261128/S04_interface_one.json"))
assert rs["S05_interface360"]["checkpoint_sha256"]==old["checkpoint_sha256"]
assert rs["S05_pilot360"]["journey_records"][3]==15 and rs["S05_interface360"]["journey_records"][3]==1012
for name in ["S05_pilot360","S05_interface360"]:
    for k,x in [("persons",20),("vehicles",13.06),("cargo_kg",100)]:assert near(rs[name]["ledger"][k]["completed"],x)
old=load(Path("artifacts/akm_observables_owners_20261128/S08_valley25380.json"))
p=rs["S07_migrate25380"]
for k in ["manifest_sha256","source_checkpoint_sha256","calendar_legs","calendar_totals","unsupported_legs","ledger","road_rows","active_road_mass","active_road_birth"]:
    assert p[k]==old[k],k
assert all(near(x,y,1e-12) for a,b in zip(p["class_road_ledger"],old["class_road_ledger"]) for x,y in zip(a,b))
class_delta=max(abs(x-y) for a,b in zip(p["class_road_ledger"],old["class_road_ledger"]) for x,y in zip(a,b))
assert p["journey_records"]==[876091,149339,55921,2121] and old["journey_records"]==[1833556,287095,55921,59571]
fresh=rs["S06_fresh_day"];migrated=rs["S07_resume_day"];fail=rs["S08_blocker"]
assert fresh["status"]==migrated["status"]==fail["status"]=="BLOCKED"
assert fresh["time_s"]==25430 and migrated["time_s"]==25470 and fail["time_s"]==25430
assert fresh["requested_end_s"]==migrated["requested_end_s"]==86400
assert fresh["pilot"]["idle_skipped_s"]==21600 and near(fresh["whole_bus"]["exited_veh"],4)
assert fail["failure"]=="AKM total sparse support 1004024 > 1000000" and fail["pilot"]["failure_kind"]=="Resource"
w=wire("S06_fresh_day")
assert w["identity"]==fresh["model_identity"] and w["time_s"]==fresh["time_s"] and w["classes"]==[tuple(x) for x in fresh["class_road_ledger"]]
assert sum(x["rows"] for x in w["maps"])==fresh["road_rows"]
assert near(sum(x["mass_veh"] for x in w["maps"]),fresh["active_road_mass"])
assert near(sum(x["birth"] for x in w["maps"]),fresh["active_road_birth"])
for a,b in zip(w["maps"],fail["support_census"]):
    for k in ["storage","rows","distinct_tags"]:assert a[k]==b[k]
    assert near(a["mass_veh"],b["mass_veh"])
    for x,y in zip(a["bins"],b["bins"]):
        assert x["threshold_veh"]==y["threshold_veh"] and x["rows"]==y["rows"]
        assert near(x["mass_veh"],y["mass_veh"],1e-12) and near(x["birth_veh_s"],y["birth_veh_s"],1e-12)
c=fail["support_census"][0]
out=dict(status="D09_ATTEMPT1_BLOCKED_SCOPED_POSITIVE_RESULTS_NOT_RELEASE",support={"day":day,"direct_uncompleted":direct,"groups":s["groups"],"windows":s["windows"]},
    fixture={"old_history":1012,"pilot_history":15,"recovery":True},
    matched={"time_s":25380,"old_records":old["journey_records"],"pilot_records":p["journey_records"],"ledger_exact":True,"class_ledger_max_abs_delta":class_delta,"road_rows":p["road_rows"],"old_checkpoint_bytes":old["checkpoint_bytes"],"pilot_checkpoint_bytes":p["checkpoint_bytes"]},
    actual_city=[{k:r[k] for k in ["status","failure","time_s","requested_end_s","wall_s","peak_rss_kib","road_rows","journey_records","ledger","whole_bus","checkpoint_sha256"]} for r in [fresh,migrated]],
    rollback={"attempted_rows":1004024,"limit":1000000,"last_rows":fresh["road_rows"],"unchanged_bytes":True,"recovered_both":True},
    tail={"independent_wire":w["maps"],"fraction_rows_le_1e_9":c["bins"][2]["rows"]/c["rows"],"fraction_mass_le_1e_9":c["bins"][2]["mass_veh"]/c["mass_veh"]},
    decision="D09 READY 1/2 consumed; 24h and PM not reached; structural unsupported demand and positive spatial support are independent. Next final attempt must change closure/support, not raise cap. Preserve D05/D07/D08 and original release gate.")
print(json.dumps(out,indent=2))
